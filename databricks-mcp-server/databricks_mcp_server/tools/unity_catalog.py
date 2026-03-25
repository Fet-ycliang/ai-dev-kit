"""
Unity Catalog MCP Tools

Consolidated MCP tools for Unity Catalog operations.
8 tools covering: objects, grants, storage, connections,
tags, security policies, monitors, and sharing.
"""

import logging
from typing import Any, Dict, List

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.unity_catalog import (
    # Metric Views
    create_metric_view as _create_metric_view,
    alter_metric_view as _alter_metric_view,
    drop_metric_view as _drop_metric_view,
    describe_metric_view as _describe_metric_view,
    query_metric_view as _query_metric_view,
    grant_metric_view as _grant_metric_view,
)
from databricks_tools_core.unity_catalog import (
    # Catalogs
    list_catalogs as _list_catalogs,
    get_catalog as _get_catalog,
    create_catalog as _create_catalog,
    update_catalog as _update_catalog,
    delete_catalog as _delete_catalog,
    # Schemas
    list_schemas as _list_schemas,
    get_schema as _get_schema,
    create_schema as _create_schema,
    update_schema as _update_schema,
    delete_schema as _delete_schema,
    # Volumes
    list_volumes as _list_volumes,
    get_volume as _get_volume,
    create_volume as _create_volume,
    update_volume as _update_volume,
    delete_volume as _delete_volume,
    # Functions
    list_functions as _list_functions,
    get_function as _get_function,
    delete_function as _delete_function,
    # Grants
    grant_privileges as _grant_privileges,
    revoke_privileges as _revoke_privileges,
    get_grants as _get_grants,
    get_effective_grants as _get_effective_grants,
    # Storage
    list_storage_credentials as _list_storage_credentials,
    get_storage_credential as _get_storage_credential,
    create_storage_credential as _create_storage_credential,
    update_storage_credential as _update_storage_credential,
    delete_storage_credential as _delete_storage_credential,
    validate_storage_credential as _validate_storage_credential,
    list_external_locations as _list_external_locations,
    get_external_location as _get_external_location,
    create_external_location as _create_external_location,
    update_external_location as _update_external_location,
    delete_external_location as _delete_external_location,
    # Connections
    list_connections as _list_connections,
    get_connection as _get_connection,
    create_connection as _create_connection,
    update_connection as _update_connection,
    delete_connection as _delete_connection,
    create_foreign_catalog as _create_foreign_catalog,
    # Tags
    set_tags as _set_tags,
    unset_tags as _unset_tags,
    set_comment as _set_comment,
    query_table_tags as _query_table_tags,
    query_column_tags as _query_column_tags,
    # Security policies
    create_security_function as _create_security_function,
    set_row_filter as _set_row_filter,
    drop_row_filter as _drop_row_filter,
    set_column_mask as _set_column_mask,
    drop_column_mask as _drop_column_mask,
    # Monitors
    create_monitor as _create_monitor,
    get_monitor as _get_monitor,
    run_monitor_refresh as _run_monitor_refresh,
    list_monitor_refreshes as _list_monitor_refreshes,
    delete_monitor as _delete_monitor,
    # Sharing
    list_shares as _list_shares,
    get_share as _get_share,
    create_share as _create_share,
    add_table_to_share as _add_table_to_share,
    remove_table_from_share as _remove_table_from_share,
    delete_share as _delete_share,
    grant_share_to_recipient as _grant_share_to_recipient,
    revoke_share_from_recipient as _revoke_share_from_recipient,
    list_recipients as _list_recipients,
    get_recipient as _get_recipient,
    create_recipient as _create_recipient,
    rotate_recipient_token as _rotate_recipient_token,
    delete_recipient as _delete_recipient,
    list_providers as _list_providers,
    get_provider as _get_provider,
    list_provider_shares as _list_provider_shares,
)

from ..manifest import register_deleter
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_catalog_resource(resource_id: str) -> None:
    _delete_catalog(catalog_name=resource_id, force=True)


def _delete_schema_resource(resource_id: str) -> None:
    _delete_schema(full_schema_name=resource_id)


def _delete_volume_resource(resource_id: str) -> None:
    _delete_volume(full_volume_name=resource_id)


