---
name: stream-static-joins
description: 使用 Delta 維度表格在即時中豐富流媒體資料。適用於將快速移動的流媒體事件與緩慢變更的參考資料（裝置維度、使用者資料、產品目錄）進行連接、實作實時資料豐富化，或將內容新增至流媒體事件而無狀態管理開銷。
---

# 流-靜態連接

使用儲存在 Delta 表格中的緩慢變更參考資料豐富流媒體資料。流-靜態連接是無狀態的，每個微批次自動重新整理維度資料。

## 快速開始

```python
from pyspark.sql.functions import col, from_json

# 流媒體來源（來自 Kafka 的 IoT 事件）
iot_stream = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "iot-events")
    .load()
    .select(from_json(col("value").cast("string"), event_schema).alias("data"))
    .select("data.*")
)

# 靜態 Delta 維度表格（每個微批次重新整理）
device_dim = spark.table("device_dimensions")

# 使用左連接豐富流媒體資料（建議）
enriched = iot_stream.join(
    device_dim,
    "device_id",
    "left"  # 保留所有流媒體事件
).select(
    iot_stream["*"],
    device_dim["device_type"],
    device_dim["location"],
    device_dim["manufacturer"],
    device_dim["updated_at"].alias("dim_updated_at")
)

# 寫入豐富化資料
query = (enriched
    .writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/enriched_events")
    .trigger(processingTime="30 seconds")
    .start("/delta/enriched_iot_events")
)
```

## 核心概念

### 為什麼 Delta 表格重要

Delta 表格每個微批次啟用自動版本檢查：

```python
# Delta 表格：版本每個微批次檢查
device_dim = spark.table("device_dimensions")  # 自動讀取最新版本

# 非 Delta 格式：啟動時讀取一次（真正靜態）
device_dim = spark.read.parquet("/path/to/devices")  # 無重新整理
```

**關鍵見解**：Delta 的版本控制確保每個微批次都取得最新的維度資料，無需手動重新整理。

### 連接類型和生產使用

| 連接類型 | 行為 | 生產使用 |
|-----------|----------|----------------|
| **左** | 保留所有串流事件 | ✅ 建議 - 防止資料遺失 |
| **內** | 丟棄不相符的事件 | ⚠️ 資料遺失風險 - 避免用於生產 |
| **右** | 保留所有維度列 | 很少使用 |
| **完全** | 保留雙方 | 很少使用 |

**生產規則**：始終使用左連接以防止丟棄有效的流媒體事件。

## 常見模式

### 模式 1：基本裝置豐富化

使用裝置中繼資料豐富 IoT 事件：

```python
# 流媒體 IoT 事件
iot_stream = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "iot-events")
    .load()
    .select(from_json(col("value").cast("string"), event_schema).alias("data"))
    .select("data.*")
)

# 裝置維度表格
device_dim = spark.table("device_dimensions")

# 左連接以保留所有事件
enriched = iot_stream.join(
    device_dim,
    "device_id",
    "left"
).select(
    iot_stream["*"],
    device_dim["device_type"],
    device_dim["location"],
    device_dim["status"]
)

enriched.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start("/delta/enriched_events")
```

### 模式 2：多表格豐富化

鏈接多個維度連接：

```python
# 多個維度表格
devices = spark.table("device_dimensions")
locations = spark.table("location_dimensions")
categories = spark.table("category_dimensions")

# 鏈接連接（每個都是無狀態的）
enriched = (iot_stream
    .join(devices, "device_id", "left")
    .join(locations, "location_id", "left")
    .join(categories, "category_id", "left")
    .select(
        iot_stream["*"],
        devices["device_type"],
        devices["manufacturer"],
        locations["region"],
        locations["country"],
        categories["category_name"]
    )
)

# 每個連接每個微批次獨立重新整理
```

### 模式 3：廣播雜湊連接最佳化

最佳化連接以確保廣播：

```python
from pyspark.sql.functions import broadcast

# 選項 1：僅選擇所需的欄
small_dim = device_dim.select("device_id", "device_type", "location")

# 選項 2：篩選為作用中記錄
active_dim = device_dim.filter(col("status") == "active")

# 選項 3：強制廣播提示
enriched = iot_stream.join(
    broadcast(active_dim),
    "device_id",
    "left"
)

# 在 Spark UI 中驗證：尋找查詢計畫中的 "BroadcastHashJoin"
```

### 模式 4：稽核維度新鮮度

追蹤維度資料的新鮮程度：

