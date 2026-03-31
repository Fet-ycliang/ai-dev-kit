"""
Databricks MCP Server

將 Databricks 操作公開為 MCP 工具的 FastMCP 伺服器。
僅包裝 databricks-tools-core 中的函式。
"""

import asyncio
import functools
import inspect
import subprocess
import sys
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .middleware import TimeoutHandlingMiddleware


# ---------------------------------------------------------------------------
# Windows 修補——必須在 FastMCP 初始化與工具註冊之前執行
# ---------------------------------------------------------------------------


def _patch_subprocess_stdin():
    """在 Windows 上對 subprocess 進行 monkey-patch，讓 stdin 預設為 DEVNULL。

    當 MCP 伺服器以 stdio 模式執行時，stdin 就是 JSON-RPC pipe。
    任何未明確指定 stdin 的 subprocess 呼叫，都會讓子行程繼承
    這個 pipe handle。在 Windows 上，Databricks SDK 會透過
    ``subprocess.run(["databricks", "auth", "token", ...], shell=True)``
    重新整理 auth token，卻未設定 stdin——因此啟動的 ``databricks.exe``
    會阻塞等待讀取共用 pipe，導致所有 MCP 工具呼叫卡住。

    修正方式：將 stdin 預設為 DEVNULL，讓子行程永遠不會碰到該 pipe。

    參見: https://github.com/modelcontextprotocol/python-sdk/issues/671
    """
    _original_run = subprocess.run

    @functools.wraps(_original_run)
    def _patched_run(*args, **kwargs):
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        return _original_run(*args, **kwargs)

    subprocess.run = _patched_run

    _OriginalPopen = subprocess.Popen

    class _PatchedPopen(_OriginalPopen):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stdin", subprocess.DEVNULL)
            super().__init__(*args, **kwargs)

    subprocess.Popen = _PatchedPopen


def _filter_supported_tool_kwargs(tool_callable, kwargs):
    """過濾目前 FastMCP.tool 支援的 decorator kwargs。"""
    signature = inspect.signature(tool_callable)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs

    supported_kwargs = set(signature.parameters)
    return {key: value for key, value in kwargs.items() if key in supported_kwargs}


def _patch_tool_decorator():
    """替 @mcp.tool 加上相容層，並在 Windows 上包裝同步工具函式。

    FastMCP 的 FunctionTool.run() 會直接在 asyncio 事件迴圈執行緒上
    呼叫同步函式，這會阻塞 stdio transport 的 I/O 工作。在 Windows
    （ProactorEventLoop）上，這會造成 deadlock——所有 MCP 工具都會無限期卡住。

    此修補會攔截 @mcp.tool 的註冊流程：
    1. 過濾當前 FastMCP 版本不支援的 decorator kwargs（例如 timeout）
    2. 在 Windows 上包裝同步函式，使其於執行緒集區中執行，
       把 I/O 所需的控制權交還給事件迴圈

    參見: https://github.com/modelcontextprotocol/python-sdk/issues/671
    """
    original_tool = mcp.tool

    @functools.wraps(original_tool)
    def patched_tool(fn=None, *args, **kwargs):
        filtered_kwargs = _filter_supported_tool_kwargs(original_tool, kwargs)

        # 處理 @mcp.tool("name")——會回傳一個 decorator
        if fn is None or isinstance(fn, str):
            decorator = original_tool(fn, *args, **filtered_kwargs)

            @functools.wraps(decorator)
            def wrapper(func):
                if sys.platform == "win32" and not inspect.iscoroutinefunction(func):
                    func = _wrap_sync_in_thread(func)
                return decorator(func)

            return wrapper

        # 處理 @mcp.tool（裸 decorator，fn 就是函式本身）
        if sys.platform == "win32" and not inspect.iscoroutinefunction(fn):
            fn = _wrap_sync_in_thread(fn)
        return original_tool(fn, *args, **filtered_kwargs)

    mcp.tool = patched_tool


def _wrap_sync_in_thread(fn):
    """包裝同步函式，使其在 asyncio.to_thread() 中執行，並保留中繼資料。"""

    @functools.wraps(fn)
    async def async_wrapper(**kwargs):
        return await asyncio.to_thread(fn, **kwargs)

    return async_wrapper


# 及早套用 subprocess 修補——在任何 Databricks SDK 匯入之前
if sys.platform == "win32":
    _patch_subprocess_stdin()

# ---------------------------------------------------------------------------
# 伺服器初始化
# ---------------------------------------------------------------------------

# 在 Windows 上停用 FastMCP 內建的 task worker。
# docket worker 使用 fakeredis XREADGROUP BLOCK，會讓
# ProactorEventLoop 發生 deadlock，導致 asyncio.to_thread() callback 無法執行。
# 透過覆寫 _docket_lifespan 來阻止 worker 啟動（見下方）。
mcp = FastMCP("Databricks MCP Server")

if sys.platform == "win32":

    @asynccontextmanager
    async def _noop_lifespan(*args, **kwargs):
        yield

    if hasattr(mcp, "_docket_lifespan"):
        mcp._docket_lifespan = _noop_lifespan

# 註冊 middleware（各項細節請見 middleware.py）
mcp.add_middleware(TimeoutHandlingMiddleware())

_patch_tool_decorator()

# 匯入並註冊所有工具（具副作用的匯入：各模組都會註冊 @mcp.tool decorator）
from .tools import (  # noqa: F401, E402
    sql,
    compute,
    file,
    pipelines,
    jobs,
    agent_bricks,
    aibi_dashboards,
    serving,
    unity_catalog,
    volume_files,
    genie,
    manifest,
    vector_search,
    lakebase,
    user,
    apps,
    workspace,
    pdf,
)
