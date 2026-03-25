# DLT 到 SDP 的遷移指南

將 Delta Live Tables (DLT) Python pipelines 遷移至 Spark Declarative Pipelines (SDP) SQL 的指南。

⚠️ **針對新的 Python SDP pipelines**：請使用現代的 `pyspark.pipelines` API。請參閱 [5-python-api.md](5-python-api.md)。

---

## 遷移決策矩陣

| 功能/模式 | DLT Python | SDP SQL | 建議 |
|-----------------|------------|---------|----------------|
| 簡單轉換 | ✓ | ✓ | **遷移至 SQL** |
| 聚合 | ✓ | ✓ | **遷移至 SQL** |
| 篩選、WHERE 子句 | ✓ | ✓ | **遷移至 SQL** |
| CASE 運算式 | ✓ | ✓ | **遷移至 SQL** |
| SCD Type 1/2 | ✓ | ✓ | **遷移至 SQL**（AUTO CDC） |
| 簡單 joins | ✓ | ✓ | **遷移至 SQL** |
| Auto Loader | ✓ | ✓ | **遷移至 SQL**（read_files） |
| Streaming 來源（Kafka） | ✓ | ✓ | **遷移至 SQL**（read_stream） |
| 複雜 Python UDF | ✓ | ❌ | **保留在 Python** |
| 外部 API 呼叫 | ✓ | ❌ | **保留在 Python** |
| 自訂函式庫 | ✓ | ❌ | **保留在 Python** |
| 複雜 apply 函式 | ✓ | ❌ | **保留在 Python** 或簡化 |
| ML 模型推論 | ✓ | ❌ | **保留在 Python** |

**規則**：若有 80% 以上可用 SQL 表達，請遷移至 SDP SQL。若大量依賴 Python 邏輯，則維持 DLT Python 或採用混合式。

---

## 對照：關鍵模式

### 基本 Streaming Table

**DLT Python**:
```python
@dlt.table(name="bronze_sales", comment="原始銷售資料")
def bronze_sales():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/sales")
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE bronze_sales
COMMENT '原始銷售資料'
AS
SELECT *, current_timestamp() AS _ingested_at
FROM read_files('/mnt/raw/sales', format => 'json');
```

### 篩選與轉換

**DLT Python**:
```python
@dlt.table(name="silver_sales")
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_drop("valid_sale_id", "sale_id IS NOT NULL")
def silver_sales():
    return (
        dlt.read_stream("bronze_sales")
        .withColumn("sale_date", F.to_date("sale_date"))
        .withColumn("amount", F.col("amount").cast("decimal(10,2)"))
        .select("sale_id", "customer_id", "amount", "sale_date")
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE silver_sales AS
SELECT
  sale_id, customer_id,
  CAST(amount AS DECIMAL(10,2)) AS amount,
  CAST(sale_date AS DATE) AS sale_date
FROM STREAM bronze_sales
WHERE amount > 0 AND sale_id IS NOT NULL;
```

### SCD Type 2

**DLT Python**:
```python
dlt.create_streaming_table("customers_history")

dlt.apply_changes(
    target="customers_history",
    source="customers_cdc_clean",
    keys=["customer_id"],
    sequence_by="event_timestamp",
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**SDP SQL**（子句順序：`APPLY AS DELETE WHEN` 必須在 `SEQUENCE BY` 前；`EXCEPT` 只能排除 source 中實際存在的欄位；若 `TRACK HISTORY ON *` 造成 parse errors，請省略）:
```sql
CREATE OR REFRESH STREAMING TABLE customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM stream(customers_cdc_clean)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (operation, _ingested_at, _source_file)
STORED AS SCD TYPE 2;
```

### Joins

**DLT Python**:
```python
@dlt.table(name="silver_sales_enriched")
def silver_sales_enriched():
    sales = dlt.read_stream("silver_sales")
    products = dlt.read("dim_products")

    return (
        sales.join(products, "product_id", "left")
        .select(sales["*"], products["product_name"], products["category"])
    )
