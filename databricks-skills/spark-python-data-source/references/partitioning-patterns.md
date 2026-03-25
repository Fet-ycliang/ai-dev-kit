# 分割區模式

分配讀取到 Spark 執行器供平行處理的策略。

## 基於時間的分割區

對於具時間序列資料或串流來源的 API。

### 固定持續時間分割區

```python
from pyspark.sql.datasource import InputPartition
from datetime import datetime, timedelta

class TimeRangePartition(InputPartition):
    def __init__(self, start_time, end_time):
        self.start_time = start_time
        self.end_time = end_time

class TimeBasedReader:
    def __init__(self, options, schema):
        self.partition_duration = int(options.get("partition_duration", "3600"))  # 秒
        # 從選項分析開始/結束時間

    def partitions(self):
        """將時間範圍分割成固定持續時間分割區。"""
        partitions = []
        current = self.start_time
        delta = timedelta(seconds=self.partition_duration)

        while current < self.end_time:
            next_time = min(current + delta, self.end_time)
            partitions.append(TimeRangePartition(current, next_time))
            current = next_time

        return partitions

    def read(self, partition):
        """查詢特定時間範圍的資料。"""
        response = self._query_api(
            start=partition.start_time,
            end=partition.end_time
        )
        for item in response:
            yield self._convert_to_row(item)
```

### 自動細分用於大型結果

透過自動細分大型分割區處理結果大小限制的 API：

```python
class AutoSubdivideReader:
    def __init__(self, options, schema):
        self.min_partition_seconds = int(options.get("min_partition_seconds", "60"))
        self.max_retries = int(options.get("max_retries", "5"))

    def read(self, partition):
        """在大小限制錯誤時自動細分進行讀取。"""
        try:
            response = self._execute_query(partition.start_time, partition.end_time)

            # 檢查回應是否因大小限制為部分
            if self._is_size_limit_error(response):
                yield from self._read_with_subdivision(partition)
                return

            yield from self._process_response(response)

        except Exception as e:
            raise

    def _read_with_subdivision(self, partition):
        """遞迴細分大型分割區。"""
        duration = (partition.end_time - partition.start_time).total_seconds()

        if duration <= self.min_partition_seconds:
            raise Exception(
                f"無法進一步細分。持續時間 {duration}s 達最低。"
                f"考慮更具選擇性的查詢或提高 min_partition_seconds。"
            )

        # 分成兩半
        midpoint = partition.start_time + timedelta(seconds=duration / 2)

        first_half = TimeRangePartition(partition.start_time, midpoint)
        second_half = TimeRangePartition(midpoint, partition.end_time)

        yield from self.read(first_half)
        yield from self.read(second_half)

    def _is_size_limit_error(self, response):
        """偵測結果大小限制錯誤。"""
        size_limit_codes = [
            "QueryExecutionResultSizeLimitExceeded",
            "ResponsePayloadTooLarge",
            "E_QUERY_RESULT_SET_TOO_LARGE",
        ]

        if hasattr(response, "error") and response.error:
            if response.error.code in size_limit_codes:
                return True

            error_str = str(response.error).lower()
            return any(p in error_str for p in ["size limit", "too large", "exceed"])

        return False
```

## 權杖範圍分割區

對於使用一致性雜湊的分散式資料庫（Cassandra、ScyllaDB）。

### Cassandra 權杖範圍模式

