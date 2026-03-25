"""
Unity Catalog - Function 作業

用於管理 UC function（UDF）的函式。
注意：建立 function 需要 SQL（CREATE FUNCTION 陳述式）。
請使用 execute_sql 或 security_policies 模組來建立 function。
"""

from typing import List
from databricks.sdk.service.catalog import FunctionInfo

from ..auth import get_workspace_client


def list_functions(catalog_name: str, schema_name: str) -> List[FunctionInfo]:
    """
    列出 Schema 中的所有 function。

    參數:
        catalog_name: Catalog 名稱
        schema_name: Schema 名稱

    回傳:
        包含 function 中繼資料的 FunctionInfo 物件清單

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return list(
        w.functions.list(
            catalog_name=catalog_name,
            schema_name=schema_name,
        )
    )


def get_function(full_function_name: str) -> FunctionInfo:
    """
    取得特定 function 的詳細資訊。

    參數:
        full_function_name: 完整 function 名稱（catalog.schema.function 格式）

    回傳:
        包含以下 function 中繼資料的 FunctionInfo 物件：
        - name, full_name, catalog_name, schema_name
        - input_params, return_params, routine_body
        - owner, comment, created_at

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return w.functions.get(name=full_function_name)


def delete_function(full_function_name: str, force: bool = False) -> None:
    """
    從 Unity Catalog 刪除 function。

    參數:
        full_function_name: 完整 function 名稱（catalog.schema.function 格式）
        force: 若為 True，則強制刪除

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    w.functions.delete(name=full_function_name, force=force)
