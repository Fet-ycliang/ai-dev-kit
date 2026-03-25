"""
資料表統計資訊

用於取得資料表詳細資料與統計資訊的高階函式。
同時支援 Unity Catalog 資料表與 Volume 資料夾資料。
"""

import logging
from typing import List, Literal, Optional

from .sql_utils.models import (
    ColumnDetail,
    DataSourceInfo,
    TableSchemaResult,
    TableStatLevel,
    VolumeFileInfo,
)
from .sql_utils.table_stats_collector import TableStatsCollector
from .warehouse import get_best_warehouse
from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def _has_glob_pattern(name: str) -> bool:
    """檢查名稱是否包含 glob 萬用字元。"""
    return any(c in name for c in ["*", "?", "[", "]"])


def get_table_details(
    catalog: str,
    schema: str,
    table_names: Optional[List[str]] = None,
    table_stat_level: TableStatLevel = TableStatLevel.SIMPLE,
    warehouse_id: Optional[str] = None,
) -> TableSchemaResult:
    """
    取得 schema 中資料表的詳細資訊。

    依據 table_names 支援三種模式：
    1. 空清單或 None：列出 schema 中的所有資料表
    2. 含有 glob 模式的名稱（*、?、[]）：先列出資料表，再依模式篩選
    3. 精確名稱：不列出資料表，直接取得指定資料表（較快）

    參數:
        catalog: Catalog 名稱
        schema: Schema 名稱
        table_names: 可選的資料表名稱或 glob 模式清單。
            範例:
            - None 或 []：取得所有資料表
            - ["customers", "orders"]：取得特定資料表
            - ["raw_*"]：取得所有以 "raw_" 開頭的資料表
            - ["*_customers", "orders"]：混合使用模式與精確名稱
        table_stat_level: 要收集的統計資訊層級：
            - NONE: 僅取得 DDL，不收集統計資訊（快速、不使用快取）
            - SIMPLE: 基本統計資訊，並使用快取（預設）
            - DETAILED: 完整統計資訊，包含 histograms 與 percentiles
        warehouse_id: 可選的 warehouse ID。若未提供，會自動選擇。

    回傳:
        包含所要求統計資訊層級之資料表資訊的 TableSchemaResult

    引發:
        Exception: 當 warehouse 不可用或 catalog/schema 不存在時

    範例:
        >>> # 取得所有資料表及基本統計資訊
        >>> result = get_table_details("my_catalog", "my_schema")

        >>> # 取得特定資料表
        >>> result = get_table_details("my_catalog", "my_schema", ["customers", "orders"])

        >>> # 取得符合模式的資料表與完整統計資訊
        >>> result = get_table_details(
        ...     "my_catalog", "my_schema",
        ...     ["gold_*"],
        ...     table_stat_level=TableStatLevel.DETAILED
        ... )

        >>> # 僅快速查詢 DDL（不含統計資訊）
        >>> result = get_table_details(
        ...     "my_catalog", "my_schema",
        ...     ["my_table"],
        ...     table_stat_level=TableStatLevel.NONE
        ... )
    """
    # 若未提供，則自動選擇 warehouse
    if not warehouse_id:
        logger.debug("未提供 warehouse_id，正在選擇最佳可用的 warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise Exception(
                "workspace 中沒有可用的 SQL warehouse。"
                "請建立 SQL warehouse 或啟動現有的 warehouse，"
                "或提供特定的 warehouse_id。"
            )
        logger.debug(f"已自動選擇 warehouse：{warehouse_id}")

    collector = TableStatsCollector(warehouse_id=warehouse_id)

    # 判斷是否需要先列出資料表
    table_names = table_names or []
    has_patterns = any(_has_glob_pattern(name) for name in table_names)
    needs_listing = len(table_names) == 0 or has_patterns
    failed_tables: List[DataSourceInfo] = []

    if needs_listing:
        # 先列出所有資料表
        logger.debug(f"正在列出 {catalog}.{schema} 中的資料表")
        all_tables = collector.list_tables(catalog, schema)

        if table_names:
            # 依模式篩選
            tables_to_fetch = collector.filter_tables_by_patterns(all_tables, table_names)
            logger.debug(
                f"已將 {len(all_tables)} 個資料表篩選為 {len(tables_to_fetch)} 個符合模式的資料表：{table_names}"
            )
        else:
            tables_to_fetch = all_tables
            logger.debug(f"找到 {len(tables_to_fetch)} 個資料表")
    else:
        # 直接查詢，不先列出資料表
        logger.debug(f"直接查詢資料表：{table_names}")
        tables_to_fetch = []
        for name in table_names:
            try:
                # 透過 SDK 取得中繼資料，以取得 comment 與 updated_at
                t = collector.client.tables.get(f"{catalog}.{schema}.{name}")
                tables_to_fetch.append(
                    {
                        "name": t.name,
                        "updated_at": getattr(t, "updated_at", None),
                        "comment": getattr(t, "comment", None),
                    }
                )
            except Exception as e:
                logger.warning(f"取得 {catalog}.{schema}.{name} 的中繼資料失敗：{e}")
                failed_tables.append(
                    DataSourceInfo(
                        name=f"{catalog}.{schema}.{name}",
                        error=f"取得資料表中繼資料失敗：{e}",
                    )
                )

    if not tables_to_fetch and not failed_tables:
        return TableSchemaResult(catalog=catalog, schema_name=schema, tables=[])

    # 判斷是否要收集統計資訊
    collect_stats = table_stat_level != TableStatLevel.NONE

    # 取得資料表資訊（有或沒有統計資訊）
    logger.info(f"正在取得 {len(tables_to_fetch)} 個資料表，stat_level={table_stat_level.value}")
    table_infos = collector.get_tables_info_parallel(
        catalog=catalog,
        schema=schema,
        tables=tables_to_fetch,
        collect_stats=collect_stats,
    )

    # 將中繼資料查詢失敗的資料表及其錯誤資訊附加到結果中
    if failed_tables:
        table_infos.extend(failed_tables)

    # 建立結果
    result = TableSchemaResult(
        catalog=catalog,
        schema_name=schema,
        tables=table_infos,
    )

    # 套用統計資訊層級轉換
    if table_stat_level == TableStatLevel.SIMPLE:
        return result.keep_basic_stats()
    elif table_stat_level == TableStatLevel.NONE:
        return result.remove_stats()
    else:
        # DETAILED：回傳所有資訊
        return result


