---
name: trigger-and-cost-optimization
description: 選擇和調整 Spark Structured Streaming 的觸發器以平衡延遲和成本。適用於選擇 processingTime、availableNow 和實時模式（RTM）、計算最佳觸發間隔、透過叢集調整大小、排程流媒體、多串流叢集或管理延遲與成本權衡來最佳化成本。
---

# 觸發器和成本最佳化

選擇和調整觸發器以平衡延遲要求與成本。透過觸發器調整、叢集調整大小、多串流叢集、儲存最佳化和排程執行模式來最佳化流媒體工作成本。

## 快速開始

```python
# 成本最佳化：排程流媒體而非持續
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .trigger(availableNow=True) \  # 處理所有，然後停止
    .start("/delta/target")

# 透過 Databricks 工作排程：每 15 分鐘
# 成本：8 核心叢集上 100 個表格約 $20/天
```

## 觸發器類型

### ProcessingTime 觸發器

按固定間隔處理：

```python
# 每 30 秒處理
.trigger(processingTime="30 seconds")

# 每 5 分鐘處理
.trigger(processingTime="5 minutes")

# 延遲：觸發間隔 + 處理時間
# 成本：持續叢集執行
```

### AvailableNow 觸發器

處理所有可用資料，然後停止：

```python
# 處理所有可用資料，然後停止
.trigger(availableNow=True)

# 透過 Databricks 工作排程：
# - 每 15 分鐘：接近即時
# - 每 4 小時：批次樣式

# 延遲：排程間隔 + 處理時間
# 成本：叢集僅在處理期間執行
```

### 實時模式（RTM）

使用 Photon 的亞秒延遲：

```python
# 實時模式（Databricks 13.3+）
.trigger(realTime=True)

# 要求：
# - 啟用 Photon
# - 固定大小的叢集（無自動調整）
# - 延遲：< 800 毫秒

# 成本：持續叢集和 Photon
```

## 觸發器選擇指南

| 延遲要求 | 觸發器 | 成本 | 使用情況 |
|---------------------|---------|------|----------|
| < 800 毫秒 | RTM | $$$ | 即時分析、警報 |
| 1-30 秒 | processingTime | $$ | 接近即時的儀表板 |
| 15-60 分鐘 | availableNow（排程） | $ | 批次樣式 SLA |
| > 1 小時 | availableNow（排程） | $ | ETL 管道 |

## 觸發器間隔計算

### 經驗法則：SLA / 3

```python
# 從 SLA 計算觸發間隔
business_sla_minutes = 60  # 1 小時 SLA
trigger_interval_minutes = business_sla_minutes / 3  # 20 分鐘

.trigger(processingTime=f"{trigger_interval_minutes} minutes")

# 為什麼 /3？
# - 處理時間緩衝
# - 復原時間緩衝
# - 安全裕度
```

### 範例計算

```python
# 範例 1：1 小時 SLA
sla = 60  # 分鐘
trigger = sla / 3  # 20 分鐘
.trigger(processingTime="20 minutes")

# 範例 2：15 分鐘 SLA
sla = 15  # 分鐘
trigger = sla / 3  # 5 分鐘
.trigger(processingTime="5 minutes")

# 範例 3：即時要求
.trigger(realTime=True)  # < 800 毫秒
```

## 成本最佳化策略

### 策略 1：觸發間隔調整

平衡延遲和成本：

```python
# 較短的間隔 = 更高的成本
.trigger(processingTime="5 seconds")   # 昂貴 - 持續處理

# 較長的間隔 = 更低的成本
.trigger(processingTime="5 minutes")   # 便宜 - 不頻繁處理

# 使用 availableNow 進行批次樣式（最便宜）
.trigger(availableNow=True)            # 處理待辦項目，然後停止

# 經驗法則：SLA / 3
# 範例：1 小時 SLA → 20 分鐘觸發
```

### 策略 2：排程與持續

根據 SLA 選擇執行模式：

| 模式 | 成本 | 延遲 | 使用情況 |
|---------|------|---------|----------|
| 持續 | $$$ | < 1 分鐘 | 即時要求 |
| 15 分鐘排程 | $$ | 15-30 分鐘 | 接近即時 |
| 4 小時排程 | $ | 4-5 小時 | 批次樣式 SLA |

```python
# 持續（昂貴）
.trigger(processingTime="30 seconds")

# 排程（成本效益）
.trigger(availableNow=True)  # 排程透過工作：每 15 分鐘

# 批次樣式（最便宜）
.trigger(availableNow=True)  # 排程透過工作：每 4 小時
```

### 策略 3：叢集調整大小

根據工作負載調整叢集大小：

