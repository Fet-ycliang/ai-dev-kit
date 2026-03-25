# SDP 的資料擷取模式

涵蓋 Spark Declarative Pipelines 的資料擷取模式，包括用於雲端儲存體的 Auto Loader，以及 Kafka 和 Event Hub 等串流來源。

**語言支援**：SQL（主要）、透過現代 `pyspark.pipelines` API 的 Python。Python 語法請參閱 [5-python-api.md](5-python-api.md)。

---

## Auto Loader（Cloud Files）

Auto Loader 會在新資料檔案抵達雲端儲存體時，以增量方式進行處理。在 streaming table 查詢中，你**必須在 `read_files` 前使用 `STREAM` 關鍵字**；接著 `read_files` 會利用 Auto Loader。請參閱 [read_files — Usage in streaming tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables)。

### 基本模式

```sql
CREATE OR REPLACE STREAMING TABLE bronze_orders AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS source_file,
  _metadata.file_modification_time AS file_timestamp
FROM STREAM read_files(
  '/mnt/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, amount DECIMAL(10,2)'
);
```

### 作為 AUTO CDC 上游的 Bronze

如果 bronze 資料表會提供給下游的 **AUTO CDC** flow（例如 `FROM stream(bronze_orders_cdc)`），請使用 **`FROM STREAM read_files(...)`**，讓來源保持為串流。否則你可能會看到：*"Cannot create a streaming table append once flow from a batch query."* 與上方相同，在 streaming table 查詢中，你必須在 `read_files` 前使用 `STREAM` 關鍵字。

```sql
CREATE OR REPLACE STREAMING TABLE bronze_orders_cdc AS
SELECT ...,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '/Volumes/catalog/schema/raw_orders_cdc',
  format => 'parquet',
  schemaHints => '...'
);
```

### Schema 演進

```sql
CREATE OR REPLACE STREAMING TABLE bronze_customers AS
SELECT
  *,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '/mnt/raw/customers/',
  format => 'json',
  schemaHints => 'customer_id STRING, email STRING',
  mode => 'PERMISSIVE'  -- 可平順處理 schema 變更
);
```

### 檔案格式

**JSON**：
```sql
FROM read_files(
  's3://bucket/data/',
  format => 'json',
  schemaHints => 'id STRING, timestamp TIMESTAMP'
)
```

**CSV**：
```sql
FROM read_files(
  '/mnt/raw/data/',
  format => 'csv',
  schemaHints => 'id STRING, name STRING, amount DECIMAL(10,2)',
  header => true,
  delimiter => ','
)
```

**Parquet**（自動推斷 schema）：
```sql
FROM read_files(
  'abfss://container@storage.dfs.core.windows.net/data/',
  format => 'parquet'
)
```

**Avro**：
```sql
FROM read_files(
  '/mnt/raw/events/',
  format => 'avro',
  schemaHints => 'event_id STRING, event_time TIMESTAMP'
)
```

### Schema 推斷

**明確提示**（正式環境建議）：
```sql
FROM read_files(
  '/mnt/raw/sales/',
  format => 'json',
  schemaHints => 'sale_id STRING, customer_id STRING, amount DECIMAL(10,2), sale_date DATE'
)
```

**部分提示**（其餘欄位自動推斷）：
```sql
FROM read_files(
  '/mnt/raw/data/',
  format => 'json',
  schemaHints => 'id STRING, critical_field DECIMAL(10,2)'  -- 其餘欄位自動推斷
)
```

在 `resources/*_etl.pipeline.yml` 的 pipeline 設定中加入下列內容：
```yaml
configuration:
  bronze_schema: ${var.bronze_schema}
  silver_schema: ${var.silver_schema}
  gold_schema: ${var.gold_schema}
  schema_location_base: ${var.schema_location_base}
```

並在 `databricks.yml` 中定義變數：
```yaml
variables:
  catalog:
    description: 要使用的 catalog
  bronze_schema:
    description: 要使用的 bronze schema
  silver_schema:
    description: 要使用的 silver schema
  gold_schema:
    description: 要使用的 gold schema
  schema_location_base:
    description: Auto Loader schema 中繼資料的基礎路徑

targets:
  dev:
    variables:
      catalog: my_catalog
      bronze_schema: bronze_dev
      silver_schema: silver_dev
      gold_schema: gold_dev
      schema_location_base: /Volumes/my_catalog/pipeline_metadata/my_pipeline_metadata/schemas

  prod:
    variables:
      catalog: my_catalog
      bronze_schema: bronze
      silver_schema: silver
      gold_schema: gold
      schema_location_base: /Volumes/my_catalog/pipeline_metadata/my_pipeline_metadata/schemas
```

