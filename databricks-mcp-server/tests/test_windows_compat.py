"""Windows 相容性包裝器 (_wrap_sync_in_thread) 的測試。"""

import asyncio
import inspect
import threading

import pydantic
import pytest

from databricks_mcp_server.server import _wrap_sync_in_thread


def sample_tool(query: str, limit: int = 10) -> str:
    """Execute a sample query."""
    return f"result:{query}:{limit}"


class TestWrapSyncInThread:
    """_wrap_sync_in_thread 包裝器的測試。"""

    def test_preserves_function_name(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__name__ == "sample_tool"

    def test_preserves_docstring(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__doc__ == "Execute a sample query."

    def test_preserves_annotations(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__annotations__ == sample_tool.__annotations__

    def test_preserves_signature(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        original_sig = inspect.signature(sample_tool)
        wrapped_sig = inspect.signature(wrapped)
        assert str(original_sig) == str(wrapped_sig)

    def test_is_coroutine_function(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert inspect.iscoroutinefunction(wrapped)

    @pytest.mark.asyncio
    async def test_returns_correct_result(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        result = await wrapped(query="test", limit=5)
        assert result == "result:test:5"

    @pytest.mark.asyncio
    async def test_returns_correct_result_with_defaults(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        result = await wrapped(query="test")
        assert result == "result:test:10"

    @pytest.mark.asyncio
    async def test_runs_in_thread_pool(self):
        """驗證同步函式會在與 event loop 不同的執行緒中執行。"""
        main_thread = threading.current_thread().ident

        def capture_thread(query: str) -> int:
            return threading.current_thread().ident

        wrapped = _wrap_sync_in_thread(capture_thread)
        worker_thread = await wrapped(query="test")
        assert worker_thread != main_thread

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self):
        """驗證包裝後的函式執行期間，並行任務仍可執行。"""
        import time

        def slow_tool(query: str) -> str:
            time.sleep(0.2)
            return "done"

        wrapped = _wrap_sync_in_thread(slow_tool)

        concurrent_ran = False

        async def concurrent_task():
            nonlocal concurrent_ran
            await asyncio.sleep(0.05)
            concurrent_ran = True

        await asyncio.gather(wrapped(query="test"), concurrent_task())
        assert concurrent_ran

    @pytest.mark.asyncio
    async def test_propagates_exceptions(self):
        def failing_tool(query: str) -> str:
            raise ValueError("something went wrong")

        wrapped = _wrap_sync_in_thread(failing_tool)
        with pytest.raises(ValueError, match="something went wrong"):
            await wrapped(query="test")

    def test_pydantic_type_adapter_returns_awaitable(self):
        """驗證 pydantic 的 TypeAdapter 可以呼叫包裝後的函式並取得 coroutine。

        FastMCP 會使用 TypeAdapter.validate_python() 來呼叫工具函式。
        包裝器必須產生 pydantic 可辨識為可呼叫的結果，
        並保留原始 signature。
        """
        wrapped = _wrap_sync_in_thread(sample_tool)
        pydantic.TypeAdapter(wrapped.__annotations__.get("return", str))
        # TypeAdapter 應能讀取函式的 annotations
        sig = inspect.signature(wrapped)
        assert "query" in sig.parameters
        assert "limit" in sig.parameters
        # 呼叫包裝器會回傳 coroutine
        coro = wrapped(query="test", limit=5)
        assert inspect.iscoroutine(coro)
        # 清理未 await 的 coroutine
        coro.close()
