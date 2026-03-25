"""
Unity Catalog - Connection 作業

用於管理 Lakehouse Federation 外部 Connection 的函式。
"""

import re
from typing import Any, Dict, List, Optional
from databricks.sdk.service.catalog import ConnectionInfo, ConnectionType

from ..auth import get_workspace_client

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.\-]*$")


def _validate_identifier(name: str) -> str:
    """驗證 SQL 識別子以防止注入。"""
    if not _IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"無效的 SQL 識別子：'{name}'")
    return name


def _execute_uc_sql(sql_query: str, warehouse_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """使用既有的 execute_sql 基礎設施執行 SQL。"""
    from ..sql.sql import execute_sql

    return execute_sql(sql_query=sql_query, warehouse_id=warehouse_id)


def list_connections() -> List[ConnectionInfo]:
    """
    列出所有外部 Connection。

    回傳:
        ConnectionInfo 物件清單

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return list(w.connections.list())


def get_connection(name: str) -> ConnectionInfo:
    """
    取得特定的外部 Connection。

    參數:
        name: Connection 名稱

    回傳:
        包含 Connection 詳細資料的 ConnectionInfo

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return w.connections.get(name=name)


def create_connection(
    name: str,
    connection_type: str,
    options: Dict[str, str],
    comment: Optional[str] = None,
) -> ConnectionInfo:
    """
    為 Lakehouse Federation 建立外部 Connection。

    參數:
        name: Connection 名稱
        connection_type: Connection 類型。有效值：
            "SNOWFLAKE", "POSTGRESQL", "MYSQL", "SQLSERVER", "BIGQUERY",
            "REDSHIFT", "SQLDW"
        options: Connection 選項 dict。常見鍵值：
            - host: 資料庫主機名稱
            - port: 資料庫連接埠
            - user: 使用者名稱
            - password: 密碼（為了安全性請使用 secret('scope', 'key')）
            - database: 資料庫名稱
            - warehouse: Snowflake warehouse
            - httpPath: 某些 connector 會使用
        comment: 可選的說明

    回傳:
        包含已建立 Connection 詳細資料的 ConnectionInfo

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    kwargs: Dict[str, Any] = {
        "name": name,
        "connection_type": ConnectionType(connection_type.upper()),
        "options": options,
    }
    if comment is not None:
        kwargs["comment"] = comment
    return w.connections.create(**kwargs)


def update_connection(
    name: str,
    options: Optional[Dict[str, str]] = None,
    new_name: Optional[str] = None,
    owner: Optional[str] = None,
) -> ConnectionInfo:
    """
    更新外部 Connection。

    參數:
        name: Connection 目前的名稱
        options: 新的 Connection 選項
        new_name: Connection 的新名稱
        owner: 新的擁有者

    回傳:
        包含更新後詳細資料的 ConnectionInfo

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    kwargs: Dict[str, Any] = {"name": name}
    if options is not None:
        kwargs["options"] = options
    if new_name is not None:
        kwargs["new_name"] = new_name
    if owner is not None:
        kwargs["owner"] = owner
    return w.connections.update(**kwargs)


def delete_connection(name: str) -> None:
    """
    刪除外部 Connection。

    參數:
        name: 要刪除的 Connection 名稱

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    w.connections.delete(name=name)


def create_foreign_catalog(
    catalog_name: str,
    connection_name: str,
    catalog_options: Optional[Dict[str, str]] = None,
    comment: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用 connection 建立 foreign catalog（Lakehouse Federation）。

    參數:
        catalog_name: 新 foreign catalog 的名稱
        connection_name: 要使用的 Connection 名稱
        catalog_options: 選項（例如 {"database": "my_db"}）
        comment: 可選的說明
        warehouse_id: 可選的 SQL warehouse ID

    回傳:
        包含狀態與已執行 SQL 的 Dict
    """
    _validate_identifier(catalog_name)
    _validate_identifier(connection_name)

    sql = f"CREATE FOREIGN CATALOG {catalog_name} USING CONNECTION {connection_name}"
    if catalog_options:
        opts = ", ".join(f"'{k}' = '{v}'" for k, v in catalog_options.items())
        sql += f" OPTIONS ({opts})"
    if comment:
        escaped = comment.replace("'", "\\'")
        sql += f" COMMENT '{escaped}'"

    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {
        "status": "created",
        "catalog_name": catalog_name,
        "connection_name": connection_name,
        "sql": sql,
    }