```python
# 不要過度調整大小：
# - 監控 CPU 使用率（目標 60-80%）
# - 檢查空閒時間
# - 為流媒體使用固定大小的叢集（無自動調整）

# 調整規模測試方法：
# 1. 從小開始
# 2. 監控延遲（最大位移落後最新）
# 3. 如果落後則調整規模
# 4. 根據穩定狀態調整大小
```

### 策略 4：多串流叢集

在一個叢集上執行多個串流：

```python
# 在一個叢集上執行多個串流
# 已測試：8 核心單一節點叢集上的 100 個串流
# 成本：100 個表格約 $20/天

# 範例：同一叢集上的多個串流
stream1.writeStream.option("checkpointLocation", "/checkpoints/stream1").start()
stream2.writeStream.option("checkpointLocation", "/checkpoints/stream2").start()
stream3.writeStream.option("checkpointLocation", "/checkpoints/stream3").start()
# ... 最多 100+ 個串流

# 監控：每個串流的 CPU/記憶體
# 如果彙總使用率 > 80%，調整叢集大小
```

### 策略 5：儲存最佳化

減少儲存成本：

```sql
-- VACUUM 舊檔案
VACUUM table RETAIN 24 HOURS;

-- 啟用自動最佳化以減少小檔案
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- 將舊資料歸檔到更便宜的儲存
-- 使用資料保留原則
```

## 成本公式

```
每日成本 =
    (叢集 DBU/小時 × 執行小時數) +
    (儲存 GB × 儲存速率) +
    (網路傳出，如適用)

最佳化槓桿：
- 減少執行小時數（排程觸發器）
- 減少叢集大小（調整大小）
- 減少儲存（VACUUM、壓縮）
- 減少網路傳出（同地運算和儲存）
```

## 常見模式

### 模式 1：成本最佳化的排程流媒體

將持續轉換為排程：

```python
# 之前：持續（昂貴）
df.writeStream \
    .trigger(processingTime="30 seconds") \
    .start()

# 之後：排程（成本效益）
df.writeStream \
    .trigger(availableNow=True) \  # 處理所有，然後停止
    .start()

# 透過 Databricks 工作排程：
# - 每 15 分鐘：接近即時
# - 每 4 小時：批次樣式
# 相同的程式碼，不同的排程
```

### 模式 2：多串流叢集

最佳化叢集使用率：

```python
# 在一個叢集上執行多個串流
def start_all_streams():
    streams = []

    # 啟動多個串流
    for i in range(100):
        stream = (spark
            .readStream
            .table(f"source_{i}")
            .writeStream
            .format("delta")
            .option("checkpointLocation", f"/checkpoints/stream_{i}")
            .trigger(availableNow=True)
            .start(f"/delta/target_{i}")
        )
        streams.append(stream)

    return streams

# 監控彙總 CPU/記憶體
# 如果需要，調整叢集大小
```

### 模式 3：亞秒延遲的 RTM

對即時要求使用 RTM：

```python
# 亞秒延遲的實時模式
df.writeStream \
    .format("kafka") \
    .option("topic", "output") \
    .trigger(realTime=True) \
    .start()

# 必需的組態：
spark.conf.set("spark.databricks.photon.enabled", "true")
spark.conf.set("spark.sql.streaming.stateStore.providerClass",
               "com.databricks.sql.streaming.state.RocksDBStateProvider")

# 延遲：< 800 毫秒
# 成本：持續叢集和 Photon
```

## 實時模式（RTM）設定

### 啟用 RTM

```python
# 啟用實時模式
.trigger(realTime=True)

# 必需的組態：
spark.conf.set("spark.databricks.photon.enabled", "true")
spark.conf.set("spark.sql.streaming.stateStore.providerClass",
               "com.databricks.sql.streaming.state.RocksDBStateProvider")

# 叢集要求：
# - 固定大小的叢集（無自動調整）
# - 啟用 Photon
# - 驅動程式：最少 4 核心
```

### RTM 使用情況

```python
# RTM 適合：
# - 亞秒延遲要求
# - 簡單的轉換
# - 無狀態操作
# - Kafka 到 Kafka 管道

# RTM 不建議用於：
# - 有狀態操作（彙總、連接）
# - 複雜的轉換
# - 大型批次大小
```

## 效能考慮

### 批次持續時間與觸發間隔

```python
# 批次持續時間應該 < 觸發間隔
# 範例：
trigger_interval = 30  # 秒
batch_duration = 10  # 秒

# 健康：batch_duration < trigger_interval
# 不健康：batch_duration >= trigger_interval

# 在 Spark UI 中監控：
# - 批次持續時間
# - 觸發間隔
# - 如果批次持續時間 >= 觸發間隔，發出警報
```

### 觸發間隔調整

