# Python API：Modern 與 Legacy

**最後更新**：2026 年 1 月
**狀態**：所有新專案皆建議使用 Modern API (`pyspark.pipelines`)

---

## 概觀

Databricks 為 Spark Declarative Pipelines 提供兩種 Python API：

1. **Modern API** (`pyspark.pipelines` as `dp`) - **建議使用（2025）**
2. **Legacy API** (`dlt`) - 較舊的 Delta Live Tables API，仍受支援

**關鍵建議**：新專案一律使用 **Modern API**。只有在維護既有 DLT 程式碼時才使用 Legacy API。

---

## 快速比較

| 面向 | Modern (`dp`) | Legacy (`dlt`) |
|------|---------------|----------------|
| **匯入** | `from pyspark import pipelines as dp` | `import dlt` |
| **狀態** | ✅ **建議** | ⚠️ Legacy |
| **資料表 decorator** | `@dp.table()` | `@dlt.table()` |
| **讀取** | `spark.read.table("table")` | `dlt.read("table")` |
| **CDC/SCD** | `dp.create_auto_cdc_flow()` | `dlt.apply_changes()` |
| **用途** | 新專案 | 維護既有專案 |

---

## 並列範例

### 基本資料表定義

**Modern（建議）**:
```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_events", comment="原始事件")
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/events")
    )
```

**Legacy**:
```python
import dlt
from pyspark.sql import functions as F

@dlt.table(name="bronze_events", comment="原始事件")
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/events")
    )
```

### 讀取資料表

**Modern（建議）**:
```python
@dp.table(name="silver_events")
def silver_events():
    # 明確指定 Unity Catalog 路徑
    return spark.read.table("bronze_events").filter(...)
```

**Legacy**:
```python
@dlt.table(name="silver_events")
def silver_events():
    # 隱含的 LIVE schema
    return dlt.read("bronze_events").filter(...)
```

**關鍵差異**：Modern 使用明確的 UC 路徑，Legacy 使用隱含的 `LIVE.*`。

### Streaming 讀取

**Modern（建議）**:
```python
@dp.table(name="silver_events")
def silver_events():
    # 具備內容感知，不需要獨立的 read_stream
    return (
        spark.readStream.table("catalog.schema.bronze_events")
        .filter(F.col("event_type").isNotNull())
    )
```

**Legacy**:
```python
@dlt.table(name="silver_events")
def silver_events():
    # 明確的 streaming 讀取
    return (
        dlt.read_stream("bronze_events")
        .filter(F.col("event_type").isNotNull())
    )
```

### 資料品質 Expectations

**Modern（建議）**:
```python
@dp.table(name="silver_validated")
@dp.expect_or_drop("valid_id", "id IS NOT NULL")
@dp.expect_or_drop("valid_amount", "amount > 0")
@dp.expect_or_fail("critical_field", "timestamp IS NOT NULL")
def silver_validated():
    return spark.read.table("catalog.schema.bronze_events")
```

**Legacy**:
```python
@dlt.table(name="silver_validated")
@dlt.expect_or_drop("valid_id", "id IS NOT NULL")
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_fail("critical_field", "timestamp IS NOT NULL")
def silver_validated():
    return dlt.read("bronze_events")
```

**注意**：兩個版本的 Expectations API 相同。

### SCD Type 2（AUTO CDC）

**Modern（建議）**:
```python
from pyspark.sql.functions import col

dp.create_streaming_table("customers_history")

dp.create_auto_cdc_flow(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**Legacy**:
```python
dlt.create_streaming_table("customers_history")

dlt.apply_changes(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by="event_timestamp",
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**關鍵差異**：Modern 使用 `create_auto_cdc_flow()`，Legacy 使用 `apply_changes()`。

### Liquid Clustering

**Modern（建議）**:
```python
@dp.table(
    name="bronze_events",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    },
    cluster_by=["event_type", "event_date"]  # 使用 Liquid Clustering
)
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

**Legacy**:
```python
@dlt.table(
    name="bronze_events",
    table_properties={
        "pipelines.autoOptimize.managed": "true",
        "pipelines.autoOptimize.zOrderCols": "event_type"
    },
    partition_cols=["event_date"]  # 舊版 partitioning
)
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

**關鍵差異**：Modern 支援使用 `cluster_by` 進行 Liquid Clustering。

---

## 決策矩陣

### 適合使用 Modern API (`dp`) 的情況：
- ✅ **開始新專案**（預設選擇）
- ✅ **學習 SDP/LDP**（學習目前標準）
- ✅ **需要 Liquid Clustering**
- ✅ **偏好明確的 Unity Catalog 路徑**
- ✅ **遵循 2025 最佳實務**

### 適合使用 Legacy API (`dlt`) 的情況：
- ⚠️ **維護既有 DLT 管線**（不要重寫運作良好的程式碼）
- ⚠️ **團隊已熟悉 DLT**（與既有程式碼保持一致）
- ⚠️ **較舊的 DBR 版本**（若 Modern API 尚不可用）

**預設**：除非有明確理由使用 Legacy，否則請使用 Modern `dp` API。

---

## 遷移指南：dlt → dp

### 步驟 1：更新匯入

**修改前**:
```python
import dlt
```

**修改後**:
```python
from pyspark import pipelines as dp
```

### 步驟 2：更新 Decorator

**修改前**：`@dlt.table(name="my_table")`
**修改後**：`@dp.table(name="my_table")`

### 步驟 3：更新讀取方式

**修改前**:
```python
dlt.read("source_table")
dlt.read_stream("source_table")
```

**修改後**:
```python
spark.table("catalog.schema.source_table")
# Streaming 具備內容感知，不需要獨立的 read_stream
```

### 步驟 4：更新 CDC/SCD 操作

**修改前**:
```python
dlt.apply_changes(target="dim_customer", source="cdc_source", ...)
```

**修改後**:
```python
from pyspark.sql.functions import col

dp.create_auto_cdc_flow(
    target="dim_customer",
    source="cdc_source",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**關鍵變更**：`dlt.apply_changes()` → `dp.create_auto_cdc_flow()`

### 步驟 5：更新 Clustering

**修改前**：`@dlt.table(partition_cols=["date"])`
**修改後**：`@dp.table(cluster_by=["date", "other_col"])`

---

## 關鍵模式（2025）

### 1. 使用 Liquid Clustering

```python
@dp.table(cluster_by=["key_col", "date_col"])
def my_table():
    return ...

# 或自動選擇
@dp.table(cluster_by=["AUTO"])
def my_table():
    return ...
```

### 2. 明確的 UC 路徑

```python
# ✅ Modern：明確路徑
spark.table("catalog.schema.table")

# ❌ Legacy：隱含 LIVE
dlt.read("table")
```

### 3. 供自訂 Sink 使用的 forEachBatch

```python
def write_to_custom_sink(batch_df, batch_id):
    batch_df.write.format("custom").save(...)

@dp.table(name="my_table")
def my_table():
    return (
        spark.readStream
        .format("cloudFiles")
        .load("/data")
        .writeStream
        .foreachBatch(write_to_custom_sink)
    )
```

---

## 總結

**新專案**：使用 Modern `pyspark.pipelines` (`dp`)
- ✅ 目前最佳實務（2025）
- ✅ 支援 Liquid Clustering
- ✅ 明確的 Unity Catalog 路徑

**既有專案**：Legacy `dlt` 仍完整受支援
- ⚠️ 可在方便時遷移，不必急迫處理
- ⚠️ 新檔案可考慮採用 Modern API

**重點結論**：Modern API 提供相同功能並加入新特性。所有新專案請從 `from pyspark import pipelines as dp` 開始。
