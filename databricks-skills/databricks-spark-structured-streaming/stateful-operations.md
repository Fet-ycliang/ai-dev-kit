---
name: stateful-operations
description: 為 Spark Structured Streaming 有狀態操作設定水位標記和管理狀態儲存。適用於設定有狀態操作、調整水位標記持續時間、處理延遲到達的資料、為大型狀態設定 RocksDB、監控狀態儲存大小或最佳化狀態效能。
---

# 有狀態操作：水位標記和狀態儲存

設定水位標記以處理延遲到達的資料，並為有狀態流媒體操作管理狀態儲存。水位標記控制狀態清潔，而狀態儲存處理有狀態資料的儲存和檢索。

## 快速開始

```python
# 為大型狀態儲存啟用 RocksDB
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# 具有水位標記的有狀態操作
df = (spark.readStream
    .format("kafka")
    .option("subscribe", "events")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "10 minutes")  # 延遲資料閾值 + 狀態清潔
    .dropDuplicates(["event_id"])  # 有狀態操作
)

# 水位標記 = 最新事件時間 - 10 分鐘
# 狀態在水位標記持續時間後自動過期
```

## 水位標記設定

### 水位標記如何運作

```python
# 水位標記 = 最新事件時間 - 延遲閾值
.withWatermark("event_time", "10 minutes")

# 時間戳記 < 水位標記的事件被視為「太遲」
# 遲到事件的狀態會自動清潔
# 遲到事件可能被丟棄（外連接）或處理（內連接）
```

### 水位標記持續時間選擇

| 水位標記設定 | 效果 | 使用情況 |
|-------------------|--------|----------|
| `"10 minutes"` | 中等延遲 | 一般流媒體 |
| `"1 hour"` | 高完整性 | 金融交易 |
| `"5 minutes"` | 低延遲 | 即時分析 |
| `"24 hours"` | 批次樣式 | 回填情況 |

**經驗法則**：從 2-3 倍的 p95 延遲開始。監控遲到資料速率並調整。

### 水位標記和狀態大小

```python
# 水位標記直接影響狀態儲存大小
# 狀態保留期間 = 水位標記持續時間 + 處理時間

# 範例計算：
# - 10 分鐘水位標記
# - 每分鐘 1M 個事件
# - 狀態大小 = ~10M 鍵 × 鍵大小

# 減少水位標記以減少狀態大小
.withWatermark("event_time", "5 minutes")  # 更小的狀態

# 狀態在水位標記持續時間後自動過期
# 無需手動清潔
```

## 狀態儲存設定

### 啟用 RocksDB

對於超過記憶體容量的狀態儲存使用 RocksDB：

```python
# 啟用 RocksDB 狀態儲存提供者
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# 優勢：
# - 狀態儲存在磁碟上，減少記憶體壓力
# - 建議用於：高基數鍵、長水位標記持續時間
# - 大型狀態儲存的更好效能
```

### 狀態儲存設定

```python
# 狀態儲存批次保留
spark.conf.set("spark.sql.streaming.stateStore.minBatchesToRetain", "2")

# 狀態維護間隔
spark.conf.set("spark.sql.streaming.stateStore.maintenanceInterval", "5m")

# 狀態儲存位置（預設：checkpoint/state）
# 由 Spark 自動管理
```

## 常見模式

### 模式 1：帶水位標記的基本有狀態操作

```python
# 去重的水位標記
df = (spark.readStream
    .format("kafka")
    .option("subscribe", "events")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "10 minutes")
    .dropDuplicates(["event_id"])
)

# 狀態在水位標記持續時間後過期
# 防止無限狀態增長
```

### 模式 2：連接特定的水位標記調整

為延遲不同的串流使用不同的水位標記：

