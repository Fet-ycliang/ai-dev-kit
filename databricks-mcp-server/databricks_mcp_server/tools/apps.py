"""App 工具 - 管理 Databricks Apps 生命週期。

提供 3 個以工作流程為導向的工具，遵循 Lakebase 模式：
- create_or_update_app：冪等建立 + 選擇性部署
- get_app：依名稱取得詳細資訊（可選擇包含 logs），或列出全部
- delete_app：依名稱刪除
"""

import logging
from typing import Any, Dict, Optional

from databricks_tools_core.apps.apps import (
    create_app as _create_app,
    get_app as _get_app,
    list_apps as _list_apps,
    deploy_app as _deploy_app,
    delete_app as _delete_app,
    get_app_logs as _get_app_logs,
)
from databricks_tools_core.identity import with_description_footer

from ..manifest import register_deleter
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_app_resource(resource_id: str) -> None:
    _delete_app(name=resource_id)


register_deleter("app", _delete_app_resource)


# ============================================================================
# 輔助函式
# ============================================================================


def _find_app_by_name(name: str) -> Optional[Dict[str, Any]]:
    """依名稱尋找 app，若找不到則回傳 None。"""
    try:
        result = _get_app(name=name)
        if result.get("error"):
            return None
        return result
    except Exception:
        return None


# ============================================================================
# 工具 1: create_or_update_app
# ============================================================================


@mcp.tool
def create_or_update_app(
    name: str,
    source_code_path: Optional[str] = None,
    description: Optional[str] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    若 Databricks App 不存在則建立，並可選擇部署它。

    若 app 已存在且提供 source_code_path，則會部署最新程式碼。
    這是標準工作流程：「讓這個 app 存在，
    並執行最新程式碼。」

    參數:
        name: App 名稱（在 workspace 內必須唯一）。
        source_code_path: 要部署的 Workspace 路徑
            （例如 /Workspace/Users/user@example.com/my_app）。
            若有提供，則在建立或找到後進行部署。
        description: 選用的人類可讀描述（僅在建立時使用）。
        mode: 選用的部署模式（例如 "snapshot"）。

    回傳:
        包含以下內容的字典：
        - name: App 名稱
        - created: 若為新建立則為 True，若原本已存在則為 False
        - url: App URL
        - status: App 狀態
        - deployment: 部署詳細資訊（若提供 source_code_path）

    範例:
        >>> create_or_update_app("my-app", "/Workspace/Users/me/my_app")
        {"name": "my-app", "created": True, "url": "...", "deployment": {...}}
    """
    existing = _find_app_by_name(name)

    if existing:
        result = {**existing, "created": False}
    else:
        app_result = _create_app(name=name, description=with_description_footer(description))
        result = {**app_result, "created": True}

        # 在成功建立時追蹤資源
        try:
            if result.get("name"):
                from ..manifest import track_resource

                track_resource(
                    resource_type="app",
                    name=result["name"],
                    resource_id=result["name"],
                )
        except Exception:
            pass  # 盡力追蹤

    # 若提供 source_code_path 則部署
    if source_code_path:
        try:
            deployment = _deploy_app(
                app_name=name,
                source_code_path=source_code_path,
                mode=mode,
            )
            result["deployment"] = deployment
        except Exception as e:
            logger.warning("Failed to deploy app '%s': %s", name, e)
            result["deployment_error"] = str(e)

    return result


# ============================================================================
# 工具 2: get_app
# ============================================================================


@mcp.tool
def get_app(
    name: Optional[str] = None,
    name_contains: Optional[str] = None,
    include_logs: bool = False,
    deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    依名稱取得 app 詳細資訊，或列出所有 apps。

    傳入 name 可取得單一 app 的詳細資訊（可選擇包含最近 logs）。
    省略 name 則列出所有 apps（可選擇使用 name_contains 篩選）。

    參數:
        name: App 名稱。若提供，則回傳詳細 app 資訊。
        name_contains: 依名稱子字串篩選 apps（用於列出時）。
        include_logs: 若為 True 且提供 name，則包含部署 logs。
        deployment_id: logs 專用的特定 deployment ID。若省略，
            則使用作用中的 deployment。

    回傳:
        若提供 name，則回傳單一 app dict；否則回傳 {"apps": [...]}。

    範例:
        >>> get_app("my-app")
        {"name": "my-app", "url": "...", "status": "RUNNING", ...}
        >>> get_app("my-app", include_logs=True)
        {"name": "my-app", ..., "logs": "..."}
        >>> get_app()
        {"apps": [{"name": "my-app", ...}, ...]}
    """
    if name:
        result = _get_app(name=name)

        if include_logs:
            try:
                logs = _get_app_logs(
                    app_name=name,
                    deployment_id=deployment_id,
                )
                result["logs"] = logs.get("logs", "")
                result["logs_deployment_id"] = logs.get("deployment_id")
            except Exception as e:
                result["logs_error"] = str(e)

        return result

    return {"apps": _list_apps(name_contains=name_contains)}


# ============================================================================
# 工具 3: delete_app
# ============================================================================


@mcp.tool
def delete_app(name: str) -> Dict[str, str]:
    """
    刪除 Databricks App。

    參數:
        name: 要刪除的 App 名稱。

    回傳:
        確認刪除結果的字典。
    """
    result = _delete_app(name=name)

    # 從已追蹤資源中移除
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="app", resource_id=name)
    except Exception:
        pass  # 盡力追蹤

    return result
