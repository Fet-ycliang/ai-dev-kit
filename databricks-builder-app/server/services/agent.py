"""管理 agent session 的 Claude Code Agent 服務。

使用 claude-agent-sdk 建立並管理 Claude Code agent session，
同時搭配目錄範圍的檔案權限與 Databricks 工具。

Databricks 工具會透過 SDK 工具包裝器，
由 databricks-mcp-server 以 in-process 方式載入。
認證使用 contextvars 處理，以支援多使用者情境。

MLflow Tracing：
  此模組整合 MLflow 以追蹤 Claude Code 對話。
  使用 query() 搭配自訂 Stop hook，正確處理串流與 tracing。
  參考：https://mlflow.org/docs/latest/genai/tracing/integrations/listing/claude_code/

注意：此處套用 fresh event loop 的權宜處理方式，
用來修正 claude-agent-sdk issue #462 在 FastAPI/uvicorn 情境中
發生子程序 transport 失敗的問題。
參考：https://github.com/anthropics/claude-agent-sdk-python/issues/462
"""

import asyncio
import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
from contextvars import copy_context
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, query, HookMatcher
from claude_agent_sdk.types import (
  AssistantMessage,
  PermissionResultAllow,
  PermissionResultDeny,
  ResultMessage,
  StreamEvent,
  SystemMessage,
  TextBlock,
  ThinkingBlock,
  ToolPermissionContext,
  ToolResultBlock,
  ToolUseBlock,
  UserMessage,
)
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

from .backup_manager import ensure_project_directory as _ensure_project_directory
from .databricks_tools import load_databricks_tools, create_filtered_databricks_server
from .system_prompt import get_system_prompt

logger = logging.getLogger(__name__)

# 內建 Claude Code 工具
BUILTIN_TOOLS = [
  'Read',
  'Write',
  'Edit',
#  'Bash',
  'Glob',
  'Grep',
]

# 快取的 Databricks 工具（只載入一次）
_databricks_server = None
_databricks_tool_names = None

# 快取的 Claude 設定（只載入一次）
_claude_settings = None


def _load_claude_settings() -> dict:
  """初始化 Claude 設定字典。

  過去會從 .claude/settings.json 載入，但現在所有認證設定
  都會根據使用者的 Databricks 憑證與 app.yaml 中設定的
  環境變數動態注入。

  Returns:
      傳給 Claude 子程序的環境變數字典
  """
  global _claude_settings

  if _claude_settings is not None:
    return _claude_settings

  # 先以空字典開始 - 認證設定會依每次請求動態加入
  _claude_settings = {}
  return _claude_settings


def get_databricks_tools(force_reload: bool = False):
  """取得 Databricks 工具，必要時可強制重新載入。

  Args:
      force_reload: 若為 True，會重建 MCP server 以清除任何損壞狀態

  Returns:
      (server, tool_names) 的 tuple
  """
  global _databricks_server, _databricks_tool_names
  if _databricks_server is None or force_reload:
    if force_reload:
      logger.info('Force reloading Databricks MCP server')
    _databricks_server, _databricks_tool_names = load_databricks_tools()
  return _databricks_server, _databricks_tool_names


def get_project_directory(project_id: str) -> Path:
  """取得專案的目錄路徑。

  若目錄不存在，會嘗試從備份還原。
  若沒有備份，則建立空目錄。

  Args:
      project_id: 專案 UUID

  Returns:
      專案目錄的 Path
  """
  return _ensure_project_directory(project_id)