def _parse_volume_path(volume_path: str) -> str:
    """
    解析 volume 路徑並回傳完整的 /Volumes/... 路徑。

    注意:
        可接受以下格式：
    - catalog/schema/volume/path
    - /Volumes/catalog/schema/volume/path

    回傳:
        /Volumes/catalog/schema/volume/path 格式的完整路徑
    """
    path = volume_path.strip("/")
    if path.lower().startswith("volumes/"):
        return f"/{path}"
    return f"/Volumes/{path}"


def _list_volume_files(volume_path: str) -> tuple[List[VolumeFileInfo], int, Optional[str]]:
    """
    使用 Files API 列出 volume 資料夾中的檔案。

    回傳:
        (files_list, total_size_bytes, error_message) 的 tuple
    """
    w = get_workspace_client()
    files = []
    total_size = 0

    try:
        for entry in w.files.list_directory_contents(volume_path):
            file_info = VolumeFileInfo(
                name=entry.name,
                path=entry.path,
                size_bytes=getattr(entry, "file_size", None),
                is_directory=entry.is_directory,
                modification_time=str(getattr(entry, "last_modified", None))
                if hasattr(entry, "last_modified")
                else None,
            )
            files.append(file_info)
            if file_info.size_bytes:
                total_size += file_info.size_bytes

        return files, total_size, None

    except Exception as e:
        error_msg = str(e)
        if "NOT_FOUND" in error_msg or "404" in error_msg:
            return (
                [],
                0,
                f"找不到 volume 路徑：{volume_path}。請確認 catalog、schema、volume 與路徑存在。",
            )
        return [], 0, f"列出 volume 路徑失敗：{volume_path}。錯誤：{error_msg}"


def _extract_catalog_schema_from_volume_path(volume_path: str) -> tuple[str, str]:
    """從 /Volumes/catalog/schema/volume/... 這類 volume 路徑中擷取 catalog 與 schema。"""
    parts = volume_path.strip("/").split("/")
    if parts[0].lower() == "volumes" and len(parts) >= 3:
        return parts[1], parts[2]
    elif len(parts) >= 2:
        return parts[0], parts[1]
    return "volumes", "data"


