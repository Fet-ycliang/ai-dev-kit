---
name: spark-python-data-source
description: 使用 PySpark DataSource API 為 Apache Spark 建立自訂 Python 資料來源——為外部系統實作批次與串流讀取器/寫入器。當有人想要將 Spark 連接到外部系統（資料庫、API、訊息佇列、自訂通訊協定）、用 Python 建立 Spark connector 或外掛、實作 DataSourceReader 或 DataSourceWriter、透過 Spark 從系統拉取資料或將資料推送到系統，或以任何方式使用 PySpark DataSource API 時，都應使用此技能。即使他們只是說「在 Spark 從 X 讀取」或「把 DataFrame 寫入 Y」，而且沒有原生 connector，這個技能也適用。
---

# spark-python-data-source

為 Apache Spark 4.0+ 建立自訂 Python 資料來源，以在批次與串流模式下從外部系統讀取與寫入資料。

## 指引

你是一位經驗豐富的 Spark 開發者，負責使用 PySpark DataSource API 建立自訂 Python 資料來源。請遵循下列原則與模式。

### 核心架構

每個資料來源都遵循扁平、單層的繼承結構：

1. **DataSource class** — 回傳 readers/writers 的進入點
2. **Base Reader/Writer classes** — 共用 options 與資料處理邏輯
3. **Batch classes** — 繼承 base class 與 `DataSourceReader`/`DataSourceWriter`
4. **Stream classes** — 繼承 base class 與 `DataSourceStreamReader`/`DataSourceStreamWriter`

請參閱 [implementation-template.md](references/implementation-template.md)，其中包含涵蓋四種模式（批次讀取/寫入、串流讀取/寫入）的完整註解骨架。

### Spark 專屬設計限制

以下限制是 PySpark DataSource API 與其 driver/executor 架構所特有的一般 Python 最佳實務（乾淨程式碼、最小依賴、不過早抽象化）仍然適用，但此處不再重複。

**只使用扁平的單層繼承。** PySpark 會序列化 reader/writer 執行個體，並將它們傳送到 executors。複雜的繼承階層與抽象 base class 會破壞序列化，也會讓跨程序除錯變得困難。請使用一個共用 base class，再混入對應的 PySpark 介面（例如 `class YourBatchWriter(YourWriter, DataSourceWriter)`）。

**在 executor 方法內匯入第三方函式庫。** `read()` 與 `write()` 方法會在遠端 executor 程序上執行，這些程序不會共享 driver 的 Python 環境。driver 端的頂層 imports 在 executors 上不可用，因此像 `requests` 或資料庫 driver 這類函式庫，務必在會於 worker 上執行的方法內匯入。

**將依賴降到最低。** 你新增的每個套件都必須安裝在叢集中所有 executor 節點上，而不只是 driver。優先使用標準函式庫；若確實需要外部套件，請選擇少量且廣為人知的套件。

**除非外部系統的 SDK 只支援 async，否則不要使用 async/await。** PySpark DataSource API 是同步式的，因此 async 只會增加複雜度而沒有實質效益。

### 專案設定

使用 `uv`、`poetry` 或 `hatch` 等封裝工具建立 Python 專案。以下範例使用 `uv`（可替換為你偏好的工具）：

```bash
uv init your-datasource
cd your-datasource
uv add pyspark pytest pytest-spark
```

```
your-datasource/
├── pyproject.toml
├── src/
│   └── your_datasource/
│       ├── __init__.py
│       └── datasource.py
└── tests/
    ├── conftest.py
    └── test_datasource.py
```

所有指令都應透過封裝工具執行，以確保使用正確的虛擬環境：

```bash
uv run pytest                       # 執行測試
uv run ruff check src/              # 執行 Lint 檢查
uv run ruff format src/             # 格式化程式碼
uv build                            # 建置 wheel
```

### 關鍵實作決策

**Partitioning Strategy** — 依據資料來源特性選擇：
- Time-based：適用於具有時間序資料的 API
- Token-range：適用於分散式資料庫
- ID-range：適用於具分頁機制的 API
- 各策略的實作請參閱 [partitioning-patterns.md](references/partitioning-patterns.md)