```python
from pyspark.sql.functions import unix_timestamp, current_timestamp

enriched = (iot_stream
    .join(device_dim, "device_id", "left")
    .withColumn(
        "dim_lag_seconds",
        unix_timestamp(current_timestamp()) -
        unix_timestamp(col("dim_updated_at"))
    )
    .withColumn(
        "dim_fresh",
        col("dim_lag_seconds") < 3600  # 少於 1 小時舊
    )
)

# 監控：如果 dim_lag_seconds > 閾值，發出警報
# 用於資料品質檢查
```

### 模式 5：時間旅遊維度查詢

於事件時間連接維度版本：

```python
from delta import DeltaTable

def enrich_with_time_travel(batch_df, batch_id):
    """用事件時間的維度版本豐富"""
    from pyspark.sql.functions import max as spark_max

    # 取得最新維度版本
    latest_version = DeltaTable.forName(spark, "device_dimensions") \
        .history() \
        .select(spark_max("version").alias("max_version")) \
        .first()[0]

    # 讀取特定版本的維度
    dim_at_version = (spark
        .read
        .format("delta")
        .option("versionAsOf", latest_version)
        .table("device_dimensions")
    )

    # 連接到批次
    enriched = batch_df.join(dim_at_version, "device_id", "left")

    # 寫入
    (enriched
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "enrichment_job")
        .saveAsTable("enriched_events")
    )

iot_stream.writeStream \
    .foreachBatch(enrich_with_time_travel) \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start()
```

### 模式 6：回填遺失的維度

每日工作修正左連接中的 Null 維度：

```python
# 每日批次工作以回填遺失的維度
spark.sql("""
    MERGE INTO enriched_events target
    USING device_dimensions source
    ON target.device_id = source.device_id
      AND target.device_type IS NULL
    WHEN MATCHED THEN
        UPDATE SET
            device_type = source.device_type,
            location = source.location,
            manufacturer = source.manufacturer,
            dim_updated_at = source.updated_at
""")

# 在維度表格更新後執行
# 修正在維度可用之前到達的事件
```

### 模式 7：維度變更偵測

反應維度變更的串流：

```python
def update_reference_cache(batch_df, batch_id):
    """維度表格變更時更新記憶體中的快取"""
    # 維度表格已變更
    # 更新應用程式快取或通知下游系統
    pass

# 串流維度表格變更
dim_changes = (spark
    .readStream
    .format("delta")
    .table("device_dimensions")
    .writeStream
    .foreachBatch(update_reference_cache)
    .option("checkpointLocation", "/checkpoints/dim_changes")
    .start()
)
```

## 效能最佳化

### 檢查清單

- [ ] 維度表格 < 100MB 用於廣播（或增加閾值）
- [ ] 在連接前選擇所需的欄
- [ ] 篩選維度為僅作用中記錄
- [ ] 驗證查詢計畫中的 "BroadcastHashJoin"
- [ ] 分割區大小 100-200MB（記憶體中）
- [ ] 為運算和儲存使用相同的區域

### 組態

```python
# 如果維度較大，增加廣播閾值
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "1g")

# 控制分割區大小
spark.conf.set("spark.sql.shuffle.partitions", "200")

# 最佳化維度表格讀取
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")
```

### 減少維度大小

```python
# 連接前：僅選擇所需的欄
small_dim = device_dim.select(
    "device_id",
    "device_type",
    "location",
    "status"
)

# 篩選為作用中記錄
active_dim = small_dim.filter(col("status") == "active")

# 使用較小的維度連接
enriched = iot_stream.join(active_dim, "device_id", "left")
```

## 監控

### 關鍵指標

```python
# Null 速率（左連接品質）
spark.sql("""
    SELECT
        date_trunc('hour', timestamp) as hour,
        count(*) as total_events,
        count(device_type) as matched_events,
        count(*) - count(device_type) as unmatched_events,
        (count(*) - count(device_type)) * 100.0 / count(*) as null_rate_pct
    FROM enriched_events
    GROUP BY 1
    ORDER BY 1 DESC
""")

# 維度新鮮度
spark.sql("""
    SELECT
        date_trunc('hour', timestamp) as hour,
        avg(dim_lag_seconds) as avg_lag_seconds,
        max(dim_lag_seconds) as max_lag_seconds,
        count(*) as events_with_dim
    FROM enriched_events
    WHERE dim_updated_at IS NOT NULL
    GROUP BY 1
    ORDER BY 1 DESC
""")
```

### 程式化監控

```python
# 監控串流健康狀況
for stream in spark.streams.active:
    status = stream.status
    progress = stream.lastProgress

    if progress:
        print(f"串流：{stream.name}")
        print(f"輸入速率：{progress.get('inputRowsPerSecond', 0)} 列/秒")
        print(f"處理速率：{progress.get('processedRowsPerSecond', 0)} 列/秒")
        print(f"批次持續時間：{progress.get('durationMs', {}).get('triggerExecution', 0)} 毫秒")
```

