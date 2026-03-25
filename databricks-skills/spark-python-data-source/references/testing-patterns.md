# 測試模式

Spark 資料來源的單位和整合測試策略。

## 基本單位測試

測試資料來源註冊和初始化：

```python
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark():
    """為測試建立 Spark 工作階段。"""
    return SparkSession.builder \
        .master("local[2]") \
        .appName("test") \
        .config("spark.sql.shuffle.partitions", "2") \
        .getOrCreate()

def test_data_source_name():
    """測試資料來源名稱註冊。"""
    assert YourDataSource.name() == "your-format"

def test_data_source_initialization():
    """測試資料來源可初始化。"""
    options = {"url": "http://api.example.com"}
    ds = YourDataSource(options)
    assert ds.options == options

def test_missing_required_option():
    """測試缺少必要選項時出錯。"""
    options = {}  # 缺少必要的 'url'

    with pytest.raises(AssertionError, match="url is required"):
        YourDataSource(options)
```

## 模擬 HTTP 請求

在無外部依存情況下測試寫入器：

```python
from unittest.mock import patch, Mock
import pytest

@pytest.fixture
def basic_options():
    """測試的共通選項。"""
    return {
        "url": "http://api.example.com",
        "batch_size": "10"
    }

@pytest.fixture
def sample_schema():
    """測試的樣本綱要。"""
    from pyspark.sql.types import StructType, StructField, IntegerType, StringType
    return StructType([
        StructField("id", IntegerType(), False),
        StructField("name", StringType(), True)
    ])

def test_writer_sends_batch(spark, basic_options, sample_schema):
    """測試寫入器以批次傳送資料。"""
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        # 建立測試資料
        df = spark.createDataFrame([
            (1, "Alice"),
            (2, "Bob"),
            (3, "Charlie")
        ], ["id", "name"])

        # 使用資料來源寫入
        df.write.format("your-format").options(**basic_options).save()

        # 驗證 API 被呼叫
        assert mock_post.called
        assert mock_post.call_count > 0

def test_writer_respects_batch_size(spark, basic_options, sample_schema):
    """測試寫入器尊重已設定的批次大小。"""
    with patch('requests.post') as mock_post:
        mock_post.return_value = Mock(status_code=200)

        # 使用 batch_size=10 建立 25 列
        rows = [(i, f"name_{i}") for i in range(25)]
        df = spark.createDataFrame(rows, ["id", "name"])

        df.write.format("your-format").options(**basic_options).save()

        # 應進行 3 次呼叫：10 + 10 + 5
        assert mock_post.call_count == 3
```

## 測試讀取器

模擬外部 API 回應：

```python
def test_reader_fetches_data(spark, basic_options):
    """測試讀取器擷取並轉換資料。"""
    with patch('requests.get') as mock_get:
        # 模擬 API 回應
        mock_response = Mock()
        mock_response.json.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]
        mock_get.return_value = mock_response

        # 使用資料來源讀取
        df = spark.read.format("your-format").options(**basic_options).load()

        # 驗證資料
        rows = df.collect()
        assert len(rows) == 2
        assert rows[0]["id"] == 1
        assert rows[0]["name"] == "Alice"

def test_reader_handles_empty_response(spark, basic_options):
    """測試讀取器處理空回應。"""
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        df = spark.read.format("your-format").options(**basic_options).load()

        assert df.count() == 0
```

## 測試分割區

測試分割區建立邏輯：

```python
def test_partitions_created(basic_options, sample_schema):
    """測試建立正確的分割區數。"""
    options = {**basic_options, "num_partitions": "4"}

    reader = YourBatchReader(options, sample_schema)
    partitions = reader.partitions()

    assert len(partitions) == 4

def test_partition_ranges_non_overlapping():
    """測試分割區具非重疊的範圍。"""
    from datetime import datetime, timedelta

    reader = TimeBasedReader(options, schema)
    partitions = reader.partitions()

    # 檢查無間隙或重疊
    for i in range(len(partitions) - 1):
        current_end = partitions[i].end_time
        next_start = partitions[i + 1].start_time

        # 下一個分割區應在目前結束後立即開始
        assert next_start >= current_end
```

## 測試串流

測試位移管理和串流邏輯：

```python
def test_initial_offset():
    """測試初始位移正確。"""
    from datetime import datetime

    reader = YourStreamReader(options, schema)
    initial = reader.initialOffset()

    # 應為有效 JSON
    import json
    offset_dict = json.loads(initial)

    assert "timestamp" in offset_dict

def test_latest_offset_advances():
    """測試最新位移隨時間推進。"""
    reader = YourStreamReader(options, schema)

    offset1 = reader.latestOffset()
    import time
    time.sleep(0.1)
    offset2 = reader.latestOffset()

    # 位移應推進
    assert offset2 > offset1 or offset2 != offset1

def test_partitions_non_overlapping(basic_options, sample_schema):
    """測試串流分割區不重疊。"""
    reader = YourStreamReader(basic_options, sample_schema)

    start = reader.initialOffset()
    end = reader.latestOffset()

    partitions = reader.partitions(start, end)

    # 驗證無重疊
    for i in range(len(partitions) - 1):
        assert partitions[i].end_time < partitions[i + 1].start_time
```

## 測試類型轉換

測試型別對應和轉換：