**Authentication** — 依優先順序支援多種方法：
- Databricks Unity Catalog credentials
- Cloud default credentials（managed identity）
- Explicit credentials（service principal、API key、username/password）
- 具備 fallback 鏈的模式請參閱 [authentication-patterns.md](references/authentication-patterns.md)

**Type Conversion** — 在 Spark 與外部型別之間對應：
- 處理 null、timestamps、UUIDs、collections
- 雙向對應表與輔助函式請參閱 [type-conversion.md](references/type-conversion.md)

**Streaming Offsets** — 針對 exactly-once semantics 進行設計：
- 可 JSON 序列化的 offset class
- 不重疊的分區邊界
- offset 追蹤與 watermark 模式請參閱 [streaming-patterns.md](references/streaming-patterns.md)

**Error Handling** — 實作重試與韌性：
- 針對暫時性失敗（網路、rate limits）使用指數退避
- 使用 circuit breakers 防止連鎖失敗
- 重試 decorator 與失敗分類請參閱 [error-handling.md](references/error-handling.md)

### 測試

```python
import pytest
from unittest.mock import patch, Mock

@pytest.fixture
def spark():
    from pyspark.sql import SparkSession
    return SparkSession.builder.master("local[2]").getOrCreate()

def test_data_source_name():
    assert YourDataSource.name() == "your-format"

def test_writer_sends_data(spark):
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        df = spark.createDataFrame([(1, "test")], ["id", "value"])
        df.write.format("your-format").option("url", "http://api").save()

        assert mock_post.called
```

單元測試、整合測試模式、fixtures 與測試執行方式請參閱 [testing-patterns.md](references/testing-patterns.md)。

### 參考實作

請研究下列真實世界模式：
- [cyber-spark-data-connectors](https://github.com/alexott/cyber-spark-data-connectors) — Sentinel、Splunk、REST
- [spark-cassandra-data-source](https://github.com/alexott/spark-cassandra-data-source) — Token-range 分區
- [pyspark-hubspot](https://github.com/dgomez04/pyspark-hubspot) — REST API 分頁
- [pyspark-mqtt](https://github.com/databricks-industry-solutions/python-data-sources/tree/main/mqtt) — 使用 TLS 的串流

## 範例提示

```
建立一個支援分片的 MongoDB Spark 資料來源
建立一個具備至少一次投遞保證的 RabbitMQ 串流 connector
為 Snowflake 實作具備 staged uploads 的批次 writer
為具備 OAuth2 認證與分頁機制的 REST API 撰寫資料來源
```

## 相關技能

- databricks-testing: 在 Databricks 叢集上測試資料來源
- databricks-spark-declarative-pipelines: 在 DLT pipelines 中使用自訂來源
- python-dev: Python 開發最佳實務

## 參考資料

- [implementation-template.md](references/implementation-template.md) — 開始新資料來源時必讀的完整註解骨架
- [partitioning-patterns.md](references/partitioning-patterns.md) — 當來源支援平行讀取，且你需要將工作分散到 executors 時請閱讀
- [authentication-patterns.md](references/authentication-patterns.md) — 當外部系統需要 credentials 或 tokens 時請閱讀
- [type-conversion.md](references/type-conversion.md) — 當需要在 Spark 型別與外部系統型別系統之間進行對應時請閱讀
- [streaming-patterns.md](references/streaming-patterns.md) — 當要實作 `DataSourceStreamReader` 或 `DataSourceStreamWriter` 時請閱讀
- [error-handling.md](references/error-handling.md) — 當要加入重試邏輯或處理暫時性失敗時請閱讀
- [testing-patterns.md](references/testing-patterns.md) — 撰寫測試時請閱讀；涵蓋單元、整合與效能測試
- [production-patterns.md](references/production-patterns.md) — 進入生產環境前請閱讀；涵蓋可觀測性、安全性與輸入驗證
- [Databricks 官方文件](https://docs.databricks.com/aws/en/pyspark/datasources)
- [Apache Spark Python DataSource 教學](https://spark.apache.org/docs/latest/api/python/tutorial/sql/python_data_source.html)
- [awesome-python-datasources](https://github.com/allisonwang-db/awesome-python-datasources) — 社群實作目錄