接著可在 Python 程式碼中這樣存取：
```python
bronze_schema = spark.conf.get("bronze_schema")
silver_schema = spark.conf.get("silver_schema")
gold_schema = spark.conf.get("gold_schema")
schema_location_base = spark.conf.get("schema_location_base")
```

### Rescue Data 與隔離區

使用 `_rescued_data` 處理格式異常的記錄：

```sql
-- 標記出現解析錯誤的記錄
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CASE WHEN _rescued_data IS NOT NULL THEN TRUE ELSE FALSE END AS has_parsing_errors
FROM read_files(
  '/mnt/raw/events/',
  format => 'json',
  schemaHints => 'event_id STRING, event_time TIMESTAMP'
);

-- 建立隔離區供調查
CREATE OR REPLACE STREAMING TABLE bronze_events_quarantine AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NOT NULL;

-- 供下游使用的乾淨資料
CREATE OR REPLACE STREAMING TABLE silver_events_clean AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NULL;
```

---

## 串流來源（Kafka、Event Hub、Kinesis）

### Kafka 來源

```sql
CREATE OR REPLACE STREAMING TABLE bronze_kafka_events AS
SELECT
  CAST(key AS STRING) AS event_key,
  CAST(value AS STRING) AS event_value,
  topic,
  partition,
  offset,
  timestamp AS kafka_timestamp,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'kafka',
  kafka.bootstrap.servers => '${kafka_brokers}',
  subscribe => 'events-topic',
  startingOffsets => 'latest',  -- 或 'earliest'
  kafka.security.protocol => 'SASL_SSL',
  kafka.sasl.mechanism => 'PLAIN',
  kafka.sasl.jaas.config => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="${kafka_username}" password="${kafka_password}";'
);
```

### Kafka 搭配多個 Topic

```sql
FROM read_stream(
  format => 'kafka',
  kafka.bootstrap.servers => '${kafka_brokers}',
  subscribe => 'topic1,topic2,topic3',
  startingOffsets => 'latest'
)
```

### Azure Event Hub

```sql
CREATE OR REPLACE STREAMING TABLE bronze_eventhub_events AS
SELECT
  CAST(body AS STRING) AS event_body,
  enqueuedTime AS event_time,
  offset,
  sequenceNumber,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'eventhubs',
  eventhubs.connectionString => '${eventhub_connection_string}',
  eventhubs.consumerGroup => '${consumer_group}',
  startingPosition => 'latest'
);
```

### AWS Kinesis

```sql
CREATE OR REPLACE STREAMING TABLE bronze_kinesis_events AS
SELECT
  CAST(data AS STRING) AS event_data,
  partitionKey,
  sequenceNumber,
  approximateArrivalTimestamp AS arrival_time,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'kinesis',
  kinesis.streamName => '${stream_name}',
  kinesis.region => '${aws_region}',
  kinesis.startingPosition => 'LATEST'
);
```

### 解析串流來源中的 JSON

```sql
-- 解析 Kafka value 中的 JSON
CREATE OR REPLACE STREAMING TABLE silver_kafka_parsed AS
SELECT
  from_json(
    event_value,
    'event_id STRING, event_type STRING, user_id STRING, timestamp TIMESTAMP, properties MAP<STRING, STRING>'
  ) AS event_data,
  kafka_timestamp,
  _ingested_at
FROM STREAM bronze_kafka_events;

-- 攤平解析後的 JSON
CREATE OR REPLACE STREAMING TABLE silver_kafka_flattened AS
SELECT
  event_data.event_id,
  event_data.event_type,
  event_data.user_id,
  event_data.timestamp AS event_timestamp,
  event_data.properties,
  kafka_timestamp,
  _ingested_at
FROM STREAM silver_kafka_parsed;
```

---

## 認證

### 使用 Databricks Secrets

**Kafka**：
```sql
kafka.sasl.jaas.config => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="{{secrets/kafka/username}}" password="{{secrets/kafka/password}}";'
```

**Event Hub**：
```sql
eventhubs.connectionString => '{{secrets/eventhub/connection-string}}'
```

### 使用 Pipeline 變數

在 SQL 中引用變數：
```sql
kafka.bootstrap.servers => '${kafka_brokers}'
```

在 pipeline 設定中定義：
```yaml
variables:
  kafka_brokers:
    default: "broker1:9092,broker2:9092"
```

---

## 關鍵模式

### 1. 一律加入擷取時間戳記

```sql
SELECT
  *,
  current_timestamp() AS _ingested_at  -- 追蹤資料進入系統的時間
FROM read_files(...)
```

