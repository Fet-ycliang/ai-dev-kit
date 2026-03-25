# 錯誤處理和復原力

重試、斷路器和優雅降級的模式。

## 指數退避

使用指數退避進行暫時性失敗重試：

```python
def write_with_retry(self, iterator):
    """使用指數退避進行寫入。"""
    import time

    max_retries = int(self.options.get("max_retries", "5"))
    initial_backoff = float(self.options.get("initial_backoff", "1.0"))
    max_backoff = float(self.options.get("max_backoff", "60.0"))

    for row in iterator:
        retry_count = 0

        while retry_count <= max_retries:
            try:
                self._send_data(row)
                break  # 成功

            except Exception as e:
                if not self._is_retryable_error(e):
                    # 不可重試的錯誤 - 立即失敗
                    raise

                if retry_count >= max_retries:
                    # 超過最大重試次數
                    raise Exception(f"超過最大重試次數 ({max_retries})：{e}")

                # 計算指數增長的退避
                backoff = min(initial_backoff * (2 ** retry_count), max_backoff)
                time.sleep(backoff)
                retry_count += 1

def _is_retryable_error(self, error):
    """判斷錯誤是否可重試。"""
    from requests.exceptions import RequestException, Timeout, ConnectionError

    # 網路錯誤可重試
    if isinstance(error, (Timeout, ConnectionError)):
        return True

    # HTTP 錯誤
    if hasattr(error, 'response') and error.response:
        status_code = error.response.status_code
        # 在 429（限流）和 5xx（伺服器錯誤）時重試
        if status_code == 429 or 500 <= status_code < 600:
            return True

    return False
```

## 尊重限流的重試

使用 Retry-After 標頭處理 API 速率限制：

```python
def write_with_throttling(self, iterator):
    """尊重速率限制進行寫入。"""
    import time
    from requests.exceptions import HTTPError

    for row in iterator:
        max_attempts = 5
        attempt = 0

        while attempt < max_attempts:
            try:
                self._send_data(row)
                break

            except HTTPError as e:
                if e.response.status_code == 429:
                    # 限流 - 尊重 Retry-After 標頭
                    retry_after = self._get_retry_after(e.response)
                    time.sleep(retry_after)
                    attempt += 1
                else:
                    raise

        if attempt >= max_attempts:
            raise Exception("超過限流重試嘗試次數上限")

def _get_retry_after(self, response):
    """從 Retry-After 標頭萃取重試延遲。"""
    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            # 嘗試作為秒數 (int)
            return int(retry_after)
        except ValueError:
            # 嘗試作為 HTTP 日期
            from datetime import datetime
            try:
                retry_date = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT")
                delay = (retry_date - datetime.utcnow()).total_seconds()
                return max(0, delay)
            except ValueError:
                pass

    # 預設回復
    return 1.0
```

## 斷路器

使用斷路器模式防止級聯失敗：

```python
class CircuitBreaker:
    """防止級聯失敗的斷路器。"""

    def __init__(self, threshold=10, timeout=300):
        self.threshold = threshold  # 開啟前的失敗次數
        self.timeout = timeout  # 重試前的秒數
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until = None

    def record_success(self):
        """記錄成功操作。"""
        self.consecutive_failures = 0

    def record_failure(self):
        """記錄失敗操作。"""
        from datetime import datetime, timedelta

        self.consecutive_failures += 1

        if self.consecutive_failures >= self.threshold:
            self.circuit_open = True
            self.circuit_open_until = datetime.now() + timedelta(seconds=self.timeout)

    def is_open(self):
        """檢查斷路器是否開啟。"""
        from datetime import datetime

        if self.circuit_open:
            if datetime.now() >= self.circuit_open_until:
                # 逾時已過期 - 重試
                self.circuit_open = False
                self.consecutive_failures = 0
                return False
            return True

        return False

class ResilientWriter:
    def __init__(self, options):
        self.circuit_breaker = CircuitBreaker(
            threshold=int(options.get("circuit_breaker_threshold", "10")),
            timeout=int(options.get("circuit_breaker_timeout", "300"))
        )

    def write(self, iterator):
        """使用斷路器保護進行寫入。"""
        for row in iterator:
            if self.circuit_breaker.is_open():
                raise Exception("斷路器開啟 - 太多失敗")

            try:
                self._send_data(row)
                self.circuit_breaker.record_success()

            except Exception as e:
                self.circuit_breaker.record_failure()
                raise
```

## 優雅降級

處理部分失敗和回復策略：

```python
def read_with_fallback(self, partition):
    """具備次要來源回復的讀取。"""
    try:
        # 嘗試主要來源
        yield from self._read_primary(partition)

    except ConnectionError as e:
        # 主要失敗 - 嘗試次要
        if self.secondary_endpoint:
            print(f"主要失敗，使用次要：{e}")
            yield from self._read_secondary(partition)
        else:
            raise

    except TimeoutError as e:
        # 逾時 - 嘗試更小分割區
        if partition.can_subdivide():
            print(f"逾時，細分：{e}")
            for sub_partition in partition.subdivide():
                yield from self.read(sub_partition)
        else:
            raise

    except PartialResultError as e:
        # 部分結果 - 記錄警告並繼續
        print(f"警告：分割區 {partition.id} 的部分結果：{e}")
        yield from e.partial_results
```

