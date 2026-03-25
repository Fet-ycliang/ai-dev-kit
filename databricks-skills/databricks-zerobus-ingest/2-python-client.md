# Python 客戶端

Zerobus Ingest 的 Python SDK 模式：同步與非同步 API、JSON 與 Protobuf 流程，以及可重用的 client 類別。

---

## SDK 匯入

```python
# 同步 API
from zerobus.sdk.sync import ZerobusSdk

# 非同步 API（功能相同）
from zerobus.sdk.aio import ZerobusSdk as AsyncZerobusSdk

# 共用型別（同步與非同步都會使用）
from zerobus.sdk.shared import (
    RecordType,
    AckCallback,
    ZerobusException,
    NonRetriableException,
    StreamConfigurationOptions,
    TableProperties,
)
```

---

<!-- ## JSON 攝取（快速開始)

JSON 是最簡單的路徑。請傳入鍵名與目標資料表欄位名稱相符的 Python dict。

```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

server_endpoint = os.environ["ZEROBUS_SERVER_ENDPOINT"]
workspace_url = os.environ["DATABRICKS_WORKSPACE_URL"]
table_name = os.environ["ZEROBUS_TABLE_NAME"]
client_id = os.environ["DATABRICKS_CLIENT_ID"]
client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

sdk = ZerobusSdk(server_endpoint, workspace_url)

options = StreamConfigurationOptions(record_type=RecordType.JSON)
table_props = TableProperties(table_name)

stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(100):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        offset = stream.ingest_record_offset(record)
        stream.wait_for_offset(offset)  # 阻塞直到完成持久化寫入
finally:
    stream.close()
``` -->

---

## Protobuf 攝取

你必須一律使用 Protobuf。
若為需要型別安全的正式環境工作負載，請使用 Protobuf。先產生並編譯你的 `.proto`（請參閱 [4-protobuf-schema.md](4-protobuf-schema.md)），然後：

```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

# 匯入你編譯好的 protobuf 模組
import record_pb2

server_endpoint = os.environ["ZEROBUS_SERVER_ENDPOINT"]
workspace_url = os.environ["DATABRICKS_WORKSPACE_URL"]
table_name = os.environ["ZEROBUS_TABLE_NAME"]
client_id = os.environ["DATABRICKS_CLIENT_ID"]
client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

sdk = ZerobusSdk(server_endpoint, workspace_url)

options = StreamConfigurationOptions(record_type=RecordType.PROTO)
table_props = TableProperties(table_name, record_pb2.AirQuality.DESCRIPTOR)

stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(100):
        record = record_pb2.AirQuality(
            device_name=f"sensor-{i}",
            temp=22,
            humidity=55,
        )
        offset = stream.ingest_record_offset(record)
        stream.wait_for_offset(offset)
finally:
    stream.close()
```

---

## ACK Callback（非同步確認）

若不想在每個 ACK 上阻塞，可以註冊 `AckCallback` 子類別，以便在背景確認持久化：

```python
from zerobus.sdk.shared import AckCallback, StreamConfigurationOptions, RecordType

class MyAckHandler(AckCallback):
    def on_ack(self, offset: int) -> None:
        print(f"已持久化至 offset: {offset}")

    def on_error(self, offset: int, message: str) -> None:
        print(f"offset {offset} 發生錯誤: {message}")

options = StreamConfigurationOptions(
    record_type=RecordType.JSON,
    ack_callback=MyAckHandler(),
)

# 使用 callback 建立 stream
stream = sdk.create_stream(client_id, client_secret, table_props, options)

try:
    for i in range(1000):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        stream.ingest_record_nowait(record)  # Fire-and-forget，ACK 會透過 callback 抵達
    stream.flush()  # 確保所有緩衝記錄都已送出
finally:
    stream.close()
```

---

## 可重用的 Client 類別

具備重試邏輯、重新連線能力，並同時支援 JSON 與 Protobuf 的正式環境封裝：

