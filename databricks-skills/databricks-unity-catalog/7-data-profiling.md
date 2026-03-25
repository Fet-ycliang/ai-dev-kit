# 資料側寫（原 Lakehouse Monitoring）

Unity Catalog 資料側寫完整參考：在資料表上建立品質監控，追蹤資料統計側寫、偵測漂移，並監控 ML 模型效能。

## 概覽

資料側寫會隨時間自動計算資料表的統計側寫與漂移指標。建立監控後，Databricks 會生成兩張輸出 Delta 資料表（側寫指標 + 漂移指標）以及可選的儀表板。

| 元件 | 說明 |
|------|------|
| **Monitor（監控）** | 附加於 Unity Catalog 資料表的設定 |
| **Profile Metrics Table（側寫指標資料表）** | 依欄位計算的摘要統計數據 |
| **Drift Metrics Table（漂移指標資料表）** | 與基準線或前一時間窗口的統計漂移比較 |
| **Dashboard（儀表板）** | 自動生成的指標視覺化 |

### 前置需求

- 已啟用 Unity Catalog 的工作區
- Databricks SQL 存取權限
- 所需權限：資料表的 `USE CATALOG`、`USE SCHEMA`、`SELECT` 與 `MANAGE`
- 僅支援 Delta 資料表（受管、外部、View、物化 View、串流資料表）

---

## 側寫類型

| 類型 | 使用情境 | 關鍵參數 | 限制 |
|------|---------|---------|------|
| **Snapshot** | 無時間欄位的通用資料表 | 無需額外參數 | 資料表最大 4TB |
| **TimeSeries** | 含時間戳記欄位的資料表 | `timestamp_column`、`granularities` | 僅處理最近 30 天 |
| **InferenceLog** | ML 模型監控 | `timestamp_column`、`granularities`、`model_id_column`、`problem_type`、`prediction_column` | 僅處理最近 30 天 |

### 時間粒度（適用於 TimeSeries 與 InferenceLog）

支援的 `AggregationGranularity` 值：`AGGREGATION_GRANULARITY_5_MINUTES`、`AGGREGATION_GRANULARITY_30_MINUTES`、`AGGREGATION_GRANULARITY_1_HOUR`、`AGGREGATION_GRANULARITY_1_DAY`、`AGGREGATION_GRANULARITY_1_WEEK` 至 `AGGREGATION_GRANULARITY_4_WEEKS`、`AGGREGATION_GRANULARITY_1_MONTH`、`AGGREGATION_GRANULARITY_1_YEAR`

---

## MCP 工具

使用 `manage_uc_monitors` 工具執行所有監控操作：

| 動作 | 說明 |
|------|------|
| `create` | 在資料表上建立品質監控 |
| `get` | 取得監控詳情與狀態 |
| `run_refresh` | 觸發指標重新整理 |
| `list_refreshes` | 列出重新整理歷程 |
| `delete` | 刪除監控（不刪除相關資產） |

### 建立監控

> **注意：** MCP 工具目前僅支援建立 **Snapshot** 監控。如需 TimeSeries 或 InferenceLog 監控，請直接使用 Python SDK（見下方）。

```python
manage_uc_monitors(
    action="create",
    table_name="catalog.schema.my_table",
    output_schema_name="catalog.schema",
)
```

### 取得監控狀態

```python
manage_uc_monitors(
    action="get",
    table_name="catalog.schema.my_table",
)
```

### 觸發重新整理

```python
manage_uc_monitors(
    action="run_refresh",
    table_name="catalog.schema.my_table",
)
```

### 刪除監控

```python
manage_uc_monitors(
    action="delete",
    table_name="catalog.schema.my_table",
)
```

---

## Python SDK 範例

**文件：** https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dataquality/data_quality.html

新版 SDK 透過 `w.data_quality` 完整支援所有側寫類型。

### 建立 Snapshot 監控

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, SnapshotConfig,
)

w = WorkspaceClient()

# 查詢 UUID——新版 API 使用 object_id 與 output_schema_id（均為 UUID）
table_info = w.tables.get("catalog.schema.my_table")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
            output_schema_id=schema_info.schema_id,
            snapshot=SnapshotConfig(),
        ),
    ),
)
print(f"監控狀態：{monitor.data_profiling_config.status}")
```

### 建立 TimeSeries 監控

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, TimeSeriesConfig, AggregationGranularity,
)

table_info = w.tables.get("catalog.schema.events")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/events",
            output_schema_id=schema_info.schema_id,
            time_series=TimeSeriesConfig(
                timestamp_column="event_timestamp",
                granularities=[AggregationGranularity.AGGREGATION_GRANULARITY_1_DAY],
            ),
        ),
    ),
)
```

