"""Lakebase 工具 - 管理 Lakebase 資料庫（Provisioned 與 Autoscaling）。

提供 8 個高階工作流程工具，封裝細粒度的 databricks-tools-core
函式，並遵循 pipelines 的 create_or_update 模式。
"""

import logging
from typing import Any, Dict, List, Optional

# Provisioned 核心函式
from databricks_tools_core.lakebase import (
    create_lakebase_instance as _create_instance,
    get_lakebase_instance as _get_instance,
    list_lakebase_instances as _list_instances,
    update_lakebase_instance as _update_instance,
    delete_lakebase_instance as _delete_instance,
    generate_lakebase_credential as _generate_provisioned_credential,
    create_lakebase_catalog as _create_catalog,
    get_lakebase_catalog as _get_catalog,
    delete_lakebase_catalog as _delete_catalog,
    create_synced_table as _create_synced_table,
    get_synced_table as _get_synced_table,
    delete_synced_table as _delete_synced_table,
)

# Autoscale 核心函式
from databricks_tools_core.lakebase_autoscale import (
    create_project as _create_project,
    get_project as _get_project,
    list_projects as _list_projects,
    update_project as _update_project,
    delete_project as _delete_project,
    create_branch as _create_branch,
    list_branches as _list_branches,
    update_branch as _update_branch,
    delete_branch as _delete_branch,
    create_endpoint as _create_endpoint,
    list_endpoints as _list_endpoints,
    update_endpoint as _update_endpoint,
    generate_credential as _generate_autoscale_credential,
)

from ..server import mcp

logger = logging.getLogger(__name__)


# ============================================================================
# 輔助函式
# ============================================================================


def _find_instance_by_name(name: str) -> Optional[Dict[str, Any]]:
    """依名稱尋找 provisioned instance，若找不到則回傳 None。"""
    try:
        return _get_instance(name=name)
    except Exception:
        return None


def _find_project_by_name(name: str) -> Optional[Dict[str, Any]]:
    """依名稱尋找 autoscale project，若找不到則回傳 None。"""
    try:
        return _get_project(name=name)
    except Exception:
        return None


def _find_branch(project_name: str, branch_id: str) -> Optional[Dict[str, Any]]:
    """在 project 中尋找 branch，若找不到則回傳 None。"""
    try:
        branches = _list_branches(project_name=project_name)
        for branch in branches:
            branch_name = branch.get("name", "")
            if branch_name.endswith(f"/branches/{branch_id}"):
                return branch
    except Exception:
        pass
    return None


# ============================================================================
# 工具 1: create_or_update_lakebase_database
# ============================================================================


@mcp.tool
def create_or_update_lakebase_database(
    name: str,
    type: str = "provisioned",
    capacity: str = "CU_1",
    stopped: bool = False,
    display_name: Optional[str] = None,
    pg_version: str = "17",
) -> Dict[str, Any]:
    """
    建立或更新 Lakebase 受管 PostgreSQL 資料庫。

    依名稱尋找現有資料庫並更新，或建立新的資料庫。
    對於 autoscale，新的 project 會自動包含 production branch、預設 compute，
    以及 databricks_postgres 資料庫。

    參數:
        name: 資料庫名稱（1-63 個字元，小寫字母、數字、連字號）
        type: "provisioned"（固定容量）或 "autoscale"（自動擴縮 compute）
        capacity: Provisioned compute："CU_1"、"CU_2"、"CU_4" 或 "CU_8"
        stopped: 若為 True，則以 stopped 狀態建立 provisioned instance
        display_name: Autoscale 顯示名稱（預設為 name）
        pg_version: Autoscale Postgres 版本："16" 或 "17"

    回傳:
        包含資料庫詳細資訊、狀態與連線資訊的字典。
    """
    db_type = type.lower()

    if db_type == "provisioned":
        existing = _find_instance_by_name(name)
        if existing:
            result = _update_instance(name=name, capacity=capacity, stopped=stopped)
            return {**result, "created": False, "type": "provisioned"}
        else:
            result = _create_instance(name=name, capacity=capacity, stopped=stopped)
            try:
                from ..manifest import track_resource

                track_resource(resource_type="lakebase_instance", name=name, resource_id=name)
            except Exception:
                pass
            return {**result, "created": True, "type": "provisioned"}

    elif db_type == "autoscale":
        existing = _find_project_by_name(name)
        if existing:
            result = _update_project(name=name, display_name=display_name)
            return {**result, "created": False, "type": "autoscale"}
        else:
            result = _create_project(
                project_id=name,
                display_name=display_name,
                pg_version=pg_version,
            )
            try:
                from ..manifest import track_resource

                track_resource(resource_type="lakebase_project", name=name, resource_id=name)
            except Exception:
                pass
            return {**result, "created": True, "type": "autoscale"}

    else:
        return {"error": f"Invalid type '{type}'. Use 'provisioned' or 'autoscale'."}


