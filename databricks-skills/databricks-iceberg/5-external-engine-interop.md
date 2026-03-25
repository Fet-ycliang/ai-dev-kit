# 外部引擎互通性

本檔案說明如何透過 Iceberg REST Catalog（IRC）將外部引擎連線至 Databricks。每個引擎章節都包含讀取 Databricks 管理之 Iceberg 資料表所需的最小設定（若支援，也涵蓋寫入）。

**所有引擎的前置條件**：
- 已啟用 external data access 的 Databricks 工作區
- 已在目標 schema 上授與 `EXTERNAL USE SCHEMA`
- 用於驗證且具備必要權限的 PAT 或 OAuth（service principal）憑證。
- **網路存取**：client 必須能透過 HTTPS（port 443）連到 Databricks 工作區。若工作區已啟用 **IP access lists**，請將 client 的 egress CIDR 加入 allowlist —— 這是很常見的設定問題，即使憑證與授權正確也會因此無法連線。

IRC 端點細節請參閱 [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md)。

---

## PyIceberg

PyIceberg 是一個 Python library，可在不依賴 Spark 的情況下讀寫 Iceberg 資料表。

### 安裝

請明確升級這兩個套件 —— 若 `pyarrow`（v15）太舊，會造成寫入錯誤。另外也要安裝 `adlfs` 以支援 Azure storage access：

```bash
pip install --upgrade "pyiceberg>=0.9,<0.10" "pyarrow>=17,<20"
pip install adlfs
```

對於非 Databricks 環境：

```bash
pip install "pyiceberg[pyarrow]>=0.9"
```

### 連線到 Catalog

`warehouse` 參數會固定 catalog，因此後續所有資料表識別子都使用 `<schema>.<table>`（而不是 `<catalog>.<schema>.<table>`）：

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "uc",
    uri="https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest",
    warehouse="<uc-catalog-name>",  # Unity Catalog catalog 名稱
    token="<pat-token>",
)
```

### 讀取資料表

```python
# 載入資料表 —— 因為 'warehouse' 已固定 UC catalog，所以識別子為 <schema>.<table>
tbl = catalog.load_table("<schema>.<table>")

# 檢視 schema 與目前 snapshot
print(tbl)                    # schema、partitioning、snapshot 摘要
print(tbl.current_snapshot()) # snapshot metadata

# 讀取範例列
df = tbl.scan(limit=10).to_pandas()
print(df.head())

# Pushdown filter（支援 SQL 風格的 filter 字串）
df = tbl.scan(
    row_filter="event_date >= '2025-01-01'",
    limit=1000,
).to_pandas()

# 以 Arrow 讀取
arrow_table = tbl.scan().to_arrow()
```

### 附加資料

```python
import pyarrow as pa
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "uc",
    uri="https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest",
    warehouse="<uc-catalog-name>",
    token="<pat-token>",
)

tbl = catalog.load_table("<schema>.<table>")

# Schema 必須與 Iceberg 資料表 schema 完全一致 —— 請使用明確的 Arrow types
# PyArrow 預設為 int64；若 Iceberg 資料表使用 int（32-bit），請明確轉型
arrow_schema = pa.schema([
    pa.field("id",   pa.int32()),
    pa.field("name", pa.string()),
    pa.field("qty",  pa.int32()),
])

rows = [
    {"id": 1, "name": "foo", "qty": 10},
    {"id": 2, "name": "bar", "qty": 20},
]
arrow_tbl = pa.Table.from_pylist(rows, schema=arrow_schema)

tbl.append(arrow_tbl)

# 驗證
print("Current snapshot:", tbl.current_snapshot())
```

---

## OSS Apache Spark

> **重要**：僅能在 **Databricks Runtime 外部** 這樣設定。在 DBR 內請使用內建的 Iceberg 支援 —— **不要**安裝 Iceberg library。

### 依賴

需要兩個 JAR：Spark runtime，以及用於 object storage access 的雲端專屬 bundle。請選擇與 Databricks metastore 所在雲端相對應的 bundle：

| 雲端 | Bundle |
|-------|--------|
| AWS | `org.apache.iceberg:iceberg-aws-bundle:<version>` |
| Azure | `org.apache.iceberg:iceberg-azure-bundle:<version>` |
| GCP | `org.apache.iceberg:iceberg-gcp-bundle:<version>` |

### Spark Session 設定

Databricks 文件建議外部 Spark 連線使用 OAuth2（service principal）。請設定 `rest.auth.type=oauth2`，並提供 OAuth2 server URI、credential 與 scope：

```python
from pyspark.sql import SparkSession