```python
# 快速來源：5 分鐘水位標記
impressions = (spark.readStream
    .format("kafka")
    .option("subscribe", "impressions")
    .load()
    .select(from_json(col("value").cast("string"), impression_schema).alias("data"))
    .select("data.*")
    .withWatermark("impression_time", "5 minutes")
)

# 較慢來源：15 分鐘水位標記
clicks = (spark.readStream
    .format("kafka")
    .option("subscribe", "clicks")
    .load()
    .select(from_json(col("value").cast("string"), click_schema).alias("data"))
    .select("data.*")
    .withWatermark("click_time", "15 minutes")
)

# 有效水位標記 = max(5, 15) = 15 分鐘
joined = impressions.join(
    clicks,
    expr("""
        impressions.ad_id = clicks.ad_id AND
        clicks.click_time BETWEEN impressions.impression_time AND
                                impressions.impression_time + interval 1 hour
    """),
    "inner"
)
```

### 模式 3：帶水位標記的視窗彙總

```python
from pyspark.sql.functions import window, count, sum, max, current_timestamp

windowed = (df
    .withWatermark("event_time", "10 minutes")
    .groupBy(
        window(col("event_time"), "5 minutes"),
        col("user_id")
    )
    .agg(
        count("*").alias("event_count"),
        sum("value").alias("total_value"),
        max("event_time").alias("latest_event")
    )
    .withColumn("processing_time", current_timestamp())
)

# 當遲到資料到達時使用更新模式獲取更正結果
windowed.writeStream \
    .outputMode("update") \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/windowed") \
    .start("/delta/windowed_metrics")
```

### 模式 4：監控狀態分割區平衡

檢查狀態儲存傾斜：

```python
def check_state_balance(checkpoint_path):
    """檢查狀態儲存分割區平衡"""
    state_df = spark.read.format("statestore").load(f"{checkpoint_path}/state")

    partition_counts = state_df.groupBy("partitionId").count().orderBy(desc("count"))
    partition_counts.show()

    # 計算傾斜
    counts = [row['count'] for row in partition_counts.collect()]
    if counts:
        max_count = max(counts)
        min_count = min(counts)
        skew_ratio = max_count / min_count if min_count > 0 else float('inf')

        print(f"狀態傾斜比率：{skew_ratio:.2f}")
        if skew_ratio > 10:
            print("警告：檢測到高狀態傾斜")
            return False
    return True
```

### 模式 5：監控狀態增長

```python
def monitor_state_growth(checkpoint_path):
    """追蹤狀態儲存增長"""
    state_df = spark.read.format("statestore").load(f"{checkpoint_path}/state")

    # 目前狀態大小
    total_rows = state_df.count()

    print(f"狀態列數：{total_rows}")

    # 檢查過期
    from pyspark.sql.functions import current_timestamp, col
    expired = state_df.filter(col("expirationMs") < current_timestamp().cast("long") * 1000)
    expired_count = expired.count()

    print(f"已過期狀態列數：{expired_count}")
    print(f"活躍狀態列數：{total_rows - expired_count}")
```

## 狀態大小控制

### 使用水位標記

水位標記自動清潔已過期的狀態：

```python
# 狀態在水位標記持續時間後過期
.withWatermark("event_time", "10 minutes")

# 狀態大小 = f(水位標記持續時間、鍵基數)
# 10 分鐘水位標記 × 每分鐘 1M 個事件 = 可管理
# 72 小時水位標記 × 每分鐘 1M 個事件 = 非常大
```

### 降低鍵基數

```python
# 不佳：高基數鍵
.dropDuplicates(["user_id"])  # 數百萬個不同值

# 良好：更低的基數或過期鍵
.dropDuplicates(["session_id"])  # 工作階段自然過期
.dropDuplicates(["event_id", "date"])  # 按日期分割降低基數
```

## 監控

### 程式化狀態監控

```python
# 以程式化方式監控狀態大小
for stream in spark.streams.active:
    progress = stream.lastProgress

    if progress and "stateOperators" in progress:
        for op in progress["stateOperators"]:
            print(f"操作者：{op.get('operatorName', 'unknown')}")
            print(f"狀態列數：{op.get('numRowsTotal', 0)}")
            print(f"狀態記憶體：{op.get('memoryUsedBytes', 0)}")
            print(f"狀態磁碟：{op.get('diskBytesUsed', 0)}")
```

### 追蹤遲到資料速率