### 2. 納入檔案中繼資料以便偵錯

```sql
SELECT
  *,
  _metadata.file_path AS source_file,
  _metadata.file_modification_time AS file_timestamp,
  _metadata.file_size AS file_size
FROM read_files(...)
```

### 3. 正式環境使用 Schema Hints

```sql
-- ✅ 明確 schema 可避免意外
FROM read_files(
  '/mnt/data/',
  format => 'json',
  schemaHints => 'id STRING, amount DECIMAL(10,2), date DATE'
)

-- ❌ 完全自動推斷的 schema 可能發生漂移
FROM read_files('/mnt/data/', format => 'json')
```

### 4. 使用 Rescue Data 維護資料品質

```sql
-- 將錯誤資料送往隔離區，乾淨資料送往下游
CREATE OR REPLACE STREAMING TABLE bronze_data_quarantine AS
SELECT * FROM STREAM bronze_data WHERE has_errors;

CREATE OR REPLACE STREAMING TABLE silver_data AS
SELECT * FROM STREAM bronze_data WHERE NOT has_errors;
```

### 5. 起始位置

**開發**：`startingOffsets => 'latest'`（僅新資料）
**回補**：`startingOffsets => 'earliest'`（所有可用資料）
**復原**：Checkpoints 會自動處理

---

## 常見問題

| 問題 | 解法 |
|-------|----------|
| 檔案未被擷取 | 確認 format 與檔案一致，且路徑正確 |
| Schema 演進造成中斷 | 使用 `mode => 'PERMISSIVE'` 並監控 `_rescued_data` |
| Kafka lag 持續增加 | 檢查下游瓶頸並提高平行度 |
| 重複事件 | 在 silver 層實作去重（請參閱 [2-streaming-patterns.md](2-streaming-patterns.md)） |
| 解析錯誤 | 使用 rescue data 模式將格式異常的記錄送往隔離區 |

---

## Python API 範例

對於 Python，請使用現代 `pyspark.pipelines` API。完整指引請參閱 [5-python-api.md](5-python-api.md)。

**Python 重要事項**：使用 `spark.readStream.format("cloudFiles")` 進行雲端儲存體擷取時，你**必須指定 `cloudFiles.schemaLocation`** 來儲存 Auto Loader 的 schema 中繼資料。

### Schema Location 最佳實務（僅限 Python）

**絕對不要使用來源資料的 volume 來儲存 schema** —— 這會造成權限衝突，並污染原始資料。

#### 提示使用者提供 Schema Location

建立使用 Auto Loader 的 Python 管線時，**一定要詢問使用者**要把 schema 中繼資料存放在哪裡：

**建議模式：**
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas/{table_name}
```

**提示範例：**
```
你希望將 Auto Loader 的 schema 中繼資料儲存在哪裡？

我建議：
  /Volumes/my_catalog/pipeline_metadata/orders_pipeline_metadata/schemas/

此路徑：
- 保持來源資料乾淨
- 避免權限問題
- 讓 pipeline 狀態更容易管理
- 可依環境（dev/prod）參數化

如果還不存在，你可能需要先建立 `pipeline_metadata` volume。

你要使用這個路徑嗎？
```

### Auto Loader（Python）

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# 從 pipeline 設定取得 schema location
# 建議格式：/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_orders", cluster_by=["order_date"])
def bronze_orders():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_orders")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("/Volumes/catalog/schema/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )
```

**Pipeline 設定**（位於 `pipeline.yml`）：
```yaml
configuration:
  schema_location_base: /Volumes/my_catalog/pipeline_metadata/orders_pipeline_metadata/schemas
```

### Kafka（Python）

```python
@dp.table(name="bronze_kafka_events")
def bronze_kafka_events():
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
        .option("subscribe", "events-topic")
        .option("startingOffsets", "latest")
        .load()
        .selectExpr(
            "CAST(key AS STRING) AS event_key",
            "CAST(value AS STRING) AS event_value",
            "topic", "partition", "offset",
            "timestamp AS kafka_timestamp"
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

### 隔離區（Python）

```python
# 從 pipeline 設定取得 schema location
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_events", cluster_by=["ingestion_date"])
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .option("rescuedDataColumn", "_rescued_data")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
        .withColumn("_has_parsing_errors",
                   F.when(F.col("_rescued_data").isNotNull(), True)
                   .otherwise(False))
    )

@dp.table(name="bronze_events_quarantine")
def bronze_events_quarantine():
    return (
        spark.read.table("catalog.schema.bronze_events")
        .filter(F.col("_has_parsing_errors") == True)
    )
```