```python
import os
import time
import logging
from typing import Optional

from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import (
    RecordType,
    AckCallback,
    StreamConfigurationOptions,
    TableProperties,
)

logger = logging.getLogger(__name__)


class ZerobusClient:
    """可重用的 Zerobus Ingest client，具備重試與重新連線能力。"""

    def __init__(
        self,
        server_endpoint: str,
        workspace_url: str,
        table_name: str,
        client_id: str,
        client_secret: str,
        record_type: RecordType = RecordType.JSON,
        ack_callback: Optional[AckCallback] = None,
        proto_descriptor=None,
    ):
        self.server_endpoint = server_endpoint
        self.workspace_url = workspace_url
        self.table_name = table_name
        self.client_id = client_id
        self.client_secret = client_secret
        self.record_type = record_type
        self.ack_callback = ack_callback
        self.proto_descriptor = proto_descriptor

        self.sdk = ZerobusSdk(self.server_endpoint, self.workspace_url)
        self.stream = None

    def init_stream(self) -> None:
        """開啟通往目標資料表的新 stream。"""
        options = StreamConfigurationOptions(
            record_type=self.record_type,
            ack_callback=self.ack_callback,
        )
        if self.record_type == RecordType.PROTO and self.proto_descriptor:
            table_props = TableProperties(self.table_name, self.proto_descriptor)
        else:
            table_props = TableProperties(self.table_name)

        self.stream = self.sdk.create_stream(
            self.client_id, self.client_secret, table_props, options
        )
        logger.info("已為 %s 初始化 Zerobus stream", self.table_name)

    def ingest(self, payload, max_retries: int = 3) -> bool:
        """攝取單筆記錄（JSON 使用 dict，PROTO 使用 protobuf 訊息）。

        成功時回傳 True，重試用盡後回傳 False。
        """
        for attempt in range(max_retries):
            try:
                if self.stream is None:
                    self.init_stream()
                offset = self.stream.ingest_record_offset(payload)
                self.stream.wait_for_offset(offset)
                return True
            except Exception as e:
                err = str(e).lower()
                logger.warning(
                    "第 %d/%d 次攝取嘗試失敗: %s", attempt + 1, max_retries, e
                )
                if "closed" in err or "connection" in err:
                    self.close()
                    self.init_stream()
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)  # 指數退避：1s、2s、4s
        return False

    def flush(self) -> None:
        """將緩衝寫入 flush。"""
        if self.stream:
            self.stream.flush()

    def close(self) -> None:
        """關閉 stream 並釋放資源。"""
        if self.stream:
            self.stream.close()
            self.stream = None

    def __enter__(self):
        self.init_stream()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        self.close()
        return False
```

### 使用 Client 類別

```python
# 使用 context manager 的 JSON 流程
with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.JSON,
) as client:
    for i in range(100):
        client.ingest({"device_name": f"sensor-{i}", "temp": 22, "humidity": 55})

# Protobuf 流程
import record_pb2

with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.PROTO,
    proto_descriptor=record_pb2.AirQuality.DESCRIPTOR,
) as client:
    for i in range(100):
        record = record_pb2.AirQuality(device_name=f"sensor-{i}", temp=22, humidity=55)
        client.ingest(record)
```

---

## Async Python API

SDK 提供可搭配 `asyncio` 使用的等效 async API：

```python
import asyncio
from zerobus.sdk.aio import ZerobusSdk as AsyncZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties


async def ingest_async():
    sdk = AsyncZerobusSdk(server_endpoint, workspace_url)
    options = StreamConfigurationOptions(record_type=RecordType.JSON)
    table_props = TableProperties(table_name)

    stream = await sdk.create_stream(client_id, client_secret, table_props, options)

    try:
        for i in range(100):
            record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
            offset = await stream.ingest_record_offset(record)
            await stream.wait_for_offset(offset)
    finally:
        await stream.close()


asyncio.run(ingest_async())
```

**提示：** sync 與 async API 具備相同能力。請依你的應用程式架構選擇（FastAPI/aiohttp -> async；scripts/batch jobs -> sync）。

---

## 批次模式

若要獲得較高吞吐量，請使用 `ingest_record_nowait`（fire-and-forget）或批次方法，並在最後 flush：

```python
with ZerobusClient(
    server_endpoint=os.environ["ZEROBUS_SERVER_ENDPOINT"],
    workspace_url=os.environ["DATABRICKS_WORKSPACE_URL"],
    table_name=os.environ["ZEROBUS_TABLE_NAME"],
    client_id=os.environ["DATABRICKS_CLIENT_ID"],
    client_secret=os.environ["DATABRICKS_CLIENT_SECRET"],
    record_type=RecordType.JSON,
) as client:
    for i in range(10_000):
        record = {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
        client.stream.ingest_record_nowait(record)  # Fire-and-forget
    # flush() 與 close() 會由 context manager 自動呼叫
```

若要進行真正的批次攝取，請使用批次版本：

```python
records = [
    {"device_name": f"sensor-{i}", "temp": 22, "humidity": 55}
    for i in range(10_000)
]
# Fire-and-forget 批次
stream.ingest_records_nowait(records)
stream.flush()

# 或使用 offset 追蹤
offset = stream.ingest_records_offset(records)
stream.wait_for_offset(offset)
```

---

## 攝取方法比較

| 方法 | 回傳 | 會阻塞？ | 最適合 |
|--------|---------|---------|----------|
| `ingest_record_offset(record)` | offset | 否（僅排入佇列） | 需要持久性追蹤的單筆記錄 |
| `ingest_record_nowait(record)` | None | 否 | 單筆記錄的最大吞吐量 |
| `ingest_records_offset(records)` | 最後一個 offset | 否（僅排入佇列） | 需要持久性追蹤的批次 |
| `ingest_records_nowait(records)` | None | 否 | 批次的最大吞吐量 |
| `wait_for_offset(offset)` | None | 是（直到 ACK） | 確認持久性 |
| `flush()` | None | 是（直到送出完成） | 確保所有緩衝記錄都已送出 |
| `ingest_record(record)` | RecordAcknowledgment | 否 | SDK v1.1.0+ 的主要方法；若為 JSON 請傳入 `json.dumps(record)` |