### 建立 InferenceLog 監控

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, InferenceLogConfig,
    AggregationGranularity, InferenceProblemType,
)

table_info = w.tables.get("catalog.schema.model_predictions")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/predictions",
            output_schema_id=schema_info.schema_id,
            inference_log=InferenceLogConfig(
                timestamp_column="prediction_timestamp",
                granularities=[AggregationGranularity.AGGREGATION_GRANULARITY_1_HOUR],
                model_id_column="model_version",
                problem_type=InferenceProblemType.INFERENCE_PROBLEM_TYPE_CLASSIFICATION,
                prediction_column="prediction",
                label_column="label",
            ),
        ),
    ),
)
```

### 排程監控

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, SnapshotConfig, CronSchedule,
)

table_info = w.tables.get("catalog.schema.my_table")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
            output_schema_id=schema_info.schema_id,
            snapshot=SnapshotConfig(),
            schedule=CronSchedule(
                quartz_cron_expression="0 0 12 * * ?",  # 每日中午執行
                timezone_id="UTC",
            ),
        ),
    ),
)
```

### 取得、重新整理與刪除

```python
# 取得監控詳情
monitor = w.data_quality.get_monitor(
    object_type="table",
    object_id=table_info.table_id,
)

# 觸發重新整理
from databricks.sdk.service.dataquality import Refresh

refresh = w.data_quality.create_refresh(
    object_type="table",
    object_id=table_info.table_id,
    refresh=Refresh(
        object_type="table",
        object_id=table_info.table_id,
    ),
)

# 刪除監控（不刪除輸出資料表或儀表板）
w.data_quality.delete_monitor(
    object_type="table",
    object_id=table_info.table_id,
)
```

---

## 異常偵測

異常偵測在 **Schema 層級**啟用，非單一資料表。啟用後，Databricks 會以資料表更新的相同頻率自動掃描 Schema 中的所有資料表。

```python
from databricks.sdk.service.dataquality import Monitor, AnomalyDetectionConfig

schema_info = w.schemas.get("catalog.schema")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="schema",
        object_id=schema_info.schema_id,
        anomaly_detection_config=AnomalyDetectionConfig(),
    ),
)
```

> **注意：** 異常偵測需要 `MANAGE SCHEMA` 或 `MANAGE CATALOG` 權限，且工作區須啟用無伺服器計算。

---

## 輸出資料表

建立監控後，會在指定的輸出 Schema 中生成兩張指標資料表：

| 資料表 | 命名規則 | 內容 |
|--------|---------|------|
| **側寫指標** | `{table_name}_profile_metrics` | 每欄統計數據（空值比率、最小值、最大值、平均值、相異計數等） |
| **漂移指標** | `{table_name}_drift_metrics` | 與基準線或前一時間窗口的統計檢定結果 |

### 查詢輸出資料表

```sql
-- 查看最新側寫指標
SELECT *
FROM catalog.schema.my_table_profile_metrics
ORDER BY window_end DESC
LIMIT 100;

-- 查看最新漂移指標
SELECT *
FROM catalog.schema.my_table_drift_metrics
ORDER BY window_end DESC
LIMIT 100;
```

---

## 常見問題

| 問題 | 原因 | 解決方式 |
|------|------|---------|
| `FEATURE_NOT_ENABLED` | 工作區未啟用資料側寫功能 | 聯絡工作區管理員啟用此功能 |
| `PERMISSION_DENIED` | 缺少資料表的 `MANAGE` 權限 | 為您的使用者/群組授予資料表的 `MANAGE` 權限 |
| Monitor 重新整理卡在 `PENDING` | 無可用的 SQL Warehouse | 確保 SQL Warehouse 正在執行，或設定 `warehouse_id` |
| 側寫指標資料表為空 | 重新整理尚未完成 | 透過 `list_refreshes` 確認重新整理狀態，等待 `SUCCESS` |
| Snapshot 監控在大型資料表失敗 | 資料表超過 4TB 限制 | 改用 TimeSeries 側寫類型 |
| TimeSeries 顯示資料有限 | 僅處理最近 30 天 | 此為預期行為；如需調整請聯絡客戶成功團隊 |

---

> **注意：** 資料側寫前身為 Lakehouse Monitoring。舊版 SDK 存取器 `w.lakehouse_monitors` 與 MCP 工具 `manage_uc_monitors` 仍使用舊版 API。

## 參考資源

- [資料品質監控文件](https://docs.databricks.com/aws/en/data-quality-monitoring/)
- [Data Quality SDK 參考](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dataquality/data_quality.html)
- [舊版 Lakehouse Monitors SDK 參考](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/catalog/lakehouse_monitors.html)
