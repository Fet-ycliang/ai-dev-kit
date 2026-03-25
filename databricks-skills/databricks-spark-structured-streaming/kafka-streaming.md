---
name: kafka-streaming
description: Kafka 流媒體模式的完整指南，包含 Kafka 到 Delta 的攝取、Kafka 到 Kafka 的管道，以及用於亞秒延遲的實時模式。適用於建置 Kafka 攝取管道、實作事件豐富化、格式轉換或低延遲流媒體工作負載。
---

# Kafka 流媒體模式

Spark Structured Streaming 與 Kafka 流媒體的完整指南：從攝取到 Delta、Kafka 到 Kafka 管道，以及用於亞秒延遲的實時模式。

## 快速開始

### Kafka 到 Delta

```python
from pyspark.sql.functions import col, from_json

# 從 Kafka 讀取
df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker1:9092,broker2:9092")
    .option("subscribe", "topic_name")
    .option("startingOffsets", "earliest")
    .option("minPartitions", "6")  # 匹配 Kafka 分割區
    .load()
)

# 解析 JSON 值
df_parsed = df.select(
    col("key").cast("string"),
    from_json(col("value").cast("string"), event_schema).alias("data"),
    col("topic"), col("partition"), col("offset"),
    col("timestamp").alias("kafka_timestamp")
).select("key", "data.*", "topic", "partition", "offset", "kafka_timestamp")

# 寫入 Delta
df_parsed.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/kafka_stream") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/bronze_events")
```

### Kafka 到 Kafka

```python
from pyspark.sql.functions import col, from_json, to_json, struct, current_timestamp

# 從來源 Kafka 讀取
source_df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker1:9092")
    .option("subscribe", "input-events")
    .option("startingOffsets", "latest")
    .load()
)

# 解析並轉換
parsed_df = source_df.select(
    col("key").cast("string"),
    from_json(col("value").cast("string"), event_schema).alias("data"),
    col("topic").alias("source_topic")
).select("key", "data.*", "source_topic")

# 轉換事件
enriched_df = parsed_df.withColumn(
    "processed_at", current_timestamp()
).withColumn(
    "value", to_json(struct("event_id", "user_id", "event_type", "processed_at"))
)

# 寫入輸出 Kafka 主題
enriched_df.select("key", "value").writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker1:9092") \
    .option("topic", "output-events") \
    .option("checkpointLocation", "/checkpoints/kafka-to-kafka") \
    .trigger(processingTime="30 seconds") \
    .start()
```

## 常見模式

### 模式 1：銅層攝取（Kafka 到 Delta）

最少轉換、保留原始欄位：

```python
# 最佳實踐：最少轉換、保留原始欄位
# 為什麼：Kafka 保留期很昂貴（預設 7 天）
# Delta 提供永久儲存和完整歷史

df_bronze = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", servers)
    .option("subscribe", topic)
    .option("startingOffsets", "earliest")
    .option("maxOffsetsPerTrigger", 10000)  # 控制批次大小
    .load()
    .select(
        col("key").cast("string"),
        col("value").cast("string"),
        col("topic"), col("partition"), col("offset"),
        col("timestamp").alias("kafka_timestamp"),
        current_timestamp().alias("ingestion_timestamp")
    )
)

df_bronze.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/bronze_events") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/bronze_events")
```

### 模式 2：排程流（成本最佳化）

定期執行而非持續執行：

```python
# 每 4 小時執行一次，而非持續
# 相同的程式碼，只需改變工作排程器中的觸發器

df_bronze.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/bronze_events") \
    .trigger(availableNow=True) \  # 處理所有可用項目，然後停止
    .start("/delta/bronze_events")

# 在 Databricks 工作中：
# - 排程：每 4 小時
# - 叢集：固定大小（流媒體不使用自動調整）
# - 相同的流媒體程式碼，批次樣式執行
```

### 模式 3：實時模式（亞秒延遲）

對於亞秒延遲要求使用 RTM。需要 DBR 16.4 LTS+：

