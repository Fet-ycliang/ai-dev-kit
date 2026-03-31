"""Databricks 工具的動態工具載入器。

從 databricks-mcp-server 掃描 FastMCP 工具並為
Claude Code Agent SDK 建立 in-process SDK 工具。

包含長時間執行操作的非同步移交，以避免
Claude 連線逾時。當工具超過 SAFE_EXECUTION_THRESHOLD 時，
執行繼續在背景進行並回傳操作 ID 供輪詢。
"""

import asyncio
import inspect
import json
import logging
import threading
import time
from contextvars import copy_context
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from .operation_tracker import (
    create_operation,
    complete_operation,
    get_operation,
    list_operations,
)

logger = logging.getLogger(__name__)

# 切換到非同步模式以避免連線逾時的秒數
# Anthropic API 有約 50 秒的 stream 閒置逾時，我們提早切換以保持訊息流動
# 較低的閾值確保工具結果快速回傳，避免累積逾時
SAFE_EXECUTION_THRESHOLD = 10


def load_databricks_tools():
    """動態掃描 FastMCP 工具並建立 in-process SDK MCP server。

    Returns:
        Tuple (server_config, tool_names)，其中：
        - server_config: ClaudeAgentOptions.mcp_servers 的 McpSdkServerConfig
        - tool_names: mcp__databricks__* 格式的工具名稱列表
    """
    sdk_tools, tool_names = _get_all_sdk_tools()

    logger.info(f'Loaded {len(sdk_tools)} Databricks tools: {[n.split("__")[-1] for n in tool_names]}')

    server = create_sdk_mcp_server(name='databricks', tools=sdk_tools)
    return server, tool_names


# 快取的 SDK 工具（載入一次，重複用於過濾的 server 建立）
_all_sdk_tools = None
_all_tool_names = None


def _get_all_sdk_tools():
    """載入並快取所有 SDK 工具包裝器。

    Returns:
        Tuple (sdk_tools, tool_names)
    """
    global _all_sdk_tools, _all_tool_names

    if _all_sdk_tools is not None:
        return _all_sdk_tools, _all_tool_names

    # Import 觸發 @mcp.tool 註冊
    from databricks_mcp_server.server import mcp
    from databricks_mcp_server.tools import sql, compute, file, pipelines  # noqa: F401

    sdk_tools = []
    tool_names = []

    # 包裝所有 Databricks MCP 工具
    for name, mcp_tool in mcp._tool_manager._tools.items():
        input_schema = _convert_schema(mcp_tool.parameters)
        fn = mcp_tool.fn
        # 解包 Windows async 包裝器（來自 server.py 的 _wrap_sync_in_thread），
        # 取得原始同步函式以便在執行緒池中正確執行。
        # functools.wraps 會設定 __wrapped__ 指向原始函式。
        if inspect.iscoroutinefunction(fn) and hasattr(fn, '__wrapped__') and not inspect.iscoroutinefunction(fn.__wrapped__):
            fn = fn.__wrapped__
        sdk_tool = _make_wrapper(name, mcp_tool.description, input_schema, fn)
        sdk_tools.append(sdk_tool)
        tool_names.append(f'mcp__databricks__{name}')

    # 新增操作追蹤工具（用於非同步移交模式）
    sdk_tools.append(_create_check_operation_status_tool())
    tool_names.append('mcp__databricks__check_operation_status')

    sdk_tools.append(_create_list_operations_tool())
    tool_names.append('mcp__databricks__list_operations')

    _all_sdk_tools = sdk_tools
    _all_tool_names = tool_names
    return sdk_tools, tool_names


def create_filtered_databricks_server(allowed_tool_names: list[str]):
    """建立僅包含指定工具的 MCP server。

    用於根據啟用的技能限制 agent 可存取的 Databricks 工具。

    Args:
        allowed_tool_names: mcp__databricks__* 格式的工具名稱列表

    Returns:
        Tuple (server_config, filtered_tool_names)
    """
    all_sdk_tools, all_tool_names = _get_all_sdk_tools()

    allowed_set = set(allowed_tool_names)
    filtered_tools = []
    filtered_names = []

    for sdk_tool, tool_name in zip(all_sdk_tools, all_tool_names):
        if tool_name in allowed_set:
            filtered_tools.append(sdk_tool)
            filtered_names.append(tool_name)

    logger.info(
        f'Created filtered Databricks server: {len(filtered_names)}/{len(all_tool_names)} tools '
        f'({len(all_tool_names) - len(filtered_names)} blocked)'
    )

    server = create_sdk_mcp_server(name='databricks', tools=filtered_tools)
    return server, filtered_names


