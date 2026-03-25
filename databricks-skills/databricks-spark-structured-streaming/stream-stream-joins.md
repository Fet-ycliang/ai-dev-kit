---
name: stream-stream-joins
description: 使用事件時間語義、水位標記和狀態管理在即時中連接兩個流媒體來源。適用於關聯來自不同串流的事件（訂單與付款、點擊與轉換、感應器讀數）、處理延遲到達的資料或實作跨多個串流的視窗彙總。
---

# 流-流連接

在即時中連接兩個流媒體來源，以關聯在不同時間和速度到達的事件。流-流連接是有狀態的：雙方必須緩衝事件，直到找到匹配或狀態過期。

## 快速開始

```python
from pyspark.sql.functions import expr, from_json, col
from pyspark.sql.types import StructType

# 讀取兩個流媒體來源
orders = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "orders")
    .load()
    .select(from_json(col("value").cast("string"), order_schema).alias("data"))
    .select("data.*")
    .withWatermark("order_time", "10 minutes")
)

payments = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "payments")
    .load()
    .select(from_json(col("value").cast("string"), payment_schema).alias("data"))
    .select("data.*")
    .withWatermark("payment_time", "10 minutes")
)

# 使用時間邊界連接
matched = (orders
    .join(
        payments,
        expr("""
            orders.order_id = payments.order_id AND
            payments.payment_time >= orders.order_time - interval 5 minutes AND
            payments.payment_time <= orders.order_time + interval 10 minutes
        """),
        "inner"
    )
)

# 寫入結果
query = (matched
    .writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/orders_payments")
    .trigger(processingTime="30 seconds")
    .start("/delta/order_payments")
)
```

## 核心概念

### 為什麼流-流連接需要水位標記

流-流連接是有狀態的：雙方必須緩衝事件，直到找到匹配或狀態過期。水位標記定義何時可以安全地清潔狀態。

```python
# 水位標記 = 最新事件時間 - 延遲閾值
.withWatermark("event_time", "10 minutes")

# 時間戳記 < 水位標記的事件被視為「太遲」
# 遲到事件的狀態會自動清潔
```

### 連接類型和行為

| 連接類型 | 匹配 | 遲到事件 | 使用情況 |
|-----------|---------|-------------|----------|
| **內** | 雙方 | 如果另一方未過期，可能仍會匹配 | 相關性分析 |
| **左外** | 所有左 + 匹配右 | 從左側丟棄水位標記後 | 帶選擇性資料的豐富化 |
| **右外** | 所有右 + 匹配左 | 從右側丟棄水位標記後 | 很少使用 |
| **完全外** | 雙方所有事件 | 水位標記後丟棄 | 完整圖片 |

## 常見模式

### 模式 1：訂單-付款配對

在時間視窗內配對訂單和付款：

```python
orders = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "orders")
    .load()
    .select(from_json(col("value").cast("string"), order_schema).alias("data"))
    .select("data.*")
    .withWatermark("order_time", "10 minutes")
)

payments = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "payments")
    .load()
    .select(from_json(col("value").cast("string"), payment_schema).alias("data"))
    .select("data.*")
    .withWatermark("payment_time", "10 minutes")
)

# 在訂單 10 分鐘內配對付款
matched = (orders
    .join(
        payments,
        expr("""
            orders.order_id = payments.order_id AND
            payments.payment_time >= orders.order_time - interval 5 minutes AND
            payments.payment_time <= orders.order_time + interval 10 minutes
        """),
        "leftOuter"  # 包含無付款的訂單
    )
    .withColumn("matched", col("payment_id").isNotNull())
)

matched.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start("/delta/order_payments")
```

### 模式 2：點擊-轉換歸因

將轉換歸因於時間視窗內的點擊：