def _get_mlflow_stop_hook(experiment_name: str | None = None):
  """取得用於追蹤 Claude Code 對話的 MLflow Stop hook。

  此 hook 會在對話結束後處理 transcript，
  並建立 MLflow trace。和只支援 ClaudeSDKClient 的 autolog 不同，
  此方法可搭配 query() 使用。

  Args:
      experiment_name: MLflow experiment 名稱（可選）

  Returns:
      非同步 hook 函式；若 MLflow 無法使用則回傳 None
  """
  try:
    import mlflow
    from mlflow.claude_code.tracing import process_transcript, setup_mlflow

    # 設定 MLflow tracking
    mlflow.set_tracking_uri('databricks')
    if experiment_name:
      try:
        # 同時支援 experiment ID（數字）與 experiment 名稱（路徑）
        if experiment_name.isdigit():
          mlflow.set_experiment(experiment_id=experiment_name)
          logger.info(f'MLflow experiment set by ID: {experiment_name}')
        else:
          mlflow.set_experiment(experiment_name)
          logger.info(f'MLflow experiment set to: {experiment_name}')
      except Exception as e:
        logger.warning(f'Could not set MLflow experiment: {e}')

    async def mlflow_stop_hook(input_data: dict, tool_use_id: str | None, context) -> dict:
      """在對話結束時處理 transcript 並建立 MLflow trace。"""
      try:
        session_id = input_data.get('session_id')
        transcript_path = input_data.get('transcript_path')

        logger.info(f'MLflow Stop hook triggered: session={session_id}')

        # 確保 MLflow 已完成設定（tracking URI 與 experiment）
        setup_mlflow()

        # 處理 transcript 並建立 trace
        trace = process_transcript(transcript_path, session_id)

        if trace:
          logger.info(f'MLflow trace created: {trace.info.trace_id}')

          # 將請求的模型名稱加入 trace tags
          # trace 會記錄回應模型（例如 claude-opus-4-5-20251101）
          # 但我們也希望記錄實際請求的 Databricks endpoint 名稱
          try:
            client = mlflow.MlflowClient()
            trace_id = trace.info.trace_id
            requested_model = os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-opus-4-5')
            requested_model_mini = os.environ.get('ANTHROPIC_MODEL_MINI', 'databricks-claude-sonnet-4-5')
            base_url = os.environ.get('ANTHROPIC_BASE_URL', '')

            # 設定 tags 以明確標示使用的 Databricks 模型 endpoint
            client.set_trace_tag(trace_id, 'databricks.requested_model', requested_model)
            client.set_trace_tag(trace_id, 'databricks.requested_model_mini', requested_model_mini)
            if base_url:
              client.set_trace_tag(trace_id, 'databricks.model_serving_endpoint', base_url)
            client.set_trace_tag(trace_id, 'llm.provider', 'databricks-fmapi')

            logger.info(f'Added Databricks model tags to trace {trace_id}: {requested_model}')
          except Exception as tag_err:
            logger.warning(f'Could not add model tags to trace: {tag_err}')
        else:
          logger.debug('MLflow trace creation returned None (possibly empty transcript)')

        return {'continue': True}
      except Exception as e:
        logger.error(f'Error in MLflow Stop hook: {e}', exc_info=True)
        # 回傳 continue=True，避免中斷對話
        return {'continue': True}

    logger.info(f'MLflow tracing hook configured: {mlflow.get_tracking_uri()}')
    return mlflow_stop_hook

  except ImportError as e:
    logger.debug(f'MLflow not available: {e}')
    return None
  except Exception as e:
    logger.warning(f'Failed to create MLflow stop hook: {e}')
    return None


