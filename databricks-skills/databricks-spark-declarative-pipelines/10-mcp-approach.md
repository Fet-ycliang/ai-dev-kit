使用 MCP 工具來建立、執行並反覆迭代 **SDP pipelines**。**主要工具是 `create_or_update_pipeline`**，它可處理整個生命週期。

**重要：預設應使用 serverless pipelines，並將其視為最佳選項；但若提到 classic、advanced、pro compute types，則不要這樣建議。** 只有在使用者明確要求 R language、Spark RDD APIs 或 JAR libraries 時，才使用 classic clusters。

### 步驟 1：在本機撰寫 Pipeline 檔案

在本機資料夾中建立 `.sql` 或 `.py` 檔案：

```
my_pipeline/
├── bronze/
│   ├── ingest_orders.sql       # SQL（大多數情況的預設選擇）
│   └── ingest_events.py        # Python（適用於複雜邏輯）
├── silver/
│   └── clean_orders.sql
└── gold/
    └── daily_summary.sql
```

**SQL 範例**（`bronze/ingest_orders.sql`）：
```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders
CLUSTER BY (order_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM read_files(
  '/Volumes/catalog/schema/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, customer_id STRING, amount DECIMAL(10,2), order_date DATE'
);
```

**Python 範例**（`bronze/ingest_events.py`）：
```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, current_timestamp

# 從 pipeline 設定取得 schema 位置
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_source_file", col("_metadata.file_path"))
    )
```

### 步驟 2：上傳到 Databricks Workspace

```python
# MCP 工具：upload_folder
upload_folder(
    local_folder="/path/to/my_pipeline",
    workspace_folder="/Workspace/Users/user@example.com/my_pipeline"
)
```

### 步驟 3：建立/更新並執行 Pipeline

使用 **`create_or_update_pipeline`** 管理資源，再用 **`run_pipeline`** 執行：

```python
# MCP 工具：create_or_update_pipeline
result = create_or_update_pipeline(
    name="my_orders_pipeline",
    root_path="/Workspace/Users/user@example.com/my_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    workspace_file_paths=[
        "/Workspace/Users/user@example.com/my_pipeline/bronze/ingest_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/silver/clean_orders.sql",
        "/Workspace/Users/user@example.com/my_pipeline/gold/daily_summary.sql"
    ]
)

# MCP 工具：run_pipeline
run_result = run_pipeline(
    pipeline_id=result["pipeline_id"],
    full_refresh=True,            # 完整重新整理所有資料表
    wait_for_completion=True,     # 等待並回傳最終狀態
    timeout=1800                  # 30 分鐘逾時
)
```

**結果會包含可採取行動的資訊：**
```python
{
    "success": True,                    # 此操作是否成功？
    "pipeline_id": "abc-123",           # 後續操作要用的 Pipeline ID
    "pipeline_name": "my_orders_pipeline",
    "created": True,                    # 新建為 True，更新則為 False
    "state": "COMPLETED",               # COMPLETED、FAILED、TIMEOUT 等
    "catalog": "my_catalog",            # 目標 catalog
    "schema": "my_schema",              # 目標 schema
    "duration_seconds": 45.2,           # 耗時
    "message": "Pipeline 已建立並在 45.2 秒內成功完成。資料表已寫入 my_catalog.my_schema",
    "error_message": None,              # 若失敗則提供錯誤摘要
    "errors": []                        # 若失敗則提供詳細錯誤清單
}
```

### 步驟 4：處理結果

**成功時：**
```python
if result["success"]:
    # 驗證輸出資料表
    stats = get_table_details(
        catalog="my_catalog",
        schema="my_schema",
        table_names=["bronze_orders", "silver_orders", "gold_daily_summary"]
    )
```

**失敗時：**
```python
if not run_result["success"]:
    # 訊息中已包含建議的後續步驟
    print(run_result["message"])

    # 取得詳細錯誤（get_pipeline 會補上最近事件）
    details = get_pipeline(pipeline_id=result["pipeline_id"])
    print(details.get("recent_events"))
```

### 步驟 5：持續迭代直到可正常運作

1. 檢查 run result 或 `get_pipeline` 回傳的錯誤
2. 修正本機檔案中的問題
3. 使用 `upload_folder` 重新上傳
4. 再次執行 `create_or_update_pipeline`（它會更新，不會重建）
5. 重複上述步驟，直到 `result["success"] == True`

---

## MCP 工具快速參考

### 主要工具

| 工具 | 說明 |
|------|-------------|
| **`create_or_update_pipeline`** | **主要入口。** 建立或更新 pipeline，可選擇執行並等待完成。回傳含有 `success`、`state`、`errors` 與可採取行動的 `message` 之詳細狀態。 |

### Pipeline 管理

| 工具 | 說明 |
|------|-------------|
| `get_pipeline` | 依 ID 或名稱取得 pipeline 詳細資料；會補充最新更新狀態與最近事件。不帶參數時會列出全部。 |
| `run_pipeline` | 啟動、停止或等待 pipeline 執行（`stop=True` 可停止，`validate_only=True` 可進行 dry run） |
| `delete_pipeline` | 刪除 pipeline |

### 輔助工具

| 工具 | 說明 |
|------|-------------|
| `upload_folder` | 將本機資料夾上傳到 workspace（平行） |
| `get_table_details` | 驗證輸出資料表是否具有預期的 schema 與列數 |
| `execute_sql` | 執行 ad-hoc SQL 以檢查資料 |

---