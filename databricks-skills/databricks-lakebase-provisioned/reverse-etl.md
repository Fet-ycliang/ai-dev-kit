# 使用 Lakebase Provisioned 的 Reverse ETL

## 概觀

Reverse ETL 可將 Unity Catalog Delta 資料表同步到 Lakebase Provisioned，並以 PostgreSQL 資料表呈現，讓 Lakehouse 中處理的資料支援 OLTP 存取模式。

## 同步模式

| Mode | Description | Best For | Notes |
|------|-------------|----------|-------|
| **Snapshot** | 一次性完整複製 | 初始設定、小型資料表 | 當修改超過 10% 資料時效率高 10 倍 |
| **Triggered** | 依需求排程更新 | 每小時/每日更新的儀表板 | 來源資料表須開啟 CDF |
| **Continuous** | 近即時串流（秒級延遲） | 即時應用程式 | 成本最高，最短 15 秒間隔，需啟用 CDF |

**注意：** Triggered 與 Continuous 模式必須在來源資料表啟用 Change Data Feed (CDF)：

```sql
ALTER TABLE your_catalog.your_schema.your_table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

## 建立同步資料表

### 使用 Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable,
    SyncedTableSpec,
    SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

# 將 Unity Catalog 資料表同步至 Lakebase Provisioned
synced_table = w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="lakebase_catalog.schema.synced_table",
        database_instance_name="my-lakebase-instance",
        spec=SyncedTableSpec(
            source_table_full_name="analytics.gold.user_profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
print(f"Created synced table: {synced_table.name}")
```

**關鍵參數：**

| Parameter | Description |
|-----------|-------------|
| `name` | 目標資料表完整名稱（catalog.schema.table） |
| `database_instance_name` | Lakebase Provisioned 實例名稱 |
| `source_table_full_name` | 來源 Delta 資料表完整名稱（catalog.schema.table） |
| `primary_key_columns` | 來源資料表的主鍵欄位清單 |
| `scheduling_policy` | `SNAPSHOT`, `TRIGGERED`, or `CONTINUOUS` |

### 使用 CLI

```bash
databricks database create-synced-database-table \
    --json '{
        "name": "lakebase_catalog.schema.synced_table",
        "database_instance_name": "my-lakebase-instance",
        "spec": {
            "source_table_full_name": "analytics.gold.user_profiles",
            "primary_key_columns": ["user_id"],
            "scheduling_policy": "TRIGGERED"
        }
    }'
```

**注意：** 目前沒有 SQL 語法可建立同步資料表，請改用 Python SDK、CLI 或 Catalog Explorer UI。

## 查詢同步資料表狀態

```python
status = w.database.get_synced_database_table(name="lakebase_catalog.schema.synced_table")
print(f"State: {status.data_synchronization_status.detailed_state}")
print(f"Message: {status.data_synchronization_status.message}")
```

## 刪除同步資料表

需要同時在 Unity Catalog 與 Postgres 中刪除：

1. **Unity Catalog：** 透過 Catalog Explorer 或 SDK 刪除
2. **Postgres：** Drop 資料表以釋放儲存空間

```python
# 透過 SDK 刪除同步資料表
w.database.delete_synced_database_table(name="lakebase_catalog.schema.synced_table")
```

```sql
-- 刪除 Postgres 資料表以釋放儲存空間
DROP TABLE your_database.your_schema.your_table;
```

## 使用案例

### 1. Web App 產品目錄

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ecommerce_catalog.public.products",
        database_instance_name="ecommerce-db",
        spec=SyncedTableSpec(
            source_table_full_name="gold.products.catalog",
            primary_key_columns=["product_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
# 應用程式可直接對 PostgreSQL 進行低延遲點查詢
```

### 2. 驗證用使用者檔案

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="auth_catalog.public.user_profiles",
        database_instance_name="auth-db",
        spec=SyncedTableSpec(
            source_table_full_name="gold.users.profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
```

### 3. 即時 ML Feature Store

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ml_catalog.public.user_features",
        database_instance_name="feature-store-db",
        spec=SyncedTableSpec(
            source_table_full_name="ml.features.user_features",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
# ML 模型可低延遲查詢特徵
```

## 最佳實務

1. **啟用 CDF：** 在建立 Triggered 或 Continuous 同步表前先開啟來源資料表的 CDF
2. **選擇適當同步模式：** Snapshot 適用小表或一次性載入，Triggered 適合每小時/每日刷新，Continuous 用於即時
3. **監控同步狀態：** 透過 Catalog Explorer 或 `get_synced_database_table()` 檢查失敗與延遲
4. **為目標表建立索引：** 依查詢模式在 PostgreSQL 建立合適索引
5. **處理結構變更：** Triggered/Continuous 僅支援新增欄位等加法變更；破壞性變更需刪除並重建
6. **考量連線限制：** 每個同步表最多佔用 16 條連線

## 常見問題

| 問題 | 解決方式 |
|------|----------|
| **同步因 CDF 錯誤失敗** | 在使用 Triggered 或 Continuous 前，先於來源資料表啟用 Change Data Feed |
| **結構不相容** | 僅支援加法式結構變更；若有破壞性變更需刪除並重建同步表 |
| **同步耗時過長** | 改用 Triggered 模式進行排程更新；初始大量載入使用 Snapshot |
| **目標資料表被鎖定** | 同步期間避免在目標表進行 DDL 操作 |
