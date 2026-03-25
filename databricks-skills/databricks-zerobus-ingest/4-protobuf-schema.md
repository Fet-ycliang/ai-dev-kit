# Protobuf 結構描述產生

從 Unity Catalog 資料表定義產生 `.proto` 結構描述、編譯語言繫結，並了解 Delta 到 Protobuf 的型別對應。

---

## 為什麼要用 Protobuf？

| 面向 | JSON | Protobuf |
|--------|------|----------|
| **型別安全** | 無（不相符時於執行階段發生錯誤） | 編譯期型別檢查 |
| **結構描述演進** | 手動；容易在無提示下出錯 | 天生具備向前相容性 |
| **效能** | 文字解析負擔 | 二進位編碼，payload 較小 |
| **建議用於** | 原型設計、簡單結構描述 | 正式環境、複雜結構描述 |

**建議：** 任何正式環境工作負載都請使用 Protobuf。只有在快速原型設計或結構描述非常簡單時才使用 JSON。

---

## 從 UC 資料表產生 .proto

### Python

```bash
python -m zerobus.tools.generate_proto \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output record.proto
```

### Java

```bash
java -jar zerobus-ingest-sdk-0.1.0-jar-with-dependencies.jar \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output record.proto
```

產生的 `.proto` 檔案會包含與資料表結構描述對應的 message 定義，例如：

```protobuf
syntax = "proto3";

message AirQuality {
    string device_name = 1;
    int32 temp = 2;
    int64 humidity = 3;
}
```

---

## 編譯語言繫結

### Python

```bash
pip install grpcio-tools

python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    record.proto
```

這會產生 `record_pb2.py`。匯入並使用它：

```python
import record_pb2

record = record_pb2.AirQuality(
    device_name="sensor-1",
    temp=22,
    humidity=55,
)
```

### Java

```bash
protoc --java_out=src/main/java record.proto
```

這會在 `src/main/java/` 下產生 Java 類別。用法：

```java
import com.example.proto.Record.AirQuality;

AirQuality record = AirQuality.newBuilder()
    .setDeviceName("sensor-1")
    .setTemp(22)
    .setHumidity(55)
    .build();
```

### Go

```bash
protoc --go_out=. record.proto
```

### Rust

在 `build.rs` 中使用 `prost`：

```rust
// build.rs
fn main() {
    prost_build::compile_protos(&["record.proto"], &["."]).unwrap();
}
```

---

## Delta 到 Protobuf 的型別對應

| Delta / Spark 型別 | Protobuf 型別 | 說明 |
|--------------------|---------------|-------|
| `STRING` | `string` | |
| `INT` / `INTEGER` | `int32` | |
| `LONG` / `BIGINT` | `int64` | |
| `FLOAT` | `float` | |
| `DOUBLE` | `double` | |
| `BOOLEAN` | `bool` | |
| `BINARY` | `bytes` | |
| `ARRAY<T>` | `repeated T` | 元素型別會遞迴對應 |
| `MAP<K,V>` | `map<K,V>` | 鍵必須是 string 或 integer 型別 |
| `STRUCT` | 巢狀 `message` | 欄位會遞迴對應 |
| `DATE` | `int32` | Epoch 天數（自 1970-01-01 起的天數） |
| `TIMESTAMP` | `int64` | Epoch 微秒 |
| `DECIMAL(p,s)` | `bytes` 或 `string` | 請檢查產生的 .proto 以確認實際對應 |
| `VARIANT` | `string` | JSON 編碼字串 |

**重要：** Protobuf 結構描述必須與 Delta 資料表結構描述完全一致（1:1 欄位對應）。若資料表結構描述變更，請重新產生 `.proto` 並重新編譯。

---

## 結構描述大小上限

- 每個 proto 結構描述最多 **2000 個欄位**
- 每筆個別訊息最大 **10 MB**（10,485,760 bytes）

---

## 結構描述演進流程

當你的資料表結構描述變更時：

1. 在 Unity Catalog 中修改資料表（新增欄位等）
2. 使用產生命令重新產生 `.proto` 檔案
3. 重新編譯語言繫結
4. 更新 producer 程式碼以填入新欄位
5. 重新部署

**注意：** Zerobus 不支援自動結構描述演進。你必須明確管理這個流程。

---

## 在程式碼中使用 Descriptor

### Python

```python
from zerobus.sdk.shared import TableProperties, RecordType
import record_pb2

# 傳入已編譯模組中的 DESCRIPTOR
table_props = TableProperties(
    "catalog.schema.table_name",
    record_pb2.AirQuality.DESCRIPTOR,
)
```

### Java

```java
// 傳入預設 instance 以擷取 descriptor
TableProperties<AirQuality> tableProperties = new TableProperties<>(
    "catalog.schema.table_name",
    AirQuality.getDefaultInstance()
);
```

### Go / Rust

建構 `TableProperties` 時，請傳入原始的 descriptor bytes。