```python
# 從保守開始，根據監控最佳化
# 步驟 1：從 SLA / 3 開始
trigger_interval = business_sla / 3

# 步驟 2：監控批次持續時間
# 如果批次持續時間 < 觸發間隔 / 2：可以增加觸發
# 如果批次持續時間 >= 觸發間隔：降低觸發

# 步驟 3：最佳化成本與延遲
# 增加觸發間隔以降低成本
# 降低觸發間隔以降低延遲
```

## 成本監控

### 追蹤每流成本

```python
# 使用串流名稱標籤工作
job_tags = {
    "stream_name": "orders_stream",
    "environment": "prod",
    "cost_center": "analytics"
}

# 使用 DBU 消費指標
# 按工作區/叢集監控
# 追蹤一段時間內每個串流的成本
```

### 監控叢集使用率

```python
# 檢查 CPU 使用率
# 目標：60-80% 使用率
# 低於 60%：考慮向下調整
# 高於 80%：考慮向上調整

# 檢查記憶體使用率
# 監控 OOM 錯誤
# 根據需要調整叢集大小
```

## 延遲與成本權衡

### 持續處理

```python
# 高成本、低延遲
.trigger(processingTime="30 seconds")

# 成本：持續叢集執行
# 延遲：30 秒 + 處理時間
# 使用時機：即時要求
```

### 排程處理

```python
# 更低的成本、更高的延遲
.trigger(availableNow=True)  # 排程：每 15 分鐘

# 成本：叢集僅在處理期間執行
# 延遲：排程間隔 + 處理時間
# 使用時機：批次樣式 SLA 可接受
```

### 實時模式

```python
# 最高成本、最低延遲
.trigger(realTime=True)

# 成本：持續叢集和 Photon
# 延遲：< 800 毫秒
# 使用時機：亞秒延遲需要
```

## 常見問題

| 問題 | 原因 | 解決方案 |
|-------|-------|----------|
| **延遲過高** | 觸發間隔過長 | 減少觸發間隔或使用 RTM |
| **成本過高** | 持續處理 | 使用排程（availableNow） |
| **批次持續時間 > 觸發** | 處理太慢 | 最佳化處理或增加觸發 |
| **RTM 無法工作** | Photon 未啟用 | 啟用 Photon 並設定叢集 |

## 快速勝利

1. **從持續改為 15 分鐘排程** - 顯著降低成本
2. **在一個叢集上執行多個串流** - 更好的叢集使用率
3. **啟用自動最佳化** - 減少儲存成本
4. **使用 Spot 實例** - 用於非關鍵串流（謹慎）
5. **歸檔舊資料** - 移至更便宜的儲存層

## 權衡

| 成本降低 | 影響 | 緩解 |
|----------------|--------|------------|
| 更長的觸發 | 更高的延遲 | 可接受（如果 SLA 允許） |
| 更小的叢集 | 可能落後 | 監控延遲；需要時調整 |
| 激進的 VACUUM | 較少時間旅遊 | 平衡保留與成本 |
| Spot 實例 | 可能中斷 | 用於非關鍵串流 |
| 排程與持續 | 更高的延遲 | 符合業務 SLA |

## 生產最佳實踐

### 符合觸發器與 SLA

```python
# 從業務 SLA 計算觸發
def calculate_trigger_interval(sla_minutes):
    """計算最佳觸發間隔"""
    return max(30, sla_minutes / 3)  # 最少 30 秒

trigger_interval = calculate_trigger_interval(business_sla_minutes)
.trigger(processingTime=f"{trigger_interval} seconds")
```

### 叢集設定

```python
# 固定大小的叢集（流媒體無自動調整）
cluster_config = {
    "num_workers": 4,
    "node_type_id": "i3.xlarge",
    "autotermination_minutes": 60,  # 如果空閒則終止
    "enable_elastic_disk": True  # 減少儲存成本
}
```

### 儲存管理

```sql
-- 啟用自動最佳化
ALTER TABLE table SET TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = true,
    'delta.autoOptimize.autoCompact' = true
);

-- 定期 VACUUM
VACUUM table RETAIN 7 DAYS;  -- 平衡保留與成本

-- 歸檔舊分割區
-- 移至更便宜的儲存層
```

## 生產檢查清單

- [ ] 根據延遲要求選擇觸發器類型
- [ ] 從 SLA（SLA / 3）計算觸發間隔
- [ ] 監控批次持續時間（< 觸發間隔）
- [ ] 叢集適當調整大小（60-80% 使用率）
- [ ] 多個串流每個叢集（如適用）
- [ ] 排程執行（如果 SLA 允許）
- [ ] 配置 RTM（如果需要亞秒延遲）
- [ ] 啟用自動最佳化
- [ ] 監控儲存成本
- [ ] 追蹤每個串流的成本

## 相關技能

- `kafka-streaming` - Kafka 管道的 RTM 設定
- `checkpoint-best-practices` - 檢查點管理