```

**SDP SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE silver_sales_enriched AS
SELECT
  s.*,
  p.product_name,
  p.category
FROM STREAM silver_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

---

## 處理 Expectations

**DLT Python**:
```python
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_fail("critical_id", "id IS NOT NULL")
```

**SDP SQL - 基本版**:
```sql
-- 使用 WHERE（等同於 expect_or_drop）
WHERE amount > 0 AND id IS NOT NULL
```

**SDP SQL - Quarantine 模式**（用於稽核）:
```sql
-- 標記無效紀錄
CREATE OR REPLACE STREAMING TABLE bronze_data_flagged AS
SELECT
  *,
  CASE
    WHEN amount <= 0 THEN TRUE
    WHEN id IS NULL THEN TRUE
    ELSE FALSE
  END AS is_invalid
FROM STREAM bronze_data;

-- 供下游使用的乾淨資料
CREATE OR REPLACE STREAMING TABLE silver_data_clean AS
SELECT * FROM STREAM bronze_data_flagged WHERE NOT is_invalid;

-- 供調查用的隔離資料
CREATE OR REPLACE STREAMING TABLE silver_data_quarantine AS
SELECT * FROM STREAM bronze_data_flagged WHERE is_invalid;
```

**遷移方式**：`@dlt.expect_or_drop` → WHERE 子句或 quarantine 模式。

---

## 處理 UDF

### 簡單 UDF（遷移至 SQL）

**DLT Python**:
```python
@F.udf(returnType=StringType())
def categorize_amount(amount):
    if amount > 1000:
        return "高"
    elif amount > 100:
        return "中"
    else:
        return "低"

@dlt.table(name="sales_categorized")
def sales_categorized():
    return (
        dlt.read("sales")
        .withColumn("category", categorize_amount(F.col("amount")))
    )
```

**SDP SQL**（CASE 運算式）:
```sql
CREATE OR REPLACE MATERIALIZED VIEW sales_categorized AS
SELECT
  *,
  CASE
    WHEN amount > 1000 THEN '高'
    WHEN amount > 100 THEN '中'
    ELSE '低'
  END AS category
FROM sales;
```

### 複雜 UDF（保留 Python）

**以下情況保留在 Python**：
- 複雜條件邏輯
- 外部 API 呼叫
- 自訂演算法
- ML 推論

**選項**：
1. 將轉換保留在 Python DLT 中
2. 建立混合式方案（SQL + Python 處理特定 UDF）
3. 若可行，重構為 SQL 內建函式

---

## 遷移流程

### 步驟 1：盤點

記錄以下內容：
- 資料表/views 數量
- Python UDF（簡單 vs 複雜）
- 外部依賴
- Expectations 與品質規則

### 步驟 2：分類

**容易遷移**：篩選、聚合、簡單 CASE
**中等**：可改寫為 SQL 的 UDF
**困難**：複雜 Python、外部呼叫、ML

### 步驟 3：依層級遷移

1. **Bronze**（ingestion）：將 Auto Loader 轉成 read_files()
2. **Silver**（cleansing）：將 expectations 轉成 WHERE/quarantine
3. **Gold**（aggregations）：通常相對直接
4. **SCD/CDC**：使用 AUTO CDC

### 步驟 4：測試

- 平行執行兩套 pipeline
- 比較輸出是否正確
- 驗證效能
- 檢查品質指標

---

## 何時不要遷移

**若符合以下情況，請維持 DLT Python**：
1. 大量使用 Python UDF（>30% 邏輯）
2. 需要外部 API 呼叫
3. 自訂 ML 模型推論
4. SQL 無法處理的複雜有 state 作業
5. 現有 pipeline 運作良好，團隊偏好 Python
6. SQL 經驗有限

**可考慮混合式**：大多數用 SQL，複雜邏輯用 Python。

---

## 常見問題

| 問題 | 解法 |
|-------|----------|
| UDF 無法轉譯 | 保留在 Python，或改用 SQL 內建函式重構 |
| Expectations 行為不同 | 使用 quarantine 模式稽核被捨棄的紀錄 |
| 效能下降 | 使用 CLUSTER BY 啟用 Liquid Clustering，並檢查 joins |
| Schema evolution 行為不同 | 在 read_files() 中使用 `mode => 'PERMISSIVE'` |

---

## 摘要

**遷移路徑**：
1. 使用決策矩陣（80% 以上可用 SQL 表達 → 遷移）
2. 依層級遷移（bronze → silver → gold）
3. 以 WHERE/quarantine 處理 expectations
4. 將簡單 UDF 轉成 CASE 運算式
5. 將複雜 Python 邏輯保留在 Python

**關鍵**：DLT Python 與 SDP SQL 都完整受支援。遷移是為了簡化，而不是因為必須。
