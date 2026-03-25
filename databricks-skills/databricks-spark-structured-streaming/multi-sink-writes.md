---
name: multi-sink-writes
description: 使用 ForEachBatch 將單一 Spark 串流寫入多個 Delta 表格或 Kafka 主題。適用於將流媒體資料扇出到多個接收器、實作獎牌架構（銅/銀/金）、條件路由、CDC 模式或從單一串流建立實物化檢視。
---

# 多接收器寫入

使用 ForEachBatch 有效地將單一流媒體來源寫入多個 Delta 表格或 Kafka 主題。讀取一次，寫入多次 - 避免多次重新處理來源。

## 快速開始

```python
from pyspark.sql.functions import col, current_timestamp

def write_multiple_tables(batch_df, batch_id):
    """將批次寫入多個接收器"""
    # 銅層 - 原始資料
    batch_df.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job") \
        .save("/delta/bronze_events")

    # 銀層 - 已清潔
    cleansed = batch_df.dropDuplicates(["event_id"])
    cleansed.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job_silver") \
        .save("/delta/silver_events")

    # 金層 - 已彙總
    aggregated = batch_df.groupBy("category").count()
    aggregated.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job_gold") \
        .save("/delta/category_counts")

stream.writeStream \
    .foreachBatch(write_multiple_tables) \
    .option("checkpointLocation", "/checkpoints/multi_sink") \
    .start()
```

## 核心概念

### 一個來源、一個檢查點

對整個多接收器串流使用單一檢查點：

```python
# 正確：所有接收器的一個檢查點
stream.writeStream \
    .foreachBatch(multi_sink_function) \
    .option("checkpointLocation", "/checkpoints/single_source_multi_sink") \
    .start()

# 錯誤：不要建立獨立的串流
# 每個串流都會獨立重新處理來源
```

### 交易保證

每個 ForEachBatch 呼叫代表一個 epoch。批次內的所有寫入：
- 看到相同的輸入資料
- 共用相同的 batch_id
- 如果使用 txnVersion，則是冪等的

## 常見模式

### 模式 1：銅-銀-金獎牌架構

將單一串流提供給所有三個獎牌層：

```python
from pyspark.sql.functions import window, count, sum, current_timestamp

def medallion_architecture(batch_df, batch_id):
    """將單一串流提供給所有三個獎牌層"""

    # 銅層：原始攝取
    (batch_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_bronze")
        .saveAsTable("bronze.events")
    )

    # 銀層：已清潔和驗證
    silver_df = (batch_df
        .dropDuplicates(["event_id"])
        .filter(col("status").isin(["active", "pending"]))
        .withColumn("processed_at", current_timestamp())
    )

    (silver_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_silver")
        .saveAsTable("silver.events")
    )

    # 金層：商業彙總
    gold_df = (silver_df
        .groupBy(window(col("timestamp"), "5 minutes"), "category")
        .agg(
            count("*").alias("event_count"),
            sum("amount").alias("total_amount")
        )
    )

    (gold_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_gold")
        .saveAsTable("gold.category_metrics")
    )

stream.writeStream \
    .foreachBatch(medallion_architecture) \
    .trigger(processingTime="30 seconds") \
    .option("checkpointLocation", "/checkpoints/medallion") \
    .start()
```

### 模式 2：條件路由

根據條件將事件路由到不同表格：

```python
def route_by_type(batch_df, batch_id):
    """根據型別將事件路由到不同表格"""

    # 按事件型別分割
    orders = batch_df.filter(col("event_type") == "order")
    refunds = batch_df.filter(col("event_type") == "refund")
    reviews = batch_df.filter(col("event_type") == "review")

    # 寫入各自的表格
    if orders.count() > 0:
        (orders.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_orders")
            .saveAsTable("orders")
        )

    if refunds.count() > 0:
        (refunds.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_refunds")
            .saveAsTable("refunds")
        )

    if reviews.count() > 0:
        (reviews.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_reviews")
            .saveAsTable("reviews")
        )
```

### 模式 3：平行扇出

平行寫入獨立表格的多個接收器：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_write(batch_df, batch_id):
    """平行寫入多個接收器"""

    # 快取以避免重新計算
    batch_df.cache()

    def write_table(table_name, filter_expr=None):
        """將篩選的資料寫入表格"""
        df = batch_df.filter(filter_expr) if filter_expr else batch_df
        (df.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", f"parallel_{table_name}")
            .saveAsTable(table_name)
        )
        return f"已寫入 {table_name}"

    # 定義表格和篩選器
    tables = [
        ("bronze.all_events", None),
        ("silver.errors", col("level") == "ERROR"),
        ("silver.warnings", col("level") == "WARN"),
        ("gold.metrics", col("type") == "metric")
    ]

    # 平行寫入
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(write_table, table_name, filter_expr): table_name
            for table_name, filter_expr in tables
        }

        errors = []
        for future in as_completed(futures):
            table_name = futures[future]
            try:
                future.result()
            except Exception as e:
                errors.append((table_name, str(e)))

    batch_df.unpersist()

    if errors:
        raise Exception(f"寫入失敗：{errors}")
