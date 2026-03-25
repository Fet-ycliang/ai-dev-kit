---
name: databricks-spark-declarative-pipelines
description: "使用無伺服器計算建立、設定及更新 Databricks Lakeflow Spark Declarative Pipelines（SDP/LDP）。處理串流資料表、物化視圖、CDC、SCD Type 2 及 Auto Loader 攝取模式。適用於建立資料管道、處理 Delta Live Tables、攝取串流資料、實作異動資料擷取，或當使用者提及 SDP、LDP、DLT、Lakeflow 管道、串流資料表，或 bronze/silver/gold 三層式架構時使用。"
---

# Lakeflow Spark Declarative Pipelines（SDP）

重要事項：若為全新管道（尚未存在），請參閱快速入門。務必僅使用使用者指定的語言（Python 或 SQL）。新專案務必使用 Databricks Asset Bundles。

---

## 關鍵規則（必須遵守）
- **必須**確認語言為 Python 或 SQL。除非另有指示，否則維持該語言。
- **必須**若非修改現有管道，請使用下方[快速入門](#快速入門)。
- **必須**預設建立無伺服器管道。**只有在使用者明確要求 R 語言、Spark RDD API 或 JAR 函式庫時，才使用傳統叢集。


## 必要步驟

複製此清單並逐一確認：
```
- [ ] 語言已選定：Python 或 SQL
- [ ] 計算類型已決定：無伺服器或傳統計算
- [ ] 決定使用多個 Catalog/Schema 或統一使用單一預設 Schema
- [ ] 考慮哪些設定應在管道層級參數化以便於部署
- [ ] 考慮下方[多 Schema 模式](#多-schema-模式)，不確定最佳選擇時請提問
- [ ] 考慮下方[現代預設值](#現代預設值)，不確定最佳選擇時請提問


## 快速入門：初始化新管道專案

**建議**：使用 `databricks pipelines init` 建立具備多環境支援的生產就緒 Asset Bundle 專案。

### 何時使用 Bundle 初始化

使用 bundle 初始化適合**全新管道專案**，從一開始就獲得專業結構

使用手動流程適合：
- 無需多環境支援的快速原型
- 您想繼續使用的現有手動專案
- 學習/實驗用途

### 步驟一：初始化專案

當您要求新管道時，我會自動執行此指令：

```bash
databricks pipelines init
```

**互動式提示：**
- **Project name**：例如 `customer_orders_pipeline`
- **Initial catalog**：Unity Catalog 名稱（例如 `main`、`prod_catalog`）
- **Personal schema per user?**：開發環境選 `yes`（每位使用者有獨立 schema），生產環境選 `no`
- **Language**：SQL 或 Python（根據您的需求自動偵測，詳見下方語言偵測說明）

**產生的目錄結構：**
```
my_pipeline/
├── databricks.yml              # 多環境設定（dev/prod）
├── resources/
│   └── *_etl.pipeline.yml      # Pipeline 資源定義
└── src/
    └── *_etl/
        ├── explorations/       # .ipynb 探索性程式碼
        └── transformations/    # 您的 .sql 或 .py 檔案
```

### 步驟二：自訂轉換邏輯

將 init 過程建立的範例程式碼替換為 `src/transformations/` 中的自訂轉換檔案，依據提供的需求並參照本 skill 的最佳實踐指引。

**Python 管道使用 cloudFiles 時**：詢問使用者要將 Auto Loader schema 中繼資料存放在哪裡。建議：
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas
```

### 步驟三：部署與執行

```bash
# 部署至工作區（預設為 dev）
databricks bundle deploy

# 執行管道
databricks bundle run my_pipeline_etl

# 部署至生產環境
databricks bundle deploy --target prod
```


## 快速參考

| 概念 | 說明 |
|------|------|
| **名稱** | SDP = Spark Declarative Pipelines = LDP = Lakeflow Declarative Pipelines = Lakeflow Pipelines（可互換使用） |
| **Python 匯入** | `from pyspark import pipelines as dp` |
| **主要裝飾器** | `@dp.table()`、`@dp.materialized_view()`、`@dp.temporary_view()` |
| **暫時視圖** | `@dp.temporary_view()` 建立管道內暫時視圖（無 catalog/schema，不支援 cluster_by）。適用於 AUTO CDC 前的中間邏輯，或需要多次參照而不需持久化的視圖。 |
| **取代** | Delta Live Tables（DLT）的 `import dlt` |
| **基礎** | Apache Spark 4.1+（Databricks 現代資料管道框架） |
| **文件** | https://docs.databricks.com/aws/en/ldp/developer/python-dev |

---

## 詳細指南

**攝取模式**：規劃如何將新資料匯入 Lakeflow 管道時，請使用 [1-ingestion-patterns.md](1-ingestion-patterns.md)——涵蓋檔案格式、批次/串流選項，以及增量與全量載入的技巧。（關鍵字：Auto Loader、Kafka、Event Hub、Kinesis、檔案格式）

**串流管道模式**：設計含串流資料來源、異動資料偵測、觸發器及視窗化的管道，請參閱 [2-streaming-patterns.md](2-streaming-patterns.md)。（關鍵字：去重、視窗化、有狀態操作、join）

**SCD 查詢模式**：查詢 Slowly Changing Dimensions Type 2 歷程資料表，包含當前狀態查詢、時間點分析、時序 join 及異動追蹤，請參閱 [3-scd-query-patterns.md](3-scd-query-patterns.md)。（關鍵字：SCD Type 2 歷程資料表、時序 join、查詢歷史資料）

**效能調校**：使用 Liquid Clustering、狀態管理，以及高效能串流工作負載最佳實踐來優化管道，請使用 [4-performance-tuning.md](4-performance-tuning.md)。（關鍵字：Liquid Clustering、優化、狀態管理）

**Python API 參考**：現代 `pyspark.pipelines`（dp）API 參考及從舊版 `dlt` API 遷移，請參閱 [5-python-api.md](5-python-api.md)。（關鍵字：dp API、dlt API 比較）

**DLT 遷移**：將現有 Delta Live Tables（DLT）管道遷移至 Spark Declarative Pipelines（SDP），請使用 [6-dlt-migration.md](6-dlt-migration.md)。（關鍵字：將 DLT 管道遷移至 SDP）

**進階設定**：進階管道設定，包含開發模式、持續執行、通知、Python 相依套件及自訂叢集設定，請參閱 [7-advanced-configuration.md](7-advanced-configuration.md)。（關鍵字：extra_settings 參數參考、範例）

**專案初始化**：使用 `databricks pipelines init`、Asset Bundles、多環境部署及語言偵測邏輯設定新管道專案，請使用 [8-project-initialization.md](8-project-initialization.md)。（關鍵字：databricks pipelines init、Asset Bundles、語言偵測、遷移指南）

**AUTO CDC 模式**：使用 AUTO CDC 實作異動資料擷取，包含 Slow Changing Dimensions（SCD Type 1 與 Type 2）的異動追蹤與去重，請使用 [9-auto_cdc.md](9-auto_cdc.md)。（關鍵字：AUTO CDC、Slow Changing Dimension、SCD、SCD Type 1、SCD Type 2、異動資料擷取、去重）

---

## 工作流程

1. 判斷任務類型：

   **設定新專案？** → 先閱讀 [8-project-initialization.md](8-project-initialization.md)
   **建立新管道？** → 閱讀 [1-ingestion-patterns.md](1-ingestion-patterns.md)
   **建立串流資料表？** → 閱讀 [2-streaming-patterns.md](2-streaming-patterns.md)
   **查詢 SCD 歷程資料表？** → 閱讀 [3-scd-query-patterns.md](3-scd-query-patterns.md)
   **實作 AUTO CDC 或 SCD？** → 閱讀 [9-auto_cdc.md](9-auto_cdc.md)
   **效能問題？** → 閱讀 [4-performance-tuning.md](4-performance-tuning.md)
   **使用 Python API？** → 閱讀 [5-python-api.md](5-python-api.md)
   **從 DLT 遷移？** → 閱讀 [6-dlt-migration.md](6-dlt-migration.md)
   **進階設定？** → 閱讀 [7-advanced-configuration.md](7-advanced-configuration.md)
   **驗證？** → 閱讀 [7-advanced-configuration.md](7-advanced-configuration.md)（dry_run、開發模式）

2. 遵循相關指南中的說明

3. 對下一個任務類型重複上述步驟
---

## 官方文件

- **[Lakeflow Spark Declarative Pipelines 概覽](https://docs.databricks.com/aws/en/ldp/)** - 主要文件中心
- **[SQL 語言參考](https://docs.databricks.com/aws/en/ldp/developer/sql-dev)** - 串流資料表與物化視圖的 SQL 語法
- **[Python 語言參考](https://docs.databricks.com/aws/en/ldp/developer/python-ref)** - `pyspark.pipelines` API
- **[資料載入](https://docs.databricks.com/aws/en/ldp/load)** - Auto Loader、Kafka、Kinesis 攝取
- **[異動資料擷取（CDC）](https://docs.databricks.com/aws/en/ldp/cdc)** - AUTO CDC、SCD Type 1/2


### 三層式架構模式（Medallion Architecture）
  **Bronze 層（原始資料）**
  - 以原始格式從來源攝取資料
  - 最少轉換（僅附加、加入 `_ingested_at`、`_source_file` 等中繼資料）
  - 保存資料血緣的唯一真實來源

  **Silver 層（已驗證資料）**
  - 清理並驗證後的資料
  - 可在此以 auto_cdc 去重，但若可能，通常等到最後步驟再執行 auto_cdc。
  - 套用業務邏輯（型別轉換、品質檢查、過濾無效記錄）
  - 關鍵業務實體的企業視角
  - 支援自助式分析與 ML

  **Gold 層（業務就緒資料）**
  - 聚合、反正規化、專案專用的資料表
  - 針對消費優化（報表、儀表板、BI 工具）
  - 較少 join，讀取最佳化的資料模型
  - Kimball 星型結構資料表：dim_\<entity_name\>、fact_\<entity_name\>
  - 去重通常透過 Slow Changing Dimensions（SCD）在此進行，使用 auto_cdc。有時會在 silver 上游進行，例如當需要 join 多張資料表，或業務使用者計畫直接從 silver 查詢時。

  **典型流程（可依需求調整）**
  Bronze：read_files() 或 spark.readStream.format("cloudFiles") → 串流資料表
  Silver：讀取 bronze → 過濾/清理/驗證 → 串流資料表
  Gold：讀取 silver → 聚合/反正規化 → auto_cdc 或物化視圖

  資料來源：
  - https://www.databricks.com/glossary/medallion-architecture
  - https://docs.databricks.com/aws/en/lakehouse/medallion
  - https://www.databricks.com/blog/2022/06/24/data-warehousing-modeling-techniques-and-their-implementation-on-the-databricks-lakehouse-platform.html

**三層式架構**（bronze/silver/gold）有兩種方式：
- **平面式命名**（範本預設）：`bronze_*.sql`、`silver_*.sql`、`gold_*.sql`
- **子目錄式**：`bronze/orders.sql`、`silver/cleaned.sql`、`gold/summary.sql`

兩者皆可搭配 `transformations/**` glob 模式。依個人偏好選擇。

完整的 bundle 初始化、遷移及疑難排解詳情，請參閱 **[8-project-initialization.md](8-project-initialization.md)**。

---
## 通用 SDP 開發指南
### 步驟一：在本地撰寫管道檔案

在本地資料夾中建立 `.sql` 或 `.py` 檔案：

```
my_pipeline/
├── bronze/
│   ├── ingest_orders.sql       # SQL（大多數情況的預設選擇）
│   └── ingest_events.py        # Python（複雜邏輯時使用）
├── silver/
│   └── clean_orders.sql
└── gold/
    └── daily_summary.sql
```

**SQL 範例**（`bronze/ingest_orders.sql`）：
```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders
CLUSTER BY (order_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM read_files(
  '/Volumes/catalog/schema/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, customer_id STRING, amount DECIMAL(10,2), order_date DATE'
);
```

**Python 範例**（`bronze/ingest_events.py`）：
```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col, current_timestamp

# 從管道設定取得 schema 位置
schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_events", cluster_by=["event_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_source_file", col("_metadata.file_path"))
    )
```

**Python 管道重要說明**：使用 `spark.readStream.format("cloudFiles")` 進行雲端儲存攝取，且使用 schema 推論（未指定 schema）時，**必須指定 schema 位置**。

**務必詢問使用者**要將 Auto Loader schema 中繼資料存放在哪裡。建議：
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas
```

範例：`/Volumes/my_catalog/pipeline_metadata/orders_pipeline_metadata/schemas`

**切勿使用來源資料 Volume** — 這會造成權限衝突。schema 位置應在管道設定中設定，並透過 `spark.conf.get("schema_location_base")` 存取。

**語言選擇：**

**關鍵規則**：若使用者明確在需求中提及「Python」（例如「Python Spark Declarative Pipeline」、「Python SDP」、「use Python」），**務必直接使用 Python，無需詢問**。SQL 亦同——若使用者說「SQL pipeline」，則使用 SQL。

- **明確語言需求**：使用者說「Python」→ 使用 Python。使用者說「SQL」→ 使用 SQL。**不需要詢問確認。**
- **自動偵測**（僅在未明確提及語言時）：
  - **SQL 指標**：「sql files」、「簡單轉換」、「聚合」、「materialized view」、「CREATE OR REFRESH」
  - **Python 指標**：「.py files」、「UDF」、「複雜邏輯」、「ML 推論」、「外部 API」、「@dp.table」、「pandas」、「decorator」
- **僅在語言意圖真正模糊時**（未明確提及，且有混合訊號）才請求澄清
- **僅在模糊且無 Python 指標時**預設使用 SQL

詳細語言偵測邏輯請參閱 **[8-project-initialization.md](8-project-initialization.md)**。


## 選項一：搭配 DABs 的管道
使用 asset bundles 與 pipeline CLI。
完整詳情請參閱[快速入門](#快速入門)與 **[8-project-initialization.md](8-project-initialization.md)**。

## 選項二：手動工作流程（進階）

適用於快速原型、實驗，或偏好不使用 Asset Bundles 直接控制的情境，使用手動工作流程搭配 MCP 工具。

使用 MCP 工具建立、執行及迭代**無伺服器 SDP 管道**。**主要工具為 `create_or_update_pipeline`**，可處理完整生命週期。

**重要：預設建立無伺服器管道。** 只有在使用者明確要求傳統、pro、advanced 計算，或需要 R 語言、Spark RDD API 或 JAR 函式庫時，才使用傳統叢集。

詳細指南請參閱 **[10-mcp-approach.md](10-mcp-approach.md)**。


## 最佳實踐（2026）

### 專案結構
- **新專案預設使用 `databricks pipelines init`**（建立 Asset Bundle）
- **使用 Asset Bundles** 進行多環境部署（dev/staging/prod）
- **手動結構**僅用於快速原型或舊版遷移
- **三層式架構**：兩種方式皆可搭配 Asset Bundles：
  - **平面結構**（範本預設）：`transformations/` 中的 `bronze_*.sql`、`silver_*.sql`、`gold_*.sql`
  - **子目錄結構**：`transformations/bronze/`、`transformations/silver/`、`transformations/gold/`
  - 兩者皆可搭配 `transformations/**` glob 模式——依團隊偏好選擇
- 專案設定詳情請參閱 **[8-project-initialization.md](8-project-initialization.md)**

### 管道設定最小化指引
- 在管道設定中定義參數，並在程式碼中透過 spark.conf.get("key") 存取。
- 在 Databricks Asset Bundles 中，於 resources.pipelines.\<pipeline\>.configuration 下設定；使用 databricks bundle validate 驗證。

### 現代預設值
- **CLUSTER BY**（Liquid Clustering），而非 PARTITION BY——參閱 [4-performance-tuning.md](4-performance-tuning.md)
- **原始 `.sql`/`.py` 檔案**，而非 Notebook
- **僅使用無伺服器計算**——除非明確需要，否則不使用傳統叢集
- **Unity Catalog**（無伺服器必須）
- SQL 進行雲端儲存攝取時**使用 read_files()**——參閱 [1-ingestion-patterns.md](1-ingestion-patterns.md)

### 多 Schema 模式

**預設：每個管道使用單一目標 schema。** 每個管道有一個目標 `catalog` 和 `schema`，所有資料表都寫入其中。


#### 選項一：單一管道，單一 Schema 加前綴命名（建議）

使用一個 schema，透過資料表名稱前綴區分不同層次：

```python
# 所有資料表寫入：catalog.schema.bronze_*、silver_*、gold_*
@dp.table(name="bronze_orders")  # → catalog.schema.bronze_orders
@dp.table(name="silver_orders")  # → catalog.schema.silver_orders
@dp.table(name="gold_summary")   # → catalog.schema.gold_summary
```

**優點：**
- 設定更簡單（單一管道）
- 所有資料表在同一 schema，易於探索

#### 選項二：
使用變數為不同步驟指定獨立的 catalog 和/或 schema。

以下是 Python SDP 範例，透過 spark.conf.get 從管道設定取得變數，bronze 使用預設 catalog/schema。

##### 相同 catalog，分開的 schema；bronze 使用管道預設值
- 將管道的預設 catalog 和 schema 設為 bronze 層（例如 catalog=my_catalog、schema=bronze）。在程式碼中省略 catalog/schema 時，讀寫會使用這些預設值。
- 其他 schema 及任何來源 schema/路徑使用管道參數，在程式碼中透過 spark.conf.get(...) 取得。

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# 從管道設定參數取得變數
silver_schema = spark.conf.get("silver_schema")  # 例如 "silver"
gold_schema   = spark.conf.get("gold_schema")    # 例如 "gold"
landing_schema = spark.conf.get("landing_schema")  # 例如 "landing"

# Bronze → 使用預設 catalog/schema（管道設定中設為 bronze）
@dp.table(name="orders_bronze")
def orders_bronze():
    # 從相同預設 catalog 的另一個 schema 讀取
    return spark.readStream.table(f"{landing_schema}.orders_raw")

# Silver → 相同 catalog，schema 來自參數
@dp.table(name=f"{silver_schema}.orders_clean")
def orders_clean():
    return (spark.read.table("orders_bronze")  # 未限定名稱 = 預設 catalog/schema
            .filter(col("order_id").isNotNull()))

# Gold → 相同 catalog，schema 來自參數
@dp.materialized_view(name=f"{gold_schema}.orders_by_date")
def orders_by_date():
    return (spark.read.table(f"{silver_schema}.orders_clean")
            .groupBy("order_date")
            .count().withColumnRenamed("count", "order_count"))
```
- bronze 使用未限定名稱可確保其寫入管道預設 catalog/schema；silver/gold 在相同 catalog 內以明確 schema 限定。

---

##### 每層使用自訂 catalog/schema；bronze 仍使用管道預設值
- Bronze 保留在管道預設值中（預設 catalog/schema 設為 bronze 層）。silver/gold 使用完整限定名稱，catalog 和 schema 變數來自管道設定。

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# 從管道設定參數取得變數
silver_catalog = spark.conf.get("silver_catalog")  # 例如 "my_catalog"
silver_schema  = spark.conf.get("silver_schema")   # 例如 "silver"
gold_catalog   = spark.conf.get("gold_catalog")    # 例如 "my_catalog"
gold_schema    = spark.conf.get("gold_schema")     # 例如 "gold"
landing_catalog = spark.conf.get("landing_catalog")  # 可選，若來源在另一個 catalog
landing_schema  = spark.conf.get("landing_schema")

# Bronze → 使用預設 catalog/schema（設為 bronze）
@dp.table(name="orders_bronze")
def orders_bronze():
    # 若來源在指定的 catalog/schema：
    return spark.readStream.table(f"{landing_catalog}.{landing_schema}.orders_raw")

# Silver → 透過參數指定自訂 catalog + schema
@dp.table(name=f"{silver_catalog}.{silver_schema}.orders_clean")
def orders_clean():
    # 以未限定名稱讀取 bronze（使用預設值），或視需要加上完整限定
    return (spark.read.table("orders_bronze")
            .filter(col("order_id").isNotNull()))

# Gold → 透過參數指定自訂 catalog + schema
@dp.materialized_view(name=f"{gold_catalog}.{gold_schema}.orders_by_date}")
def orders_by_date():
    return (spark.read.table(f"{silver_catalog}.{silver_schema}.orders_clean")
            .groupBy("order_date")
            .count().withColumnRenamed("count", "order_count"))
```
- 裝飾器 name 引數中的多部分名稱，可讓您在單一管道內發布至明確的 catalog.schema 目標。
- 未限定的讀寫使用管道預設值；跨 catalog 或需要明確命名空間控制時，使用完整限定名稱。

---


**注意：** `@dp.table()` 裝飾器目前不支援獨立的 `schema=` 或 `catalog=` 參數。table 參數為包含 catalog.schema.table_name 的字串，或省略 catalog 和/或 schema 以使用管道設定的預設目標 schema。

### 在 Python 中讀取資料表

**現代 SDP 最佳實踐：**
- 批次讀取使用 `spark.read.table()`
- 串流讀取使用 `spark.readStream.table()`
- 不使用 `dp.read()` 或 `dp.read_stream()`（舊語法，已不在文件中）
- 不使用 `dlt.read()` 或 `dlt.read_stream()`（舊版 DLT API）

**重點：** SDP 可從標準 Spark DataFrame 操作自動追蹤資料表依賴關係，無需特殊的讀取 API。

#### 三層識別符解析

SDP 支援三種資料表名稱限定層級：

| 層級 | 語法 | 使用時機 |
|------|------|---------|
| **未限定** | `spark.read.table("my_table")` | 讀取同一管道目標 catalog/schema 中的資料表（建議） |
| **部分限定** | `spark.read.table("other_schema.my_table")` | 從相同 catalog 的不同 schema 讀取 |
| **完整限定** | `spark.read.table("other_catalog.other_schema.my_table")` | 從外部 catalog/schema 讀取 |

#### 選項一：未限定名稱（管道內資料表的建議方式）

**管道內資料表的最佳實踐。** SDP 將未限定名稱解析為管道設定的目標 catalog 和 schema，使程式碼可在不同環境（dev/prod）間移植。

```python
@dp.table(name="silver_clean")
def silver_clean():
    # 從管道目標 catalog/schema 讀取（例如 dev_catalog.dev_schema.bronze_raw）
    return (
        spark.read.table("bronze_raw")
        .filter(F.col("valid") == True)
    )

@dp.table(name="silver_events")
def silver_events():
    # 從相同管道的 bronze_events 資料表串流讀取
    return (
        spark.readStream.table("bronze_events")
        .withColumn("processed_at", F.current_timestamp())
    )
```

#### 選項二：管道參數（用於外部來源）

**使用 `spark.conf.get()` 將外部 catalog/schema 參數化。** 在管道設定中定義參數，然後在模組層級引用。

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# 在模組層級取得參數化值（在管道啟動時計算一次）
source_catalog = spark.conf.get("source_catalog")
source_schema = spark.conf.get("source_schema", "sales")  # 含預設值

@dp.table(name="transaction_summary")
def transaction_summary():
    return (
        spark.read.table(f"{source_catalog}.{source_schema}.transactions")
        .groupBy("account_id")
        .agg(
            F.count("txn_id").alias("txn_count"),
            F.sum("txn_amount").alias("account_revenue")
        )
    )
```

**在管道設定中設定參數：**
- **Asset Bundles**：在 `pipeline.yml` 的 `configuration:` 下新增
- **手動/MCP**：透過 `extra_settings.configuration` dict 傳入

```yaml
# 在 resources/my_pipeline.pipeline.yml 中
configuration:
  source_catalog: "shared_catalog"
  source_schema: "sales"
```

#### 選項三：完整限定名稱（固定外部參考）

用於參考跨環境不會變動的特定外部資料表：

```python
@dp.table(name="enriched_orders")
def enriched_orders():
    # 管道內部資料表（未限定）
    orders = spark.read.table("bronze_orders")

    # 外部參考資料表（完整限定）
    products = spark.read.table("shared_catalog.reference.products")

    return orders.join(products, "product_id")
```

#### 選擇正確的方式

| 情境 | 建議方式 |
|------|---------|
| 讀取同一管道建立的資料表 | **未限定名稱** — 可移植，使用目標 catalog/schema |
| 讀取因環境而異的外部來源 | **管道參數** — 每次部署可設定 |
| 讀取位置固定的共用/參考資料表 | **完整限定名稱** — 明確清晰 |
| 混合管道（部分內部、部分外部） | **結合多種方式** — 內部用未限定，外部用參數 |

---

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| **輸出資料表為空** | 使用 `get_table_details` 驗證，檢查上游來源 |
| **管道卡在 INITIALIZING** | 無伺服器管道正常現象，等待幾分鐘 |
| **「Column not found」** | 確認 `schemaHints` 與實際資料相符 |
| **串流讀取失敗** | 串流資料表的檔案攝取必須使用 `STREAM` 關鍵字搭配 `read_files`：`FROM STREAM read_files(...)`。資料表串流使用 `FROM stream(table)`。參閱 [read_files — 串流資料表中的用法](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables)。 |
| **執行逾時** | 增加 `timeout`，或使用 `wait_for_completion=False` 並以 `get_pipeline` 確認狀態 |
| **物化視圖未重新整理** | 在來源資料表上啟用 row tracking |
| **SCD2：找不到查詢欄位** | Lakeflow 使用 `__START_AT` 與 `__END_AT`（雙底線），而非 `START_AT`/`END_AT`。使用 `WHERE __END_AT IS NULL` 取得當前資料列。參閱 [3-scd-query-patterns.md](3-scd-query-patterns.md)。 |
| **AUTO CDC 在 APPLY/SEQUENCE 出現解析錯誤** | 將 `APPLY AS DELETE WHEN` 放在 `SEQUENCE BY` **之前**。`COLUMNS * EXCEPT (...)` 中只列出來源中存在的欄位（除非 bronze 使用 rescue data，否則省略 `_rescued_data`）。如果 `TRACK HISTORY ON *` 導致「end of input」錯誤，可省略；預設行為相同。參閱 [2-streaming-patterns.md](2-streaming-patterns.md)。 |
| **「Cannot create streaming table from batch query」** | 串流資料表查詢中，使用 `FROM STREAM read_files(...)` 讓 `read_files` 利用 Auto Loader；單獨使用 `FROM read_files(...)` 是批次模式。參閱 [1-ingestion-patterns.md](1-ingestion-patterns.md) 與 [read_files — 串流資料表中的用法](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables)。 |

**若需詳細錯誤資訊**，`create_or_update_pipeline` 的 `result["message"]` 包含建議的後續步驟。使用 `get_pipeline(pipeline_id=...)` 可取得近期事件與錯誤詳情。

---

## 進階管道設定

進階設定選項（開發模式、持續管道、自訂叢集、通知、Python 相依套件等），請參閱 **[7-advanced-configuration.md](7-advanced-configuration.md)**。

---

## 平台限制

### 無伺服器管道需求（預設）
| 需求 | 說明 |
|------|------|
| **Unity Catalog** | 必須 — 無伺服器管道一律使用 UC |
| **工作區區域** | 必須位於支援無伺服器的區域 |
| **無伺服器條款** | 必須接受無伺服器使用條款 |
| **CDC 功能** | 需要無伺服器（或傳統叢集的 Pro/Advanced） |

### 無伺服器限制（需使用傳統叢集時）
| 限制 | 替代方案 |
|------|---------|
| **R 語言** | 不支援——若有需要請使用傳統叢集 |
| **Spark RDD API** | 不支援——若有需要請使用傳統叢集 |
| **JAR 函式庫** | 不支援——若有需要請使用傳統叢集 |
| **Maven 座標** | 不支援——若有需要請使用傳統叢集 |
| **DBFS root 存取** | 受限——必須使用 Unity Catalog 外部位置 |
| **Global temp views** | 不支援 |

### 一般限制
| 限制 | 說明 |
|------|------|
| **Schema 演進** | 串流資料表不相容的異動需要完整重新整理 |
| **SQL 限制** | 不支援 PIVOT 子句 |
| **Sink** | 僅支援 Python、僅串流、僅附加 flow |

**預設使用無伺服器**，除非使用者明確需要 R、RDD API 或 JAR 函式庫。

## 相關 Skills

- **[databricks-jobs](../databricks-jobs/SKILL.md)** — 管道執行的編排與排程
- **[databricks-bundles](../databricks-bundles/SKILL.md)** — 管道專案的多環境部署
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — 生成測試資料供管道使用
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — catalog/schema/volume 管理與治理
