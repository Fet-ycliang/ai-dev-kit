"""
SQL 執行

在 Databricks 上執行 SQL 查詢的高階函式。
"""

import logging
from typing import Any, Dict, List, Optional

from .sql_utils import SQLExecutor, SQLExecutionError, SQLParallelExecutor
from .warehouse import get_best_warehouse

logger = logging.getLogger(__name__)


def execute_sql(
    sql_query: str,
    warehouse_id: Optional[str] = None,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    timeout: int = 180,
    query_tags: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    在 Databricks SQL Warehouse 上執行 SQL 查詢。

    如果未提供 warehouse_id，會使用 get_best_warehouse()
    自動選擇最佳可用的 warehouse。

    參數:
        sql_query: 要執行的 SQL 查詢
        warehouse_id: 可選的 warehouse ID。若未提供，會自動選擇。
        catalog: 可選的 catalog 內容。若未提供，請使用完整限定名稱。
        schema: 可選的 schema 內容。若未提供，請使用完整限定名稱。
        timeout: 逾時秒數（預設：180）
        query_tags: 可選的查詢標籤，用於成本歸因與篩選。
            格式："key:value,key2:value2"（例如："team:eng,cost_center:701"）。
            會顯示於 system.query.history 與 Query History UI。

    回傳:
        由字典組成的清單，每個字典代表一列，並以欄位名稱作為鍵。
        範例：[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    引發:
        SQLExecutionError: 當查詢執行失敗時，會提供詳細錯誤訊息：
            - 沒有可用的 warehouse
            - 無法存取 warehouse
            - 查詢語法錯誤
            - 查詢逾時
            - 權限不足
    """
    # 若未提供，則自動選擇 warehouse
    if not warehouse_id:
        logger.debug("未提供 warehouse_id，正在選擇最佳可用的 warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise SQLExecutionError(
                "workspace 中沒有可用的 SQL warehouse。"
                "請建立 SQL warehouse 或啟動現有的 warehouse，"
                "或提供特定的 warehouse_id。"
            )
        logger.debug(f"已自動選擇 warehouse：{warehouse_id}")

    # 執行查詢
    executor = SQLExecutor(warehouse_id=warehouse_id)
    return executor.execute(
        sql_query=sql_query,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
        query_tags=query_tags,
    )


def execute_sql_multi(
    sql_content: str,
    warehouse_id: Optional[str] = None,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    timeout: int = 180,
    max_workers: int = 4,
    query_tags: Optional[str] = None,
) -> Dict[str, Any]:
    """
    以具備依賴感知能力的平行方式執行多個 SQL 陳述式。

    會先將 SQL 內容解析為個別陳述式，分析它們之間的依賴關係
    （依據資料表建立與參照），再以最佳順序執行。彼此沒有依賴的查詢
    會平行執行。

    如果未提供 warehouse_id，會使用 get_best_warehouse()
    自動選擇最佳可用的 warehouse。

    參數:
        sql_content: 以 ; 分隔多個陳述式的 SQL 內容
        warehouse_id: 可選的 warehouse ID。若未提供，會自動選擇。
        catalog: 可選的 catalog 內容。若未提供，請使用完整限定名稱。
        schema: 可選的 schema 內容。若未提供，請使用完整限定名稱。
        timeout: 每個查詢的逾時秒數（預設：180）
        max_workers: 每個群組的最大平行查詢數（預設：4）
        query_tags: 可選的查詢標籤，用於成本歸因（例如："team:eng,cost_center:701"）。

    回傳:
        包含以下內容的字典：
        - results: 將查詢索引對應至結果字典的 Dict，每個結果包含：
            - query_index: 查詢的 0 起始索引
            - status: "success" 或 "error"
            - execution_time: 執行所花費的秒數
            - query_preview: 查詢前 100 個字元
            - result_rows: 回傳列數（成功時）
            - sample_results: 前 5 列結果（成功時）
            - error: 錯誤訊息（失敗時）
            - error_category: 錯誤類型，例如 SYNTAX_ERROR、MISSING_TABLE（失敗時）
            - suggestion: 修正建議（失敗時）
            - group_number: 此查詢所在的執行群組
            - is_parallel: 是否與其他查詢平行執行
        - execution_summary: 整體統計資訊，包含：
            - total_queries: 解析出的查詢數量
            - total_groups: 執行群組數量
            - total_time: 總執行時間
            - stopped_after_group: 停止執行時所在的群組編號（如有錯誤）
            - groups: 群組詳細資訊清單

    引發:
        SQLExecutionError: 當解析失敗或沒有可用 warehouse 時

    範例:
        >>> result = execute_sql_multi('''
        ...     CREATE TABLE t1 AS SELECT 1 as id;
        ...     CREATE TABLE t2 AS SELECT 2 as id;
        ...     CREATE TABLE t3 AS SELECT * FROM t1 JOIN t2;
        ... ''')
        >>> # t1 與 t2 會平行執行（沒有依賴）
        >>> # t3 會在兩者完成後執行（依賴 t1 與 t2）
    """
    # 若未提供，則自動選擇 warehouse
    if not warehouse_id:
        logger.debug("未提供 warehouse_id，正在選擇最佳可用的 warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise SQLExecutionError(
                "workspace 中沒有可用的 SQL warehouse。"
                "請建立 SQL warehouse 或啟動現有的 warehouse，"
                "或提供特定的 warehouse_id。"
            )
        logger.debug(f"已自動選擇 warehouse：{warehouse_id}")

    # 使用平行執行器執行
    executor = SQLParallelExecutor(
        warehouse_id=warehouse_id,
        max_workers=max_workers,
    )
    return executor.execute(
        sql_content=sql_content,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
        query_tags=query_tags,
    )