```

### 模式 4：實物化檢視

從相同的串流建立多個衍生檢視：

```python
from pyspark.sql.functions import window, count, sum

def create_materialized_views(batch_df, batch_id):
    """從相同的串流建立多個衍生檢視"""

    # 基礎：所有事件
    (batch_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_raw")
        .save("/delta/views/raw")
    )

    # 檢視 1：小時彙總
    hourly = (batch_df
        .withWatermark("event_time", "1 hour")
        .groupBy(window(col("event_time"), "1 hour"), col("category"))
        .agg(
            count("*").alias("event_count"),
            sum("value").alias("total_value")
        )
    )

    (hourly.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_hourly")
        .save("/delta/views/hourly")
    )

    # 檢視 2：使用者工作階段（15 分鐘視窗）
    sessions = (batch_df
        .withWatermark("event_time", "15 minutes")
        .groupBy(window(col("event_time"), "15 minutes"), col("user_id"))
        .agg(count("*").alias("actions"))
    )

    (sessions.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_sessions")
        .save("/delta/views/sessions")
    )
```

### 模式 5：使用死信隊列進行錯誤處理

將無效記錄路由到 DLQ：

```python
from pyspark.sql.functions import when, lit

def write_with_dlq(batch_df, batch_id):
    """將有效記錄寫入目標，無效記錄寫入死信隊列"""

    # 驗證
    valid = batch_df.filter(
        col("required_field").isNotNull() &
        col("timestamp").isNotNull()
    )
    invalid = batch_df.filter(
        col("required_field").isNull() |
        col("timestamp").isNull()
    )

    # 寫入有效資料
    if valid.count() > 0:
        (valid.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "multi_sink_valid")
            .saveAsTable("silver.valid_events")
        )

    # 使用中繼資料寫入無效資料到 DLQ
    if invalid.count() > 0:
        dlq_df = (invalid
            .withColumn("_error_reason",
                when(col("required_field").isNull(), "missing_required_field")
                .otherwise("missing_timestamp"))
            .withColumn("_batch_id", lit(batch_id))
            .withColumn("_processed_at", current_timestamp())
        )

        (dlq_df.write
            .format("delta")
            .mode("append")
            .saveAsTable("errors.dead_letter_queue")
        )
```

## 效能最佳化

### 最小化重新計算

快取批次 DataFrame 以避免重新計算：

```python
def optimized_multi_sink(batch_df, batch_id):
    """快取以避免重新計算"""

    # 快取批次
    batch_df.cache()

    # 從快取資料進行多次寫入
    batch_df.write...  # 接收器 1
    batch_df.filter(...).write...  # 接收器 2
    batch_df.filter(...).write...  # 接收器 3

    # 完成後 unpersist
    batch_df.unpersist()
```

### 平行寫入

使用 ThreadPoolExecutor 進行獨立寫入：

```python
from concurrent.futures import ThreadPoolExecutor

def parallel_write(batch_df, batch_id):
    """對獨立表格進行平行寫入"""

    batch_df.cache()

    def write_table(table_name, df):
        df.write.format("delta").mode("append").saveAsTable(table_name)

    # 平行寫入
    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.submit(write_table, "table1", batch_df)
        executor.submit(write_table, "table2", batch_df.filter(...))
        executor.submit(write_table, "table3", batch_df.filter(...))

    batch_df.unpersist()
```

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **寫入速度慢** | 循序處理 | 使用平行 ThreadPoolExecutor |
| **重新計算** | 相同 DataFrame 的多個操作 | 快取批次 DataFrame |
| **部分失敗** | 一個接收器失敗 | 使用冪等寫入；Spark 重試整個批次 |
| **結構描述衝突** | 表格有不同的結構描述 | 在每次寫入前進行轉換 |
| **資源爭奪** | 並行寫入過多 | 限制平行性；批次寫入 |

## 生產最佳實踐

### 冪等寫入

始終使用 txnVersion 和 batch_id：

```python
.write
    .format("delta")
    .option("txnVersion", batch_id)
    .option("txnAppId", "unique_app_id_per_table")
    .mode("append")
```

### 保持批次處理速度

```python
# 良好：簡單篩選和寫入
def efficient_write(df, batch_id):
    df.filter(...).write.save("/delta/table1")
    df.filter(...).write.save("/delta/table2")

# 不佳：昂貴的彙總（移至串流定義）
def inefficient_write(df, batch_id):
    df.groupBy(...).agg(...).write.save("/delta/table3")  # 移至串流！
```

## 生產檢查清單

- [ ] 每個多接收器串流一個檢查點
- [ ] 冪等寫入已設定（txnVersion/txnAppId）
- [ ] 使用快取以避免重新計算
- [ ] 獨立表格的平行寫入
- [ ] 已設定錯誤處理和 DLQ
- [ ] 已處理結構描述演進
- [ ] 每個接收器的效能監控

## 相關技能

- `merge-operations` - 平行 MERGE 操作
- `kafka-streaming` - Kafka 攝取模式
- `stream-static-joins` - 多接收器寫入前的豐富化
- `checkpoint-best-practices` - 檢查點設定
