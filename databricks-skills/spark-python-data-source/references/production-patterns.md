# 生產模式

可觀測性、安全性、驗證和操作最佳實踐。

## 可觀測性和指標

追蹤操作指標供監控：

```python
class ObservableWriter:
    """具綜合指標追蹤的寫入器。"""

    def write(self, iterator):
        """具指標收集的寫入。"""
        from pyspark import TaskContext
        from datetime import datetime
        import time

        context = TaskContext.get()
        partition_id = context.partitionId()

        metrics = {
            "partition_id": partition_id,
            "rows_processed": 0,
            "rows_failed": 0,
            "bytes_sent": 0,
            "batches_sent": 0,
            "retry_count": 0,
            "start_time": time.time(),
            "errors": []
        }

        try:
            for row in iterator:
                try:
                    size = self._send_row(row)
                    metrics["rows_processed"] += 1
                    metrics["bytes_sent"] += size

                except Exception as e:
                    metrics["rows_failed"] += 1
                    metrics["errors"].append({
                        "type": type(e).__name__,
                        "message": str(e)
                    })

                    if not self.continue_on_error:
                        raise

            metrics["duration_seconds"] = time.time() - metrics["start_time"]
            self._report_metrics(metrics)

            return SimpleCommitMessage(
                partition_id=partition_id,
                count=metrics["rows_processed"]
            )

        except Exception as e:
            metrics["fatal_error"] = str(e)
            self._report_failure(partition_id, metrics)
            raise

    def _report_metrics(self, metrics):
        """向監控系統報告指標。"""
        # 範例：CloudWatch、Prometheus、Databricks 指標
        print(f"METRICS: {json.dumps(metrics)}")

        # 計算衍生指標
        if metrics["duration_seconds"] > 0:
            throughput = metrics["rows_processed"] / metrics["duration_seconds"]
            print(f"輸送量：{throughput:.2f} 列/秒")
```

## 記錄最佳實踐

生產偵錯的結構化記錄：

```python
import logging
import json

# 設定結構化記錄
logging.basicConfig(
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StructuredLogger:
    """具結構化輸出的記錄器。"""

    @staticmethod
    def log_operation(operation, context, **kwargs):
        """記錄具結構化內容的操作。"""
        log_entry = {
            "operation": operation,
            "context": context,
            **kwargs
        }
        logger.info(json.dumps(log_entry))

    @staticmethod
    def log_error(operation, error, context):
        """記錄具內容的錯誤。"""
        log_entry = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context
        }
        logger.error(json.dumps(log_entry))

class LoggingWriter:
    def write(self, iterator):
        """具結構化記錄的寫入。"""
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()

        StructuredLogger.log_operation(
            "write_start",
            {"partition_id": partition_id}
        )

        try:
            count = 0
            for row in iterator:
                self._send_data(row)
                count += 1

            StructuredLogger.log_operation(
                "write_complete",
                {"partition_id": partition_id},
                rows_written=count
            )

        except Exception as e:
            StructuredLogger.log_error(
                "write_failed",
                e,
                {"partition_id": partition_id}
            )
            raise
```

## 安全驗證

生產資料來源的輸入驗證和清理：

```python
import re
import ipaddress

class SecureDataSource:
    """具輸入驗證的資料來源。"""

    def __init__(self, options):
        self._validate_options(options)
        self.options = options

    def _validate_options(self, options):
        """在系統邊界驗證選項。"""
        required = ["host", "database", "table"]
        missing = [opt for opt in required if opt not in options]
        if missing:
            raise ValueError(f"缺少必要選項：{', '.join(missing)}")

        self._validate_host(options["host"])

        if "port" in options:
            port = int(options["port"])
            if port < 1 or port > 65535:
                raise ValueError(f"連接埠必須為 1-65535，得到 {port}")

        self._validate_identifier(options["table"], "table")

    def _validate_host(self, host):
        """驗證主機為有效 IP 或主機名稱。"""
        try:
            ipaddress.ip_address(host)
            return
        except ValueError:
            pass
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-\.]*[a-zA-Z0-9]$', host):
            raise ValueError(f"無效的主機格式：{host}")

    def _validate_identifier(self, identifier, name):
        """驗證 SQL 識別子以防止注入。"""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError(
                f"無效的 {name} 識別子：{identifier}。"
                f"必須僅包含字母、數字和底線。"
            )
```

如需認證中的認證清理和機密管理，請參閱 [authentication-patterns.md](authentication-patterns.md) -- 「安全最佳實踐」和「使用機密管理」章節。

## 組態驗證

在執行前驗證組態：