WORKSPACE_URL       = "https://<workspace-url>"
UC_CATALOG_NAME     = "<uc-catalog-name>"
OAUTH_CLIENT_ID     = "<oauth-client-id>"
OAUTH_CLIENT_SECRET = "<oauth-client-secret>"
CATALOG_ALIAS       = "uc"    # 在 Spark SQL 中用來參照此 catalog 的任意名稱
ICEBERG_VER         = "1.7.1"

RUNTIME      = f"org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:{ICEBERG_VER}"
CLOUD_BUNDLE = f"org.apache.iceberg:iceberg-aws-bundle:{ICEBERG_VER}"   # 或 azure/gcp-bundle

spark = (
    SparkSession.builder
    .appName("uc-iceberg")
    .config("spark.jars.packages", f"{RUNTIME},{CLOUD_BUNDLE}")
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}",
            "org.apache.iceberg.spark.SparkCatalog")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.type", "rest")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.rest.auth.type", "oauth2")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.uri",
            f"{WORKSPACE_URL}/api/2.1/unity-catalog/iceberg-rest")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.oauth2-server-uri",
            f"{WORKSPACE_URL}/oidc/v1/token")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.credential",
            f"{OAUTH_CLIENT_ID}:{OAUTH_CLIENT_SECRET}")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.scope", "all-apis")
    .config(f"spark.sql.catalog.{CATALOG_ALIAS}.warehouse", UC_CATALOG_NAME)
    .getOrCreate()
)

# 列出 schemas
spark.sql(f"SHOW NAMESPACES IN {CATALOG_ALIAS}").show(truncate=False)

# 查詢
spark.sql(f"SELECT * FROM {CATALOG_ALIAS}.<schema>.<table>").show()

# 寫入（僅限受管 Iceberg 資料表）
df.writeTo(f"{CATALOG_ALIAS}.<schema>.<table>").append()
```

### Spark SQL

```sql
-- 列出 schemas
SHOW NAMESPACES IN uc;

-- 查詢
SELECT * FROM uc.<schema>.<table>;

-- INSERT
INSERT INTO uc.<schema>.<table> VALUES (1, 'foo', 10);
```

---

## 疑難排解

| 問題 | 解法 |
|-------|----------|
| **使用有效憑證仍連線逾時或出現 `403 Forbidden`** | 工作區 IP access list 擋住了 client —— 請將 client 的 egress CIDR 加入 allowlist（管理主控台：**Settings → Security → IP access list**） |
| **`403 Forbidden`** | 檢查 `EXTERNAL USE SCHEMA` 授權與 token 是否有效 |
| **`Table not found`** | 確認 `warehouse` 設定與 UC catalog 名稱一致；並檢查 schema 與 table 名稱 |
| **DBR 中的 class conflict** | 你在 Databricks Runtime 中安裝了 Iceberg library —— 請移除；DBR 已內建支援 |
| **憑證授予失敗** | 請確認工作區已啟用 external data access |
| **讀取速度慢** | 檢查資料表是否需要 compaction（`OPTIMIZE`）；大量小檔案會降低效能 |
| **v3 資料表不相容** | 升級至 Iceberg library 1.9.0+ 以支援 v3；較舊版本無法讀取 v3 資料表 |
| **PyArrow schema 不符** | 當 Iceberg 資料表 schema 使用 32-bit integers 時，請轉型為明確型別（例如 `pa.int32()`） |
| **serverless 上的 PyIceberg 寫入錯誤** | 升級 pyarrow（`>=17`）並安裝 `adlfs` —— 內建的 pyarrow v15 不相容 |

---

## 相關內容

- [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) —— IRC 端點細節、auth、憑證授予
- [4-snowflake-interop.md](4-snowflake-interop.md) —— Snowflake 專屬整合