```python
# 監控遲到資料影響
late_data_stats = spark.sql("""
    SELECT
        date_trunc('hour', event_time) as hour,
        COUNT(*) as total_events,
        SUM(CASE
            WHEN unix_timestamp(processing_time) - unix_timestamp(event_time) > 600
            THEN 1 ELSE 0
        END) as late_events,
        AVG(unix_timestamp(processing_time) - unix_timestamp(event_time)) as avg_delay_seconds,
        MAX(unix_timestamp(processing_time) - unix_timestamp(event_time)) as max_delay_seconds
    FROM events
    WHERE processing_time >= current_timestamp() - interval 24 hours
    GROUP BY 1
    ORDER BY 1 DESC
""")
```

## 遲到資料分類

| 延遲 | 類別 | 處理 |
|-------|----------|----------|
| < 水位標記 | 準時 | 正常處理 |
| 水位標記 < 延遲 < 2×水位標記 | 遲到 | 與內連接匹配；可能仍會處理 |
| > 2×水位標記 | 非常遲到 | 手動處理的 DLQ |

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **狀態儲存爆炸** | 水位標記過長 | 減少水位標記；歸檔舊狀態 |
| **遲到資料被丟棄** | 水位標記過短 | 增加水位標記；分析延遲模式 |
| **狀態太大** | 高基數鍵或長水位標記 | 降低鍵基數；減少水位標記持續時間 |
| **狀態分割區傾斜** | 不均勻的鍵分佈 | 確保鍵均勻分佈；考慮加鹽 |
| **OOM 錯誤** | 狀態超過記憶體 | 啟用 RocksDB；增加記憶體；減少水位標記 |
| **狀態未過期** | 未設定水位標記 | 將水位標記加入有狀態操作 |

## 狀態儲存復原

```python
# 情況 1：狀態儲存損毀
# 解決方案：刪除狀態資料夾，重新啟動串流
# 狀態將從水位標記重新建置

dbutils.fs.rm("/checkpoints/stream/state", recurse=True)

# 重新啟動串流 - 狀態自動重新建置
# 注意：可能會重新處理水位標記視窗內的部分資料

# 情況 2：狀態儲存太大
# 解決方案：減少水位標記持續時間
.withWatermark("event_time", "5 minutes")  # 從 10 分鐘減少

# 情況 3：狀態分割區不平衡
# 解決方案：確保鍵均勻分佈
# 必要時考慮加鹽鍵
```

## 生產最佳實踐

### 始終為有狀態操作使用水位標記

```python
# 必需：用於有狀態操作的水位標記
df.withWatermark("event_time", "10 minutes").dropDuplicates(["id"])

# 必需：用於彙總的水位標記
df.withWatermark("event_time", "10 minutes").groupBy(...).agg(...)

# 必需：用於流-流連接的水位標記
stream1.withWatermark("ts", "10 min").join(stream2.withWatermark("ts", "10 min"))
```

### 水位標記選擇

```python
# 經驗法則：p95 延遲的 2-3 倍
# 範例：p95 延遲 = 5 分鐘 → 水位標記 = 10-15 分鐘

# 保守開始，根據監控調整
.withWatermark("event_time", "10 minutes")  # 從這裡開始
# 監控遲到資料速率
# 如果遲到事件過多則增加
# 如果狀態太大則減少
```

### 為大型狀態使用 RocksDB

```python
# 如果狀態 > 記憶體容量，啟用 RocksDB
# 典型閾值：> 100M 鍵或 > 10GB 狀態

spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
```

## 生產檢查清單

- [ ] 為所有有狀態操作設定水位標記
- [ ] 水位標記持續時間符合延遲要求（2-3× p95）
- [ ] 為大型狀態儲存啟用 RocksDB
- [ ] 監控狀態大小並設定警報
- [ ] 定期檢查狀態分割區平衡
- [ ] 持續追蹤狀態增長
- [ ] 設定遲到資料監控
- [ ] 記錄復原程序

## 相關技能

- `stream-stream-joins` - 連接中的遲到資料
- `checkpoint-best-practices` - 檢查點和狀態復原
