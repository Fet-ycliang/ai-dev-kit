---
name: databricks-spark-structured-streaming
description: "Spark Structured Streaming 的完整指南，適用於生產工作負載。用於建置串流管線、處理 Kafka 擷取、實作 Real-Time Mode (RTM)、設定 trigger（processingTime、availableNow）、以 watermark 處理有狀態運算、最佳化 checkpoint、執行 stream-stream 或 stream-static join、寫入多個 sink，或調校串流成本與效能。"
---

# Spark Structured Streaming

使用 Spark Structured Streaming 建立可用於生產環境的串流管線。本 Skill 提供詳細模式與最佳實務的導覽。

## 快速開始

```python
from pyspark.sql.functions import col, from_json

# 基本 Kafka 到 Delta 串流
df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "topic")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
)

df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/stream") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/target_table")
```

## 核心模式

| 模式 | 說明 | 參考資料 |
|------|------|----------|
| **Kafka Streaming** | Kafka 到 Delta、Kafka 到 Kafka、Real-Time Mode | 參閱 [kafka-streaming.md](kafka-streaming.md) |
| **Stream Joins** | stream-stream join、stream-static join | 參閱 [stream-stream-joins.md](stream-stream-joins.md)、[stream-static-joins.md](stream-static-joins.md) |
| **Multi-Sink Writes** | 寫入多個資料表、平行 merge | 參閱 [multi-sink-writes.md](multi-sink-writes.md) |
| **Merge Operations** | MERGE 效能、平行 merge、最佳化 | 參閱 [merge-operations.md](merge-operations.md) |

## 設定

| 主題 | 說明 | 參考資料 |
|------|------|----------|
| **Checkpoints** | Checkpoint 管理與最佳實務 | 參閱 [checkpoint-best-practices.md](checkpoint-best-practices.md) |
| **Stateful Operations** | Watermark、state store、RocksDB 設定 | 參閱 [stateful-operations.md](stateful-operations.md) |
| **Trigger & Cost** | Trigger 選擇、成本最佳化、RTM | 參閱 [trigger-and-cost-optimization.md](trigger-and-cost-optimization.md) |

## 最佳實務

| 主題 | 說明 | 參考資料 |
|------|------|----------|
| **Production Checklist** | 完整的最佳實務清單 | 參閱 [streaming-best-practices.md](streaming-best-practices.md) |

## 生產環境檢查清單

- [ ] Checkpoint 位置為持久化儲存（UC volumes，而非 DBFS）
- [ ] 每個 stream 都有唯一的 checkpoint
- [ ] 使用固定大小叢集（串流作業不要啟用 autoscaling）
- [ ] 已設定監控（input rate、lag、batch duration）
- [ ] 已驗證 exactly-once（txnVersion/txnAppId）
- [ ] 已為有狀態運算設定 watermark
- [ ] stream-static join 使用 left join（不要用 inner join）
