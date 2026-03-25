"""
Lakebase Autoscaling 專案操作

用於建立、管理與刪除 Lakebase Autoscaling 專案的函式。
專案是分支、compute、資料庫與角色的最上層容器。
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def _normalize_project_name(name: str) -> str:
    """確保專案名稱具有 'projects/' 前綴。"""
    if not name.startswith("projects/"):
        return f"projects/{name}"
    return name


def create_project(
    project_id: str,
    display_name: Optional[str] = None,
    pg_version: str = "17",
) -> Dict[str, Any]:
    """
    建立 Lakebase Autoscaling 專案。

    參數:
        project_id: 專案識別子（1-63 個字元，限小寫字母、數字與連字號）。
        display_name: 人類可讀的顯示名稱。預設為 project_id。
        pg_version: Postgres 版本（"16" 或 "17"）。預設："17"。

    回傳:
        包含以下欄位的字典：
        - name: 專案資源名稱（projects/{project_id}）
        - display_name: 顯示名稱
        - pg_version: Postgres 版本
        - status: 建立狀態

    引發:
        Exception: 當建立失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Project, ProjectSpec

        spec = ProjectSpec(
            display_name=display_name or project_id,
            pg_version=int(pg_version),
        )

        operation = client.postgres.create_project(
            project=Project(spec=spec),
            project_id=project_id,
        )
        result_project = operation.wait()

        result: Dict[str, Any] = {
            "name": result_project.name,
            "display_name": display_name or project_id,
            "pg_version": pg_version,
            "status": "CREATED",
        }

        if result_project.status:
            try:
                if result_project.status.display_name:
                    result["display_name"] = result_project.status.display_name
            except (KeyError, AttributeError):
                pass
            try:
                if result_project.status.pg_version:
                    result["pg_version"] = str(result_project.status.pg_version)
            except (KeyError, AttributeError):
                pass
            try:
                if result_project.status.state:
                    result["state"] = str(result_project.status.state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"projects/{project_id}",
                "status": "ALREADY_EXISTS",
                "error": f"專案 '{project_id}' 已存在",
            }
        raise Exception(f"建立 Lakebase Autoscaling 專案 '{project_id}' 失敗：{error_msg}")


def get_project(name: str) -> Dict[str, Any]:
    """
    取得 Lakebase Autoscaling 專案詳細資料。

    參數:
        name: 專案資源名稱（例如："projects/my-app" 或 "my-app"）

    回傳:
        包含以下欄位的字典：
        - name: 專案資源名稱
        - display_name: 顯示名稱
        - pg_version: Postgres 版本
        - state: 目前狀態（READY、CREATING 等）

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        project = client.postgres.get_project(name=full_name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": full_name,
                "state": "NOT_FOUND",
                "error": f"找不到專案 '{full_name}'",
            }
        raise Exception(f"取得 Lakebase Autoscaling 專案 '{full_name}' 失敗：{error_msg}")

    result: Dict[str, Any] = {"name": project.name}

    if project.status:
        for attr, key, transform in [
            ("display_name", "display_name", None),
            ("pg_version", "pg_version", str),
            ("owner", "owner", None),
        ]:
            try:
                val = getattr(project.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

    return result


def list_projects() -> List[Dict[str, Any]]:
    """
    列出工作區中所有 Lakebase Autoscaling 專案。

    回傳:
        包含 name、display_name、pg_version、state 的專案字典清單。

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        response = client.postgres.list_projects()
    except Exception as e:
        raise Exception(f"列出 Lakebase Autoscaling 專案失敗：{str(e)}")

    result = []
    projects = list(response) if response else []
    for proj in projects:
        entry: Dict[str, Any] = {"name": proj.name}

        if proj.status:
            for attr, key, transform in [
                ("display_name", "display_name", None),
                ("pg_version", "pg_version", str),
                ("owner", "owner", None),
            ]:
                try:
                    val = getattr(proj.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        result.append(entry)

    return result


def update_project(
    name: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    更新 Lakebase Autoscaling 專案。

    參數:
        name: 專案資源名稱（例如："projects/my-app" 或 "my-app"）
        display_name: 專案的新顯示名稱

    回傳:
        包含更新後專案詳細資料的字典

    引發:
        Exception: 當更新失敗時
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        from databricks.sdk.service.postgres import Project, ProjectSpec, FieldMask

        update_fields = []
        spec_kwargs: Dict[str, Any] = {}

        if display_name is not None:
            spec_kwargs["display_name"] = display_name
            update_fields.append("spec.display_name")

        if not update_fields:
            return {
                "name": full_name,
                "status": "NO_CHANGES",
                "error": "未指定要更新的欄位",
            }

        operation = client.postgres.update_project(
            name=full_name,
            project=Project(
                name=full_name,
                spec=ProjectSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_project = operation.wait()

        result: Dict[str, Any] = {
            "name": full_name,
            "status": "UPDATED",
        }

        if display_name is not None:
            result["display_name"] = display_name

        if result_project and result_project.status:
            try:
                if result_project.status.state:
                    result["state"] = str(result_project.status.state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"更新 Lakebase Autoscaling 專案 '{full_name}' 失敗：{str(e)}")


def delete_project(name: str) -> Dict[str, Any]:
    """
    刪除 Lakebase Autoscaling 專案及其所有資源。

    注意：
        此操作會永久刪除專案中的所有分支、compute、資料庫、角色與資料。

    參數:
        name: 專案資源名稱（例如："projects/my-app" 或 "my-app"）

    回傳:
        包含以下欄位的字典：
        - name: 專案資源名稱
        - status: "deleted" 或錯誤資訊

    引發:
        Exception: 當刪除失敗時
    """
    client = get_workspace_client()
    full_name = _normalize_project_name(name)

    try:
        operation = client.postgres.delete_project(name=full_name)
        operation.wait()
        return {
            "name": full_name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": full_name,
                "status": "NOT_FOUND",
                "error": f"找不到專案 '{full_name}'",
            }
        raise Exception(f"刪除 Lakebase Autoscaling 專案 '{full_name}' 失敗：{error_msg}")
