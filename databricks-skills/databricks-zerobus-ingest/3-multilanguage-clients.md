# 多語言用戶端

Zerobus 擷取 SDK 適用於 Java、Go、TypeScript/Node.js 和 Rust 的範例。所有語言遵循相同的核心模式：**SDK 初始化 -> 建立串流 -> 擷取記錄 -> ACK -> 清空 -> 關閉**。

---

## Java（8+）

### 安裝

Maven：
```xml
<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-ingest-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

### Protobuf 流程（推薦）

Java 預設使用 Protobuf。首先產生並編譯您的 `.proto`（參見 [4-protobuf-schema.md](4-protobuf-schema.md)）。

```java
import com.databricks.zerobus.*;
import com.example.proto.Record.AirQuality;

public class ZerobusProducer {
    public static void main(String[] args) throws Exception {
        String serverEndpoint = System.getenv("ZEROBUS_SERVER_ENDPOINT");
        String workspaceUrl = System.getenv("DATABRICKS_WORKSPACE_URL");
        String tableName = System.getenv("ZEROBUS_TABLE_NAME");
        String clientId = System.getenv("DATABRICKS_CLIENT_ID");
        String clientSecret = System.getenv("DATABRICKS_CLIENT_SECRET");

        ZerobusSdk sdk = new ZerobusSdk(serverEndpoint, workspaceUrl);

        TableProperties<AirQuality> tableProperties = new TableProperties<>(
            tableName,
            AirQuality.getDefaultInstance()
        );

        ZerobusStream<AirQuality> stream = sdk.createStream(
            tableProperties, clientId, clientSecret
        ).join();

        try {
            for (int i = 0; i < 100; i++) {
                AirQuality record = AirQuality.newBuilder()
                    .setDeviceName("sensor-" + i)
                    .setTemp(22)
                    .setHumidity(55)
                    .build();
                long offset = stream.ingestRecordOffset(record);
                stream.waitForOffset(offset);
            }
        } finally {
            stream.close();
        }
    }
}
```

### Java Proto 產生

```bash
java -jar zerobus-ingest-sdk-0.1.0-jar-with-dependencies.jar \
    --uc-endpoint "https://dbc-a1b2c3d4-e5f6.cloud.databricks.com" \
    --client-id "$DATABRICKS_CLIENT_ID" \
    --client-secret "$DATABRICKS_CLIENT_SECRET" \
    --table "catalog.schema.table_name" \
    --output "record.proto"

# 編譯為 Java
protoc --java_out=src/main/java record.proto
```

---

## Go（1.21+）

### 安裝

```bash
go get github.com/databricks/zerobus-sdk-go
```

### JSON 流程

```go
package main

import (
    "fmt"
    "log"
    "os"

    zerobus "github.com/databricks/zerobus-go-sdk/sdk"
)

func main() {
    serverEndpoint := os.Getenv("ZEROBUS_SERVER_ENDPOINT")
    workspaceURL := os.Getenv("DATABRICKS_WORKSPACE_URL")
    tableName := os.Getenv("ZEROBUS_TABLE_NAME")
    clientID := os.Getenv("DATABRICKS_CLIENT_ID")
    clientSecret := os.Getenv("DATABRICKS_CLIENT_SECRET")

    sdk, err := zerobus.NewZerobusSdk(serverEndpoint, workspaceURL)
    if err != nil {
        log.Fatal(err)
    }
    defer sdk.Free()

    options := zerobus.DefaultStreamConfigurationOptions()
    options.RecordType = zerobus.RecordTypeJson

    stream, err := sdk.CreateStream(
        zerobus.TableProperties{TableName: tableName},
        clientID, clientSecret, options,
    )
    if err != nil {
        log.Fatal(err)
    }
    defer stream.Close()

    for i := 0; i < 100; i++ {
        record := fmt.Sprintf(
            `{"device_name": "sensor-%d", "temp": 22, "humidity": 55}`, i,
        )
        offset, err := stream.IngestRecordOffset(record)
        if err != nil {
            log.Printf("記錄 %d 擷取失敗：%v", i, err)
            continue
        }
        stream.WaitForOffset(offset)
    }

    stream.Flush()
}
```

### Protobuf 流程

```go
options := zerobus.DefaultStreamConfigurationOptions()
options.RecordType = zerobus.RecordTypeProto

// 載入已編譯的 proto descriptor
tableProps := zerobus.TableProperties{
    TableName:       tableName,
    DescriptorProto: descriptorBytes, // 已編譯的 .proto descriptor
}

stream, err := sdk.CreateStream(tableProps, clientID, clientSecret, options)
// ... 擷取 protobuf 序列化位元組 ...
```

---

## TypeScript / Node.js（16+）

### 安裝

```bash
npm install @databricks/zerobus-ingest-sdk
```

### JSON 流程

```typescript
import { ZerobusSdk, RecordType } from "@databricks/zerobus-ingest-sdk";