## 批次操作錯誤處理

處理批次操作中的錯誤：

```python
def write_batch_with_error_handling(self, iterator):
    """具個別錯誤追蹤的批次寫入。"""
    from cassandra.concurrent import execute_concurrent_with_args

    batch_size = int(self.options.get("batch_size", "1000"))
    fail_on_first_error = self.options.get("fail_on_first_error", "true").lower() == "true"

    batch_params = []
    failed_rows = []

    for row in iterator:
        batch_params.append(self._row_to_params(row))

        if len(batch_params) >= batch_size:
            # 執行批次
            results = execute_concurrent_with_args(
                self.session,
                self.prepared_statement,
                batch_params,
                concurrency=100,
                raise_on_first_error=fail_on_first_error
            )

            # 檢查失敗
            for success, result_or_error in results:
                if not success:
                    failed_rows.append((batch_params[i], result_or_error))

            batch_params = []

    # 最後批次
    if batch_params:
        results = execute_concurrent_with_args(
            self.session,
            self.prepared_statement,
            batch_params,
            concurrency=100,
            raise_on_first_error=fail_on_first_error
        )

        for i, (success, result_or_error) in enumerate(results):
            if not success:
                failed_rows.append((batch_params[i], result_or_error))

    # 處理失敗列
    if failed_rows:
        if fail_on_first_error:
            raise Exception(f"{len(failed_rows)} 列無法寫入")
        else:
            # 記錄失敗但繼續
            print(f"警告：{len(failed_rows)} 列無法寫入")
```

## 死信佇列

儲存失敗記錄供稍後處理：

```python
class DeadLetterQueueWriter:
    """具死信佇列的寫入器（用於失敗記錄）。"""

    def __init__(self, options):
        self.dlq_path = options.get("dlq_path")
        self.dlq_enabled = bool(self.dlq_path)

    def write(self, iterator):
        """具 DLQ 支援的寫入。"""
        from datetime import datetime
        import json

        successful = 0
        failed = 0

        for row in iterator:
            try:
                self._send_data(row)
                successful += 1

            except Exception as e:
                failed += 1

                if self.dlq_enabled:
                    self._write_to_dlq(row, e)
                else:
                    raise

        return {
            "successful": successful,
            "failed": failed
        }

    def _write_to_dlq(self, row, error):
        """將失敗記錄寫入死信佇列。"""
        from datetime import datetime
        import json
        import os

        dlq_record = {
            "timestamp": datetime.now().isoformat(),
            "error": str(error),
            "error_type": type(error).__name__,
            "row": row.asDict()
        }

        # 附加到 DLQ 檔案
        os.makedirs(os.path.dirname(self.dlq_path), exist_ok=True)

        with open(self.dlq_path, 'a') as f:
            f.write(json.dumps(dlq_record) + '\n')
```

## 逾時處理

強制操作逾時：

```python
import signal
from contextlib import contextmanager

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("操作已逾時")

@contextmanager
def timeout(seconds):
    """操作逾時的環境管理器。"""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

class TimeoutWriter:
    def write(self, iterator):
        """具各列逾時的寫入。"""
        timeout_seconds = int(self.options.get("write_timeout", "30"))

        for row in iterator:
            try:
                with timeout(timeout_seconds):
                    self._send_data(row)

            except TimeoutError:
                print(f"寫入在 {timeout_seconds} 秒後逾時")
                raise
```

## 錯誤彙總

系統地收集並報告錯誤：

```python
class ErrorAggregator:
    """用於批次報告的錯誤彙總器。"""

    def __init__(self):
        self.errors = []
        self.error_counts = {}

    def record_error(self, error, context=None):
        """記錄具內容的錯誤。"""
        error_type = type(error).__name__
        error_msg = str(error)

        self.errors.append({
            "type": error_type,
            "message": error_msg,
            "context": context
        })

        # 按類型計數
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    def get_summary(self):
        """取得錯誤摘要。"""
        return {
            "total_errors": len(self.errors),
            "by_type": self.error_counts,
            "sample_errors": self.errors[:10]  # 前 10 個
        }

class ErrorAwareWriter:
    def write(self, iterator):
        """具錯誤彙總的寫入。"""
        aggregator = ErrorAggregator()
        successful = 0

        for i, row in enumerate(iterator):
            try:
                self._send_data(row)
                successful += 1

            except Exception as e:
                aggregator.record_error(e, context={"row_index": i})

        # 報告摘要
        if aggregator.errors:
            summary = aggregator.get_summary()
            print(f"完成 {successful} 成功、{summary['total_errors']} 錯誤")
            print(f"錯誤細分：{summary['by_type']}")

            if summary['total_errors'] > successful:
                raise Exception(f"太多錯誤：{summary}")
```

## 最佳實踐

1. **僅重試暫時性錯誤**：不重試客戶端錯誤 (4xx)
2. **尊重速率限制**：使用 Retry-After 標頭和退避
3. **斷路器**：防止分散式系統中的級聯失敗
4. **逾時操作**：設定合理逾時以防止掛起
5. **記錄錯誤**：捕捉錯誤內容供偵錯
6. **死信佇列**：儲存失敗記錄供稍後分析
7. **監控失敗率**：在異常錯誤率時發出警告
8. **優雅降級**：在適當時繼續使用部分結果