```python
# 實時觸發（DBR 16.4 LTS+）
# 要求：專用叢集、無自動調整、無 Photon、outputMode("update")
# 叢集上的 Spark 設定：spark.databricks.streaming.realTimeMode.enabled = true
query = (enriched_df
    .select(col("key"), col("value"))
    .writeStream
    .format("kafka")
    .option("kafka.bootstrap.servers", brokers)
    .option("topic", "output-events")
    .outputMode("update")         # RTM 僅支援更新模式
    .trigger(realTime="5 minutes")  # PySpark 要求指定檢查點間隔
    .option("checkpointLocation", checkpoint_path)
    .start()
)

# 何時使用 RTM：
# - 需要亞秒延遲（可達低至 5 毫秒的端到端）
# - Photon 必須停用（RTM 不支援）
# - 自動調整必須停用
# - 僅限專用（單一使用者）叢集
# - RTM 不支援 forEachBatch
```

### 模式 4：事件豐富化（Kafka 到 Kafka 與 Delta）

以維度資料豐富事件：

```python
# 讀取參考資料（Delta 表格 - 每個微批次自動重新整理）
user_dim = spark.table("users.dimension")

# 流靜態連接進行豐富化
enriched = (parsed_df
    .join(user_dim, "user_id", "left")
    .withColumn("enriched_value", to_json(struct(
        col("event_id"),
        col("user_id"),
        col("user_name"),  # 來自維度表格
        col("user_segment"),  # 來自維度表格
        col("event_type"),
        col("timestamp")
    )))
)

# 將豐富化事件寫入 Kafka
enriched.select(col("key"), col("enriched_value").alias("value")).writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", brokers) \
    .option("topic", "enriched-events") \
    .trigger(realTime=True) \
    .option("checkpointLocation", "/checkpoints/enrichment") \
    .start()
```

### 模式 5：多主題路由

將事件路由到不同的 Kafka 主題：

```python
def route_events(batch_df, batch_id):
    """將事件路由到不同的 Kafka 主題"""

    # 高優先級 → 緊急主題
    high_priority = batch_df.filter(col("priority") == "high")
    if high_priority.count() > 0:
        high_priority.select("key", "value").write \
            .format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "urgent-events") \
            .save()

    # 錯誤 → 死信隊列主題
    errors = batch_df.filter(col("event_type") == "error")
    if errors.count() > 0:
        errors.select("key", "value").write \
            .format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "error-events-dlq") \
            .save()

    # 所有事件 → 標準主題
    batch_df.select("key", "value").write \
        .format("kafka") \
        .option("kafka.bootstrap.servers", brokers) \
        .option("topic", "standard-events") \
        .save()

parsed_df.writeStream \
    .foreachBatch(route_events) \
    .trigger(realTime=True) \
    .option("checkpointLocation", "/checkpoints/routing") \
    .start()
```

### 模式 6：使用 DLQ 進行結構描述驗證

驗證結構描述並路由無效記錄：

```python
from pyspark.sql.functions import from_json, col, lit, to_json, struct, current_timestamp

def validate_and_route(batch_df, batch_id):
    """驗證結構描述，將錯誤記錄路由到 DLQ"""

    # 嘗試以嚴格結構描述解析
    parsed = batch_df.withColumn(
        "parsed",
        from_json(col("value").cast("string"), validated_schema)
    )

    # 有效記錄
    valid = parsed.filter(col("parsed").isNotNull()).select("key", "value")

    # 無效記錄 → DLQ
    invalid = parsed.filter(col("parsed").isNull()).select(
        col("key"),
        to_json(struct(
            col("value"),
            lit("SCHEMA_VALIDATION_FAILED").alias("dlq_reason"),
            current_timestamp().alias("dlq_timestamp")
        )).alias("value")
    )

    # 將有效資料寫入主要主題
    if valid.count() > 0:
        valid.write.format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "valid-events") \
            .save()

    # 將無效資料寫入 DLQ
    if invalid.count() > 0:
        invalid.write.format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "dlq-events") \
            .save()

source_df.writeStream \
    .foreachBatch(validate_and_route) \
    .trigger(realTime=True) \
    .option("checkpointLocation", "/checkpoints/validation") \
    .start()
```

## 組態

### 消費者選項（從 Kafka 讀取）

```python
(spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "host1:9092,host2:9092")
    .option("subscribe", "source-topic")
    .option("startingOffsets", "latest")  # latest, earliest, 或特定 JSON
    .option("maxOffsetsPerTrigger", "10000")  # 控制批次大小
    .option("minPartitions", "6")  # 匹配 Kafka 分割區
    .option("kafka.auto.offset.reset", "latest")
    .option("kafka.enable.auto.commit", "false")  # Spark 管理位移
    .load()
)
```

