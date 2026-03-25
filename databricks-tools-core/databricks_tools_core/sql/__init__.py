"""
SQL - SQL Warehouse 作業

用於執行 SQL 查詢、管理 SQL warehouses，以及取得資料表統計資訊的函式。
"""

from .sql import execute_sql, execute_sql_multi
from .warehouse import list_warehouses, get_best_warehouse
from .table_stats import get_table_details, get_volume_folder_details
from .sql_utils import (
    SQLExecutionError,
    TableStatLevel,
    TableSchemaResult,
    DataSourceInfo,
    TableInfo,  # DataSourceInfo 的別名（向後相容）
    ColumnDetail,
    VolumeFileInfo,
    VolumeFolderResult,  # DataSourceInfo 的別名（向後相容）
)

__all__ = [
    # SQL 執行
    "execute_sql",
    "execute_sql_multi",
    # Warehouse 管理
    "list_warehouses",
    "get_best_warehouse",
    # 資料表統計資訊
    "get_table_details",
    "get_volume_folder_details",
    "TableStatLevel",
    "TableSchemaResult",
    "DataSourceInfo",
    "TableInfo",  # DataSourceInfo 的別名
    "ColumnDetail",
    # Volume 資料夾統計資訊
    "VolumeFileInfo",
    "VolumeFolderResult",  # DataSourceInfo 的別名
    # 錯誤
    "SQLExecutionError",
]