def get_volume_folder_details(
    volume_path: str,
    format: Literal["parquet", "csv", "json", "delta", "file"] = "parquet",
    table_stat_level: TableStatLevel = TableStatLevel.SIMPLE,
    warehouse_id: Optional[str] = None,
) -> TableSchemaResult:
    """
    取得 Databricks Volume 資料夾中資料檔案的詳細資訊。

    與 get_table_details 類似，但用於儲存在 Volumes 中的原始檔案。
    會使用 SQL warehouse 透過 read_files() 函式讀取 volume 資料。

    參數:
        volume_path: Volume 資料夾路徑。可為：
            - "catalog/schema/volume/path"（例如："ai_dev_kit/demo/raw_data/customers"）
            - "/Volumes/catalog/schema/volume/path"
        format: 資料格式：
            - "parquet"、"csv"、"json"、"delta"：讀取資料並計算統計資訊
            - "file"：僅列出檔案，不讀取資料（快速）
        table_stat_level: 要收集的統計資訊層級：
            - NONE: 僅取得 schema，不收集統計資訊
            - SIMPLE: 基本統計資訊（預設）
            - DETAILED: 完整統計資訊，包含 samples
        warehouse_id: 可選的 warehouse ID。若未提供，會自動選擇。

    回傳:
        TableSchemaResult，內含單一 DataSourceInfo，其中包含檔案資訊、欄位統計資訊與 sample data

    範例:
        >>> # 取得 parquet 檔案的統計資訊
        >>> result = get_volume_folder_details(
        ...     "ai_dev_kit/demo/raw_data/customers",
        ...     format="parquet"
        ... )
        >>> info = result.tables[0]
        >>> print(f"Rows: {info.total_rows}, Columns: {len(info.column_details)}")

        >>> # 僅列出檔案（快速，不讀取資料）
        >>> result = get_volume_folder_details(
        ...     "ai_dev_kit/demo/raw_data/customers",
        ...     format="file"
        ... )
        >>> info = result.tables[0]
        >>> print(f"Files: {info.total_files}, Size: {info.total_size_bytes}")
    """
    full_path = _parse_volume_path(volume_path)
    logger.debug(f"正在取得 volume 資料夾詳細資訊：{full_path}，format={format}")

    # 為結果擷取 catalog/schema
    catalog, schema = _extract_catalog_schema_from_volume_path(full_path)

    def _make_result(info: DataSourceInfo) -> TableSchemaResult:
        """將 DataSourceInfo 包裝為 TableSchemaResult 的輔助函式。"""
        return TableSchemaResult(catalog=catalog, schema_name=schema, tables=[info])

    # 步驟 1：列出檔案以確認資料夾存在，並取得檔案資訊
    files, total_size, error = _list_volume_files(full_path)

    if error:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                error=error,
            )
        )

    if not files:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=0,
                error=f"Volume 路徑存在但內容為空：{full_path}",
            )
        )

    # 計算資料檔案數量（不含目錄）
    data_files = [f for f in files if not f.is_directory]
    directories = [f for f in files if f.is_directory]
    total_files = len(data_files) if data_files else len(directories)

    # 步驟 2：若 format="file"，僅回傳檔案清單
    if format == "file":
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=len(files),
                total_size_bytes=total_size,
                files=files,
            )
        )

    # 步驟 3：若為資料格式，使用 TableStatsCollector 讀取並計算統計資訊
    # 若未提供，則自動選擇 warehouse
    if not warehouse_id:
        logger.debug("未提供 warehouse_id，正在選擇最佳可用的 warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise Exception(
                "workspace 中沒有可用的 SQL warehouse。"
                "請建立 SQL warehouse 或啟動現有的 warehouse，"
                "或提供特定的 warehouse_id。"
            )
        logger.debug(f"已自動選擇 warehouse：{warehouse_id}")

    # 判斷是否要收集統計資訊
    collect_stats = table_stat_level != TableStatLevel.NONE

    if not collect_stats:
        # 僅取得 schema，不收集統計資訊：使用簡單查詢
        from .sql_utils.executor import SQLExecutor

        executor = SQLExecutor(warehouse_id=warehouse_id)
        volume_ref = f"read_files('{full_path}', format => '{format}')"

        try:
            # 從第一列取得 schema
            sample_query = f"SELECT * FROM {volume_ref} LIMIT 1"
            sample_result = executor.execute(sql_query=sample_query, timeout=60)

            if not sample_result:
                return _make_result(
                    DataSourceInfo(
                        name=full_path,
                        format=format,
                        total_files=total_files,
                        total_size_bytes=total_size,
                        error="讀取 volume 資料失敗：未回傳任何資料",
                    )
                )

            # 取得資料列數
            count_result = executor.execute(
                sql_query=f"SELECT COUNT(*) as total_rows FROM {volume_ref}",
                timeout=60,
            )
            total_rows = count_result[0]["total_rows"] if count_result else 0

            # 根據第一列建立欄位詳細資訊
            column_details = {}
            for col_name, value in sample_result[0].items():
                if col_name == "_rescued_data":
                    continue
                if isinstance(value, bool):
                    data_type = "boolean"
                elif isinstance(value, int):
                    data_type = "bigint"
                elif isinstance(value, float):
                    data_type = "double"
                else:
                    data_type = "string"
                column_details[col_name] = ColumnDetail(name=col_name, data_type=data_type)

            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    total_rows=total_rows,
                    column_details=column_details,
                )
            )
        except Exception as e:
            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    error=f"讀取 volume 資料失敗：{str(e)}",
                )
            )

    # 使用 TableStatsCollector 取得完整統計資訊
    collector = TableStatsCollector(warehouse_id=warehouse_id)

    try:
        column_details, total_rows, sample_data = collector.collect_volume_stats(
            volume_path=full_path,
            format=format,
        )

        if not column_details:
            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    error="收集 volume 統計資訊失敗：找不到任何欄位",
                )
            )

        volume_info = DataSourceInfo(
            name=full_path,
            format=format,
            total_files=total_files,
            total_size_bytes=total_size,
            total_rows=total_rows,
            column_details=column_details,
            sample_data=sample_data if table_stat_level == TableStatLevel.DETAILED else None,
        )

        result = _make_result(volume_info)

        # 套用統計資訊層級轉換
        if table_stat_level == TableStatLevel.SIMPLE:
            return result.keep_basic_stats()
        else:
            return result

    except Exception as e:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=total_files,
                total_size_bytes=total_size,
                error=f"讀取 volume 資料失敗：{str(e)}",
            )
        )
