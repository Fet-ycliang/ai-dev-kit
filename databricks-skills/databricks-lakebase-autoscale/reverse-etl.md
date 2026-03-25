# Lakebase 自動擴展的反向 ETL

## 概觀

反向 ETL 可將 Unity Catalog 的 Delta tables 資料同步到 Lakebase 自動擴展，建立 PostgreSQL tables，讓在 Lakehouse 處理的資料能以 OLTP 型態被存取。

## 運作方式

同步資料表會在 Lakebase 建立 Unity Catalog 資料的受管複本：

1. 一個新的 Unity Catalog table（唯讀，由同步管線管理）
2. Lakebase 中的 Postgres table（供應用查詢）

同步管線使用受管的 Lakeflow Spark 宣告式管線持續更新兩者。

### 效能

- **連續寫入：** 每 CU 約 1,200 列/秒
- **批次寫入：** 每 CU 約 15,000 列/秒
- **連線使用量：** 每個同步資料表最多 16 條連線

## 同步模式

| 模式 | 說明 | 最佳用途 | 備註 |
|------|-------------|----------|-------|
| **快照** | 單次完整複製 | 初始建置、歷史分析 | 若修改超過 10% 資料效率高 10 倍 |
| **觸發式** | 需求觸發或排程更新 | 每時/每日更新的 dashboards | 來源資料表需啟用 CDF |
| **連續** | 近即時串流（秒級延遲） | 即時應用 | 成本最高，間隔至少 15 秒，需啟用 CDF |

**注意：** 觸發式與連續模式需在來源資料表啟用 Change Data Feed (CDF)：

```sql
ALTER TABLE your_catalog.your_schema.your_table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

## 建立同步資料表

### 透過 Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable,
    SyncedTableSpec,
    NewPipelineSpec,
    SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

# 建立同步資料表
synced_table = w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="lakebase_catalog.schema.synced_table",
        spec=SyncedTableSpec(
            source_table_full_name="analytics.gold.user_profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
            new_pipeline_spec=NewPipelineSpec(
                storage_catalog="lakebase_catalog",
                storage_schema="staging"
            )
        ),
    )
)
print(f"已建立同步資料表：{synced_table.name}")
```

### 透過 CLI

```bash
databricks database create-synced-database-table \
    --json '{
        "name": "lakebase_catalog.schema.synced_table",
        "spec": {
            "source_table_full_name": "analytics.gold.user_profiles",
            "primary_key_columns": ["user_id"],
            "scheduling_policy": "TRIGGERED",
            "new_pipeline_spec": {
                "storage_catalog": "lakebase_catalog",
                "storage_schema": "staging"
            }
        }
    }'
```

## 查詢同步資料表狀態

```python
status = w.database.get_synced_database_table(name="lakebase_catalog.schema.synced_table")
print(f"狀態：{status.data_synchronization_status.detailed_state}")
print(f"訊息：{status.data_synchronization_status.message}")
```

## 刪除同步資料表

需同時刪除 Unity Catalog 與 Postgres：

1. **Unity Catalog：** 於 Catalog Explorer 或 SDK 刪除
2. **Postgres：** Drop table 以釋放儲存空間

```sql
DROP TABLE your_database.your_schema.your_table;
```

## 資料型別對應

| Unity Catalog 型別 | Postgres 型別 |
|-------------------|---------------|
| BIGINT | BIGINT |
| BINARY | BYTEA |
| BOOLEAN | BOOLEAN |
| DATE | DATE |
| DECIMAL(p,s) | NUMERIC |
| DOUBLE | DOUBLE PRECISION |
| FLOAT | REAL |
| INT | INTEGER |
| INTERVAL | INTERVAL |
| SMALLINT | SMALLINT |
| STRING | TEXT |
| TIMESTAMP | TIMESTAMP WITH TIME ZONE |
| TIMESTAMP_NTZ | TIMESTAMP WITHOUT TIME ZONE |
| TINYINT | SMALLINT |
| ARRAY | JSONB |
| MAP | JSONB |
| STRUCT | JSONB |

**不支援的型別：** GEOGRAPHY、GEOMETRY、VARIANT、OBJECT

## 容量規劃

- **連線使用量：** 每個同步資料表最多使用 16 條連線
- **容量限制：** 所有同步資料表合計上限 2 TB；建議單表 < 1 TB
- **命名規則：** Database、schema 與 table 名稱僅允許 `[A-Za-z0-9_]+`
- **Schema 演進：** 觸發式/連續模式僅支援增加欄位等加法變更

## 使用案例

### Web App 的產品目錄

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ecommerce_catalog.public.products",
        spec=SyncedTableSpec(
            source_table_full_name="gold.products.catalog",
            primary_key_columns=["product_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
```

### 即時特徵服務

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ml_catalog.public.user_features",
        spec=SyncedTableSpec(
            source_table_full_name="ml.features.user_features",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
```

## 最佳實務

1. **建立觸發式或連續表前先啟用 CDF**
2. **選擇合適同步模式**：小型資料用快照、每時/每日用觸發式、即時情境用連續
3. **監控同步狀態**：透過 Catalog Explorer 檢查失敗與延遲
4. **在 Postgres 建立索引**：依查詢模式建立適當索引
5. **處理 schema 變更**：串流模式僅支援加法變更
6. **考量連線上限**：每個同步資料表會使用最多 16 條連線
