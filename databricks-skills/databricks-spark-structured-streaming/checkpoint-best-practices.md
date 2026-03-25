---
name: checkpoint-best-practices
description: 為可靠的 Spark Structured Streaming 設定並管理 checkpoint 位置。用於設定新的串流作業、疑難排解 checkpoint 問題、遷移 checkpoint，或透過適當的 checkpoint 儲存與組織方式確保 exactly-once 語意。
---

# Checkpoint 最佳實務

為可靠串流設定 checkpoint 位置，以實現 exactly-once 語意。Checkpoint 會追蹤進度並提供容錯能力。

## 快速開始

```python
def get_checkpoint_location(table_name):
    """與目標資料表綁定的 Checkpoint"""
    return f"/Volumes/catalog/checkpoints/{table_name}"

# 範例：
# 資料表：prod.analytics.orders
# Checkpoint：/Volumes/prod/checkpoints/orders

query = (df
    .writeStream
    .format("delta")
    .option("checkpointLocation", get_checkpoint_location("orders"))
    .start("/delta/orders")
)
```

## Checkpoint 儲存

### 使用持久化儲存

```python
# 建議：使用 Unity Catalog Volumes（由 S3/ADLS 支援）
checkpoint_path = "/Volumes/catalog/checkpoints/stream_name"

# 不要：使用 DBFS（暫時性、工作區本機）
checkpoint_path = "/dbfs/checkpoints/stream_name"  # 避免
```

### 與目標綁定的組織方式

```python
def get_checkpoint_location(table_name):
    """Checkpoint 應綁定 TARGET，而不是 source"""
    return f"/Volumes/catalog/checkpoints/{table_name}"

# 為什麼要與目標綁定？
# - Checkpoint 已經包含來源資訊
# - 有系統的組織方式
# - 容易備份與還原
# - 擁有權清楚
```

### 每個 Stream 都要有唯一的 Checkpoint

```python
# 正確：每個 stream 都有自己的 checkpoint
stream1.writeStream \
    .option("checkpointLocation", "/checkpoints/stream1") \
    .start()

stream2.writeStream \
    .option("checkpointLocation", "/checkpoints/stream2") \
    .start()

# 錯誤：絕對不要在多個 stream 之間共用 checkpoint
# 這會導致資料遺失與損毀
```

## Checkpoint 結構

### 資料夾內容

```
checkpoint_location/
├── metadata/      # Query ID
├── offsets/       # 要處理的內容（意圖）
├── commits/       # 已完成的內容（確認）
├── sources/       # 來源中繼資料
└── state/         # 有狀態運算（如果有）
```

### 無狀態與有狀態

```python
# 無狀態（從 Kafka 讀取，寫入 Delta）
# Checkpoint：metadata、offsets、commits、sources
# 沒有 state 資料夾

df = (spark.readStream
    .format("kafka")
    .option("subscribe", "topic")
    .load())

# 有狀態（含 watermark 與去重複）
# Checkpoint：額外包含 state 資料夾
df_stateful = (df
    .withWatermark("timestamp", "10 minutes")
    .dropDuplicates(["partition", "offset"])
)
```

## 讀取 Checkpoint 內容

### 讀取 Offset 檔案

```python
import json

# 讀取 offset 檔案
offset_file = "/checkpoints/stream/offsets/223"
content = dbutils.fs.head(offset_file)
offset_data = json.loads(content)

# 美化輸出
print(json.dumps(offset_data, indent=2))

# 重要欄位：
# - batchWatermarkMs：Watermark 時間戳記
# - batchTimestampMs：Batch 啟動時間
# - source[0].startOffset：Batch 起始位置（含）
# - source[0].endOffset：Batch 結束位置（不含）
# - source[0].latestOffset：來源中的目前位置
```

### 讀取 State Store

```python
# 直接查詢 state store
state_df = (spark
    .read
    .format("statestore")
    .load("/checkpoints/stream/state")
)

state_df.show()
# 顯示：key、value、partitionId、expiration timestamp

# 讀取 state 中繼資料
state_metadata = (spark
    .read
    .format("state-metadata")
    .load("/checkpoints/stream")
)
state_metadata.show()
# 顯示：operatorName、numPartitions、minBatchId、maxBatchId
```

## 復原情境

### Checkpoint 遺失

```python
# 復原步驟：
# 1. 刪除 checkpoint 資料夾
dbutils.fs.rm("/checkpoints/stream", recurse=True)

# 2. 使用 startingOffsets=earliest 重新啟動 stream
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .option("startingOffsets", "earliest") \
    .start()

# 3. Stream 會從頭重新處理
# 4. Delta sink 會處理去重複（若已設定冪等寫入）
```

### Checkpoint 損毀