def _run_agent_in_fresh_loop(message, options, result_queue, context, is_cancelled_fn, mlflow_experiment=None):
  """在 fresh event loop 中執行 agent（issue #462 的權宜處理方式）。

  此函式會在獨立執行緒中建立新的 event loop，
  以避免 FastAPI/uvicorn 情境中的子程序 transport 問題。

  使用 query() 正確處理串流，並搭配自訂 MLflow Stop hook 進行 tracing。
  Stop hook 會在對話結束後處理 transcript。

  Args:
      message: 要傳送給 agent 的使用者訊息
      options: agent 使用的 ClaudeAgentOptions
      result_queue: 回傳結果給主執行緒的佇列
      context: contextvars 的複本（供 Databricks 認證等使用）
      is_cancelled_fn: 若請求已取消則回傳 True 的可呼叫物件
      mlflow_experiment: 用於 tracing 的 MLflow experiment 名稱（可選）

  參考：https://github.com/anthropics/claude-agent-sdk-python/issues/462
  """
  # 在複製的 context 中執行，以保留 contextvars（例如 Databricks 認證）
  def run_with_context():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 若已設定 experiment，則加入 MLflow Stop hook 進行 tracing
    exp_name = mlflow_experiment or os.environ.get('MLFLOW_EXPERIMENT_NAME')
    if exp_name:
      mlflow_hook = _get_mlflow_stop_hook(exp_name)
      if mlflow_hook:
        # 將 hook 加入 options
        if options.hooks is None:
          options.hooks = {}
        if 'Stop' not in options.hooks:
          options.hooks['Stop'] = []
        options.hooks['Stop'].append(HookMatcher(hooks=[mlflow_hook]))
        logger.info('MLflow Stop hook added to agent options')

    async def run_query():
      """使用 query() 執行 agent，以正確處理串流。"""
      # 在 fresh event loop 的 context 中建立 prompt generator
      async def prompt_generator():
        yield {'type': 'user', 'message': {'role': 'user', 'content': message}}

      try:
        msg_count = 0
        async for msg in query(prompt=prompt_generator(), options=options):
          msg_count += 1
          msg_type = type(msg).__name__
          logger.info(f"[AGENT DEBUG] Received message #{msg_count}: {msg_type}")

          # 為特定訊息型別記錄更多細節
          if hasattr(msg, 'content'):
            content = msg.content
            if isinstance(content, list):
              block_types = [type(b).__name__ for b in content]
              logger.info(f"[AGENT DEBUG]   Content blocks: {block_types}")
          if hasattr(msg, 'is_error') and msg.is_error:
            logger.error(f"[AGENT DEBUG]   is_error=True")
          if hasattr(msg, 'session_id'):
            logger.info(f"[AGENT DEBUG]   session_id={msg.session_id}")

          # 在處理每則訊息前檢查是否已取消
          if is_cancelled_fn():
            logger.info("Agent cancelled by user request")
            result_queue.put(('cancelled', None))
            return
          result_queue.put(('message', msg))
        logger.info(f"[AGENT DEBUG] query() loop completed normally after {msg_count} messages")
      except asyncio.CancelledError:
        logger.warning("Agent query was cancelled (asyncio.CancelledError)")
        result_queue.put(('error', Exception("Agent query cancelled - likely due to stream timeout or connection issue")))
      except ConnectionError as e:
        logger.error(f"Connection error in agent query: {e}")
        result_queue.put(('error', Exception(f"Connection error: {e}. This may occur when tools take longer than the stream timeout (50s).")))
      except BrokenPipeError as e:
        logger.error(f"Broken pipe in agent query: {e}")
        result_queue.put(('error', Exception(f"Broken pipe: {e}. The agent subprocess communication was interrupted.")))
      except Exception as e:
        logger.exception(f"Unexpected error in agent query: {type(e).__name__}: {e}")
        result_queue.put(('error', e))
      finally:
        result_queue.put(('done', None))

    try:
      loop.run_until_complete(run_query())
    finally:
      loop.close()

  # 在複製的 context 中執行
  context.run(run_with_context)


def _process_tool_result(block: ToolResultBlock, ask_user_tool_ids: set[str]) -> dict:
  """擷取並正規化 ToolResultBlock 的內容，以供串流使用。"""
  content = block.content
  if isinstance(content, list):
    texts = []
    for item in content:
      if isinstance(item, dict) and 'text' in item:
        texts.append(item['text'])
      elif isinstance(item, str):
        texts.append(item)
      else:
        texts.append(str(item))
    content = '\n'.join(texts) if texts else str(block.content)
  elif not isinstance(content, str):
    content = str(content)

  # 改寫 AskUserQuestion 結果 — can_use_tool callback 會提供
  # 合成答案，但 CLI 結果文字容易誤導（例如 "User has
  # answered your questions: ..."）。改成更清楚的訊息。
  if block.tool_use_id in ask_user_tool_ids:
    content = 'Asking user questions directly in conversation'
  elif block.is_error and 'Stream closed' in content:
    content = f'Tool execution interrupted: {content}. This may occur when operations exceed timeout limits or when the connection is interrupted. Check backend logs for more details.'
    logger.warning(f'Tool result error (improved): {content}')

  return {
    'type': 'tool_result',
    'tool_use_id': block.tool_use_id,
    'content': content,
    'is_error': block.is_error,
  }