```python
impressions = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "impressions")
    .load()
    .select(from_json(col("value").cast("string"), impression_schema).alias("data"))
    .select("data.*")
    .withWatermark("impression_time", "1 hour")
)

conversions = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "conversions")
    .load()
    .select(from_json(col("value").cast("string"), conversion_schema).alias("data"))
    .select("data.*")
    .withWatermark("conversion_time", "1 hour")
)

# 將轉換歸因於 24 小時內的最後一次曝光
attributed = (impressions
    .join(
        conversions,
        expr("""
            impressions.user_id = conversions.user_id AND
            impressions.ad_id = conversions.ad_id AND
            conversions.conversion_time >= impressions.impression_time AND
            conversions.conversion_time <= impressions.impression_time + interval 24 hours
        """),
        "inner"
    )
    .withColumn("attribution_window_hours",
                (col("conversion_time").cast("long") - col("impression_time").cast("long")) / 3600)
)

attributed.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/attribution") \
    .start("/delta/attributed_conversions")
```

### 模式 3：跨串流的工作階段化

將來自多個串流的事件分組為工作階段：

```python
from pyspark.sql.functions import session_window

pageviews = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "pageviews")
    .load()
    .select(from_json(col("value").cast("string"), pageview_schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "30 minutes")
)

clicks = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "clicks")
    .load()
    .select(from_json(col("value").cast("string"), click_schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "30 minutes")
)

# 為每個串流建立工作階段視窗
pageview_sessions = (pageviews
    .groupBy(
        col("user_id"),
        session_window(col("event_time"), "10 minutes")
    )
    .agg(
        count("*").alias("pageview_count"),
        min("event_time").alias("session_start"),
        max("event_time").alias("session_end")
    )
)

click_sessions = (clicks
    .groupBy(
        col("user_id"),
        session_window(col("event_time"), "10 minutes")
    )
    .agg(
        count("*").alias("click_count"),
        min("event_time").alias("session_start"),
        max("event_time").alias("session_end")
    )
)

# 連接工作階段
joined_sessions = (pageview_sessions
    .join(
        click_sessions,
        ["user_id", "session_window"],
        "outer"
    )
    .withColumn("total_events",
                coalesce(col("pageview_count"), lit(0)) +
                coalesce(col("click_count"), lit(0)))
)

joined_sessions.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/sessions") \
    .start("/delta/user_sessions")
```

### 模式 4：使用死信隊列處理遲到資料

將遲到到達的事件路由到單獨的表格：

```python
def write_with_late_data_handling(batch_df, batch_id):
    """分隔準時和遲到資料"""
    from pyspark.sql.functions import current_timestamp, unix_timestamp

    # 計算延遲
    processed = batch_df.withColumn(
        "processing_delay_seconds",
        unix_timestamp(current_timestamp()) - unix_timestamp(col("event_time"))
    )

    # 準時資料（在水位標記內）
    on_time = processed.filter(col("processing_delay_seconds") < 600)  # 10 分鐘

    # 遲到資料
    late = processed.filter(col("processing_delay_seconds") >= 600)

    # 寫入準時資料
    (on_time
        .drop("processing_delay_seconds")
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "stream_join_job")
        .saveAsTable("matched_events")
    )

    # 將遲到資料寫入 DLQ
    if late.count() > 0:
        (late
            .withColumn("dlq_reason", lit("LATE_ARRIVAL"))
            .withColumn("dlq_timestamp", current_timestamp())
            .write
            .format("delta")
            .mode("append")
            .saveAsTable("late_data_dlq")
        )

matched.writeStream \
    .foreachBatch(write_with_late_data_handling) \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start()
```

## 狀態管理

### 為大型狀態設定 RocksDB

對於超過記憶體容量的狀態儲存，使用 RocksDB：

```python
# 啟用 RocksDB 狀態儲存提供者
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# 狀態儲存在磁碟上，減少記憶體壓力
# 建議用於：高基數鍵、長水位標記持續時間
```

### 監控狀態大小

