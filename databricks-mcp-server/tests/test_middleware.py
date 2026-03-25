"""TimeoutHandlingMiddleware 的測試。"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from databricks_mcp_server.middleware import TimeoutHandlingMiddleware


@pytest.fixture
def middleware():
    return TimeoutHandlingMiddleware()


def _make_context(tool_name="test_tool", arguments=None):
    """為 on_call_tool 建立最小化的 MiddlewareContext mock。"""
    ctx = MagicMock()
    ctx.message.name = tool_name
    ctx.message.arguments = arguments or {}
    return ctx


@pytest.mark.asyncio
async def test_normal_call_passes_through(middleware):
    """當未發生錯誤時，工具結果應原樣傳遞。"""
    expected = MagicMock()
    call_next = AsyncMock(return_value=expected)
    ctx = _make_context()

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is expected
    call_next.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
async def test_timeout_returns_structured_result(middleware):
    """應攔截 TimeoutError 並轉換為結構化 JSON 結果。"""
    call_next = AsyncMock(side_effect=TimeoutError("Run did not complete within 3600 seconds"))
    ctx = _make_context(
        tool_name="wait_for_run",
        arguments={"run_id": 42, "timeout": 3600},
    )

    result = await middleware.on_call_tool(ctx, call_next)

    # 應回傳 ToolResult，而不是拋出例外
    assert result is not None
    assert len(result.content) == 1

    payload = json.loads(result.content[0].text)
    assert payload["timed_out"] is True
    assert payload["tool"] == "wait_for_run"
    assert payload["arguments"] == {"run_id": 42, "timeout": 3600}
    assert "3600 seconds" in payload["message"]
    assert "Do NOT retry" in payload["action_required"]


@pytest.mark.asyncio
async def test_non_timeout_exceptions_propagate(middleware):
    """非逾時例外不應被攔截，而是正常向外傳播。"""
    call_next = AsyncMock(side_effect=ValueError("bad input"))
    ctx = _make_context()

    with pytest.raises(ValueError, match="bad input"):
        await middleware.on_call_tool(ctx, call_next)


@pytest.mark.asyncio
async def test_timeout_preserves_arguments(middleware):
    """結構化結果應包含原始 arguments 以利除錯。"""
    call_next = AsyncMock(side_effect=TimeoutError("timed out"))
    args = {"pipeline_id": "abc-123", "update_id": "upd-456", "timeout": 1800}
    ctx = _make_context(
        tool_name="wait_for_pipeline_update",
        arguments=args,
    )

    result = await middleware.on_call_tool(ctx, call_next)
    payload = json.loads(result.content[0].text)

    assert payload["arguments"] == args
    assert payload["tool"] == "wait_for_pipeline_update"