### 生產者選項（寫入 Kafka）

```python
(df
    .select("key", "value")
    .writeStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "host1:9092,host2:9092")
    .option("topic", "target-topic")
    .option("kafka.acks", "all")  # 持久性：all, 1, 0
    .option("kafka.retries", "3")
    .option("kafka.batch.size", "16384")
    .option("kafka.linger.ms", "5")
    .option("kafka.compression.type", "lz4")  # lz4, snappy, gzip
    .option("checkpointLocation", checkpoint_path)
    .start()
)
```

### 安全性（SASL/SSL）

```python
# 使用 Databricks 祕密
kafka_username = dbutils.secrets.get("kafka-scope", "username")
kafka_password = dbutils.secrets.get("kafka-scope", "password")

# SASL/PLAIN 認證
df.writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", brokers) \
    .option("topic", target_topic) \
    .option("kafka.security.protocol", "SASL_SSL") \
    .option("kafka.sasl.mechanism", "PLAIN") \
    .option("kafka.sasl.jaas.config",
            f'org.apache.kafka.common.security.plain.PlainLoginModule required username="{kafka_username}" password="{kafka_password}";') \
    .option("checkpointLocation", checkpoint_path) \
    .start()
```

## 效能調整

| 參數 | 建議 | 原因 |
|-----------|---------------|-----|
| minPartitions | 匹配 Kafka 分割區 | 最佳平行性 |
| maxOffsetsPerTrigger | 10,000-100,000 | 平衡延遲與吞吐量 |
| 觸發間隔 | 業務 SLA / 3 | 恢復時間緩衝 |
| RTM | 僅在 < 800 毫秒時需要 | 微批次更具成本效益 |

## 監控

### 關鍵指標

```python
# 程式化監控
for stream in spark.streams.active:
    progress = stream.lastProgress
    if progress:
        print(f"輸入速率：{progress.get('inputRowsPerSecond', 0)} 列/秒")
        print(f"處理速率：{progress.get('processedRowsPerSecond', 0)} 列/秒")

        # Kafka 特定指標
        sources = progress.get("sources", [])
        for source in sources:
            end_offset = source.get("endOffset", {})
            latest_offset = source.get("latestOffset", {})

            # 計算每個分割區的延遲
            for topic, partitions in end_offset.items():
                for partition, end in partitions.items():
                    latest = latest_offset.get(topic, {}).get(partition, end)
                    lag = int(latest) - int(end)
                    print(f"主題 {topic}，分割區 {partition}：延遲 = {lag}")
```

### Spark UI 檢查

- **輸入速率與處理速率**：處理速率必須 > 輸入速率
- **最大位移落後最新版本**：應該一致或下降
- **批次持續時間**：應該 < 觸發間隔

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **未讀取任何資料** | `startingOffsets` 預設為 "latest" | 使用 "earliest" 來處理現有資料 |
| **延遲過高** | 微批次開銷 | 使用 RTM（trigger(realTime=True)） |
| **消費者延遲** | 處理 < 輸入速率 | 調整叢集；減少 maxOffsetsPerTrigger |
| **重複訊息** | 未設定一次性 | 啟用冪等生產者（acks=all） |
| **落後** | 處理 < 輸入速率 | 增加叢集大小 |
| **無法使用自動調整** | 流媒體要求 | 使用固定大小的叢集 |

## 生產檢查清單

- [ ] 檢查點位置是永久性的（UC 磁碟區，非 DBFS）
- [ ] 每個管道有唯一的檢查點
- [ ] 固定大小的叢集（流媒體/RTM 無自動調整）
- [ ] 僅在延遲 < 800 毫秒時啟用 RTM
- [ ] 監控消費者延遲並設定警報
- [ ] 生產者 acks=all 用於持久性
- [ ] 使用 DLQ 設定結構描述驗證
- [ ] 為生產環境設定安全性（SASL/SSL）
- [ ] 驗證一次性語義

## 相關技能

- `stream-static-joins` - 與 Delta 表格的豐富化模式
- `stream-stream-joins` - Kafka 主題間的事件相關性
- `checkpoint-best-practices` - 檢查點設定
- `trigger-tuning` - 觸發器設定和 RTM 設定