def _create_check_operation_status_tool():
    """建立 check_operation_status 工具用於輪詢非同步操作。"""

    @tool(
        "check_operation_status",
        """檢查非同步操作的狀態。

使用此工具取得移至背景執行的長時間執行操作結果。當工具執行超過 30 秒時，
它會回傳 operation_id 而非阻塞。使用此工具輪詢結果。

Args:
    operation_id: 長時間執行工具回傳的操作 ID

Returns:
    - status: 'running'、'completed' 或 'failed'
    - tool_name: 原始工具的名稱
    - result: 操作結果（若已完成）
    - error: 錯誤訊息（若失敗）
    - elapsed_seconds: 操作啟動後經過的時間
""",
        {"operation_id": str},
    )
    async def check_operation_status(args: dict[str, Any]) -> dict[str, Any]:
        operation_id = args.get("operation_id", "")

        op = get_operation(operation_id)
        if not op:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "not_found",
                                "error": f"Operation {operation_id} not found. It may have expired (TTL: 1 hour) or never existed.",
                            }
                        ),
                    }
                ]
            }

        result = {
            "status": op.status,
            "operation_id": op.operation_id,
            "tool_name": op.tool_name,
            "elapsed_seconds": round(time.time() - op.started_at, 1),
        }

        if op.status == "completed":
            result["result"] = op.result
        elif op.status == "failed":
            result["error"] = op.error

        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}

    return check_operation_status


def _create_list_operations_tool():
    """建立 list_operations 工具用於檢視所有追蹤的操作。"""

    @tool(
        "list_operations",
        """列出所有追蹤的非同步操作。

使用此工具查看所有執行中或最近完成的操作。
對檢查進行中的內容或尋找操作 ID 很有用。

Args:
    status: 可選過濾器 - 'running'、'completed' 或 'failed'

Returns:
    包含狀態和經過時間的操作列表
""",
        {"status": str},
    )
    async def list_ops(args: dict[str, Any]) -> dict[str, Any]:
        status_filter = args.get("status")
        if status_filter == "":
            status_filter = None

        ops = list_operations(status_filter)
        return {"content": [{"type": "text", "text": json.dumps(ops, default=str)}]}

    return list_ops


def _convert_schema(json_schema: dict) -> dict[str, type]:
    """將 JSON schema 轉換為 SDK 簡單格式：{"param": type}"""
    type_map = {
        'string': str,
        'integer': int,
        'number': float,
        'boolean': bool,
        'array': list,
        'object': dict,
    }
    result = {}

    for param, spec in json_schema.get('properties', {}).items():
        # 處理 anyOf（可選類型如 "string | null"）
        if 'anyOf' in spec:
            for opt in spec['anyOf']:
                if opt.get('type') != 'null':
                    result[param] = type_map.get(opt.get('type'), str)
                    break
        else:
            result[param] = type_map.get(spec.get('type'), str)

    return result