```python
class ConfigValidator:
    """驗證資料來源組態。"""

    VALID_CONSISTENCY_LEVELS = {
        "ONE", "TWO", "THREE", "QUORUM", "ALL",
        "LOCAL_QUORUM", "EACH_QUORUM", "LOCAL_ONE"
    }

    VALID_COMPRESSION = {
        "none", "gzip", "snappy", "lz4", "zstd"
    }

    @classmethod
    def validate(cls, options):
        """驗證所有組態選項。"""
        errors = []

        # 驗證一致性層級
        if "consistency" in options:
            consistency = options["consistency"].upper()
            if consistency not in cls.VALID_CONSISTENCY_LEVELS:
                errors.append(
                    f"無效的一致性層級 '{consistency}'。"
                    f"有效值：{', '.join(cls.VALID_CONSISTENCY_LEVELS)}"
                )

        # 驗證壓縮
        if "compression" in options:
            compression = options["compression"].lower()
            if compression not in cls.VALID_COMPRESSION:
                errors.append(
                    f"無效的壓縮 '{compression}'。"
                    f"有效值：{', '.join(cls.VALID_COMPRESSION)}"
                )

        # 驗證數值範圍
        if "timeout" in options:
            timeout = int(options["timeout"])
            if timeout < 0 or timeout > 300:
                errors.append(f"timeout 必須為 0-300 秒，得到 {timeout}")

        if "batch_size" in options:
            batch_size = int(options["batch_size"])
            if batch_size < 1 or batch_size > 10000:
                errors.append(f"batch_size 必須為 1-10000，得到 {batch_size}")

        # 驗證依存選項
        if options.get("ssl_enabled", "false").lower() == "true":
            if "ssl_ca_cert" not in options:
                errors.append("ssl_enabled=true 時需要 ssl_ca_cert")

        if errors:
            raise ValueError("組態錯誤：\n" + "\n".join(f"- {e}" for e in errors))
```

## 資源清理

確保適當的資源清理：

```python
class ManagedResourceWriter:
    """具保證資源清理的寫入器。"""

    def __init__(self, options):
        self.options = options
        self._connection = None
        self._session = None

    def _get_connection(self):
        """延遲連接初始化。"""
        if self._connection is None:
            self._connection = self._create_connection()
        return self._connection

    def write(self, iterator):
        """具保證清理的寫入。"""
        try:
            connection = self._get_connection()

            for row in iterator:
                self._send_data(connection, row)

        finally:
            # 始終清理資源
            self._cleanup()

    def _cleanup(self):
        """清理資源。"""
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"關閉工作階段時出錯：{e}")
            finally:
                self._session = None

        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"關閉連接時出錯：{e}")
            finally:
                self._connection = None

    def __del__(self):
        """垃圾回收時清理。"""
        self._cleanup()
```

## 健康檢查

監控系統健康：

```python
class HealthCheckMixin:
    """用於健康檢查功能的 mixin。"""

    def check_health(self):
        """在操作前執行健康檢查。"""
        checks = {
            "connection": self._check_connection(),
            "authentication": self._check_authentication(),
            "rate_limit": self._check_rate_limit(),
            "disk_space": self._check_disk_space()
        }

        failed = [name for name, passed in checks.items() if not passed]

        if failed:
            raise Exception(f"健康檢查失敗：{', '.join(failed)}")

        return checks

    def _check_connection(self):
        """檢查與外部系統的連接。"""
        try:
            self._test_connection()
            return True
        except Exception as e:
            logger.error(f"連接檢查失敗：{e}")
            return False

    def _check_authentication(self):
        """檢查認證有效。"""
        try:
            self._verify_credentials()
            return True
        except Exception as e:
            logger.error(f"認證檢查失敗：{e}")
            return False

    def _check_rate_limit(self):
        """檢查是否在速率限制以下。"""
        # 檢查目前速率使用量
        current_rate = self._get_current_rate()
        limit = self._get_rate_limit()

        return current_rate < limit * 0.8  # 80% 閾值

    def _check_disk_space(self):
        """檢查可用磁碟空間。"""
        import shutil

        usage = shutil.disk_usage("/")
        free_percent = (usage.free / usage.total) * 100

        return free_percent > 10  # 10% 最少
```

## 操作最佳實踐

1. **監控**：追蹤輸送量、延遲、錯誤率
2. **記錄**：使用具相關編號的結構化記錄
3. **機密**：永不記錄機密值，使用機密管理
4. **驗證**：驗證所有輸入以防止注入攻擊
5. **資源清理**：始終關閉連接並清理資源
6. **健康檢查**：在操作前驗證系統健康
7. **速率限制**：使用退避尊重 API 速率限制
8. **警告**：為錯誤率和延遲設定警告
9. **文件**：記錄所有組態選項
10. **版本控制**：標記版本並維護變更日誌