```python
# 與 checkpoint 遺失相同：
# 1. 刪除 checkpoint 資料夾
# 2. 以 startingOffsets=earliest 重新啟動
# 3. 或在有備份時從備份還原

# 在重大變更前備份 checkpoint
dbutils.fs.cp(
    "/checkpoints/stream",
    "/checkpoints/stream_backup_20240101",
    recurse=True
)
```

### Batch 執行期間當機

```python
# 情境：Batch 處理途中當機
# - Latest offset = 223（在開始時寫入）
# - 缺少 Commit 223（完成前發生當機）
# - 重新啟動時：Spark 會重新處理 offset 223
# - Delta 去重複可避免重複資料（若已設定 txnVersion）
```

## 監控

### Checkpoint 大小

```python
# 追蹤 checkpoint 資料夾大小
checkpoint_size = dbutils.fs.ls("/checkpoints/stream")
total_size = sum([f.size for f in checkpoint_size if f.isFile()])
print(f"Checkpoint 大小：{total_size / (1024*1024):.2f} MB")

# 對 checkpoint 存取失敗發出警示
try:
    dbutils.fs.ls("/checkpoints/stream")
except Exception as e:
    print(f"Checkpoint 存取失敗：{e}")
    # 發送警示
```

### State Store 成長

```python
# 監控 state store 大小（有狀態作業）
state_df = spark.read.format("statestore").load("/checkpoints/stream/state")

# 檢查 partition 是否平衡
state_df.groupBy("partitionId").count().orderBy(desc("count")).show()

# 檢查資料傾斜：若某個 partition 是其他 partition 的 10 倍，就有問題
# State 大小 = f(watermark 持續時間, key cardinality)
```

### Offset 與 Commit 同步

```python
# 檢查 offsets 是否有對應的 commits
import json

# 讀取最新的 offset
latest_offset_file = sorted(dbutils.fs.ls("/checkpoints/stream/offsets"))[-1].path
offset_data = json.loads(dbutils.fs.head(latest_offset_file))
batch_id = latest_offset_file.split("/")[-1]

# 檢查 commit 是否存在
commit_file = f"/checkpoints/stream/commits/{batch_id}"
if dbutils.fs.exists(commit_file):
    print(f"Batch {batch_id}：已提交")
else:
    print(f"Batch {batch_id}：尚未提交（將重新處理）")
```

## 常見問題

| 問題 | 原因 | 解決方式 |
|------|------|----------|
| **State 過度成長** | Watermark 持續時間過長或 key cardinality 過高 | 縮短 watermark 持續時間；降低 key cardinality |
| **Checkpoint 損毀** | 檔案系統問題或手動刪除 | 刪除 checkpoint 並重新啟動；從備份還原 |
| **State 作業緩慢** | Partition 不平衡 | 檢查 partition 平衡；確保 key 均勻分布 |
| **找不到 commit 檔案** | 作業當機時屬正常現象 | Spark 會在重新啟動時重新處理 |
| **Offsets 不同步** | Offset 沒有對應的 commit | 代表有尚未處理的 batch；之後會重新處理 |

## 生產環境最佳實務

### Checkpoint 位置模式

```python
def get_checkpoint_path(table_name, environment="prod"):
    """
    Checkpoint 應該：
    1. 綁定 TARGET 資料表（不是 source）
    2. 位於持久化儲存（UC Volume、S3、ADLS）
    3. 有系統地組織
    """
    return f"/Volumes/{environment}/checkpoints/{table_name}"

# 用法
checkpoint = get_checkpoint_path("orders", "prod")
```

### 備份策略

```python
# 在重大變更前備份 checkpoint
def backup_checkpoint(checkpoint_path, backup_suffix):
    backup_path = f"{checkpoint_path}_backup_{backup_suffix}"
    dbutils.fs.cp(checkpoint_path, backup_path, recurse=True)
    return backup_path

# 在程式碼變更或遷移之前
backup_checkpoint("/checkpoints/stream", "20240101")
```

### 遷移

```python
# 將 checkpoint 遷移到新位置
def migrate_checkpoint(old_path, new_path):
    # 複製 checkpoint 資料夾
    dbutils.fs.cp(old_path, new_path, recurse=True)
    
    # 更新程式碼以使用新路徑
    # 保留舊 checkpoint 以便回復
    
    # 使用新的 checkpoint 位置重新啟動 stream
```

## 生產環境檢查清單

- [ ] Checkpoint 位置為持久化儲存（S3/ADLS，而非 DBFS）
- [ ] 每個 stream 都有唯一的 checkpoint
- [ ] Checkpoint 組織方式與目標綁定
- [ ] 已定義備份策略
- [ ] 已設定監控（checkpoint 大小、存取失敗）
- [ ] 已監控 state store 成長（若為有狀態作業）
- [ ] 已記錄復原程序
- [ ] 已記錄遷移程序

## 相關技能

- `kafka-to-delta` - 具備 checkpoint 管理的 Kafka 擷取
- `stream-stream-joins` - 有狀態運算與 state store
- `state-store-management` - 深入探討 state store 最佳化