def _make_wrapper(name: str, description: str, schema: dict, fn):
    """為 FastMCP 函式建立 SDK 工具包裝器。

    包裝器在執行緒池中執行同步函式以避免
    阻塞非同步事件迴圈。它也處理複雜類型（lists、dicts）的
    JSON 字串解析，Claude agent 可能將其作為字串傳遞。

    包含長時間執行操作的非同步移交：
    - 在 SAFE_EXECUTION_THRESHOLD 內完成的操作正常回傳
    - 超過閾值的操作切換到背景執行
      並回傳 operation_id 供透過 check_operation_status 輪詢
    """

    @tool(name, description, schema)
    async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
        import sys
        import traceback
        import concurrent.futures

        start_time = time.time()
        print(f'[MCP TOOL] {name} called with args: {args}', file=sys.stderr, flush=True)
        logger.info(f'[MCP] Tool {name} called with args: {args}')
        try:
            # 解析複雜類型的 JSON 字串（Claude agent 有時將這些作為字串傳送）
            parsed_args = {}
            for key, value in args.items():
                if isinstance(value, str) and value.strip().startswith(('[', '{')):
                    # 若看起來像 list 或 dict 則嘗試解析為 JSON
                    try:
                        parsed_args[key] = json.loads(value)
                        print(f'[MCP TOOL] Parsed {key} from JSON string', file=sys.stderr, flush=True)
                    except json.JSONDecodeError:
                        # 非有效 JSON，保持為字串
                        parsed_args[key] = value
                else:
                    parsed_args[key] = value

            # FastMCP 工具是同步的 - 在執行緒池中執行並帶心跳
            print(f'[MCP TOOL] Running {name} in thread pool with heartbeat...', file=sys.stderr, flush=True)

            # 複製 context 以將 Databricks 認證 contextvars 傳播到執行緒
            ctx = copy_context()

            def run_in_context():
                """在複製的 context 中執行工具函式。"""
                return ctx.run(fn, **parsed_args)

            # 在 executor 中執行工具以便我們可以用心跳輪詢完成
            # 使用 executor.submit() 來取得 concurrent.futures.Future（執行緒安全）
            # 而非 loop.run_in_executor() 它回傳 asyncio.Future
            loop = asyncio.get_event_loop()
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            cf_future = executor.submit(run_in_context)  # concurrent.futures.Future
            # 包裝在 asyncio.Future 中以便非同步等待
            future = asyncio.wrap_future(cf_future, loop=loop)

            # 等待工具完成時每 10 秒心跳一次
            HEARTBEAT_INTERVAL = 10
            heartbeat_count = 0
            while True:
                try:
                    # 等待結果並設定逾時
                    result = await asyncio.wait_for(
                        asyncio.shield(future),
                        timeout=HEARTBEAT_INTERVAL
                    )
                    # 工具成功完成
                    break
                except asyncio.TimeoutError:
                    # 工具仍在執行 - 發出心跳
                    heartbeat_count += 1
                    elapsed = time.time() - start_time
                    print(f'[MCP HEARTBEAT] {name} still running... ({elapsed:.0f}s elapsed, heartbeat #{heartbeat_count})', file=sys.stderr, flush=True)
                    logger.debug(f'[MCP] Heartbeat for {name}: {elapsed:.0f}s elapsed')

                    # 檢查是否應切換到非同步模式以避免連線逾時
                    if elapsed > SAFE_EXECUTION_THRESHOLD:
                        op_id = create_operation(name, parsed_args)
                        print(
                            f'[MCP ASYNC] {name} exceeded {SAFE_EXECUTION_THRESHOLD}s, '
                            f'switching to async mode (operation_id: {op_id})',
                            file=sys.stderr,
                            flush=True,
                        )
                        logger.info(
                            f'[MCP] Tool {name} switched to async mode after {elapsed:.0f}s '
                            f'(operation_id: {op_id})'
                        )

                        # 啟動背景執行緒以完成操作
                        # 我們使用 threading.Thread 而非 asyncio.create_task 因為
                        # fresh event loop 模式可能不會保持任務存活
                        def complete_in_background(op_id, cf_future, executor):
                            """背景執行緒等待完成並儲存結果。"""
                            try:
                                # 阻塞直到 future 完成（它已在執行中）
                                # cf_future 是 concurrent.futures.Future，執行緒安全
                                result = cf_future.result()  # 這會阻塞
                                complete_operation(op_id, result=result)
                                print(
                                    f'[MCP ASYNC] Operation {op_id} completed successfully',
                                    file=sys.stderr,
                                    flush=True,
                                )
                            except Exception as e:
                                import traceback
                                error_details = traceback.format_exc()
                                complete_operation(op_id, error=str(e))
                                print(
                                    f'[MCP ASYNC] Operation {op_id} failed: {e}',
                                    file=sys.stderr,
                                    flush=True,
                                )
                                print(
                                    f'[MCP ASYNC] Traceback:\n{error_details}',
                                    file=sys.stderr,
                                    flush=True,
                                )
                            finally:
                                executor.shutdown(wait=False)

                        bg_thread = threading.Thread(
                            target=complete_in_background,
                            args=(op_id, cf_future, executor),
                            daemon=True,
                        )
                        bg_thread.start()

                        # 立即回傳操作資訊
                        return {
                            'content': [
                                {
                                    'type': 'text',
                                    'text': json.dumps({
                                        'status': 'async',
                                        'operation_id': op_id,
                                        'tool_name': name,
                                        'message': (
                                            f'操作執行超過 {SAFE_EXECUTION_THRESHOLD} 秒'
                                            f'已移至背景執行。'
                                            f'使用 check_operation_status("{op_id}") 輪詢結果。'
                                        ),
                                        'elapsed_seconds': round(elapsed, 1),
                                    }),
                                }
                            ]
                        }

                    # 繼續等待
                    continue

            elapsed = time.time() - start_time
            result_str = json.dumps(result, default=str)
            print(f'[MCP TOOL] {name} completed in {elapsed:.2f}s, result length: {len(result_str)}', file=sys.stderr, flush=True)
            logger.info(f'[MCP] Tool {name} completed in {elapsed:.2f}s')
            return {'content': [{'type': 'text', 'text': result_str}]}
        except asyncio.CancelledError:
            elapsed = time.time() - start_time
            error_msg = f'Tool execution cancelled after {elapsed:.2f}s (likely due to stream timeout)'
            print(f'[MCP TOOL] {name} CANCELLED: {error_msg}', file=sys.stderr, flush=True)
            logger.error(f'[MCP] Tool {name} cancelled: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error: {error_msg}'}], 'is_error': True}
        except TimeoutError as e:
            elapsed = time.time() - start_time
            error_msg = f'Tool execution timed out after {elapsed:.2f}s: {e}'
            print(f'[MCP TOOL] {name} TIMEOUT: {error_msg}', file=sys.stderr, flush=True)
            logger.error(f'[MCP] Tool {name} timeout: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error: {error_msg}'}], 'is_error': True}
        except Exception as e:
            elapsed = time.time() - start_time
            error_details = traceback.format_exc()
            error_msg = f'{type(e).__name__}: {str(e)}'
            print(f'[MCP TOOL] {name} FAILED after {elapsed:.2f}s: {error_msg}', file=sys.stderr, flush=True)
            print(f'[MCP TOOL] Stack trace:\n{error_details}', file=sys.stderr, flush=True)
            logger.exception(f'[MCP] Tool {name} failed after {elapsed:.2f}s: {error_msg}')
            return {'content': [{'type': 'text', 'text': f'Error ({type(e).__name__}): {str(e)}\n\nThis error occurred after {elapsed:.2f}s. If this is a long-running operation, it may have exceeded the stream timeout (50s).'}], 'is_error': True}

    return wrapper