### Spark UI 檢查

- **Streaming 標籤**：輸入速率與處理速率（處理必須超過輸入）
- **SQL 標籤**：尋找 "BroadcastHashJoin"（不是 "SortMergeJoin"）
- **Jobs 標籤**：檢查 shuffle 操作（應該很少）
- **Stages 標籤**：驗證分割區大小（100-200MB 目標）

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **資料遺失** | 內連接丟棄不相符的事件 | 切換為左連接 |
| **連接速度慢** | Shuffle 連接而非廣播 | 減少維度大小；強制廣播 |
| **資料過期** | 非 Delta 格式 | 將維度表格轉換為 Delta |
| **記憶體問題** | 大型維度表格 | 連接前篩選；增加廣播閾值 |
| **傾斜連接** | 維度中的熱鍵 | 加鹽連接鍵或分割維度表格 |
| **高 Null 速率** | 維度更新延遲 | 監控維度新鮮度；回填工作 |

## 生產最佳實踐

### 始終使用左連接

```python
# 錯誤：內連接遺失資料
enriched = iot_stream.join(device_dim, "device_id", "inner")

# 正確：左連接保留所有事件
enriched = iot_stream.join(device_dim, "device_id", "left")

# 為什麼？新裝置可能在維度表格更新之前傳送資料
# 左連接保留事件；稍後回填維度
```

### 處理 Null 維度

```python
# 在轉換中新增 Null 處理
enriched = (iot_stream
    .join(device_dim, "device_id", "left")
    .withColumn(
        "device_type",
        coalesce(col("device_type"), lit("UNKNOWN"))
    )
    .withColumn(
        "location",
        coalesce(col("location"), lit("UNKNOWN"))
    )
)

# 或旗標以供手動審查
enriched = enriched.withColumn(
    "needs_review",
    col("device_type").isNull()
)
```

### 冪等寫入

```python
def idempotent_write(batch_df, batch_id):
    """以交易版本寫入以確保冪等性"""
    (batch_df
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "enrichment_job")
        .saveAsTable("enriched_events")
    )

enriched.writeStream \
    .foreachBatch(idempotent_write) \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start()
```

## 生產檢查清單

- [ ] 使用左連接（不是內連接）
- [ ] 維度表格是 Delta 格式
- [ ] 查詢計畫中驗證廣播雜湊連接
- [ ] 維度大小最佳化（< 100MB 或增加閾值）
- [ ] 監控 Null 速率並設定警報
- [ ] 追蹤維度新鮮度
- [ ] 排程遺失維度的回填工作
- [ ] 每個查詢的獨特檢查點位置
- [ ] 冪等寫入已設定（txnVersion/txnAppId）
- [ ] 追蹤效能指標（輸入速率、批次持續時間）

## 專家提示

### Delta 版本檢查

Delta 表格每個微批次自動重新整理，透過檢查最新版本：

```python
# 每個微批次：
# 1. Spark 檢查 Delta 表格版本
# 2. 如果變更，讀取最新版本
# 3. 如果未變更，使用快取版本
# 4. 無需手動重新整理

# 這是為什麼 Delta 表格對維度更好比 Parquet
# Parquet：啟動時讀取一次（真正靜態）
# Delta：版本每個微批次檢查（半靜態）
```

### 廣播連接驗證

始終在生產中驗證廣播連接：

```python
# 檢查查詢計畫
enriched.explain(extended=True)

# 尋找：
# - BroadcastHashJoin ✅（快速、無 shuffle）
# - SortMergeJoin ⚠️（較慢、需要 shuffle）

# 如果看到 SortMergeJoin：
# 1. 減少維度大小（選擇欄、篩選列）
# 2. 增加廣播閾值
# 3. 強制廣播提示
```

### 維度表格最佳化

最佳化流媒體連接的維度表格：

```python
# 1. 在連接鍵上使用 Z 排序或液體叢集
spark.sql("""
    OPTIMIZE device_dimensions
    ZORDER BY (device_id)
""")

# 2. 保持維度表格小（< 100MB 理想）
# 3. 使用 Delta 以自動版本檢查
# 4. 按頻繁篩選的欄分割
```

## 相關技能

- `stream-stream-joins` - 連接兩個流媒體來源與狀態管理
- `kafka-to-delta` - Kafka 攝取模式
- `write-multiple-tables` - 多個接收器的扇出模式
- `checkpoint-best-practices` - 檢查點設定和管理