```python
from collections import namedtuple

class TokenRangePartition(InputPartition):
    def __init__(self, partition_id, start_token, end_token, pk_columns,
                 is_wrap_around=False, min_token=None):
        self.partition_id = partition_id
        self.start_token = start_token  # 無 = 無限制
        self.end_token = end_token      # 無 = 無限制
        self.pk_columns = pk_columns
        self.is_wrap_around = is_wrap_around
        self.min_token = min_token

class TokenRangeReader:
    def _get_token_ranges(self, token_map):
        """從叢集權杖環計算權杖範圍。"""
        if not token_map or not token_map.ring:
            return []

        TokenRange = namedtuple('TokenRange', ['start', 'end'])
        ranges = []
        ring = sorted(token_map.ring)

        for i in range(len(ring)):
            start = ring[i]
            end = ring[(i + 1) % len(ring)]  # 環繞
            ranges.append(TokenRange(start=start, end=end))

        return ranges

    def partitions(self):
        """遵循 TokenRangesScan.java 邏輯建立分割區。"""
        if not self.token_ranges:
            return []

        partitions = []
        sorted_ranges = sorted(self.token_ranges)
        partition_id = 0

        min_token_obj = sorted_ranges[0].start
        min_token = min_token_obj.value if hasattr(min_token_obj, 'value') else str(min_token_obj)

        for i, token_range in enumerate(sorted_ranges):
            start_value = token_range.start.value if hasattr(token_range.start, 'value') else str(token_range.start)
            end_value = token_range.end.value if hasattr(token_range.end, 'value') else str(token_range.end)

            if start_value == end_value:
                # 情況 1：單一節點叢集（整個環）
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=min_token,
                    end_token=None,  # 無限制
                    pk_columns=self.pk_columns,
                    is_wrap_around=True,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

            elif i == 0:
                # 情況 2：第一個範圍 - 分成兩個分割區
                # 分割區 1：token <= minToken（環繞）
                partition1 = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=None,
                    end_token=min_token,
                    pk_columns=self.pk_columns,
                    is_wrap_around=True,
                    min_token=min_token
                )
                partitions.append(partition1)
                partition_id += 1

                # 分割區 2：token > start AND token <= end
                partition2 = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=end_value,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition2)
                partition_id += 1

            elif end_value == min_token:
                # 情況 3：以 minToken 結束的範圍 - 無上界
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=None,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

            else:
                # 情況 4：一般範圍 - 兩個邊界
                partition = TokenRangePartition(
                    partition_id=partition_id,
                    start_token=start_value,
                    end_token=end_value,
                    pk_columns=self.pk_columns,
                    is_wrap_around=False,
                    min_token=min_token
                )
                partitions.append(partition)
                partition_id += 1

        return partitions

    def read(self, partition):
        """使用權杖範圍述詞建立查詢。"""
        pk_cols_str = ", ".join(partition.pk_columns)

        # 根據邊界建立 WHERE 子句
        if partition.start_token is None:
            where_clause = f"token({pk_cols_str}) <= {partition.end_token}"
        elif partition.end_token is None:
            where_clause = f"token({pk_cols_str}) > {partition.start_token}"
        else:
            where_clause = (
                f"token({pk_cols_str}) > {partition.start_token} AND "
                f"token({pk_cols_str}) <= {partition.end_token}"
            )

        query = f"SELECT {columns} FROM {table} WHERE {where_clause}"

        # 執行並產生結果
        for row in self._execute_query(query):
            yield row
```

## 編號範圍分割區

對於具分頁或循序編號的 API。

```python
class IdRangePartition(InputPartition):
    def __init__(self, partition_id, start_id, end_id):
        self.partition_id = partition_id
        self.start_id = start_id
        self.end_id = end_id

class IdRangeReader:
    def __init__(self, options, schema):
        self.num_partitions = int(options.get("num_partitions", "4"))
        self.page_size = int(options.get("page_size", "1000"))

    def partitions(self):
        """按編號範圍分割。"""
        # 從 API 取得總計數
        total = self._get_total_count()
        partition_size = total // self.num_partitions

        partitions = []
        for i in range(self.num_partitions):
            start_id = i * partition_size
            end_id = (i + 1) * partition_size if i < self.num_partitions - 1 else total
            partitions.append(IdRangePartition(i, start_id, end_id))

        return partitions

    def read(self, partition):
        """逐頁瀏覽編號範圍。"""
        current_id = partition.start_id

        while current_id < partition.end_id:
            response = self._query_api(
                start_id=current_id,
                limit=self.page_size
            )

            for item in response.items:
                yield self._convert_to_row(item)

            current_id += self.page_size
```

## 分割區計數指南

**用於批次讀取：**
- 從執行器核心數 2-4 倍開始
- 根據資料量和分割區大小調整
- 考慮外部系統負載限制

**用於串流讀取：**
- 使用固定持續時間分割區（如 1 小時）
- 讓 Spark 處理微批次平行處理
- 平衡延遲與輸送量

**用於權杖範圍：**
- 每個權杖範圍一個分割區（由叢集決定）
- 根據資料分佈自然分佈
- 可能分割第一個範圍成兩個分割區

## 效能考慮

1. **分割區大小**：每個分割區以 128MB - 1GB 為目標
2. **API 速率限制**：使用並行控制尊重速率限制
3. **網路負荷**：更大分割區減少往返次數
4. **偏斜處理**：監控資料偏斜，必要時重新分割
