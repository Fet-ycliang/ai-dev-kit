"""
Unity Catalog - Grant 作業

用於管理 Unity Catalog securable 物件權限的函式。
"""

from typing import Any, Dict, List, Optional
from databricks.sdk.service.catalog import (
    Privilege,
    PermissionsChange,
)

from ..auth import get_workspace_client


def _parse_securable_type(securable_type: str) -> str:
    """將 securable type 字串解析為 API 預期的字串值。

    GrantsAPI 方法預期 securable_type 為一般字串，
    而不是 SecurableType enum instance。
    """
    valid_types = {
        "catalog",
        "schema",
        "table",
        "volume",
        "function",
        "storage_credential",
        "external_location",
        "connection",
        "share",
        "metastore",
    }
    key = securable_type.lower().replace("-", "_").replace(" ", "_")
    if key not in valid_types:
        raise ValueError(f"無效的 securable_type：'{securable_type}'。有效類型：{sorted(valid_types)}")
    return key


def _parse_privileges(privileges: List[str]) -> List[Privilege]:
    """將 privilege 字串解析為 SDK enum 值。"""
    result = []
    for p in privileges:
        try:
            result.append(Privilege(p.upper().replace(" ", "_")))
        except ValueError:
            raise ValueError(
                f"無效的 privilege：'{p}'。"
                f"常見 privilege：SELECT, MODIFY, CREATE_TABLE, CREATE_SCHEMA, "
                f"USE_CATALOG, USE_SCHEMA, ALL_PRIVILEGES, EXECUTE, "
                f"READ_VOLUME, WRITE_VOLUME, CREATE_VOLUME, CREATE_FUNCTION"
            )
    return result


def grant_privileges(
    securable_type: str,
    full_name: str,
    principal: str,
    privileges: List[str],
) -> Dict[str, Any]:
    """
    將 privilege 授與 principal，套用至 UC securable。

    參數:
        securable_type: 物件類型（catalog、schema、table、volume、function、
            storage_credential、external_location、connection、share）
        full_name: securable 物件的完整名稱
        principal: 要授與的 user、group 或 service principal
        privileges: 要授與的 privilege 清單（例如 ["SELECT", "MODIFY"]）

    回傳:
        包含 privilege 指派結果的 Dict

    引發:
        ValueError: 如果 securable_type 或 privileges 無效
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)
    privs = _parse_privileges(privileges)

    result = w.grants.update(
        securable_type=stype,
        full_name=full_name,
        changes=[
            PermissionsChange(
                principal=principal,
                add=privs,
            )
        ],
    )
    return {
        "status": "granted",
        "securable_type": securable_type,
        "full_name": full_name,
        "principal": principal,
        "privileges": privileges,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def revoke_privileges(
    securable_type: str,
    full_name: str,
    principal: str,
    privileges: List[str],
) -> Dict[str, Any]:
    """
    從 principal 撤銷套用於 UC securable 的 privilege。

    參數:
        securable_type: 物件類型（catalog、schema、table、volume、function、
            storage_credential、external_location、connection、share）
        full_name: securable 物件的完整名稱
        principal: 要撤銷的 user、group 或 service principal
        privileges: 要撤銷的 privilege 清單（例如 ["SELECT", "MODIFY"]）

    回傳:
        包含撤銷結果的 Dict

    引發:
        ValueError: 如果 securable_type 或 privileges 無效
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)
    privs = _parse_privileges(privileges)

    result = w.grants.update(
        securable_type=stype,
        full_name=full_name,
        changes=[
            PermissionsChange(
                principal=principal,
                remove=privs,
            )
        ],
    )
    return {
        "status": "revoked",
        "securable_type": securable_type,
        "full_name": full_name,
        "principal": principal,
        "privileges": privileges,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def get_grants(
    securable_type: str,
    full_name: str,
    principal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    取得 UC securable 目前的權限授與。

    參數:
        securable_type: 物件類型
        full_name: securable 物件的完整名稱
        principal: 可選 - 篩選特定 principal 的授與

    回傳:
        包含 privilege assignments 清單的 Dict

    引發:
        ValueError: 如果 securable_type 無效
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)

    result = w.grants.get(
        securable_type=stype,
        full_name=full_name,
        principal=principal,
    )
    return {
        "securable_type": securable_type,
        "full_name": full_name,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def get_effective_grants(
    securable_type: str,
    full_name: str,
    principal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    取得 UC securable 的有效權限授與（繼承 + 直接）。

    參數:
        securable_type: 物件類型
        full_name: securable 物件的完整名稱
        principal: 可選 - 篩選特定 principal 的授與

    回傳:
        包含有效 privilege assignments 的 Dict（含繼承權限）

    引發:
        ValueError: 如果 securable_type 無效
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)

    result = w.grants.get_effective(
        securable_type=stype,
        full_name=full_name,
        principal=principal,
    )
    return {
        "securable_type": securable_type,
        "full_name": full_name,
        "effective_assignments": [
            {
                "principal": a.principal,
                "privileges": [
                    {
                        "privilege": p.privilege.value if p.privilege else None,
                        "inherited_from_name": p.inherited_from_name,
                        "inherited_from_type": p.inherited_from_type.value if p.inherited_from_type else None,
                    }
                    for p in (a.privileges or [])
                ],
            }
            for a in (result.privilege_assignments or [])
        ],
    }
