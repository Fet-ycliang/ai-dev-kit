"""
Lakebase Autoscaling 分支操作

用於在 Lakebase Autoscaling 專案中建立、管理與刪除分支的函式。
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_branch(
    project_name: str,
    branch_id: str,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
) -> Dict[str, Any]:
    """
    在 Lakebase Autoscaling 專案中建立分支。

    參數:
        project_name: 專案資源名稱（例如："projects/my-app"）
        branch_id: 分支識別子（1-63 個字元，限小寫字母、數字與連字號）
        source_branch: 要分岔的來源分支。若未指定，
            會自動使用專案的預設分支。
        ttl_seconds: 存活時間（秒）（最長 30 天 = 2592000 秒）。
            設定後可建立會過期的分支。
        no_expiry: 若為 True，分支永不過期。ttl_seconds
            或 no_expiry 必須指定其一。

    回傳:
        包含以下欄位的字典：
        - name: 分支資源名稱
        - status: 建立狀態
        - expire_time: 到期時間（若有設定 TTL）

    引發:
        Exception: 當建立失敗時
    """
    client = get_workspace_client()

    if not project_name.startswith("projects/"):
        project_name = f"projects/{project_name}"

    # 解析來源分支：使用傳入值，或找出預設分支
    if source_branch is None:
        branches = list_branches(project_name)
        default_branches = [b for b in branches if b.get("is_default") is True]
        if default_branches:
            source_branch = default_branches[0]["name"]
        elif branches:
            source_branch = branches[0]["name"]
        else:
            raise Exception(f"在專案 '{project_name}' 中找不到可供分岔的分支")

    try:
        from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

        spec_kwargs: Dict[str, Any] = {
            "source_branch": source_branch,
        }

        if ttl_seconds is not None:
            spec_kwargs["ttl"] = Duration(seconds=ttl_seconds)
        elif no_expiry:
            spec_kwargs["no_expiry"] = True
        else:
            # 若兩者皆未指定，預設為永不過期
            spec_kwargs["no_expiry"] = True

        operation = client.postgres.create_branch(
            parent=project_name,
            branch=Branch(spec=BranchSpec(**spec_kwargs)),
            branch_id=branch_id,
        )
        result_branch = operation.wait()

        result: Dict[str, Any] = {
            "name": result_branch.name,
            "status": "CREATED",
        }

        if result_branch.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("default", "is_default", None),
                ("is_protected", "is_protected", None),
                ("expire_time", "expire_time", str),
                ("logical_size_bytes", "logical_size_bytes", None),
            ]:
                try:
                    val = getattr(result_branch.status, attr)
                    if val is not None:
                        result[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"{project_name}/branches/{branch_id}",
                "status": "ALREADY_EXISTS",
                "error": f"分支 '{branch_id}' 已存在",
            }
        raise Exception(f"建立分支 '{branch_id}' 失敗：{error_msg}")


def get_branch(name: str) -> Dict[str, Any]:
    """
    取得 Lakebase Autoscaling 分支詳細資料。

    參數:
        name: 分支資源名稱
            （例如："projects/my-app/branches/production"）

    回傳:
        包含以下欄位的字典：
        - name: 分支資源名稱
        - state: 目前狀態
        - is_default: 是否為預設分支
        - is_protected: 分支是否受保護
        - expire_time: 到期時間（若有設定）
        - logical_size_bytes: 邏輯資料大小

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        branch = client.postgres.get_branch(name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"找不到分支 '{name}'",
            }
        raise Exception(f"取得分支 '{name}' 失敗：{error_msg}")

    result: Dict[str, Any] = {"name": branch.name}

    if branch.status:
        for attr, key, transform in [
            ("current_state", "state", str),
            ("default", "is_default", None),
            ("is_protected", "is_protected", None),
            ("expire_time", "expire_time", str),
            ("logical_size_bytes", "logical_size_bytes", None),
            ("parent_name", "parent_name", None),
        ]:
            try:
                val = getattr(branch.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

    return result


def list_branches(project_name: str) -> List[Dict[str, Any]]:
    """
    列出 Lakebase Autoscaling 專案中的所有分支。

    參數:
        project_name: 專案資源名稱（例如："projects/my-app"）

    回傳:
        包含 name、state、is_default、is_protected 的分支字典清單。

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    if not project_name.startswith("projects/"):
        project_name = f"projects/{project_name}"

    try:
        response = client.postgres.list_branches(parent=project_name)
    except Exception as e:
        raise Exception(f"列出 '{project_name}' 的分支失敗：{str(e)}")

    result = []
    branches = list(response) if response else []
    for br in branches:
        entry: Dict[str, Any] = {"name": br.name}

        if br.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("default", "is_default", None),
                ("is_protected", "is_protected", None),
                ("expire_time", "expire_time", str),
            ]:
                try:
                    val = getattr(br.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

        result.append(entry)

    return result


def update_branch(
    name: str,
    is_protected: Optional[bool] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    更新 Lakebase Autoscaling 分支（保護設定或到期設定）。

    參數:
        name: 分支資源名稱
            （例如："projects/my-app/branches/production"）
        is_protected: 設定分支保護狀態
        ttl_seconds: 新的 TTL（秒）（最長 30 天）
        no_expiry: 若為 True，移除到期設定

    回傳:
        包含更新後分支詳細資料的字典

    引發:
        Exception: 當更新失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Branch, BranchSpec, Duration, FieldMask

        spec_kwargs: Dict[str, Any] = {}
        update_fields: list[str] = []

        if is_protected is not None:
            spec_kwargs["is_protected"] = is_protected
            update_fields.append("spec.is_protected")

        if ttl_seconds is not None:
            spec_kwargs["ttl"] = Duration(seconds=ttl_seconds)
            update_fields.append("spec.expiration")
        elif no_expiry is True:
            spec_kwargs["no_expiry"] = True
            update_fields.append("spec.expiration")

        if not update_fields:
            return {
                "name": name,
                "status": "NO_CHANGES",
                "error": "未指定要更新的欄位",
            }

        operation = client.postgres.update_branch(
            name=name,
            branch=Branch(
                name=name,
                spec=BranchSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_branch = operation.wait()

        result: Dict[str, Any] = {
            "name": name,
            "status": "UPDATED",
        }

        if is_protected is not None:
            result["is_protected"] = is_protected

        if result_branch and result_branch.status:
            try:
                if result_branch.status.expire_time:
                    result["expire_time"] = str(result_branch.status.expire_time)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"更新分支 '{name}' 失敗：{str(e)}")


def delete_branch(name: str) -> Dict[str, Any]:
    """
    刪除 Lakebase Autoscaling 分支。

    注意：
        此操作會永久刪除此分支專屬的所有資料庫、角色、compute 與資料。

    參數:
        name: 分支資源名稱
            （例如："projects/my-app/branches/development"）

    回傳:
        包含以下欄位的字典：
        - name: 分支資源名稱
        - status: "deleted" 或錯誤資訊

    引發:
        Exception: 當刪除失敗時
    """
    client = get_workspace_client()

    try:
        operation = client.postgres.delete_branch(name=name)
        operation.wait()
        return {
            "name": name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "status": "NOT_FOUND",
                "error": f"找不到分支 '{name}'",
            }
        raise Exception(f"刪除分支 '{name}' 失敗：{error_msg}")


# 注意：Databricks SDK 尚未提供 reset_branch。
# 未來的 SDK 版本可能會加入。
