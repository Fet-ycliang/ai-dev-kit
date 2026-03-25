"""
Databricks MCP Server 的中介層。

提供逾時處理等橫切關注點，套用於所有 MCP 工具呼叫。
"""

import json
import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext, CallNext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams, TextContent

logger = logging.getLogger(__name__)


class TimeoutHandlingMiddleware(Middleware):
    """攔截任何工具拋出的 TimeoutError，並回傳結構化結果。

    當非同步作業（job 執行、pipeline 更新、資源佈建）
    超過逾時限制時，此 middleware 會將例外轉成 JSON
    回應，告知代理操作仍在進行中，
    且不應盲目重試。

    若沒有這個 middleware，TimeoutError 會向上冒泡成為 MCP 錯誤，
    而代理會將其解讀為失敗並重試——可能因此建立
    重複資源（見 GitHub issue #65）。
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except TimeoutError as e:
            tool_name = context.message.name
            arguments = context.message.arguments

            logger.warning(
                "Tool '%s' timed out. Returning structured result instead of error.",
                tool_name,
            )

            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "timed_out": True,
                                "tool": tool_name,
                                "arguments": arguments,
                                "message": str(e),
                                "action_required": (
                                    "Operation may still be in progress. "
                                    "Do NOT retry the same call. "
                                    "Use the appropriate get/status tool to check current state."
                                ),
                            }
                        ),
                    )
                ]
            )
