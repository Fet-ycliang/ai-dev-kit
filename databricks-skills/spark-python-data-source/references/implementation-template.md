# 實作範本

涵蓋四種模式（批次讀取、批次寫入、串流讀取、串流寫入）的完整 Python 資料來源骨架。請依需求調整——大多數 connector 只會實作其中一部分。

```python
from pyspark.sql.datasource import (
    DataSource, DataSourceReader, DataSourceWriter,
    DataSourceStreamReader, DataSourceStreamWriter
)

# 1. DataSource class — 回傳 readers/writers 的進入點
class YourDataSource(DataSource):
    @classmethod
    def name(cls):
        return "your-format"

    def __init__(self, options):
        self.options = options

    def schema(self):
        return self._infer_or_return_schema()

    def reader(self, schema):
        return YourBatchReader(self.options, schema)

    def streamReader(self, schema):
        return YourStreamReader(self.options, schema)

    def writer(self, schema, overwrite):
        return YourBatchWriter(self.options, schema)

    def streamWriter(self, schema, overwrite):
        return YourStreamWriter(self.options, schema)

# 2. Base Writer — 批次與串流寫入共用邏輯
#    這裡使用一般 class（暫時不是 DataSourceWriter），
#    讓批次/串流子類別可以混入正確的 PySpark base class。
class YourWriter:
    def __init__(self, options, schema=None):
        self.url = options.get("url")
        assert self.url, "必須提供 url"
        self.batch_size = int(options.get("batch_size", "50"))
        self.schema = schema

    def write(self, iterator):
        # 在這裡匯入——此方法會在 executors 上執行，而不是 driver。
        # executor 程序不會共享 driver 的模組狀態。
        import requests
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()

        msgs = []
        cnt = 0

        for row in iterator:
            cnt += 1
            msgs.append(row.asDict())

            if len(msgs) >= self.batch_size:
                self._send_batch(msgs)
                msgs = []

        if msgs:
            self._send_batch(msgs)

        return SimpleCommitMessage(partition_id=partition_id, count=cnt)

    def _send_batch(self, msgs):
        # 在此實作傳送邏輯
        pass

# 3. Batch Writer — 繼承共用邏輯與 PySpark 介面
class YourBatchWriter(YourWriter, DataSourceWriter):
    pass

# 4. Stream Writer — 為 micro-batch 語意加入 commit/abort
class YourStreamWriter(YourWriter, DataSourceStreamWriter):
    def commit(self, messages, batchId):
        pass

    def abort(self, messages, batchId):
        pass

# 5. Base Reader — 批次與串流讀取共用邏輯
class YourReader:
    def __init__(self, options, schema):
        self.url = options.get("url")
        assert self.url, "必須提供 url"
        self.schema = schema

    def partitions(self):
        return [YourPartition(0, start, end)]

    def read(self, partition):
        # 在這裡匯入——此方法會在 executors 上執行
        import requests

        response = requests.get(f"{self.url}?start={partition.start}")
        for item in response.json():
            yield tuple(item.values())

# 6. Batch Reader
class YourBatchReader(YourReader, DataSourceReader):
    pass

# 7. Stream Reader — 為增量讀取加入 offset 追蹤
class YourStreamReader(YourReader, DataSourceStreamReader):
    def initialOffset(self):
        return {"offset": "0"}

    def latestOffset(self):
        return {"offset": str(self._get_latest())}

    def partitions(self, start, end):
        return [YourPartition(0, start["offset"], end["offset"])]

    def commit(self, end):
        pass
```

## 註冊與使用方式

```python
# 註冊
from your_package import YourDataSource
spark.dataSource.register(YourDataSource)

# 批次讀取
df = spark.read.format("your-format").option("url", "...").load()

# 批次寫入
df.write.format("your-format").option("url", "...").save()

# 串流讀取
df = spark.readStream.format("your-format").option("url", "...").load()

# 串流寫入
df.writeStream.format("your-format").option("url", "...").start()
```