```python
def test_convert_timestamp():
    """測試時間戳記轉換。"""
    from datetime import datetime
    from pyspark.sql.types import TimestampType

    dt = datetime(2024, 1, 1, 12, 0, 0)
    result = convert_external_to_spark(dt, TimestampType())

    assert isinstance(result, datetime)
    assert result == dt

def test_convert_null_values():
    """測試 null 值處理。"""
    from pyspark.sql.types import StringType

    result = convert_external_to_spark(None, StringType())
    assert result is None

def test_convert_invalid_type():
    """測試無效型別轉換出錯。"""
    from pyspark.sql.types import IntegerType

    with pytest.raises(ValueError, match="Cannot convert"):
        convert_external_to_spark("not_a_number", IntegerType())
```

## 使用 Testcontainers 的整合測試

對實際系統執行端對端測試：

```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    """為整合測試啟動 PostgreSQL 容器。"""
    with PostgresContainer("postgres:15") as container:
        yield container

@pytest.fixture
def postgres_connection(postgres_container):
    """建立測試資料庫連接。"""
    import psycopg2

    conn = psycopg2.connect(postgres_container.get_connection_url())
    cursor = conn.cursor()

    # 建立測試表
    cursor.execute("""
        CREATE TABLE test_data (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            value INTEGER
        )
    """)
    conn.commit()

    yield conn

    conn.close()

def test_write_integration(spark, postgres_container, postgres_connection):
    """PostgreSQL 寫入整合測試。"""
    # 建立測試資料
    df = spark.createDataFrame([
        (1, "Alice", 100),
        (2, "Bob", 200)
    ], ["id", "name", "value"])

    # 使用資料來源寫入
    df.write.format("your-format") \
        .option("url", postgres_container.get_connection_url()) \
        .option("table", "test_data") \
        .save()

    # 驗證已寫入資料
    cursor = postgres_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM test_data")
    count = cursor.fetchone()[0]

    assert count == 2

def test_read_integration(spark, postgres_container, postgres_connection):
    """PostgreSQL 讀取整合測試。"""
    # 插入測試資料
    cursor = postgres_connection.cursor()
    cursor.execute("INSERT INTO test_data (name, value) VALUES ('Alice', 100)")
    cursor.execute("INSERT INTO test_data (name, value) VALUES ('Bob', 200)")
    postgres_connection.commit()

    # 使用資料來源讀取
    df = spark.read.format("your-format") \
        .option("url", postgres_container.get_connection_url()) \
        .option("table", "test_data") \
        .load()

    # 驗證資料
    assert df.count() == 2
    names = [row["name"] for row in df.collect()]
    assert "Alice" in names
    assert "Bob" in names
```

## 效能測試

測試效能特性：

```python
import time

def test_write_performance(spark, basic_options):
    """測試寫入效能符合需求。"""
    # 建立大型資料集
    rows = [(i, f"name_{i}") for i in range(10000)]
    df = spark.createDataFrame(rows, ["id", "name"])

    start = time.time()
    df.write.format("your-format").options(**basic_options).save()
    duration = time.time() - start

    # 應在合理時間內完成
    assert duration < 30.0  # 30 秒

    # 計算輸送量
    throughput = len(rows) / duration
    print(f"寫入輸送量：{throughput:.0f} 列/秒")

def test_partition_read_parallelism(spark, basic_options):
    """測試讀取以並行方式執行。"""
    options = {**basic_options, "num_partitions": "4"}

    df = spark.read.format("your-format").options(**options).load()

    # 檢查分割區計數
    assert df.rdd.getNumPartitions() == 4
```

## 測試夾具和公用程式

可重複使用的測試夾具：

```python
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark():
    """共用 Spark 工作階段。"""
    return SparkSession.builder \
        .master("local[2]") \
        .appName("test") \
        .config("spark.sql.shuffle.partitions", "2") \
        .getOrCreate()

@pytest.fixture
def sample_dataframe(spark):
    """用於測試的樣本 DataFrame。"""
    return spark.createDataFrame([
        (1, "Alice", 25),
        (2, "Bob", 30),
        (3, "Charlie", 35)
    ], ["id", "name", "age"])

@pytest.fixture
def temp_output_path(tmp_path):
    """暫時輸出路徑。"""
    return str(tmp_path / "output")

def assert_dataframes_equal(df1, df2):
    """宣告兩個 DataFrame 相等。"""
    assert df1.schema == df2.schema
    assert df1.count() == df2.count()

    rows1 = sorted(df1.collect())
    rows2 = sorted(df2.collect())

    assert rows1 == rows2
```

## 測試組織

按功能組織測試：

```
tests/
├── unit/
│   ├── test_datasource.py       # DataSource 類別測試
│   ├── test_reader.py            # 讀取器測試
│   ├── test_writer.py            # 寫入器測試
│   ├── test_partitioning.py      # 分割區邏輯
│   └── test_type_conversion.py   # 型別轉換
├── integration/
│   ├── test_read_integration.py  # 端對端讀取測試
│   ├── test_write_integration.py # 端對端寫入測試
│   └── test_streaming.py         # 串流測試
├── performance/
│   └── test_performance.py       # 效能測試
└── conftest.py                   # 共用夾具
```

## 執行測試

透過您的打包工具執行測試（如 `uv run`、`poetry run`、`hatch run`）。範例使用 `uv`：

```bash
# 執行所有測試
uv run pytest

# 執行特定測試檔
uv run pytest tests/unit/test_writer.py

# 執行特定測試
uv run pytest tests/unit/test_writer.py::test_writer_sends_batch

# 執行並提供涵蓋範圍
uv run pytest --cov=your_package --cov-report=html

# 僅執行單位測試
uv run pytest tests/unit/

# 詳細輸出執行
uv run pytest -v

# 執行並顯示 print 陳述式
uv run pytest -s
```