async def stream_agent_response(
  project_id: str,
  message: str,
  session_id: str | None = None,
  cluster_id: str | None = None,
  default_catalog: str | None = None,
  default_schema: str | None = None,
  warehouse_id: str | None = None,
  workspace_folder: str | None = None,
  fmapi_host: str | None = None,
  fmapi_token: str | None = None,
  databricks_host: str | None = None,
  databricks_token: str | None = None,
  is_cross_workspace: bool = False,
  is_cancelled_fn: callable = None,
  enabled_skills: list[str] | None = None,
  mlflow_experiment_name: str | None = None,
) -> AsyncIterator[dict]:
  """以所有事件型別串流 Claude agent 回應。

  使用 query() 搭配自訂 MLflow Stop hook 進行 tracing。
  產生已正規化的事件字典供前端使用。

  Args:
      project_id: 專案 UUID
      message: 要傳送的使用者訊息
      session_id: 用於恢復對話的 session ID（可選）
      cluster_id: 用於程式碼執行的 Databricks cluster ID（可選）
      default_catalog: 預設 Unity Catalog 名稱（可選）
      default_schema: 預設 schema 名稱（可選）
      warehouse_id: 用於查詢的 Databricks SQL warehouse ID（可選）
      workspace_folder: 用於上傳檔案的 workspace 資料夾（可選）
      fmapi_host: Builder App 的 workspace URL，供 Claude API（FMAPI）使用
      fmapi_token: Builder App 的 token，供 Claude API 驗證使用
      databricks_host: Databricks 工具操作的目標 workspace URL
      databricks_token: Databricks 工具驗證使用的目標 workspace token
      is_cross_workspace: 若為 True，表示工具操作的目標 workspace
          不同於 Builder App，並會在認證 context 中啟用 force_token
      is_cancelled_fn: 若請求已取消則回傳 True 的可呼叫物件（可選）
      enabled_skills: 已啟用 skill 名稱清單（可選）；None 代表全部 skills

  Yields:
      含有 `type` 欄位、供前端使用的事件字典
  """
  project_dir = get_project_directory(project_id)

  if session_id:
    logger.info(f'Resuming session {session_id} in {project_dir}: {message[:100]}...')
  else:
    logger.info(f'Starting new session in {project_dir}: {message[:100]}...')

  # 記錄工作目錄，協助除錯路徑問題
  logger.info(f'Agent working directory (cwd): {project_dir}')
  logger.info(f'Workspace folder (remote): {workspace_folder}')

  # 為工具操作設定認證 context（目標為指定的 workspace）
  # 跨 workspace 時，force_token 可確保即使環境中存在 OAuth M2M 憑證，
  # 仍會使用目標 workspace 的憑證
  set_databricks_auth(databricks_host, databricks_token, force_token=is_cross_workspace)

  try:
    # 建立允許工具清單
    allowed_tools = BUILTIN_TOOLS.copy()

    # 執行 agent 前先同步專案的 skills 目錄
    from .skills_manager import sync_project_skills, get_available_skills, get_allowed_mcp_tools
    sync_project_skills(project_dir, enabled_skills=enabled_skills)

    # 取得 Databricks 工具並依已啟用的 skills 過濾
    # 必須建立過濾後的 MCP server（不能只過濾 allowed_tools）
    # 因為 bypassPermissions 模式會暴露已註冊 MCP server 中的所有工具
    databricks_server, databricks_tool_names = get_databricks_tools()
    filtered_tool_names = get_allowed_mcp_tools(databricks_tool_names, enabled_skills=enabled_skills)

    if len(filtered_tool_names) < len(databricks_tool_names):
      # 有些工具被封鎖 — 建立只包含允許工具的過濾版 MCP server
      databricks_server, filtered_tool_names = create_filtered_databricks_server(filtered_tool_names)
      blocked_count = len(databricks_tool_names) - len(filtered_tool_names)
      logger.info(f'Databricks MCP server: {len(filtered_tool_names)} tools allowed, {blocked_count} blocked by disabled skills')
    else:
      logger.info(f'Databricks MCP server configured with {len(filtered_tool_names)} tools')

    allowed_tools.extend(filtered_tool_names)

    # 僅在 agent 有可用的已啟用 skills 時才加入 Skill 工具
    available = get_available_skills(enabled_skills=enabled_skills)
    if available:
      allowed_tools.append('Skill')

    # 依可用 skills、cluster、warehouse 與 catalog/schema 上下文產生 system prompt
    system_prompt = get_system_prompt(
      cluster_id=cluster_id,
      default_catalog=default_catalog,
      default_schema=default_schema,
      warehouse_id=warehouse_id,
      workspace_folder=workspace_folder,
      workspace_url=databricks_host,
      enabled_skills=enabled_skills,
    )

    # 載入 Databricks 模型服務驗證所需的 Claude 設定
    claude_env = _load_claude_settings()

    # 記錄認證狀態以利除錯
    logger.info(
      f'Auth state: fmapi_host={fmapi_host}, databricks_host={databricks_host}, '
      f'is_cross_workspace={is_cross_workspace}'
    )

    # 設定 Claude 子程序使用 Builder App workspace 上的 Databricks FMAPI。
    # 即使工具操作目標是其他 workspace（跨 workspace 模式），
    # FMAPI 認證仍一律指向 Builder App。
    # 若呼叫端未拆分 FMAPI 憑證，則回退使用 databricks_host/token。
    effective_fmapi_host = fmapi_host or databricks_host
    effective_fmapi_token = fmapi_token or databricks_token
    if effective_fmapi_host and effective_fmapi_token:
      host = effective_fmapi_host.replace('https://', '').replace('http://', '').rstrip('/')
      anthropic_base_url = f'https://{host}/serving-endpoints/anthropic'

      claude_env['ANTHROPIC_BASE_URL'] = anthropic_base_url
      claude_env['ANTHROPIC_API_KEY'] = effective_fmapi_token
      claude_env['ANTHROPIC_AUTH_TOKEN'] = effective_fmapi_token

      # 設定要使用的模型（Databricks FMAPI 必填）
      anthropic_model = os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-opus-4-6')
      claude_env['ANTHROPIC_MODEL'] = anthropic_model

      # 關閉 beta headers 與 experimental betas，以相容 Databricks FMAPI
      # ANTHROPIC_CUSTOM_HEADERS 用於啟用 FMAPI 的 coding agent mode
      # CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS 可避免傳送 FMAPI 不支援的
      # context_management 等實驗性 body 參數（400: Extra inputs not permitted）
      claude_env['ANTHROPIC_CUSTOM_HEADERS'] = 'x-databricks-use-coding-agent-mode: true'
      claude_env['CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS'] = '1'

      logger.info(f'Configured Databricks model serving: {anthropic_base_url} with model {anthropic_model}')
      logger.info(f'Claude env vars: BASE_URL={claude_env.get("ANTHROPIC_BASE_URL")}, MODEL={claude_env.get("ANTHROPIC_MODEL")}')

    # Databricks SDK upstream 追蹤，用於子程序 user-agent 歸因
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION
    claude_env['DATABRICKS_SDK_UPSTREAM'] = PRODUCT_NAME
    claude_env['DATABRICKS_SDK_UPSTREAM_VERSION'] = PRODUCT_VERSION

    # 確保已設定串流逾時（1 小時，用於處理較長的工具執行序列）
    stream_timeout = os.environ.get('CLAUDE_CODE_STREAM_CLOSE_TIMEOUT', '3600000')
    claude_env['CLAUDE_CODE_STREAM_CLOSE_TIMEOUT'] = stream_timeout

    # Stderr callback，用於擷取 Claude 子程序輸出以供除錯
    def stderr_callback(line: str):
      logger.debug(f'[Claude stderr] {line.strip()}')
      # 也印到 stderr，方便開發時立即看到
      print(f'[Claude stderr] {line.strip()}', file=sys.stderr, flush=True)

    # 平順處理 AskUserQuestion 工具呼叫。
    # 在 bypassPermissions 且沒有 callback 的情況下，AskUserQuestion 會觸發 SDK
    # 錯誤（"canUseTool callback is not provided"），進而產生 is_error=True 的
    # tool result，並在 Lemma 等下游 UI 顯示為「Failed」。
    # 此 callback 會為 AskUserQuestion 提供合成答案，
    # 讓 Claude 直接以一般文字提出問題，完全避開錯誤路徑。
    async def can_use_tool(
      tool_name: str, input_data: dict, _context: ToolPermissionContext,
    ) -> PermissionResultAllow | PermissionResultDeny:
      if tool_name == "AskUserQuestion":
        questions = input_data.get("questions", [])
        answers = {
          q.get("question", ""): "Please ask this question directly in your text response."
          for q in questions
        }
        return PermissionResultAllow(
          updated_input={"questions": questions, "answers": answers},
        )
      return PermissionResultAllow(updated_input=input_data)

    # Python 版本的 can_use_tool 需要 PreToolUse hook，
    # 才能保持串流開啟並觸發 permission callback。
    async def _keepalive_hook(_input_data, _tool_use_id, _context):
      return {"continue_": True}

    options = ClaudeAgentOptions(
      cwd=str(project_dir),
      allowed_tools=allowed_tools,
      permission_mode='bypassPermissions',  # 自動接受所有工具，包含 MCP
      can_use_tool=can_use_tool,  # 平順處理 AskUserQuestion
      hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_keepalive_hook])]},
      resume=session_id,  # 若有提供則接續先前 session
      mcp_servers={'databricks': databricks_server},  # In-process SDK 工具
      system_prompt=system_prompt,  # 聚焦 Databricks 的 system prompt
      setting_sources=["user", "project"],  # 從檔案系統載入 Skills
      env=claude_env,  # 傳入 Databricks 認證設定（ANTHROPIC_AUTH_TOKEN 等）
      include_partial_messages=True,  # 啟用逐 token 串流
      stderr=stderr_callback,  # 擷取 stderr 以供除錯
    )

    # 在 fresh event loop 中執行 agent，以避免子程序 transport 問題（#462）
    # 複製 context 以在新執行緒中保留 contextvars（Databricks 認證）
    ctx = copy_context()
    result_queue = queue.Queue()
    # 若未提供取消函式，預設為永遠回傳 False
    cancel_check = is_cancelled_fn if is_cancelled_fn else lambda: False

    # 從 request 參數取得 MLflow experiment 名稱，若無則回退到環境變數
    mlflow_experiment = mlflow_experiment_name or os.environ.get('MLFLOW_EXPERIMENT_NAME')

    agent_thread = threading.Thread(
      target=_run_agent_in_fresh_loop,
      args=(message, options, result_queue, ctx, cancel_check, mlflow_experiment),
      daemon=True
    )
    agent_thread.start()

    # 處理佇列中的訊息，並在長時間操作期間送出 keepalive
    KEEPALIVE_INTERVAL = 15  # 秒 - 若無活動則送出 keepalive
    last_activity = time.time()
    # 追蹤 AskUserQuestion 的工具 ID，以便改寫其串流結果
    ask_user_tool_ids: set[str] = set()

    while True:
      # 在 queue.get 上使用逾時，才能送出 keepalive
      def get_with_timeout():
        try:
          return result_queue.get(timeout=KEEPALIVE_INTERVAL)
        except queue.Empty:
          return ('keepalive', None)

      msg_type, msg = await asyncio.get_event_loop().run_in_executor(
        None, get_with_timeout
      )

      if msg_type == 'keepalive':
        # 送出 keepalive 事件，在長時間工具執行期間維持串流活性
        elapsed = time.time() - last_activity
        logger.debug(f'Emitting keepalive after {elapsed:.0f}s of inactivity')
        yield {
          'type': 'keepalive',
          'elapsed_since_last_event': elapsed,
        }
        continue

      # 對非 keepalive 訊息更新最後活動時間
      last_activity = time.time()

      if msg_type == 'done':
        break
      elif msg_type == 'cancelled':
        logger.info("Agent execution cancelled")
        yield {'type': 'cancelled'}
        break
      elif msg_type == 'error':
        raise msg
      elif msg_type == 'message':
        # 處理不同的訊息型別
        if isinstance(msg, AssistantMessage):
          # 處理內容區塊
          for block in msg.content:
            if isinstance(block, TextBlock):
              yield {
                'type': 'text',
                'text': block.text,
              }
            elif isinstance(block, ThinkingBlock):
              yield {
                'type': 'thinking',
                'thinking': block.thinking,
              }
            elif isinstance(block, ToolUseBlock):
              # 追蹤 AskUserQuestion 呼叫，以便改寫其結果
              if block.name == 'AskUserQuestion':
                ask_user_tool_ids.add(block.id)
              yield {
                'type': 'tool_use',
                'tool_id': block.id,
                'tool_name': block.name,
                'tool_input': block.input,
              }
            elif isinstance(block, ToolResultBlock):
              yield _process_tool_result(block, ask_user_tool_ids)

        elif isinstance(msg, ResultMessage):
          yield {
            'type': 'result',
            'session_id': msg.session_id,
            'duration_ms': msg.duration_ms,
            'total_cost_usd': msg.total_cost_usd,
            'is_error': msg.is_error,
            'num_turns': msg.num_turns,
          }

        elif isinstance(msg, SystemMessage):
          yield {
            'type': 'system',
            'subtype': msg.subtype,
            'data': msg.data if hasattr(msg, 'data') else None,
          }

        elif isinstance(msg, UserMessage):
          # UserMessage 可能包含 tool result（工具執行後回傳給 Claude）
          msg_content = msg.content
          if isinstance(msg_content, list):
            for block in msg_content:
              if isinstance(block, ToolResultBlock):
                yield _process_tool_result(block, ask_user_tool_ids)
          # 跳過字串內容（僅為使用者輸入的回顯）

        elif isinstance(msg, StreamEvent):
          # 處理逐 token 更新的串流事件
          event_data = msg.event
          event_type = event_data.get('type', '')

          # 處理文字 delta 事件（逐 token 串流）
          if event_type == 'content_block_delta':
            delta = event_data.get('delta', {})
            delta_type = delta.get('type', '')
            if delta_type == 'text_delta':
              text = delta.get('text', '')
              if text:
                yield {
                  'type': 'text_delta',
                  'text': text,
                }
            elif delta_type == 'thinking_delta':
              thinking = delta.get('thinking', '')
              if thinking:
                yield {
                  'type': 'thinking_delta',
                  'thinking': thinking,
                }
          # 必要時透傳其他串流事件
          elif event_type not in ('content_block_start', 'content_block_stop', 'message_start', 'message_delta', 'message_stop'):
            yield {
              'type': 'stream_event',
              'event': event_data,
              'session_id': msg.session_id,
            }

  except Exception as e:
    # 記錄完整 traceback 以利除錯
    error_msg = f'Error during Claude query: {e}'
    full_traceback = traceback.format_exc()

    # 使用 print 輸出到 stderr，方便立即查看
    print(f'\n{"="*60}', file=sys.stderr)
    print(f'AGENT ERROR: {error_msg}', file=sys.stderr)
    print(full_traceback, file=sys.stderr)

    # 也以一般方式寫入日誌
    logger.error(error_msg)
    logger.error(full_traceback)

    # 若為 ExceptionGroup，記錄所有子例外
    if hasattr(e, 'exceptions'):
      for i, sub_exc in enumerate(e.exceptions):
        sub_tb = ''.join(traceback.format_exception(type(sub_exc), sub_exc, sub_exc.__traceback__))
        print(f'Sub-exception {i}: {sub_exc}', file=sys.stderr)
        print(sub_tb, file=sys.stderr)
        logger.error(f'Sub-exception {i}: {sub_exc}')
        logger.error(sub_tb)

    print(f'{"="*60}\n', file=sys.stderr)

    yield {
      'type': 'error',
      'error': str(e),
    }
  finally:
    # 結束時一律清除認證 context
    clear_databricks_auth()


# 保留簡單別名以維持向後相容
async def simple_query(project_id: str, message: str) -> AsyncIterator[dict]:
  """在專案目錄中對 Claude 進行簡單的無狀態查詢。"""
  async for event in stream_agent_response(project_id, message):
    yield event