const serverEndpoint = process.env.ZEROBUS_SERVER_ENDPOINT!;
const workspaceUrl = process.env.DATABRICKS_WORKSPACE_URL!;
const tableName = process.env.ZEROBUS_TABLE_NAME!;
const clientId = process.env.DATABRICKS_CLIENT_ID!;
const clientSecret = process.env.DATABRICKS_CLIENT_SECRET!;

const sdk = new ZerobusSdk(serverEndpoint, workspaceUrl);

const stream = await sdk.createStream(
  { tableName },
  clientId,
  clientSecret,
  { recordType: RecordType.Json }
);

try {
  for (let i = 0; i < 100; i++) {
    const record = { device_name: `sensor-${i}`, temp: 22, humidity: 55 };
    const offset = await stream.ingestRecordOffset(record);
    await stream.waitForOffset(offset);
  }
  await stream.flush();
} finally {
  await stream.close();
}
```

### 搭配錯誤處理

```typescript
import { ZerobusSdk, RecordType } from "@databricks/zerobus-ingest-sdk";

async function ingestWithRetry(
  stream: any,
  record: Record<string, unknown>,
  maxRetries = 3
): Promise<boolean> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const offset = await stream.ingestRecordOffset(record);
      await stream.waitForOffset(offset);
      return true;
    } catch (error) {
      console.warn(`嘗試 ${attempt + 1}/${maxRetries} 失敗：`, error);
      if (attempt < maxRetries - 1) {
        await new Promise((r) => setTimeout(r, 2 ** attempt * 1000));
      }
    }
  }
  return false;
}
```

---

## Rust（1.70+）

### 安裝

```bash
cargo add databricks-zerobus-ingest-sdk
cargo add tokio --features macros,rt-multi-thread
```

### JSON 流程

```rust
use databricks_zerobus_ingest_sdk::{
    RecordType, StreamConfigurationOptions, TableProperties, ZerobusSdk,
};
use std::env;
use std::error::Error;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let server_endpoint = env::var("ZEROBUS_SERVER_ENDPOINT")?;
    let workspace_url = env::var("DATABRICKS_WORKSPACE_URL")?;
    let table_name = env::var("ZEROBUS_TABLE_NAME")?;
    let client_id = env::var("DATABRICKS_CLIENT_ID")?;
    let client_secret = env::var("DATABRICKS_CLIENT_SECRET")?;

    let table_properties = TableProperties {
        table_name,
        descriptor_proto: None,
    };

    let options = StreamConfigurationOptions {
        record_type: RecordType::Json,
        ..Default::default()
    };

    let sdk = ZerobusSdk::new(server_endpoint, workspace_url)?;
    let mut stream = sdk
        .create_stream(table_properties, client_id, client_secret, Some(options))
        .await?;

    for i in 0..100 {
        let record = format!(
            r#"{{"device_name": "sensor-{}", "temp": 22, "humidity": 55}}"#,
            i
        );
        let offset = stream.ingest_record_offset(record.into_bytes()).await?;
        stream.wait_for_offset(offset).await?;
    }

    stream.close().await?;
    Ok(())
}
```

### Protobuf 流程

```rust
let table_properties = TableProperties {
    table_name: table_name.clone(),
    descriptor_proto: Some(proto_descriptor_bytes),
};

let options = StreamConfigurationOptions {
    record_type: RecordType::Proto,
    ..Default::default()
};

let mut stream = sdk
    .create_stream(table_properties, client_id, client_secret, Some(options))
    .await?;

// 擷取序列化的 protobuf 位元組
let record_bytes = my_proto_message.encode_to_vec();
let offset = stream.ingest_record_offset(record_bytes).await?;
stream.wait_for_offset(offset).await?;
```

---

## 語言比較

| 功能 | Python | Java | Go | TypeScript | Rust |
|---------|--------|------|----|------------|------|
| 最小版本 | 3.9+ | 8+ | 1.21+ | Node 16+ | 1.70+ |
| 套件 | `databricks-zerobus-ingest-sdk` | `com.databricks:zerobus-ingest-sdk` | `github.com/databricks/zerobus-sdk-go` | `@databricks/zerobus-ingest-sdk` | `databricks-zerobus-ingest-sdk` |
| 預設序列化 | JSON | Protobuf | JSON | JSON | JSON |
| 非同步 API | 是（單獨模組） | CompletableFuture | Goroutines | 原生 async/await | Tokio async/await |
| ACK 模式 | `wait_for_offset(offset)` 或 `AckCallback` | `waitForOffset(offset)` | `WaitForOffset(offset)` | `await waitForOffset(offset)` | `wait_for_offset(offset).await?` |
| Proto 產生 | `python -m zerobus.tools.generate_proto` | JAR CLI 工具 | 外部 `protoc` | 外部 `protoc` | 外部 `protoc` |