```python
# 直接讀取狀態儲存
state_df = (spark
    .read
    .format("statestore")
    .load("/checkpoints/orders_payments/state")
)

# 檢查分割區平衡
state_df.groupBy("partitionId").count().orderBy(desc("count")).show()

# 檢查狀態大小
state_metadata = (spark
    .read
    .format("state-metadata")
    .load("/checkpoints/orders_payments")
)
state_metadata.show()

# 程式化監控
for stream in spark.streams.active:
    progress = stream.lastProgress
    if progress and "stateOperators" in progress:
        for op in progress["stateOperators"]:
            print(f"狀態列數：{op.get('numRowsTotal', 0)}")
            print(f"狀態記憶體：{op.get('memoryUsedBytes', 0)}")
```

### 控制狀態增長

```python
# 1. 使用水位標記（自動清潔）
.withWatermark("event_time", "10 minutes")  # 水位標記後狀態過期

# 2. 減少鍵基數
# 不佳：user_id（數百萬個不同值）
# 良好：session_id（自然過期）

# 3. 設定合理的時間邊界
# 不佳：無邊界時間範圍
expr("s2.ts >= s1.ts")  # 狀態永遠增長！

# 良好：有邊界的時間範圍
expr("s2.ts BETWEEN s1.ts AND s1.ts + interval 1 hour")
```

## 水位標記設定

### 選擇水位標記持續時間

平衡延遲和完整性：

```python
# 經驗法則：預期延遲的 2-3 倍
# 如果 99 百分位延遲是 5 分鐘 → 使用 10-15 分鐘水位標記

# 高容限（更多匹配、更大狀態）
.withWatermark("event_time", "2 hours")

# 低容限（更快結果、更小狀態）
.withWatermark("event_time", "10 minutes")
```

### 多個水位標記

連接具有不同延遲的串流時：

```python
# 串流 1：快速、低延遲
stream1 = stream1.withWatermark("ts", "5 minutes")

# 串流 2：慢速、高延遲
stream2 = stream2.withWatermark("ts", "15 minutes")

# 有效水位標記 = max(5, 15) = 15 分鐘
joined = stream1.join(stream2, join_condition, "inner")
```

## 生產最佳實踐

### 冪等寫入

確保一次性語義：

```python
def idempotent_write(batch_df, batch_id):
    """以交易版本寫入以確保冪等性"""
    (batch_df
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "stream_join_job")
        .saveAsTable("matched_events")
    )

matched.writeStream \
    .foreachBatch(idempotent_write) \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start()
```

### 多串流連接（3+ 個串流）

謹慎鏈接連接 - 每個增加狀態開銷：

```python
# 步驟 1：連接串流 A 和 B
ab = (stream_a
    .withWatermark("ts", "10 minutes")
    .join(
        stream_b.withWatermark("ts", "10 minutes"),
        expr("a.key = b.key AND b.ts BETWEEN a.ts - interval 5 min AND a.ts + interval 5 min"),
        "inner"
    )
)

# 步驟 2：連接結果與串流 C
abc = ab.join(
    stream_c.withWatermark("ts", "10 minutes"),
    expr("ab.key = c.key AND c.ts BETWEEN ab.ts - interval 5 min AND ab.ts + interval 5 min"),
    "inner"
)

# 注意：結果水位標記來自左側 (ab)
```

### 效能調整

```python
# 狀態儲存批次保留
spark.conf.set("spark.sql.streaming.stateStore.minBatchesToRetain", "2")

# 狀態維護間隔
spark.conf.set("spark.sql.streaming.stateStore.maintenanceInterval", "5m")

# Shuffle 分割區（符合工作程式核心數）
spark.conf.set("spark.sql.shuffle.partitions", "200")
```

## 監控

### 關鍵指標

```python
# 程式化監控
for stream in spark.streams.active:
    status = stream.status
    progress = stream.lastProgress

    if progress:
        print(f"串流：{stream.name}")
        print(f"輸入速率：{progress.get('inputRowsPerSecond', 0)} 列/秒")
        print(f"處理速率：{progress.get('processedRowsPerSecond', 0)} 列/秒")

        # 狀態指標
        if "stateOperators" in progress:
            for op in progress["stateOperators"]:
                print(f"狀態列數：{op.get('numRowsTotal', 0)}")
                print(f"狀態記憶體：{op.get('memoryUsedBytes', 0)}")

        # 水位標記
        if "eventTime" in progress:
            print(f"水位標記：{progress['eventTime'].get('watermark', 'N/A')}")
```