# ============================================================================
# 工具 2: get_lakebase_database
# ============================================================================


@mcp.tool
def get_lakebase_database(
    name: Optional[str] = None,
    type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    取得 Lakebase 資料庫詳細資訊，或列出所有資料庫。

    傳入 name 可取得單一資料庫的詳細資訊（對 autoscale 也包含 branches、
    endpoints）。省略 name 則列出所有資料庫。

    參數:
        name: 資料庫名稱。若省略則列出所有資料庫。
        type: 依 "provisioned" 或 "autoscale" 篩選。若省略則兩者都會檢查。

    回傳:
        若提供 name，則回傳單一資料庫 dict；否則回傳 {"databases": [...]}。
    """
    if name:
        result = None
        if type is None or type.lower() == "provisioned":
            result = _find_instance_by_name(name)
            if result:
                result["type"] = "provisioned"

        if result is None and (type is None or type.lower() == "autoscale"):
            result = _find_project_by_name(name)
            if result:
                result["type"] = "autoscale"
                try:
                    result["branches"] = _list_branches(project_name=name)
                except Exception:
                    pass
                try:
                    for branch in result.get("branches", []):
                        branch_name = branch.get("name", "")
                        branch["endpoints"] = _list_endpoints(branch_name=branch_name)
                except Exception:
                    pass

        if result is None:
            return {"error": f"Database '{name}' not found."}
        return result

    # 列出所有資料庫
    databases = []

    if type is None or type.lower() == "provisioned":
        try:
            for inst in _list_instances():
                inst["type"] = "provisioned"
                databases.append(inst)
        except Exception as e:
            logger.warning("Failed to list provisioned instances: %s", e)

    if type is None or type.lower() == "autoscale":
        try:
            for proj in _list_projects():
                proj["type"] = "autoscale"
                databases.append(proj)
        except Exception as e:
            logger.warning("Failed to list autoscale projects: %s", e)

    return {"databases": databases}


# ============================================================================
# 工具 3: delete_lakebase_database
# ============================================================================


@mcp.tool
def delete_lakebase_database(
    name: str,
    type: str = "provisioned",
    force: bool = False,
) -> Dict[str, Any]:
    """
    刪除 Lakebase 資料庫及其資源。

    對於 provisioned：刪除 instance（使用 force=True 以級聯刪除子資源）。
    對於 autoscale：刪除 project 及所有 branches、computes 與資料。

    參數:
        name: 要刪除的資料庫名稱
        type: "provisioned" 或 "autoscale"
        force: 若為 True，則強制刪除子資源（僅 provisioned）

    回傳:
        包含名稱與刪除狀態的字典。
    """
    db_type = type.lower()

    if db_type == "provisioned":
        return _delete_instance(name=name, force=force, purge=True)
    elif db_type == "autoscale":
        return _delete_project(name=name)
    else:
        return {"error": f"Invalid type '{type}'. Use 'provisioned' or 'autoscale'."}


# ============================================================================
# 工具 4: create_or_update_lakebase_branch
# ============================================================================


@mcp.tool
def create_or_update_lakebase_branch(
    project_name: str,
    branch_id: str,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
    is_protected: Optional[bool] = None,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    建立或更新 Lakebase Autoscale branch 及其 compute 端點。

    Branch 是使用 copy-on-write 儲存的隔離資料庫環境。
    若 branch 已存在，則更新其設定；否則建立新的 branch，
    並在其上建立 compute 端點。

    參數:
        project_name: Project 名稱（例如 "my-app" 或 "projects/my-app"）
        branch_id: Branch 識別碼（1-63 個字元，小寫字母、數字、連字號）
        source_branch: 要 fork 的來源 branch（預設：production）
        ttl_seconds: 存活時間（秒）（上限 30 天 = 2592000 秒）
        no_expiry: 若為 True，則 branch 永不過期
        is_protected: 若為 True，則 branch 不可刪除
        endpoint_type: "ENDPOINT_TYPE_READ_WRITE" 或 "ENDPOINT_TYPE_READ_ONLY"
        autoscaling_limit_min_cu: 最小 compute units（0.5-32）
        autoscaling_limit_max_cu: 最大 compute units（0.5-112）
        scale_to_zero_seconds: 因閒置而暫停前的逾時秒數（0 表示停用）

    回傳:
        包含 branch 詳細資訊與端點連線資訊的字典。
    """
    existing = _find_branch(project_name, branch_id)

    if existing:
        branch_name = existing.get("name", f"{project_name}/branches/{branch_id}")
        branch_result = _update_branch(
            name=branch_name,
            is_protected=is_protected,
            ttl_seconds=ttl_seconds,
            no_expiry=no_expiry if no_expiry else None,
        )

        # 若提供縮放參數則更新端點
        endpoint_result = None
        if any(v is not None for v in [autoscaling_limit_min_cu, autoscaling_limit_max_cu, scale_to_zero_seconds]):
            try:
                endpoints = _list_endpoints(branch_name=branch_name)
                if endpoints:
                    ep_name = endpoints[0].get("name", "")
                    endpoint_result = _update_endpoint(
                        name=ep_name,
                        autoscaling_limit_min_cu=autoscaling_limit_min_cu,
                        autoscaling_limit_max_cu=autoscaling_limit_max_cu,
                        scale_to_zero_seconds=scale_to_zero_seconds,
                    )
            except Exception as e:
                logger.warning("Failed to update endpoint: %s", e)

        result = {**branch_result, "created": False}
        if endpoint_result:
            result["endpoint"] = endpoint_result
        return result

    else:
        branch_result = _create_branch(
            project_name=project_name,
            branch_id=branch_id,
            source_branch=source_branch,
            ttl_seconds=ttl_seconds,
            no_expiry=no_expiry,
        )

        # 在新 branch 上建立 compute 端點
        branch_name = branch_result.get("name", f"{project_name}/branches/{branch_id}")
        endpoint_result = None
        try:
            endpoint_result = _create_endpoint(
                branch_name=branch_name,
                endpoint_id=f"{branch_id}-ep",
                endpoint_type=endpoint_type,
                autoscaling_limit_min_cu=autoscaling_limit_min_cu,
                autoscaling_limit_max_cu=autoscaling_limit_max_cu,
                scale_to_zero_seconds=scale_to_zero_seconds,
            )
        except Exception as e:
            logger.warning("Failed to create endpoint on branch: %s", e)

        result = {**branch_result, "created": True}
        if endpoint_result:
            result["endpoint"] = endpoint_result
        return result


# ============================================================================
# 工具 5: delete_lakebase_branch
# ============================================================================


@mcp.tool
def delete_lakebase_branch(name: str) -> Dict[str, Any]:
    """
    刪除 Lakebase Autoscale branch 及其 compute 端點。

    該 branch 的資料、資料庫、roles 與 computes 會被永久刪除。
    無法刪除受保護的 branches 或具有子項的 branches。

    參數:
        name: Branch 資源名稱
            （例如 "projects/my-app/branches/development"）

    回傳:
        包含名稱與刪除狀態的字典。
    """
    return _delete_branch(name=name)


# ============================================================================
# 工具 6: create_or_update_lakebase_sync
# ============================================================================


@mcp.tool
def create_or_update_lakebase_sync(
    instance_name: str,
    source_table_name: str,
    target_table_name: str,
    catalog_name: Optional[str] = None,
    database_name: str = "databricks_postgres",
    primary_key_columns: Optional[List[str]] = None,
    scheduling_policy: str = "TRIGGERED",
) -> Dict[str, Any]:
    """
    設定從 Delta table 到 Lakebase 的 reverse ETL。

    確保 UC catalog 註冊存在後，再建立 synced table，
    將資料從 Lakehouse 複寫到 PostgreSQL。

    參數:
        instance_name: Lakebase instance 名稱
        source_table_name: 來源 Delta table（catalog.schema.table）
        target_table_name: Lakebase 中的目標資料表（catalog.schema.table）
        catalog_name: 此 Lakebase instance 的 UC catalog 名稱。
            若省略，則從 target_table_name 推導。
        database_name: PostgreSQL 資料庫名稱（預設："databricks_postgres"）
        primary_key_columns: 主鍵欄位（預設使用來源資料表的 PK）
        scheduling_policy: "TRIGGERED"、"SNAPSHOT" 或 "CONTINUOUS"

    回傳:
        包含 catalog 與 synced table 詳細資訊的字典。
    """
    # 若未提供，則從 target_table_name 推導 catalog 名稱
    if not catalog_name:
        parts = target_table_name.split(".")
        if len(parts) >= 1:
            catalog_name = parts[0]
        else:
            return {"error": "Cannot derive catalog_name from target_table_name. Provide catalog_name explicitly."}

    # 確保 catalog 註冊存在
    catalog_result = None
    try:
        catalog_result = _get_catalog(name=catalog_name)
    except Exception:
        try:
            catalog_result = _create_catalog(
                name=catalog_name,
                instance_name=instance_name,
                database_name=database_name,
            )
        except Exception as e:
            return {"error": f"Failed to create catalog '{catalog_name}': {e}"}

    # 檢查 synced table 是否已存在
    try:
        existing = _get_synced_table(table_name=target_table_name)
        return {
            "catalog": catalog_result,
            "synced_table": existing,
            "created": False,
        }
    except Exception:
        pass

    # 建立 synced table
    sync_result = _create_synced_table(
        instance_name=instance_name,
        source_table_name=source_table_name,
        target_table_name=target_table_name,
        primary_key_columns=primary_key_columns,
        scheduling_policy=scheduling_policy,
    )

    return {
        "catalog": catalog_result,
        "synced_table": sync_result,
        "created": True,
    }


# ============================================================================
# 工具 7: delete_lakebase_sync
# ============================================================================


@mcp.tool
def delete_lakebase_sync(
    table_name: str,
    catalog_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    移除 Lakebase synced table，並可選擇移除其 UC catalog 註冊。

    來源 Delta table 不受影響。

    參數:
        table_name: 完整限定的 synced table 名稱（catalog.schema.table）
        catalog_name: 要一併移除的 UC catalog。若省略，則只刪除
            synced table。

    回傳:
        包含 synced table 與 catalog 刪除狀態的字典。
    """
    result = {}

    sync_result = _delete_synced_table(table_name=table_name)
    result["synced_table"] = sync_result

    if catalog_name:
        try:
            catalog_result = _delete_catalog(name=catalog_name)
            result["catalog"] = catalog_result
        except Exception as e:
            result["catalog"] = {"error": str(e)}

    return result


# ============================================================================
# 工具 8: generate_lakebase_credential
# ============================================================================


@mcp.tool
def generate_lakebase_credential(
    instance_names: Optional[List[str]] = None,
    endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    產生用於連線 Lakebase 資料庫的 OAuth token。

    Provisioned 資料庫請提供 instance_names，autoscale 請提供 endpoint。
    權杖約可使用 1 小時。請在 PostgreSQL connection strings 中搭配
    sslmode=require 作為 password 使用。

    參數:
        instance_names: 要產生憑證的 Provisioned instance 名稱
        endpoint: Autoscale 端點資源名稱
            （例如 "projects/my-app/branches/production/endpoints/ep-primary"）

    回傳:
        包含 OAuth token 與使用說明的字典。
    """
    if instance_names:
        return _generate_provisioned_credential(instance_names=instance_names)
    elif endpoint:
        return _generate_autoscale_credential(endpoint=endpoint)
    else:
        return {"error": "Provide either instance_names (provisioned) or endpoint (autoscale)."}
