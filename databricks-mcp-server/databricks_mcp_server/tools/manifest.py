"""資源追蹤 manifest 工具。

將資源 manifest 透過 MCP 工具公開，讓代理程式可以列出並清理
跨工作階段建立的資源。
"""

import logging
from typing import Any, Dict, Optional

from ..manifest import _RESOURCE_DELETERS, list_resources, remove_resource
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_from_databricks(resource_type: str, resource_id: str) -> Optional[str]:
    """使用已註冊的 deleter 從 Databricks 刪除資源。

    成功時回傳 None，失敗時回傳錯誤字串。
    """
    deleter = _RESOURCE_DELETERS.get(resource_type)
    if not deleter:
        return f"Unsupported resource type for deletion: {resource_type}"
    try:
        deleter(resource_id)
        return None
    except Exception as exc:
        return str(exc)


@mcp.tool
def list_tracked_resources(type: Optional[str] = None) -> Dict[str, Any]:
    """
    列出專案 manifest 中追蹤的資源。

    manifest 會記錄所有透過 MCP server 建立的資源
    （dashboards、jobs、pipelines、Genie spaces、KAs、MAS、schemas、volumes 等）。
    可用此查看跨工作階段建立的內容。

    參數:
        type: 依資源類型進行選用過濾。可為："dashboard", "job",
            "pipeline", "genie_space", "knowledge_assistant",
            "multi_agent_supervisor", "catalog", "schema", "volume"。
            若未提供，則回傳所有追蹤中的資源。

    回傳:
        包含下列內容的 dictionary：
        - resources: 追蹤中的資源清單（type、name、id、url、timestamps）
        - count: 回傳的資源數量
    """
    resources = list_resources(resource_type=type)
    return {
        "resources": resources,
        "count": len(resources),
    }


@mcp.tool
def delete_tracked_resource(
    type: str,
    resource_id: str,
    delete_from_databricks: bool = False,
) -> Dict[str, Any]:
    """
    從專案 manifest 刪除資源，並可選擇同時從 Databricks 刪除。

    可用此清理開發／測試期間建立的資源。

    參數:
        type: 資源類型（例如 "dashboard", "job", "pipeline", "genie_space",
            "knowledge_assistant", "multi_agent_supervisor", "catalog", "schema", "volume"）
        resource_id: 資源 ID（如 list_tracked_resources 中所示）
        delete_from_databricks: 若為 True，會先從 Databricks 刪除資源，
            再從 manifest 移除。預設：False（僅移除 manifest）。

    回傳:
        包含下列內容的 dictionary：
        - success: 作業是否成功
        - removed_from_manifest: 是否找到並從 manifest 移除該資源
        - deleted_from_databricks: 是否已從 Databricks 刪除該資源
        - error: 若刪除失敗則為錯誤訊息
    """
    result: Dict[str, Any] = {
        "success": True,
        "removed_from_manifest": False,
        "deleted_from_databricks": False,
        "error": None,
    }

    # 可選擇先從 Databricks 刪除
    if delete_from_databricks:
        error = _delete_from_databricks(type, resource_id)
        if error:
            result["error"] = f"Databricks deletion failed: {error}"
            result["success"] = False
            # 即使 Databricks 刪除失敗，仍從 manifest 移除
        else:
            result["deleted_from_databricks"] = True

    # 從 manifest 移除
    removed = remove_resource(resource_type=type, resource_id=resource_id)
    result["removed_from_manifest"] = removed

    if not removed and not result.get("error"):
        result["error"] = f"Resource {type}/{resource_id} not found in manifest"
        result["success"] = result.get("deleted_from_databricks", False)

    return result
