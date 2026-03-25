# 串流模式

用於 exactly-once semantics 的 offset 管理與串流實作模式。

## 基本 Offset 實作

簡單的可 JSON 序列化 offset：

```python
class SimpleOffset:
    """具有單一 timestamp 欄位的基本 offset。"""

    def __init__(self, timestamp):
        self.timestamp = timestamp

    def json(self):
        """序列化為 JSON 字串。"""
        import json
        return json.dumps({"timestamp": self.timestamp})

    @staticmethod
    def from_json(json_str):
        """從 JSON 字串反序列化。"""
        import json
        data = json.loads(json_str)
        return SimpleOffset(data["timestamp"])
```

## 多欄位 Offset

包含多個欄位的複合 offset：

```python
class MultiFieldOffset:
    """包含 timestamp、sequence ID 與 partition 的 offset。"""

    def __init__(self, timestamp, sequence_id, partition_id):
        self.timestamp = timestamp
        self.sequence_id = sequence_id
        self.partition_id = partition_id

    def json(self):
        import json
        return json.dumps({
            "timestamp": self.timestamp,
            "sequence_id": self.sequence_id,
            "partition_id": self.partition_id
        })

    @staticmethod
    def from_json(json_str):
        import json
        data = json.loads(json_str)
        return MultiFieldOffset(
            timestamp=data["timestamp"],
            sequence_id=data["sequence_id"],
            partition_id=data["partition_id"]
        )

    def __lt__(self, other):
        """支援 offset 的排序比較。"""
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        if self.sequence_id != other.sequence_id:
            return self.sequence_id < other.sequence_id
        return self.partition_id < other.partition_id
```

## Stream Reader 實作

具備 offset 管理的完整串流 reader：

```python
from pyspark.sql.datasource import DataSourceStreamReader

class YourStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # 解析起始時間選項
        start_time = options.get("start_time", "latest")

        if start_time == "latest":
            from datetime import datetime, timezone
            self.start_time = datetime.now(timezone.utc).isoformat()

        elif start_time == "earliest":
            # 查詢最早的 timestamp（一次性成本）
            self.start_time = self._get_earliest_timestamp()

        else:
            # 驗證 ISO 8601 格式
            from datetime import datetime
            datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            self.start_time = start_time

        # 分區持續時間（例如 1 小時）
        self.partition_duration = int(options.get("partition_duration", "3600"))

    def _get_earliest_timestamp(self):
        """為 `earliest` 選項找出最早的資料 timestamp。"""
        from datetime import datetime, timezone

        timestamp_column = self.options.get("timestamp_column", "timestamp")
        query = f"{self.query} | summarize earliest=min({timestamp_column})"

        response = self._execute_query(query, timespan=None)

        if response.tables and response.tables[0].rows:
            earliest_value = response.tables[0].rows[0][0]
            if earliest_value:
                if isinstance(earliest_value, datetime):
                    return earliest_value.isoformat()
                return str(earliest_value)

        # fallback 為目前時間
        return datetime.now(timezone.utc).isoformat()

    def initialOffset(self):
        """
        回傳初始 offset（起始時間減去 1 微秒）。

        減去 1µs 是為了搭配 partitions() 方法中的 +1µs，
        以避免批次之間發生重疊。
        """
        from datetime import datetime, timedelta

        start_dt = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
        adjusted = start_dt - timedelta(microseconds=1)
        return SimpleOffset(adjusted.isoformat()).json()

    def latestOffset(self):
        """回傳最新 offset（目前時間）。"""
        from datetime import datetime, timezone

        current_time = datetime.now(timezone.utc).isoformat()
        return SimpleOffset(current_time).json()

    def partitions(self, start, end):
        """
        依 offset 範圍建立不重疊的分區。

        會在起點加上 1µs，以避免與前一個批次重疊。
        """
        from datetime import datetime, timedelta

        start_offset = SimpleOffset.from_json(start)
        end_offset = SimpleOffset.from_json(end)

        start_time = datetime.fromisoformat(start_offset.timestamp.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end_offset.timestamp.replace("Z", "+00:00"))

        # 加上 1µs 以避免與前一個批次重疊
        # 這會搭配 initialOffset() 中的 -1µs，確保：
        # - 初始批次：(start - 1µs) + 1µs = start（正確）
        # - 後續批次：previous_end + 1µs（不重疊）
        start_time = start_time + timedelta(microseconds=1)

        # 建立固定持續時間的分區
        partitions = []
        current = start_time
        delta = timedelta(seconds=self.partition_duration)

        while current < end_time:
            next_time = min(current + delta, end_time)
            partitions.append(TimeRangePartition(current, next_time))
            current = next_time + timedelta(microseconds=1)  # 不重疊

        return partitions if partitions else [TimeRangePartition(start_time, end_time)]

    def commit(self, end):
        """當批次成功處理後呼叫。"""
        # Spark 會處理 checkpointing；通常不需要額外動作
        pass

    def read(self, partition):
        """讀取指定分區時間範圍內的資料。"""
        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )

        for item in response:
            yield self._convert_to_row(item)
```

## Watermarking 支援

支援事件時間 watermarking：

