"""Claude Code agent 呼叫端點。

處理來自 Claude Code agent session 的非同步串流回應與 SSE。

非同步模式：
1. POST /invoke_agent - 啟動 agent，立即回傳 execution_id
2. POST /stream_progress/{execution_id} - SSE 串流事件（50 秒視窗）
3. POST /stop_stream/{execution_id} - 取消執行
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.active_stream import get_stream_manager
from ..services.agent import get_project_directory, stream_agent_response
from ..services.backup_manager import mark_for_backup
from ..services.storage import ConversationStorage, ProjectStorage
from ..services.title_generator import generate_title_async
from ..services.user import get_current_user, get_current_token, get_fmapi_token, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()

# SSE 串流視窗持續時間（秒）- 在 60 秒逾時前中斷
SSE_WINDOW_SECONDS = 50


def sse_event(data: dict) -> str:
    """格式化資料為 SSE 事件。"""
    return f'data: {json.dumps(data)}\n\n'


class InvokeAgentRequest(BaseModel):
    """呼叫 Claude Code agent 的請求。"""

    project_id: str
    conversation_id: Optional[str] = None  # 若未提供則建立新對話
    message: str
    cluster_id: Optional[str] = None  # 執行程式碼用的 Databricks cluster
    default_catalog: Optional[str] = None  # 預設 Unity Catalog
    default_schema: Optional[str] = None  # 預設 schema
    warehouse_id: Optional[str] = None  # 查詢用的 Databricks SQL warehouse
    workspace_folder: Optional[str] = None  # 檔案上傳用的 workspace 資料夾
    mlflow_experiment_name: Optional[str] = None  # tracing 用的 MLflow 實驗名稱
    target_databricks_host: Optional[str] = None  # 跨 workspace 操作的目標 workspace URL
    target_databricks_token: Optional[str] = None  # 目標 workspace 的預先產生 OAuth token


class InvokeAgentResponse(BaseModel):
    """invoke_agent 的回應，包含執行追蹤資訊。"""

    execution_id: str
    conversation_id: str


class StreamProgressRequest(BaseModel):
    """從執行中的執行串流進度的請求。"""

    last_event_timestamp: Optional[float] = None


class StopStreamResponse(BaseModel):
    """stop_stream 端點的回應。"""

    success: bool
    message: str


@router.post('/invoke_agent', response_model=InvokeAgentResponse)
async def invoke_agent(request: Request, body: InvokeAgentRequest):
    """非同步啟動 Claude Code agent。

    若未提供 conversation_id 則建立新對話。
    立即回傳 execution_id 以供串流進度。

    agent 在背景執行並累積事件。
    使用 POST /stream_progress/{execution_id} 透過 SSE 串流事件。
    使用 POST /stop_stream/{execution_id} 取消執行。
    """
    logger.info(
        f'Invoking agent for project: {body.project_id}, conversation: {body.conversation_id}'
    )

    # 取得目前使用者與 Databricks 認證
    user_email = await get_current_user(request)
    # 使用 FMAPI token 給 Claude API（正式環境中為 Service Principal OAuth）
    user_token = await get_fmapi_token(request)
    workspace_url = get_workspace_url()

    # FMAPI（Claude API）永遠使用 Builder App 自己的 workspace
    fmapi_host = workspace_url
    fmapi_token = user_token

    # Databricks 工具操作在提供跨 workspace 參數時以呼叫者指定的 workspace 為目標，
    # 否則預設為此 workspace
    is_cross_workspace = body.target_databricks_host is not None
    tools_host = body.target_databricks_host or workspace_url
    tools_token = body.target_databricks_token or user_token

    # 驗證專案存在且屬於使用者
    project_storage = ProjectStorage(user_email)
    project = await project_storage.get(body.project_id)
    if not project:
        logger.error(f'Project not found: {body.project_id}')
        raise HTTPException(status_code=404, detail=f'Project not found: {body.project_id}')

    # 從專案檔案系統（非資料庫）讀取已啟用的 skill
    from ..services.skills_manager import get_project_enabled_skills
    project_dir = get_project_directory(body.project_id)
    enabled_skills = get_project_enabled_skills(project_dir)

    # 取得或建立對話
    conv_storage = ConversationStorage(user_email, body.project_id)
    conversation_id = body.conversation_id

    if not conversation_id:
        # 建立臨時標題的新對話（將由 AI 更新）
        temp_title = body.message[:40].strip()
        if len(body.message) > 40:
            temp_title = temp_title.rsplit(' ', 1)[0] + '...'
        conversation = await conv_storage.create(title=temp_title)
        conversation_id = conversation.id
        logger.info(f'Created new conversation: {conversation_id}')

        # 在背景產生 AI 標題（發射後不等待）
        # 標題產生會呼叫 Claude API，因此永遠使用 FMAPI 憑證
        asyncio.create_task(
            generate_title_async(
                message=body.message,
                conversation_id=conversation_id,
                user_email=user_email,
                project_id=body.project_id,
                databricks_host=fmapi_host,
                databricks_token=fmapi_token,
            )
        )
    else:
        # 驗證對話存在並取得 session_id 以供恢復
        conversation = await conv_storage.get(conversation_id)
        if not conversation:
            logger.error(f'Conversation not found: {conversation_id}')
            raise HTTPException(status_code=404, detail=f'Conversation not found: {conversation_id}')

    # 從對話取得 session_id 以供恢復
    session_id = conversation.session_id if conversation else None

    # 使用 user_email 建立持久性的主動串流
    stream_manager = get_stream_manager()
    stream = await stream_manager.create_stream(
        project_id=body.project_id,
        conversation_id=conversation_id,
        user_email=user_email,
    )

    # 發送 conversation_id 作為第一個事件
    stream.add_event({'type': 'conversation.created', 'conversation_id': conversation_id})

    # 建立將在背景執行的 agent coroutine
    async def run_agent():
        """執行 agent 並在串流中累積事件。"""
        final_text = ''
        new_session_id: Optional[str] = None
        error_message: Optional[str] = None
        received_deltas = False  # 追蹤是否收到串流 delta

        try:
            # 從 Claude 串流所有事件
            # 傳遞取消檢查函式以便 agent 執行緒可提前停止
            async for event in stream_agent_response(
                project_id=body.project_id,
                message=body.message,
                session_id=session_id,
                cluster_id=body.cluster_id,
                default_catalog=body.default_catalog,
                default_schema=body.default_schema,
                warehouse_id=body.warehouse_id,
                workspace_folder=body.workspace_folder,
                fmapi_host=fmapi_host,
                fmapi_token=fmapi_token,
                databricks_host=tools_host,
                databricks_token=tools_token,
                is_cross_workspace=is_cross_workspace,
                is_cancelled_fn=lambda: stream.is_cancelled,
                enabled_skills=enabled_skills,
                mlflow_experiment_name=body.mlflow_experiment_name,
            ):
                # 檢查是否已取消（agent 執行緒中也有檢查，但這裡再次確認）
                if stream.is_cancelled:
                    logger.info(f'Stream {stream.execution_id} cancelled, stopping agent')
                    break

                event_type = event.get('type', '')

                if event_type == 'text_delta':
                    # 逐 token 串流 - 這是偏好方式
                    text = event.get('text', '')
                    final_text += text
                    received_deltas = True
                    stream.add_event({'type': 'text_delta', 'text': text})

                elif event_type == 'text':
                    # 完整文字區塊 - 累積所有文字區塊
                    # Claude 在工具呼叫之間會傳送多個文字區塊
                    # 我們追蹤 received_deltas 以知道是否也應發送文字事件
                    # （如果正在使用 delta，客戶端已逐 token 取得文字）
                    text = event.get('text', '')
                    if text:
                        if not received_deltas:
                            # 未收到 delta，因此傳送完整文字區塊給客戶端
                            final_text += text
                            stream.add_event({'type': 'text', 'text': text})
                        # 注意：若 received_deltas 為 True，我們跳過傳送 'text' 事件
                        # 因為客戶端已透過 'text_delta' 收到相同內容
                        # 但我們仍需追蹤 final_text 以供持久化
                        # text_delta 處理器已累積到 final_text

                elif event_type == 'thinking':
                    stream.add_event({
                        'type': 'thinking',
                        'thinking': event.get('thinking', ''),
                    })

                elif event_type == 'tool_use':
                    tool_name = event.get('tool_name', '')
                    tool_input = event.get('tool_input', {})

                    stream.add_event({
                        'type': 'tool_use',
                        'tool_id': event.get('tool_id', ''),
                        'tool_name': tool_name,
                        'tool_input': tool_input,
                    })

                    # 當呼叫 TodoWrite 時發送專用的 todos 事件
                    if tool_name == 'TodoWrite' and 'todos' in tool_input:
                        stream.add_event({
                            'type': 'todos',
                            'todos': tool_input['todos'],
                        })

                elif event_type == 'tool_result':
                    content = event.get('content', '')
                    is_error = event.get('is_error', False)

                    # 偵測連鎖失敗模式 - "Stream closed" 錯誤表示
                    # Claude 子程序的 MCP 連線已中斷
                    if is_error and 'Stream closed' in str(content):
                        logger.error(f'Detected MCP connection failure: {content}')
                        # 為錯誤加入上下文
                        content = f'MCP Connection Lost: 工具執行被中斷，因為內部通訊通道斷裂。這通常發生在長時間執行操作之後。請開始新對話以重設連線。原始錯誤：{content}'

                    stream.add_event({
                        'type': 'tool_result',
                        'tool_use_id': event.get('tool_use_id', ''),
                        'content': content,
                        'is_error': is_error,
                    })

                elif event_type == 'result':
                    new_session_id = event.get('session_id')
                    stream.add_event({
                        'type': 'result',
                        'session_id': new_session_id,
                        'duration_ms': event.get('duration_ms'),
                        'total_cost_usd': event.get('total_cost_usd'),
                        'is_error': event.get('is_error', False),
                        'num_turns': event.get('num_turns'),
                    })

                elif event_type == 'error':
                    error_message = event.get('error', 'Unknown error')
                    logger.error(f'Agent error received: {error_message}')
                    stream.add_event({'type': 'error', 'error': error_message})

                elif event_type == 'system':
                    # 若尚未設定 session_id，從 init 事件中提取
                    data = event.get('data')
                    if event.get('subtype') == 'init' and data and not new_session_id:
                        new_session_id = data.get('session_id')
                    stream.add_event({
                        'type': 'system',
                        'subtype': event.get('subtype', ''),
                        'data': data,
                    })

                elif event_type == 'cancelled':
                    # agent 被使用者要求取消
                    logger.info(f'Stream {stream.execution_id} received cancellation confirmation')
                    stream.add_event({'type': 'cancelled'})
                    break

                elif event_type == 'keepalive':
                    # 長時間工具執行期間的保持連線 - 轉發到串流以維持連線
                    elapsed = event.get('elapsed_since_last_event', 0)
                    logger.debug(f'Stream {stream.execution_id} keepalive - {elapsed:.0f}s since last event')
                    stream.add_event({
                        'type': 'keepalive',
                        'elapsed_since_last_event': elapsed,
                    })

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f'Error during agent stream: {type(e).__name__}: {e}')
            logger.error(f'Agent stream traceback:\n{error_details}')
            print(f'[AGENT STREAM ERROR] {type(e).__name__}: {e}', flush=True)
            print(f'[AGENT STREAM TRACEBACK]\n{error_details}', flush=True)

            # 為常見錯誤提供更多上下文
            error_message = str(e)
            if 'Stream closed' in error_message:
                error_message = f'Agent 通訊中斷：{error_message}。這通常發生在 Claude 子程序意外終止時。請檢查後端日誌以取得詳細資訊。'

            stream.add_event({'type': 'error', 'error': error_message})

        # 在串流完成後儲存訊息到儲存體（若未取消）
        if not stream.is_cancelled:
            try:
                # 儲存使用者訊息
                await conv_storage.add_message(
                    conversation_id=conversation_id,
                    role='user',
                    content=body.message,
                )

                # 儲存助理回應（或錯誤）
                if final_text or error_message:
                    content = final_text if final_text else f'Error: {error_message}'
                    is_error = bool(error_message and not final_text)
                    logger.info(f'Saving assistant message: {len(content)} chars, is_error={is_error}')
                    await conv_storage.add_message(
                        conversation_id=conversation_id,
                        role='assistant',
                        content=content,
                        is_error=is_error,
                    )
                else:
                    logger.warning('No response to save (no text and no error)')

                # 更新對話恢復用的 session_id
                if new_session_id:
                    await conv_storage.update_session_id(conversation_id, new_session_id)

                # 如有提供則更新 cluster_id
                if body.cluster_id:
                    await conv_storage.update_cluster_id(conversation_id, body.cluster_id)

                # 如有提供則更新 catalog/schema
                if body.default_catalog or body.default_schema:
                    await conv_storage.update_catalog_schema(
                        conversation_id, body.default_catalog, body.default_schema
                    )

                # 如有提供則更新 warehouse_id
                if body.warehouse_id:
                    await conv_storage.update_warehouse_id(conversation_id, body.warehouse_id)

                # 如有提供則更新 workspace_folder
                if body.workspace_folder:
                    await conv_storage.update_workspace_folder(conversation_id, body.workspace_folder)

                logger.info(
                    f'Saved messages to conversation {conversation_id}: '
                    f'text={len(final_text)} chars, error={error_message is not None}'
                )

                # 標記專案以供備份（將由備份工作者處理）
                mark_for_backup(body.project_id)

            except Exception as e:
                logger.error(f'Failed to save messages: {e}')

        # 標記串流為完成
        if error_message and not final_text:
            stream.mark_error(error_message)
        else:
            stream.mark_complete()

    # 在背景啟動 agent
    await stream_manager.start_stream(stream, run_agent)

    return InvokeAgentResponse(
        execution_id=stream.execution_id,
        conversation_id=conversation_id,
    )


@router.post('/stream_progress/{execution_id}')
async def stream_progress(execution_id: str, body: StreamProgressRequest):
    """透過 SSE 從執行中的執行串流事件。

    此端點以 Server-Sent Events（SSE）串流事件。
    在傳送重新連線訊號前會執行最多 50 秒，
    允許客戶端在 60 秒 HTTP 逾時前重新連線。

    Args:
        execution_id: 從 invoke_agent 取得的執行 ID
        body: 包含 last_event_timestamp 的請求本體，用於恢復

    Returns:
        事件的 SSE 串流
    """
    stream_manager = get_stream_manager()
    stream = await stream_manager.get_stream(execution_id)

    if not stream:
        raise HTTPException(
            status_code=404,
            detail=f'Stream not found: {execution_id}'
        )

    async def generate_events():
        """產生具有 50 秒視窗的 SSE 事件串流。"""
        last_timestamp = body.last_event_timestamp or 0.0
        start_time = datetime.now()

        # 持續串流直到逾時或完成
        while True:
            # 取得自上次時間戳記後的新事件
            new_events, new_cursor = stream.get_events_since(last_timestamp)

            # 傳送新事件
            for event in new_events:
                yield sse_event(event)

            # 更新時間戳記
            if new_events:
                last_timestamp = new_cursor

            # 檢查串流是否完成或取消
            if stream.is_complete or stream.is_cancelled:
                # 清空上次輪詢與完成之間加入的任何事件
                remaining, _ = stream.get_events_since(last_timestamp)
                for event in remaining:
                    if event.get('type') != 'stream.completed':
                        yield sse_event(event)
                yield sse_event({
                    'type': 'stream.completed',
                    'is_error': stream.error is not None,
                    'is_cancelled': stream.is_cancelled,
                })
                yield 'data: [DONE]\n\n'
                break

            # 檢查是否已超過 SSE 視窗（50 秒）
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > SSE_WINDOW_SECONDS:
                # 傳送帶有最後時間戳記的重新連線訊號
                yield sse_event({
                    'type': 'stream.reconnect',
                    'execution_id': execution_id,
                    'last_timestamp': last_timestamp,
                    'message': 'Reconnect to continue streaming',
                })
                break

            # 在檢查新事件前稍等片刻
            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate_events(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post('/stop_stream/{execution_id}', response_model=StopStreamResponse)
async def stop_stream(execution_id: str):
    """停止/取消執行中的串流。

    Args:
        execution_id: 從 invoke_agent 取得的執行 ID

    Returns:
        成功狀態與訊息
    """
    stream_manager = get_stream_manager()
    stream = await stream_manager.get_stream(execution_id)

    if not stream:
        raise HTTPException(
            status_code=404,
            detail=f'Stream not found: {execution_id}'
        )

    if stream.is_complete:
        return StopStreamResponse(
            success=False,
            message='Stream already complete'
        )

    cancelled = stream.cancel()

    return StopStreamResponse(
        success=cancelled,
        message='Stream cancelled' if cancelled else 'Failed to cancel stream'
    )


@router.get('/projects/{project_id}/files')
async def list_project_files(request: Request, project_id: str):
    """列出專案目錄中的檔案。"""
    user_email = await get_current_user(request)

    # 驗證專案存在且屬於使用者
    project_storage = ProjectStorage(user_email)
    project = await project_storage.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f'Project {project_id} not found')

    # 取得專案目錄並列出檔案
    project_dir = get_project_directory(project_id)

    files = []
    for path in project_dir.rglob('*'):
        if path.is_file():
            rel_path = path.relative_to(project_dir)
            files.append(
                {
                    'path': str(rel_path),
                    'name': path.name,
                    'size': path.stat().st_size,
                    'modified': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
            )

    return {'project_id': project_id, 'files': files}


@router.get('/projects/{project_id}/conversations/{conversation_id}/executions')
async def get_conversation_executions(
    request: Request,
    project_id: str,
    conversation_id: str,
):
    """取得對話的進行中與近期執行紀錄。

    會回傳目前進行中的執行（若有）以及近期已完成的執行。
    這可支援 session 獨立性，讓使用者在離開頁面後仍能重新連線。
    """
    from ..services.storage import ExecutionStorage

    user_email = await get_current_user(request)

    # 驗證專案存在且屬於使用者
    project_storage = ProjectStorage(user_email)
    project = await project_storage.get(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f'Project {project_id} not found'
        )

    # 首先檢查此對話的記憶體內串流（永遠有效）
    stream_manager = get_stream_manager()
    in_memory_active = None
    async with stream_manager._lock:
        for stream in stream_manager._streams.values():
            if (
                stream.conversation_id == conversation_id
                and not stream.is_complete
                and not stream.is_cancelled
            ):
                in_memory_active = {
                    'id': stream.execution_id,
                    'conversation_id': stream.conversation_id,
                    'project_id': stream.project_id,
                    'status': 'running',
                    'events': [e.data for e in stream.events],
                    'error': stream.error,
                    'created_at': None,
                }
                break

    # 嘗試從資料庫取得執行（若資料表尚未存在可能會失敗）
    active = None
    recent = []
    try:
        exec_storage = ExecutionStorage(user_email, project_id, conversation_id)
        active = await exec_storage.get_active()
        recent = await exec_storage.get_recent(limit=5)
    except Exception as e:
        # 資料表可能尚未存在（待遷移）- 記錄並繼續
        # 記憶體內串流仍可運作
        logger.warning(f'Failed to query executions table (may not exist yet): {e}')

    return {
        'active': (
            in_memory_active
            or (active.to_dict() if active else None)
        ),
        'recent': [e.to_dict() for e in recent if e.id != (
            active.id if active else None
        )],
    }