### Spark UI 檢查

- **Streaming 標籤**：輸入速率與處理速率（處理必須超過輸入）
- **狀態操作者**：狀態大小和記憶體使用量
- **水位標記**：目前水位標記時間戳記
- **批次持續時間**：應該 < 觸發間隔

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **狀態太大** | 高基數鍵或長水位標記 | 減少鍵空間；減少水位標記持續時間 |
| **遲到事件被丟棄** | 水位標記太激進 | 增加水位標記延遲 |
| **無匹配** | 時間條件錯誤 | 檢查時間邊界和單位（分鐘 vs 小時） |
| **OOM 錯誤** | 狀態爆炸 | 使用 RocksDB；增加記憶體；減少水位標記 |
| **遺失水位標記** | 狀態永遠增長 | 始終在雙方定義水位標記 |
| **無邊界狀態** | 開放式時間範圍 | 在連接條件中使用有邊界的時間範圍 |

## 生產檢查清單

- [ ] 在兩個流媒體來源上設定水位標記
- [ ] 連接條件包含明確的時間邊界
- [ ] 設定狀態儲存提供者（RocksDB 用於大型狀態）
- [ ] 監控狀態大小並設定警報
- [ ] 已定義遲到資料處理策略（DLQ 或容限）
- [ ] 輸出模式是 "append"（流媒體連接必需）
- [ ] 檢查點位置對每個查詢唯一
- [ ] 冪等寫入已設定（txnVersion/txnAppId）
- [ ] 跨串流規範化時區
- [ ] 追蹤效能指標（輸入速率、狀態大小、水位標記延遲）

## 專家提示

### 事件時間與處理時間

始終為流-流連接使用事件時間：

```python
# ✅ 正確：事件時間（確定性）
.withWatermark("event_time", "10 minutes")

# ❌ 錯誤：處理時間（非確定性）
# 處理時間因系統負載而異
# 結果不可重現
```

### 水位標記語義深潛

了解水位標記行為：

```python
# 水位標記 = 最大事件時間 - 延遲閾值
# 範例：max_event_time = 10:15，延遲 = 10 分鐘
# 水位標記 = 10:05

# 時間戳記 < 10:05 的事件被視為「太遲」
# - 內連接：如果另一方未過期，可能仍會匹配
# - 外連接：水位標記通過後從外側丟棄

# 有效水位標記 = max(左水位標記，右水位標記)
```

### 狀態儲存後端選擇

選擇正確的狀態儲存後端：

```python
# 預設：記憶體中（快速但有限）
# 用於：小狀態（< 10GB）、低基數鍵

# RocksDB：磁碟支持（較慢但可擴展）
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
# 用於：大狀態（> 10GB）、高基數鍵

# 監控狀態大小以決定何時切換
```

### 連接條件最佳實踐

始終包含明確的時間邊界：

```python
# ❌ 不佳：無邊界（狀態永遠增長）
expr("s1.key = s2.key AND s2.ts >= s1.ts")

# ✅ 良好：有邊界（狀態受水位標記限制）
expr("""
    s1.key = s2.key AND
    s2.ts >= s1.ts - interval 5 minutes AND
    s2.ts <= s1.ts + interval 10 minutes
""")

# 為什麼？有邊界的範圍允許狀態清潔
# 無邊界的範圍導致狀態無限增長
```

## 相關技能

- `stream-static-joins` - 使用 Delta 維度表格豐富串流
- `kafka-to-delta` - Kafka 攝取模式
- `watermark-configuration` - 水位標記語義的深潛
- `state-store-management` - 狀態儲存最佳化和監控