```python
class WatermarkedStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # watermark 設定
        self.watermark_column = options.get("watermark_column")
        self.watermark_delay = options.get("watermark_delay", "10 minutes")

    def read(self, partition):
        """以事件時間 watermarking 方式讀取。"""
        from datetime import datetime

        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )

        for item in response:
            row = self._convert_to_row(item)

            # 驗證 watermark 欄位存在
            if self.watermark_column:
                if not hasattr(row, self.watermark_column):
                    raise ValueError(
                        f"在資料列中找不到 watermark 欄位 '{self.watermark_column}'"
                    )

                # 確保 watermark 欄位是 timestamp
                watermark_value = getattr(row, self.watermark_column)
                if not isinstance(watermark_value, datetime):
                    raise ValueError(
                        f"watermark 欄位必須是 timestamp，實際為 {type(watermark_value)}"
                    )

            yield row
```

## 狀態式串流

跨批次追蹤狀態：

```python
class StatefulStreamReader(DataSourceStreamReader):
    def __init__(self, options, schema):
        super().__init__(options, schema)

        # 狀態管理
        self.checkpoint_location = options.get("checkpoint_location")
        self._state = {}

    def _load_state(self):
        """從 checkpoint 位置載入狀態。"""
        import json
        import os

        if not self.checkpoint_location:
            return {}

        state_file = os.path.join(self.checkpoint_location, "reader_state.json")

        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)

        return {}

    def _save_state(self):
        """將狀態儲存到 checkpoint 位置。"""
        import json
        import os

        if not self.checkpoint_location:
            return

        os.makedirs(self.checkpoint_location, exist_ok=True)
        state_file = os.path.join(self.checkpoint_location, "reader_state.json")

        with open(state_file, 'w') as f:
            json.dump(self._state, f)

    def initialOffset(self):
        """載入狀態並回傳初始 offset。"""
        self._state = self._load_state()

        # 檢查是否已有先前狀態
        if "last_offset" in self._state:
            return self._state["last_offset"]

        # 第一次執行 - 使用設定的起始時間
        return self._create_initial_offset()

    def commit(self, end):
        """在批次成功後儲存狀態。"""
        self._state["last_offset"] = end
        self._state["last_commit_time"] = datetime.now().isoformat()
        self._save_state()
```

## Exactly-Once 語意

透過冪等寫入確保 exactly-once 投遞語意：

```python
class ExactlyOnceWriter(DataSourceStreamWriter):
    def __init__(self, options, schema):
        super().__init__(options, schema)
        self.enable_idempotency = options.get("enable_idempotency", "true").lower() == "true"

    def write(self, iterator):
        """使用冪等鍵進行寫入。"""
        import hashlib
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()
        batch_id = getattr(context, 'batchId', lambda: 0)()

        for row in iterator:
            # 以 batch_id + partition_id + 資料列內容產生冪等鍵
            row_dict = row.asDict()

            if self.enable_idempotency:
                idempotency_key = self._generate_idempotency_key(
                    batch_id,
                    partition_id,
                    row_dict
                )
                row_dict["_idempotency_key"] = idempotency_key

            # 搭配冪等檢查寫入
            self._write_with_idempotency_check(row_dict)

    def _generate_idempotency_key(self, batch_id, partition_id, row_dict):
        """產生具決定性的冪等鍵。"""
        import hashlib
        import json

        key_data = {
            "batch_id": batch_id,
            "partition_id": partition_id,
            "row": row_dict
        }

        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _write_with_idempotency_check(self, row_dict):
        """僅在冪等鍵尚未出現時才寫入。"""
        idempotency_key = row_dict.get("_idempotency_key")

        if idempotency_key:
            # 檢查是否已經寫入（實作方式取決於目標系統）
            if self._is_already_written(idempotency_key):
                return  # 跳過重複資料

        # 寫入資料
        self._write_data(row_dict)

    def commit(self, messages, batchId):
        """在所有寫入成功後提交批次。"""
        # 記錄成功的批次
        print(f"批次 {batchId} 已成功提交")

    def abort(self, messages, batchId):
        """處理失敗的批次。"""
        # 記錄失敗的批次
        print(f"批次 {batchId} 已中止")
```

## 監控與進度

追蹤串流處理進度：

```python
class MonitoredStreamReader(DataSourceStreamReader):
    def read(self, partition):
        """在讀取時追蹤進度。"""
        from datetime import datetime

        start_time = datetime.now()
        row_count = 0

        for row in self._read_partition(partition):
            row_count += 1
            yield row

        duration = (datetime.now() - start_time).total_seconds()

        # 記錄指標
        self._log_partition_metrics(
            partition_id=partition.partition_id,
            row_count=row_count,
            duration=duration
        )

    def _log_partition_metrics(self, partition_id, row_count, duration):
        """記錄分區處理指標。"""
        print(f"分區 {partition_id}：{row_count} 筆資料，用時 {duration:.2f}s")
```

## 最佳實務

1. **不重疊分區**：使用微秒調整避免重複資料
2. **冪等性**：產生具決定性的鍵以實現 exactly-once 語意
3. **狀態管理**：將 offsets 儲存在 Spark checkpoints 中
4. **Watermarking**：支援事件時間處理以處理延遲到達的資料
5. **監控**：追蹤批次進度與 lag 指標
6. **錯誤處理**：串流 writers 會持續執行，因此特別容易受到暫時性失敗（網路抖動、rate limits）影響。請在 `write()` 方法中使用 [error-handling.md](error-handling.md) 的指數退避重試模式。
7. **Backpressure**：使用適當的分區大小來遵守速率限制
