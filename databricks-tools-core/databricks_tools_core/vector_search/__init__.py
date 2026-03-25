"""
Vector Search 操作

用於管理 Databricks Vector Search 端點、索引，
以及執行相似度查詢的函式。
"""

from .endpoints import (
    create_vs_endpoint,
    get_vs_endpoint,
    list_vs_endpoints,
    delete_vs_endpoint,
)
from .indexes import (
    create_vs_index,
    get_vs_index,
    list_vs_indexes,
    delete_vs_index,
    sync_vs_index,
    query_vs_index,
    upsert_vs_data,
    delete_vs_data,
    scan_vs_index,
)

__all__ = [
    # 端點
    "create_vs_endpoint",
    "get_vs_endpoint",
    "list_vs_endpoints",
    "delete_vs_endpoint",
    # 索引
    "create_vs_index",
    "get_vs_index",
    "list_vs_indexes",
    "delete_vs_index",
    "sync_vs_index",
    "query_vs_index",
    "upsert_vs_data",
    "delete_vs_data",
    "scan_vs_index",
]