register_deleter("catalog", _delete_catalog_resource)
register_deleter("schema", _delete_schema_resource)
register_deleter("volume", _delete_volume_resource)


def _auto_tag(object_type: str, full_name: str) -> None:
    """Best-effort: apply default tags to a newly created UC object.

    Tags are set individually so that a tag-policy violation on one key
    does not prevent the remaining tags from being applied.
    """
    for key, value in get_default_tags().items():
        try:
            _set_tags(object_type=object_type, full_name=full_name, tags={key: value})
        except Exception:
            logger.warning("Failed to set tag %s=%s on %s '%s'", key, value, object_type, full_name, exc_info=True)


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert SDK objects to serializable dicts."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return vars(obj)


def _to_dict_list(items: list) -> List[Dict[str, Any]]:
    """Convert a list of SDK objects to serializable dicts."""
    return [_to_dict(item) for item in items]


# =============================================================================
# 工具 1: manage_uc_objects
# =============================================================================


@mcp.tool
def manage_uc_objects(
    object_type: str,
    action: str,
    name: str = None,
    full_name: str = None,
    catalog_name: str = None,
    schema_name: str = None,
    comment: str = None,
    owner: str = None,
    storage_root: str = None,
    volume_type: str = None,
    storage_location: str = None,
    new_name: str = None,
    properties: Dict[str, str] = None,
    isolation_mode: str = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    管理 Unity Catalog 命名空間物件：catalogs、schemas、volumes、functions。

    各 object_type 可用的動作：
    - catalog: create, get, list, update, delete
    - schema: create, get, list, update, delete
    - volume: create, get, list, update, delete
    - function: get, list, delete（請透過 manage_uc_security_policies 或 execute_sql 建立 function）

    參數:
        object_type: "catalog", "schema", "volume" 或 "function"
        action: "create", "get", "list", "update" 或 "delete"
        name: 物件名稱（用於 create）
        full_name: 完整限定名稱（用於 get/update/delete）。
                   格式："catalog"、"catalog.schema" 或 "catalog.schema.object"。
        catalog_name: 父層 catalog（用於列出 schemas/volumes/functions，或建立 schema）
        schema_name: 父層 schema（用於列出 volumes/functions，或建立 volume）
        comment: 說明（用於 create/update）
        owner: 擁有者（用於 create/update）
        storage_root: 受管儲存位置（用於 catalog/schema create）
        volume_type: "MANAGED" 或 "EXTERNAL"（用於 volume create，預設：MANAGED）
        storage_location: 雲端儲存 URL（用於 external volumes）
        new_name: 新名稱（用於 update/rename）
        properties: 鍵值屬性（用於 catalog create）
        isolation_mode: "OPEN" 或 "ISOLATED"（用於 catalog update）
        force: 強制刪除（預設：False）

    回傳:
        包含作業結果的 dict。對 list 為 {"items": [...]}。對 get/create/update 為物件詳細資料。
    """
    otype = object_type.lower()

    if otype == "catalog":
        if action == "create":
            result = _to_dict(
                _create_catalog(
                    name=name,
                    comment=comment,
                    storage_root=storage_root,
                    properties=properties,
                )
            )
            _auto_tag("catalog", name)
            try:
                from ..manifest import track_resource

                track_resource(
                    resource_type="catalog",
                    name=name,
                    resource_id=result.get("name", name),
                )
            except Exception:
                pass
            return result
        elif action == "get":
            return _to_dict(_get_catalog(catalog_name=full_name or name))
        elif action == "list":
            return {"items": _to_dict_list(_list_catalogs())}
        elif action == "update":
            return _to_dict(
                _update_catalog(
                    catalog_name=full_name or name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                    isolation_mode=isolation_mode,
                )
            )
        elif action == "delete":
            _delete_catalog(catalog_name=full_name or name, force=force)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="catalog", resource_id=full_name or name)
            except Exception:
                pass
            return {"status": "deleted", "catalog": full_name or name}

    elif otype == "schema":
        if action == "create":
            result = _to_dict(_create_schema(catalog_name=catalog_name, schema_name=name, comment=comment))
            _auto_tag("schema", f"{catalog_name}.{name}")
            try:
                from ..manifest import track_resource

                full_schema = result.get("full_name") or f"{catalog_name}.{name}"
                track_resource(resource_type="schema", name=full_schema, resource_id=full_schema)
            except Exception:
                logger.warning("Failed to track schema in manifest", exc_info=True)
            return result
        elif action == "get":
            return _to_dict(_get_schema(full_schema_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_schemas(catalog_name=catalog_name))}
        elif action == "update":
            return _to_dict(
                _update_schema(
                    full_schema_name=full_name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                )
            )
        elif action == "delete":
            _delete_schema(full_schema_name=full_name)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="schema", resource_id=full_name)
            except Exception:
                pass
            return {"status": "deleted", "schema": full_name}

    elif otype == "volume":
        if action == "create":
            result = _to_dict(
                _create_volume(
                    catalog_name=catalog_name,
                    schema_name=schema_name,
                    name=name,
                    volume_type=volume_type or "MANAGED",
                    comment=comment,
                    storage_location=storage_location,
                )
            )
            _auto_tag("volume", f"{catalog_name}.{schema_name}.{name}")
            try:
                from ..manifest import track_resource

                full_vol = result.get("full_name") or f"{catalog_name}.{schema_name}.{name}"
                track_resource(resource_type="volume", name=full_vol, resource_id=full_vol)
            except Exception:
                pass
            return result
        elif action == "get":
            return _to_dict(_get_volume(full_volume_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_volumes(catalog_name=catalog_name, schema_name=schema_name))}
        elif action == "update":
            return _to_dict(
                _update_volume(
                    full_volume_name=full_name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                )
            )
        elif action == "delete":
            _delete_volume(full_volume_name=full_name)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="volume", resource_id=full_name)
            except Exception:
                pass
            return {"status": "deleted", "volume": full_name}

    elif otype == "function":
        if action == "create":
            return {
                "error": """Functions cannot be created via SDK. Use manage_uc_security_policies tool with 
                action='create_security_function' or execute_sql with a CREATE FUNCTION statement."""
            }
        elif action == "get":
            return _to_dict(_get_function(full_function_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_functions(catalog_name=catalog_name, schema_name=schema_name))}
        elif action == "delete":
            _delete_function(full_function_name=full_name, force=force)
            return {"status": "deleted", "function": full_name}

    raise ValueError(f"Invalid object_type='{object_type}' or action='{action}'")


# =============================================================================
# 工具 2: manage_uc_grants
# =============================================================================


@mcp.tool
def manage_uc_grants(
    action: str,
    securable_type: str,
    full_name: str,
    principal: str = None,
    privileges: List[str] = None,
) -> Dict[str, Any]:
    """
    管理 Unity Catalog securable 物件上的權限。

    動作:
    - grant: 對 principal 授予 privileges。
    - revoke: 從 principal 撤銷 privileges。
    - get: 取得物件目前的 grants。
    - get_effective: 取得有效的（繼承 + 直接）grants。

    參數:
        action: "grant", "revoke", "get" 或 "get_effective"
        securable_type: 物件類型："catalog", "schema", "table", "volume", "function",
            "storage_credential", "external_location", "connection", "share", "metastore"
        full_name: securable 物件的完整名稱
        principal: 使用者、群組或 service principal（grant/revoke 時必填）
        privileges: privilege 清單（grant/revoke 時必填）。
            常見值："SELECT", "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA",
            "USE_CATALOG", "USE_SCHEMA", "ALL_PRIVILEGES", "EXECUTE",
            "READ_VOLUME", "WRITE_VOLUME", "CREATE_VOLUME", "CREATE_FUNCTION"

    回傳:
        包含 grant/revoke 結果或目前權限的 dict
    """
    act = action.lower()

    if act == "grant":
        return _grant_privileges(
            securable_type=securable_type,
            full_name=full_name,
            principal=principal,
            privileges=privileges,
        )
    elif act == "revoke":
        return _revoke_privileges(
            securable_type=securable_type,
            full_name=full_name,
            principal=principal,
            privileges=privileges,
        )
    elif act == "get":
        return _get_grants(securable_type=securable_type, full_name=full_name, principal=principal)
    elif act == "get_effective":
        return _get_effective_grants(securable_type=securable_type, full_name=full_name, principal=principal)

    raise ValueError(f"Invalid action: '{action}'. Valid: grant, revoke, get, get_effective")


# =============================================================================
# 工具 3: manage_uc_storage
# =============================================================================


@mcp.tool
def manage_uc_storage(
    resource_type: str,
    action: str,
    name: str = None,
    aws_iam_role_arn: str = None,
    azure_access_connector_id: str = None,
    url: str = None,
    credential_name: str = None,
    read_only: bool = False,
    comment: str = None,
    owner: str = None,
    new_name: str = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    管理 storage credentials 與 external locations。

    resource_type + action 的組合：
    - credential: create, get, list, update, delete, validate
    - external_location: create, get, list, update, delete

    參數:
        resource_type: "credential" 或 "external_location"
        action: "create", "get", "list", "update", "delete", "validate"
        name: 資源名稱（除 list 外的所有 actions）
        aws_iam_role_arn: AWS IAM Role ARN（AWS 上 credential create/update 用）
        azure_access_connector_id: Azure Access Connector ID（Azure 上 credential create/update 用）
        url: 雲端儲存 URL（用於 external_location create/update，或 credential validate）
        credential_name: storage credential 名稱（用於 external_location create/update）
        read_only: 資源是否唯讀（預設：False）
        comment: 說明
        owner: 擁有者
        new_name: update/rename 用的新名稱
        force: 強制刪除（預設：False）

    回傳:
        包含作業結果的 dict
    """
    rtype = resource_type.lower().replace(" ", "_").replace("-", "_")

    if rtype == "credential":
        if action == "create":
            return _to_dict(
                _create_storage_credential(
                    name=name,
                    comment=comment,
                    aws_iam_role_arn=aws_iam_role_arn,
                    azure_access_connector_id=azure_access_connector_id,
                    read_only=read_only,
                )
            )
        elif action == "get":
            return _to_dict(_get_storage_credential(name=name))
        elif action == "list":
            return {"items": _to_dict_list(_list_storage_credentials())}
        elif action == "update":
            return _to_dict(
                _update_storage_credential(
                    name=name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                    aws_iam_role_arn=aws_iam_role_arn,
                    azure_access_connector_id=azure_access_connector_id,
                )
            )
        elif action == "delete":
            _delete_storage_credential(name=name, force=force)
            return {"status": "deleted", "credential": name}
        elif action == "validate":
            return _validate_storage_credential(name=name, url=url)

    elif rtype == "external_location":
        if action == "create":
            return _to_dict(
                _create_external_location(
                    name=name,
                    url=url,
                    credential_name=credential_name,
                    comment=comment,
                    read_only=read_only,
                )
            )
        elif action == "get":
            return _to_dict(_get_external_location(name=name))
        elif action == "list":
            return {"items": _to_dict_list(_list_external_locations())}
        elif action == "update":
            return _to_dict(
                _update_external_location(
                    name=name,
                    new_name=new_name,
                    url=url,
                    credential_name=credential_name,
                    comment=comment,
                    owner=owner,
                    read_only=read_only,
                )
            )
        elif action == "delete":
            _delete_external_location(name=name, force=force)
            return {"status": "deleted", "external_location": name}

    raise ValueError(f"Invalid resource_type='{resource_type}' or action='{action}'")


# =============================================================================
# 工具 4: manage_uc_connections
# =============================================================================


@mcp.tool
def manage_uc_connections(
    action: str,
    name: str = None,
    connection_type: str = None,
    options: Dict[str, str] = None,
    comment: str = None,
    owner: str = None,
    new_name: str = None,
    connection_name: str = None,
    catalog_name: str = None,
    catalog_options: Dict[str, str] = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    管理 Lakehouse Federation 外部連線。

    動作:
    - create: 建立外部連線。
    - get: 取得連線詳細資料。
    - list: 列出所有連線。
    - update: 更新連線。
    - delete: 刪除連線。
    - create_foreign_catalog: 使用連線建立 foreign catalog。

    參數:
        action: "create", "get", "list", "update", "delete", "create_foreign_catalog"
        name: 連線名稱（CRUD 作業用）
        connection_type: "SNOWFLAKE", "POSTGRESQL", "MYSQL", "SQLSERVER", "BIGQUERY"（create 用）
        options: 連線選項 dict，包含如 "host", "port", "user", "password", "database" 等鍵
        comment: 說明
        owner: 擁有者
        new_name: 重新命名用的新名稱
        connection_name: 要使用的連線（create_foreign_catalog 用）
        catalog_name: foreign catalog 名稱（create_foreign_catalog 用）
        catalog_options: foreign catalog 的選項（例如 {"database": "mydb"}）
        warehouse_id: SQL warehouse ID（create_foreign_catalog 用）

    回傳:
        包含作業結果的 dict
    """
    act = action.lower()

    if act == "create":
        return _to_dict(
            _create_connection(
                name=name,
                connection_type=connection_type,
                options=options,
                comment=comment,
            )
        )
    elif act == "get":
        return _to_dict(_get_connection(name=name))
    elif act == "list":
        return {"items": _to_dict_list(_list_connections())}
    elif act == "update":
        return _to_dict(_update_connection(name=name, options=options, new_name=new_name, owner=owner))
    elif act == "delete":
        _delete_connection(name=name)
        return {"status": "deleted", "connection": name}
    elif act == "create_foreign_catalog":
        return _create_foreign_catalog(
            catalog_name=catalog_name,
            connection_name=connection_name,
            catalog_options=catalog_options,
            comment=comment,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# 工具 5: manage_uc_tags
# =============================================================================


@mcp.tool
def manage_uc_tags(
    action: str,
    object_type: str = None,
    full_name: str = None,
    column_name: str = None,
    tags: Dict[str, str] = None,
    tag_names: List[str] = None,
    comment_text: str = None,
    catalog_filter: str = None,
    tag_name_filter: str = None,
    tag_value_filter: str = None,
    table_name_filter: str = None,
    limit: int = 100,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    管理 Unity Catalog 物件上的 tags 與 comments。

    動作:
    - set_tags: 在物件或欄位上設定 tags。
    - unset_tags: 從物件或欄位移除 tags。
    - set_comment: 在物件或欄位上設定 comment。
    - query_table_tags: 從 system.information_schema.table_tags 查詢 tags。
    - query_column_tags: 從 system.information_schema.column_tags 查詢 tags。

    參數:
        action: "set_tags", "unset_tags", "set_comment", "query_table_tags", "query_column_tags"
        object_type: "catalog", "schema", "table" 或 "column"（set/unset/comment 用）
        full_name: 物件完整名稱（set/unset/comment 用）
        column_name: 當 object_type 為 "column" 時的欄位名稱
        tags: set_tags 用的 tag 鍵值對（例如 {"pii": "true", "classification": "confidential"}）
        tag_names: unset_tags 要移除的 tag 鍵
        comment_text: set_comment 用的 comment 文字
        catalog_filter: 依 catalog 名稱過濾（query actions 用）
        tag_name_filter: 依 tag 名稱過濾（query actions 用）
        tag_value_filter: 依 tag 值過濾（query actions 用）
        table_name_filter: 依資料表名稱過濾（query_column_tags 用）
        limit: 查詢最大列數（預設：100）
        warehouse_id: SQL warehouse ID（若未提供會自動選取）

    回傳:
        包含作業結果或查詢結果的 dict
    """
    act = action.lower()

    if act == "set_tags":
        return _set_tags(
            object_type=object_type,
            full_name=full_name,
            tags=tags,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "unset_tags":
        return _unset_tags(
            object_type=object_type,
            full_name=full_name,
            tag_names=tag_names,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "set_comment":
        return _set_comment(
            object_type=object_type,
            full_name=full_name,
            comment_text=comment_text,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "query_table_tags":
        return {
            "data": _query_table_tags(
                catalog_filter=catalog_filter,
                tag_name=tag_name_filter,
                tag_value=tag_value_filter,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }
    elif act == "query_column_tags":
        return {
            "data": _query_column_tags(
                catalog_filter=catalog_filter,
                table_name=table_name_filter,
                tag_name=tag_name_filter,
                tag_value=tag_value_filter,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# 工具 6: manage_uc_security_policies
# =============================================================================


@mcp.tool
def manage_uc_security_policies(
    action: str,
    table_name: str = None,
    column_name: str = None,
    filter_function: str = None,
    filter_columns: List[str] = None,
    mask_function: str = None,
    function_name: str = None,
    function_body: str = None,
    parameter_name: str = None,
    parameter_type: str = None,
    return_type: str = None,
    function_comment: str = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    管理列層級安全性與欄位遮罩原則。

    動作:
    - set_row_filter: 對資料表套用列篩選函式。
    - drop_row_filter: 從資料表移除列篩選。
    - set_column_mask: 套用欄位遮罩函式。
    - drop_column_mask: 移除欄位遮罩。
    - create_security_function: 建立供列篩選或欄位遮罩使用的 SQL 函式。

    參數:
        action: "set_row_filter", "drop_row_filter", "set_column_mask", "drop_column_mask", "create_security_function"
        table_name: 完整資料表名稱（row filter/column mask 作業用）
        column_name: 欄位名稱（column mask 作業用）
        filter_function: 列篩選用的完整函式名稱
        filter_columns: 傳入篩選函式的欄位
        mask_function: 欄位遮罩用的完整函式名稱
        function_name: 要建立的完整函式名稱（catalog.schema.function）
        function_body: SQL 函式主體（例如 "RETURN IF(IS_ACCOUNT_GROUP_MEMBER('admins'), val, '***')"）
        parameter_name: 函式輸入參數名稱
        parameter_type: 函式輸入參數型別（例如 "STRING"）
        return_type: 函式回傳型別（篩選為 "BOOLEAN"，遮罩則為資料型別）
        function_comment: 函式說明
        warehouse_id: SQL warehouse ID（若未提供會自動選取）

    回傳:
        包含作業結果與已執行 SQL 的 dict
    """
    act = action.lower()

    if act == "set_row_filter":
        return _set_row_filter(
            table_name=table_name,
            filter_function=filter_function,
            filter_columns=filter_columns,
            warehouse_id=warehouse_id,
        )
    elif act == "drop_row_filter":
        return _drop_row_filter(table_name=table_name, warehouse_id=warehouse_id)
    elif act == "set_column_mask":
        return _set_column_mask(
            table_name=table_name,
            column_name=column_name,
            mask_function=mask_function,
            warehouse_id=warehouse_id,
        )
    elif act == "drop_column_mask":
        return _drop_column_mask(table_name=table_name, column_name=column_name, warehouse_id=warehouse_id)
    elif act == "create_security_function":
        return _create_security_function(
            function_name=function_name,
            parameter_name=parameter_name,
            parameter_type=parameter_type,
            return_type=return_type,
            function_body=function_body,
            comment=function_comment,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# 工具 7: manage_uc_monitors
# =============================================================================


@mcp.tool
def manage_uc_monitors(
    action: str,
    table_name: str,
    output_schema_name: str = None,
    schedule_cron: str = None,
    schedule_timezone: str = "UTC",
    assets_dir: str = None,
) -> Dict[str, Any]:
    """
    管理資料表上的 Lakehouse 品質監視器。

    動作:
    - create: 在資料表上建立品質監視器。
    - get: 取得監視器詳細資料。
    - run_refresh: 觸發監視器重新整理。
    - list_refreshes: 列出重新整理歷程。
    - delete: 刪除監視器。

    參數:
        action: "create", "get", "run_refresh", "list_refreshes", "delete"
        table_name: 被監視的完整資料表名稱（catalog.schema.table）
        output_schema_name: 輸出資料表所用的 schema（create 用，例如 "catalog.schema"）
        schedule_cron: Quartz cron 表達式（create 用，例如 "0 0 12 * * ?"）
        schedule_timezone: 時區（預設："UTC"）
        assets_dir: assets 的 workspace 路徑（create 用）

    回傳:
        包含監視器詳細資料或作業結果的 dict
    """
    act = action.lower()

    if act == "create":
        return _create_monitor(
            table_name=table_name,
            output_schema_name=output_schema_name,
            assets_dir=assets_dir,
            schedule_cron=schedule_cron,
            schedule_timezone=schedule_timezone,
        )
    elif act == "get":
        return _get_monitor(table_name=table_name)
    elif act == "run_refresh":
        return _run_monitor_refresh(table_name=table_name)
    elif act == "list_refreshes":
        return {"refreshes": _list_monitor_refreshes(table_name=table_name)}
    elif act == "delete":
        _delete_monitor(table_name=table_name)
        return {"status": "deleted", "table_name": table_name}

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# 工具 8: manage_uc_sharing
# =============================================================================


@mcp.tool
def manage_uc_sharing(
    resource_type: str,
    action: str,
    name: str = None,
    comment: str = None,
    table_name: str = None,
    shared_as: str = None,
    partition_spec: str = None,
    authentication_type: str = None,
    sharing_id: str = None,
    ip_access_list: List[str] = None,
    share_name: str = None,
    recipient_name: str = None,
    include_shared_data: bool = True,
) -> Dict[str, Any]:
    """
    管理 Delta Sharing：shares、recipients 與 providers。

    resource_type + action 的組合：
    - share: create, get, list, delete, add_table, remove_table, grant_to_recipient, revoke_from_recipient
    - recipient: create, get, list, delete, rotate_token
    - provider: get, list, list_shares

    參數:
        resource_type: "share", "recipient" 或 "provider"
        action: 要執行的作業（請參閱上述組合）
        name: 資源名稱（share/recipient/provider 名稱）
        comment: 說明（create 用）
        table_name: add_table/remove_table 用的完整資料表名稱
        shared_as: 分享資料表的別名（隱藏內部命名）
        partition_spec: 分享資料表的分割過濾條件
        authentication_type: "TOKEN" 或 "DATABRICKS"（recipient create 用）
        sharing_id: D2D sharing 的 sharing 識別碼（recipient create 用）
        ip_access_list: 允許的 IP 位址（recipient create 用）
        share_name: share 名稱（grant/revoke 作業用）
        recipient_name: recipient 名稱（grant/revoke 作業用）
        include_shared_data: get 時是否包含已分享物件（預設：True）

    回傳:
        包含作業結果的 dict
    """
    rtype = resource_type.lower()
    act = action.lower()

    if rtype == "share":
        if act == "create":
            return _create_share(name=name, comment=comment)
        elif act == "get":
            return _get_share(name=name, include_shared_data=include_shared_data)
        elif act == "list":
            return {"items": _list_shares()}
        elif act == "delete":
            _delete_share(name=name)
            return {"status": "deleted", "share": name}
        elif act == "add_table":
            return _add_table_to_share(
                share_name=name or share_name,
                table_name=table_name,
                shared_as=shared_as,
                partition_spec=partition_spec,
            )
        elif act == "remove_table":
            return _remove_table_from_share(share_name=name or share_name, table_name=table_name)
        elif act == "grant_to_recipient":
            return _grant_share_to_recipient(share_name=name or share_name, recipient_name=recipient_name)
        elif act == "revoke_from_recipient":
            return _revoke_share_from_recipient(share_name=name or share_name, recipient_name=recipient_name)

    elif rtype == "recipient":
        if act == "create":
            return _create_recipient(
                name=name,
                authentication_type=authentication_type or "TOKEN",
                sharing_id=sharing_id,
                comment=comment,
                ip_access_list=ip_access_list,
            )
        elif act == "get":
            return _get_recipient(name=name)
        elif act == "list":
            return {"items": _list_recipients()}
        elif act == "delete":
            _delete_recipient(name=name)
            return {"status": "deleted", "recipient": name}
        elif act == "rotate_token":
            return _rotate_recipient_token(name=name)

    elif rtype == "provider":
        if act == "get":
            return _get_provider(name=name)
        elif act == "list":
            return {"items": _list_providers()}
        elif act == "list_shares":
            return {"items": _list_provider_shares(name=name)}

    raise ValueError(f"Invalid resource_type='{resource_type}' or action='{action}'")


# =============================================================================
# 工具 9: manage_metric_views
# =============================================================================


@mcp.tool
def manage_metric_views(
    action: str,
    full_name: str,
    source: str = None,
    dimensions: List[Dict[str, str]] = None,
    measures: List[Dict[str, str]] = None,
    version: str = "1.1",
    comment: str = None,
    filter_expr: str = None,
    joins: List[Dict[str, Any]] = None,
    materialization: Dict[str, Any] = None,
    or_replace: bool = False,
    query_measures: List[str] = None,
    query_dimensions: List[str] = None,
    where: str = None,
    order_by: str = None,
    limit: int = None,
    principal: str = None,
    privileges: List[str] = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    管理 Unity Catalog metric views：create、alter、describe、query、drop 與 grant。

    Metric views 以 YAML 定義可重複使用、受治理的業務指標。它們將
    measure 定義與 dimension 分組分開，讓執行階段能依任何 dimension
    彈性查詢。需要 Databricks Runtime 17.2+ 與 SQL warehouse。

    動作:
    - create: 建立包含 dimensions 與 measures 的 metric view。
    - alter: 更新 metric view 的 YAML 定義。
    - describe: 取得 metric view 的完整定義與中繼資料。
    - query: 使用 MEASURE() 語法查詢依 dimensions 分組的 measures。
    - drop: 刪除 metric view。
    - grant: 在 metric view 上授予 privileges（例如 SELECT）。

    參數:
        action: "create", "alter", "describe", "query", "drop" 或 "grant"
        full_name: 三層名稱（catalog.schema.metric_view_name）
        source: 來源資料表/檢視（create/alter 用，例如 "catalog.schema.orders"）
        dimensions: create/alter 用的 dimension dict 清單。每個項目包含：
            - name: 顯示名稱（例如 "Order Month"）
            - expr: SQL 表達式（例如 "DATE_TRUNC('MONTH', order_date)"）
            - comment: （選用）說明
        measures: create/alter 用的 measure dict 清單。每個項目包含：
            - name: 顯示名稱（例如 "Total Revenue"）
            - expr: 彙總表達式（例如 "SUM(total_price)"）
            - comment: （選用）說明
        version: YAML spec 版本（預設："1.1"，適用 DBR 17.2+）
        comment: metric view 的說明（create/alter 用）
        filter_expr: 套用到所有查詢的 SQL 布林過濾條件（create/alter 用）
        joins: Star/snowflake schema joins（create/alter 用）。
            每個 dict 包含：name、source、on（或 using）、joins（snowflake 用巢狀結構）
        materialization: Materialization 設定（experimental，create/alter 用）。
            鍵值：schedule、mode（"relaxed"）、materialized_views（list）
        or_replace: 若為 True，使用 CREATE OR REPLACE（create 用，預設：False）
        query_measures: 要查詢的 measure 名稱（query action 用）
        query_dimensions: 要分組的 dimension 名稱（query action 用）
        where: WHERE 子句過濾條件（query action 用）
        order_by: ORDER BY 子句，若要 ORDER BY ALL 請用 "ALL"（query action 用）
        limit: 列數上限（query action 用）
        principal: 要授權的使用者/群組（grant action 用）
        privileges: 要授予的 privileges，預設為 ["SELECT"]（grant action 用）
        warehouse_id: SQL warehouse ID（若未提供會自動選取）

    回傳:
        包含作業結果的 dict。對 query 則為列 dict 清單。
    """
    act = action.lower()

    if act == "create":
        result = _create_metric_view(
            full_name=full_name,
            source=source,
            dimensions=dimensions,
            measures=measures,
            version=version,
            comment=comment,
            filter_expr=filter_expr,
            joins=joins,
            materialization=materialization,
            or_replace=or_replace,
            warehouse_id=warehouse_id,
        )
        _auto_tag("metric_view", full_name)
        try:
            from ..manifest import track_resource

            track_resource(
                resource_type="metric_view",
                name=full_name,
                resource_id=full_name,
            )
        except Exception:
            pass
        return result
    elif act == "alter":
        return _alter_metric_view(
            full_name=full_name,
            source=source,
            dimensions=dimensions,
            measures=measures,
            version=version,
            comment=comment,
            filter_expr=filter_expr,
            joins=joins,
            materialization=materialization,
            warehouse_id=warehouse_id,
        )
    elif act == "describe":
        return _describe_metric_view(
            full_name=full_name,
            warehouse_id=warehouse_id,
        )
    elif act == "query":
        if not query_measures:
            raise ValueError("query_measures is required for query action")
        return {
            "data": _query_metric_view(
                full_name=full_name,
                measures=query_measures,
                dimensions=query_dimensions,
                where=where,
                order_by=order_by,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }
    elif act == "drop":
        result = _drop_metric_view(
            full_name=full_name,
            warehouse_id=warehouse_id,
        )
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="metric_view", resource_id=full_name)
        except Exception:
            pass
        return result
    elif act == "grant":
        return _grant_metric_view(
            full_name=full_name,
            principal=principal,
            privileges=privileges,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'. Valid: create, alter, describe, query, drop, grant")
