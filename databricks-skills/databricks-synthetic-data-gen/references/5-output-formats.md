# 輸出格式指南

生成的合成資料的儲存位置和方式。

## 在指令碼中建立基礎結構

始終在 Python 指令碼內使用 `spark.sql()` 建立結構描述和磁區。不要進行單獨的 MCP SQL 呼叫 - 速度會慢得多。

```python
CATALOG = "<user-provided-catalog>"  # 必須詢問使用者 - 永不預設
SCHEMA = "<user-provided-schema>"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 注意：假設目錄已存在 - 不要建立它
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA} COMMENT '合成資料用於演示案例'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

**重要：** 不要建立目錄 - 假設它們已經存在。僅建立結構描述和磁區。始終為結構描述新增 `COMMENT` 描述資料集目的。

---

## 格式比較

| 格式 | 使用案例 | 副檔名 | 最佳用於 |
|------|---------|--------|---------|
| **Parquet** | SDP 管線輸入 | `.parquet` 或無 | 最佳壓縮、查詢效能 |
| **JSON** | 日誌類型擷取 | `.json` | 模擬外部資料摘要 |
| **CSV** | 舊版系統 | `.csv` | 人類可讀、試算表匯入 |
| **Delta 表格** | 預設 - 直接分析 | N/A | 視為 ETL 的 bronze 表格或略過 ETL 並立即查詢 |

---

## Parquet 到磁區（預設）

SDP 管線輸入的標準格式。最佳壓縮和查詢效能。

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 儲存為 parquet 檔案（目錄格式）
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
orders_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
tickets_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")
```

**注意：**
- 檔案可能沒有副檔名或可能以 `.parquet` 結尾
- Spark 以含 part 檔案的目錄形式寫入
- 對一次性產生使用 `mode("overwrite")`
- 對增量/排程工作使用 `mode("append")`

---

## JSON 到磁區

常見模式，用於模擬來自外部資料摘要（日誌、webhook）的 SDP 擷取。

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 儲存為 JSON 檔案
customers_df.write.mode("overwrite").json(f"{VOLUME_PATH}/customers_json")
orders_df.write.mode("overwrite").json(f"{VOLUME_PATH}/orders_json")
```

**何時使用：**
- 模擬日誌擷取
- 外部 API 資料摘要
- 使用者明確要求 JSON 格式

---

## CSV 到磁區

常見模式，用於模擬來自舊版系統或試算表匯出的資料。

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 儲存為 CSV 檔案（含標題）
customers_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/customers_csv")
orders_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/orders_csv")
```

**選項：**
```python
# CSV 的完整選項
df.write \
    .mode("overwrite") \
    .option("header", "true") \
    .option("delimiter", ",") \
    .option("quote", '"') \
    .option("escape", "\\") \
    .csv(f"{VOLUME_PATH}/data_csv")
```

**何時使用：**
- 舊版系統整合
- 人類可讀資料
- 試算表匯入測試

---

## Delta 表格（統一目錄）

在資料準備好供分析使用（略過 SDP 管線）時直接寫入受管理 Delta 表格。

```python
# 確保結構描述存在
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# 儲存為受管理 Delta 表格
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
orders_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.orders")

# 具有其他選項
customers_df.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
```

**何時使用：**
- 使用者想要資料立即可查詢
- 略過 SDP bronze/silver/gold 管線
- 直接 SQL 分析

### 新增表格和列註解

始終為 Delta 表格新增註解，以便在統一目錄中探索。偏好 DDL 優先方法 — 先定義表格和註解，然後插入資料。

**DDL 優先（偏好）：**
```python
# 建立具有內聯列註解和表格註解的表格
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.customers (
        customer_id STRING COMMENT '唯一顧客識別碼 (CUST-XXXXX)',
        name STRING COMMENT '完整顧客名稱',
        email STRING COMMENT '顧客電子郵件地址',
        tier STRING COMMENT '顧客層級：Free、Pro、Enterprise',
        region STRING COMMENT '地理地區',
        arr DOUBLE COMMENT '美元年度經常性收入'
    )
    COMMENT '電子商務演示的合成顧客資料'
""")

# 然後將資料寫入預定義表格
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
```

**具有註解的 PySpark 綱要：**
```python
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

schema = StructType([
    StructField("customer_id", StringType(), True, metadata={"comment": "唯一顧客識別碼 (CUST-XXXXX)"}),
    StructField("name", StringType(), True, metadata={"comment": "完整顧客名稱"}),
    StructField("email", StringType(), True, metadata={"comment": "顧客電子郵件地址"}),
    StructField("tier", StringType(), True, metadata={"comment": "顧客層級：Free、Pro、Enterprise"}),
    StructField("region", StringType(), True, metadata={"comment": "地理地區"}),
    StructField("arr", DoubleType(), True, metadata={"comment": "美元年度經常性收入"}),
])

# 建立 DataFrame 時套用綱要，在儲存為 Delta 時保持註解
customers_df = spark.createDataFrame(data, schema)
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
```

**寫入後（備用）：**
```python
# 先寫入，然後新增註解
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 新增表格註解
spark.sql(f"COMMENT ON TABLE {CATALOG}.{SCHEMA}.customers IS '電子商務演示的合成顧客資料'")

# 新增列註解
spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.customers ALTER COLUMN customer_id COMMENT '唯一顧客識別碼 (CUST-XXXXX)'")
spark.sql(f"ALTER TABLE {CATALOG}.{SCHEMA}.customers ALTER COLUMN tier COMMENT '顧客層級：Free、Pro、Enterprise'")
```

**注意：** 列/表格註解僅適用於統一目錄中的 Delta 表格。寫入磁區的 Parquet/JSON/CSV 檔案不支援元資料註解。

---

## 寫入模式

| 模式 | 行為 | 使用案例 |
|------|------|---------|
| `overwrite` | 取代現有資料 | 一次性產生、重新產生 |
| `append` | 新增到現有資料 | 增量/排程工作 |
| `ignore` | 略過如果存在 | 等冪產生 |
| `error` | 如果存在則失敗 | 安全檢查 |

### 增量產生模式

```python
WRITE_MODE = "append"  # 用於排程工作

# 僅產生自上次執行以來的新記錄
from datetime import datetime, timedelta

LAST_RUN = datetime.now() - timedelta(days=1)
END_DATE = datetime.now()

# 僅產生新資料
new_orders_df = generate_orders(start_date=LAST_RUN, end_date=END_DATE)
new_orders_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/orders")
```

---

## 寫入後驗證

成功執行後，驗證產生的資料：

```python
# 讀取回並驗證
customers_check = spark.read.parquet(f"{VOLUME_PATH}/customers")
orders_check = spark.read.parquet(f"{VOLUME_PATH}/orders")

print(f"顧客：{customers_check.count():,} 列")
print(f"訂單：{orders_check.count():,} 列")

# 驗證分佈
customers_check.groupBy("tier").count().show()
orders_check.describe("amount").show()
```

或使用 `get_volume_folder_details` MCP 工具：
- `volume_path`："my_catalog/my_schema/raw_data/customers"
- `format`："parquet"
- `table_stat_level`："SIMPLE"
