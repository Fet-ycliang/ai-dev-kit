---
name: "streaming-best-practices"
description: "Spark 流媒體生產驗證的最佳實踐：觸發間隔、分割區、檢查點管理和叢集組態，用於可靠的管道。"
tags: ["spark-streaming", "best-practices", "production", "performance", "expert"]
---

# 流媒體最佳實踐專家包

## 概述

從生產經驗蒸餾的完整檢查清單。這些實踐在幾乎所有場景中都應該適用。

**來源**：Canadian Data Guy — "Spark 流媒體最佳實踐"

## 初學者檢查清單

### 1. 始終設定觸發間隔

```python
# ✅ 良好：控制 API 成本和列表操作
stream.writeStream \
    .trigger(processingTime='5 seconds') \
    .start()

# ❌ 不佳：無觸發器表示持續微批次
# 可能導致 S3/ADLS 列表成本過高
```

**為什麼**：快速處理（< 1 秒）重複列表操作，造成非預期成本。

### 2. 使用 Auto Loader 通知模式

```python
# 從檔案列表切換到事件驅動
spark.readStream \
    .format("cloudFiles") \
    .option("cloudFiles.useNotifications", "true") \
    .load("/path/to/data")
```

[Auto Loader 檔案通知模式](https://docs.databricks.com/ingestion/auto-loader/file-notification-mode.html)

### 3. 停用 S3 版本控制

```python
# ❌ 不要在使用 Delta 的 S3 儲存桶上啟用版本控制
# ✅ Delta 有時間旅遊 — 無需 S3 版本控制
# 版本控制在規模上增加顯著延遲
```

### 4. 同地運算和儲存

```python
# ✅ 將運算和儲存保留在相同的區域
# 跨區域 = 延遲 + 傳出成本
```

### 5. 在 Azure 上使用 ADLS Gen2

```python
# ✅ ADLS Gen2 針對大資料分析進行最佳化
# ❌ 常規 blob 儲存 = 效能較慢
```

### 6. 分割區策略

```python
# ✅ 按低基數欄分割：日期、區域、國家
# ❌ 避免高基數：user_id、transaction_id

# 經驗法則：< 100,000 個分割區
# 範例：10 年 × 365 天 × 20 個國家 = 73,000 個分割區 ✅
```

### 7. 為流媒體查詢命名

```python
# ✅ 在 Spark UI 中輕鬆識別
stream.writeStream \
    .option("queryName", "IngestFromKafka") \
    .start()

# 在 Streaming 標籤中顯示為 "IngestFromKafka"
```

### 8. 每個串流一個檢查點

```python
# ✅ 每個串流有自己的檢查點
# ❌ 永不在串流間共用檢查點

# 範例：兩個來源 → 一個目標
# 來源 1 → checkpoint_1 → 目標
# 來源 2 → checkpoint_2 → 目標
```

### 9. 不要多工串流

```python
# ❌ 不要在相同的驅動程式上執行多個串流
# 可能導致穩定性問題

# ✅ 使用獨立的工作或詳細基準測試
```

### 10. 最佳分割區大小

```python
# 目標：記憶體中每個分割區 100-200MB

# 使用以下調整：
.option("maxFilesPerTrigger", "100")
.option("maxBytesPerTrigger", "100MB")

# 在 Spark UI → Stages → 分割區大小中監控
```

### 11. 偏好廣播雜湊連接

```python
# ✅ BroadcastHashJoin 比 SortMergeJoin 快
# Spark 自動廣播 < 100MB 的表格

# 必要時增加閾值：
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "1g")
```

## 進階檢查清單

### 12. 檢查點命名慣例

```python
# 結構：{table_location}/_checkpoints/_{target_table_name}_starting_{identifier}

# 範例：
# 1. 按時間戳記：/delta/events/_checkpoints/_events_starting_2024_01_15
# 2. 按版本：/delta/events/_checkpoints/_events_startingVersion_12345

# 為什麼：表格生命週期上的多個檢查點（升級、邏輯變更）
```

### 13. 最小化 Shuffle Spill

```python
# ✅ 目標：Shuffle spill（磁碟）= 0
# ✅ 只應存在 shuffle 讀取

# 檢查：Spark UI → SQL → Exchange 操作者
# 如果 spill > 0：增加記憶體或減少分割區大小
```

### 14. 對有狀態操作使用 RocksDB

```python
# 對於大型狀態儲存，使用 RocksDB 後端
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
```

### 15. 透過 Kafka Connector 使用事件中樞

```python
# ✅ 為 Azure 事件中樞使用 Kafka 通訊協定
# 分割區處理更靈活

# 注意：使用事件中樞 Kafka 連接器
# 核心數可能與分割區數不同
# （與原生事件中樞比較：核心 == 分割區）
```

### 16. 狀態清潔的水位標記

```python
# ✅ 始終將水位標記用於有狀態作業
# 防止無限狀態增長

stream.withWatermark("timestamp", "10 minutes") \
    .groupBy("user_id") \
    .agg(sum("amount"))

# 例外：如果需要無限狀態，在 Delta + ZORDER 中儲存
```

### 17. 大規模去重

```python
# 在十億記錄規模：
# ✅ Delta merge 優於 dropDuplicates

# dropDuplicates：狀態儲存增長非常大
# Delta merge：使用表格進行查詢

# 範例：
spark.sql("""
    MERGE INTO target t
    USING source s ON t.event_id = s.event_id
    WHEN NOT MATCHED THEN INSERT *
""")
```

### 18. Azure 實例系列選擇

| 工作負載 | 實例系列 |
|----------|----------------|
| 對應繁重（解析、JSON） | F 系列 |
| 來自相同來源的多個串流 | Fsv2 系列 |
| 連接/彙總/最佳化 | DS_v2 系列 |
| Delta 快取 | L 系列（SSD） |

### 19. Shuffle 分割區

```python
# 設定等於總工作程式核心數
spark.conf.set("spark.sql.shuffle.partitions", "200")

# ❌ 不要設定過高
# 如果變更：清除檢查點（儲存舊值）
```

## 快速參考

### 觸發器選擇

| 延遲要求 | 觸發器 |
|---------------------|---------|
| < 1 秒 | 實時模式（RTM） |
| 1-10 秒 | processingTime('5 seconds') |
| 1-60 分鐘 | 基於 SLA/3 的 processingTime |
| 批次樣式 | availableNow=True |

### 叢集大小調整

```python
# 建議為流媒體使用固定大小的叢集
# ❌ 不要為流媒體工作負載使用自動調整

# 為什麼：預先分配的資源 = 可預測的延遲
```

## 監控檢查清單

- [ ] 輸入速率與處理速率（處理 > 輸入）
- [ ] 最大位移落後最新版本（應隨時間下降）
- [ ] 批次持續時間與觸發間隔（存在迴旋空間）
- [ ] 狀態儲存大小（如果使用有狀態作業）
- [ ] Shuffle spill = 0
- [ ] 左連接中的 Null 速率（資料品質）

## 常見錯誤

| 錯誤 | 影響 | 修正 |
|---------|--------|-----|
| 共用檢查點 | 資料遺失/損毀 | 分隔檢查點 |
| 無水位標記 | 狀態爆炸 | 加入水位標記 |
| S3 版本控制 | 延遲 | 停用版本控制 |
| 自動調整叢集 | 不可預測的延遲 | 固定大小的叢集 |
| 高基數分割區 | 檔案小 | 按日期分割 |

## 相關技能

- `spark-streaming-master-class-kafka-to-delta` — 端到端模式
- `mastering-checkpoints-in-spark-streaming` — 檢查點深度潛水
- `scaling-spark-streaming-jobs` — 效能調整
