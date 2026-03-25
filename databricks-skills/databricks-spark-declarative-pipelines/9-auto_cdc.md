# AUTO CDC 的 Change Data Capture 模式

**關鍵字**：Slow Changing Dimension、SCD、SCD Type 1、SCD Type 2、AUTO CDC、change data capture、dp.create_auto_cdc_flow、deduplication

---

## 概觀

AUTO CDC 會自動處理 Change Data Capture（CDC），透過 Slow Changing Dimension（SCD）追蹤資料中的變更。它提供自動 deduplication、變更追蹤，並能正確處理延遲到達的資料。

**適合套用 AUTO CDC 的位置：**
- **Silver layer**：當業務使用者需要去重複或歷史資料來進行分析/ML
- **Gold layer**：當要用 dim/fact tables 實作 dimensional modeling（star schema）
- **如何選擇**：取決於下游的使用模式與查詢需求

---

## SCD Type 1 與 Type 2

### SCD Type 1（就地更新）
- **以新值覆寫**舊值
- **不保留歷史**——只維護目前狀態
- **適用於**：不需要歷史的維度屬性
  - 修正資料錯誤（例如拼字錯誤）
  - 更新不需要保留歷史的屬性
  - 每個 key 只維護一筆目前紀錄
- **語法**：`stored_as_scd_type="1"`（string）

### SCD Type 2（歷史追蹤）
- **每次變更都建立新列**
- **透過 `__START_AT` 與 `__END_AT` 時間戳記完整保留歷史**
- **適用於**：需要追蹤長期變更
  - 客戶地址變更
  - 產品價格歷史
  - 員工職務變更
  - 任何需要時間維度分析的維度
- **語法**：`stored_as_scd_type=2`（integer）

---

## 模式：資料清理 + AUTO CDC

### 步驟 1：清理並驗證資料

建立一個已清理的串流資料表，包含正確型別與資料品質檢查：

```python
# 已清理資料的準備作業（可以放在 silver 或中介 layer）
from pyspark import pipelines as dp
from pyspark.sql import functions as F

schema = spark.conf.get("schema")

@dp.table(
    name=f"{schema}.users_clean",
    comment="經過正確型別轉換與資料品質檢查後的使用者資料",
    cluster_by=["user_id"]
)
def users_clean():
    """
    準備乾淨資料，包含：
    - 正確的 timestamp 型別
    - 資料品質驗證
    - 移除 email 無效或 user_id 為 null 的紀錄
    """
    return (
        spark.readStream.table("bronze_users")
        .filter(F.col("user_id").isNotNull())
        .filter(F.col("email").isNotNull())
        .filter(F.col("email").rlike(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"))
        .withColumn("created_timestamp", F.to_timestamp("created_timestamp"))
        .withColumn("updated_timestamp", F.to_timestamp("updated_timestamp"))
        .drop("_rescued_data")
        .select(
            "user_id",
            "email",
            "name",
            "subscription_tier",
            "country",
            "created_timestamp",
            "updated_timestamp",
            "_ingested_at",
            "_source_file"
        )
    )
```

### 步驟 2：套用 AUTO CDC（SCD Type 2）

建立保留完整變更歷史的維度資料表：

```python
# 搭配 SCD Type 2 的 AUTO CDC（歷史追蹤）
from pyspark import pipelines as dp

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

# 為 AUTO CDC 建立目標資料表
dp.create_streaming_table(f"{target_schema}.dim_users")

# 套用 AUTO CDC（SCD Type 2）
dp.create_auto_cdc_flow(
    target=f"{target_schema}.dim_users",
    source=f"{source_schema}.users_clean",
    keys=["user_id"],
    sequence_by="updated_timestamp",
    stored_as_scd_type=2  # Type 2 使用 integer
)
```

**產生的資料表會包含：**
- 來源中的所有原始欄位
- `__START_AT` - 這個版本開始生效的時間
- `__END_AT` - 這個版本失效的時間（目前版本為 NULL）

### 步驟 3：套用 AUTO CDC（SCD Type 1）

建立就地更新且去重複的資料表（不保留歷史）：

```python
# 搭配 SCD Type 1 的 AUTO CDC（就地更新）
from pyspark import pipelines as dp

target_schema = spark.conf.get("target_schema")
source_schema = spark.conf.get("source_schema")

# 為 AUTO CDC 建立目標資料表
dp.create_streaming_table(f"{target_schema}.orders_current")

# 套用 AUTO CDC（SCD Type 1）
dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source=f"{source_schema}.orders_clean",
    keys=["order_id"],
    sequence_by="updated_timestamp",
    stored_as_scd_type="1"  # Type 1 使用 string
)
```

---

## 主要優點

- **依據 keys 自動 deduplication**——不需要手寫 MERGE 邏輯
- **自動變更追蹤**，附帶時間性 metadata（`__START_AT`、`__END_AT`）
- **正確處理延遲到達資料**，透過 `sequence_by` 時間戳記排序
- **簡化 pipeline 程式碼**——不需要複雜的 merge/upsert 邏輯
- **內建冪等性**——可安全重新處理資料

---

## 常見模式

### 模式 1：Gold 維度模型

在 Gold layer 的 star schema 維度中使用 AUTO CDC：

```python
# Silver：已清理的串流資料表
@dp.table(name="silver.customers_clean")
def customers_clean():
    return spark.readStream.table("bronze.customers").filter(...)

# Gold：SCD Type 2 維度
dp.create_streaming_table("gold.dim_customers")
dp.create_auto_cdc_flow(
    target="gold.dim_customers",
    source="silver.customers_clean",
    keys=["customer_id"],
    sequence_by="updated_at",
    stored_as_scd_type=2
)

# Gold：Fact table（不使用 AUTO CDC）
@dp.table(name="gold.fact_orders")
def fact_orders():
    return spark.read.table("silver.orders_clean")
```

### 模式 2：用於 Join 的 Silver 去重複

當需要 join 多個資料表時，可在 Silver 使用 AUTO CDC：

```python
# Silver：使用 AUTO CDC 去重複
dp.create_streaming_table("silver.products_dedupe")
dp.create_auto_cdc_flow(
    target="silver.products_dedupe",
    source="bronze.products",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type="1"  # Type 1：僅去重複，不保留歷史
)

# Silver：與去重複後的資料 join
@dp.table(name="silver.orders_enriched")
def orders_enriched():
    orders = spark.readStream.table("bronze.orders")
    products = spark.read.table("silver.products_dedupe")
    return orders.join(products, "product_id")
```

### 模式 3：混合使用不同 SCD Type

依需求讓不同資料表使用不同的 SCD Type：

```python
# SCD Type 2：需要歷史
dp.create_auto_cdc_flow(
    target="gold.dim_customers",
    source="silver.customers",
    keys=["customer_id"],
    sequence_by="updated_at",
    stored_as_scd_type=2  # 追蹤地址隨時間的變化
)

# SCD Type 1：只需要修正後的目前值
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type="1"  # 只保留目前產品資訊
)
```

---

## 選擇性歷史追蹤

只追蹤特定欄位的歷史（SCD Type 2）：

```python
dp.create_auto_cdc_flow(
    target="gold.dim_products",
    source="silver.products_clean",
    keys=["product_id"],
    sequence_by="modified_at",
    stored_as_scd_type=2,
    track_history_column_list=["price", "cost"]  # 只追蹤這些欄位
)
```

當 `price` 或 `cost` 變更時，會建立新版本。其他欄位變更只會更新目前紀錄，不會建立新版本。

---

## 搭配 AUTO CDC 使用 Temporary Views

**`@dp.temporary_view()`** 會建立只在 pipeline 執行期間存在的 pipeline 內 temporary views。這對於在 AUTO CDC 前進行中介轉換很有幫助。

**主要限制：**
- 不能指定 `catalog` 或 `schema`（temporary views 只限 pipeline 範圍）
- 不能使用 `cluster_by`（不會被持久化）
- 只在 pipeline 執行期間存在

**使用情境：**
- 在 AUTO CDC 前進行複雜轉換
- 多次參照的中介邏輯
- 避免重複進行相同轉換

**範例：在 AUTO CDC 前先做準備**

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# 步驟 1：以 temporary view 處理複雜商業邏輯
@dp.temporary_view()
def orders_with_calculated_fields():
    """
    用於複雜計算的 temporary view。
    不需要 catalog/schema——只存在於 pipeline 內。
    """
    return (
        spark.readStream.table("bronze.orders")
        .withColumn("order_total", F.col("quantity") * F.col("unit_price"))
        .withColumn("discount_amount", F.col("order_total") * F.col("discount_rate"))
        .withColumn("final_amount", F.col("order_total") - F.col("discount_amount"))
        .withColumn("order_category",
            F.when(F.col("final_amount") > 1000, "large")
             .when(F.col("final_amount") > 100, "medium")
             .otherwise("small")
        )
        .filter(F.col("order_id").isNotNull())
        .filter(F.col("final_amount") > 0)
        .filter(F.col("order_date").isNotNull())
    )

# 步驟 2：以 temporary view 作為來源套用 AUTO CDC
target_schema = spark.conf.get("target_schema")

dp.create_streaming_table(f"{target_schema}.orders_current")
dp.create_auto_cdc_flow(
    target=f"{target_schema}.orders_current",
    source="orders_with_calculated_fields",  # 以名稱參照 temporary view
    keys=["order_id"],
    sequence_by="order_date",
    stored_as_scd_type="1"
)
```

**優點：**
- 避免建立不必要的持久化資料表
- 降低儲存成本（不會寫入磁碟）
- 簡化多步驟的複雜轉換
- 可在同一個 pipeline 的多個資料表之間重複使用程式碼

---

## 相關文件

- **[3-scd-query-patterns.md](3-scd-query-patterns.md)** - 查詢 SCD Type 2 歷史資料表、時間點分析、temporal joins
- **[1-ingestion-patterns.md](1-ingestion-patterns.md)** - CDC 資料來源（Kafka、Event Hubs、Kinesis）
- **[2-streaming-patterns.md](2-streaming-patterns.md)** - 不使用 AUTO CDC 的 deduplication 模式

---

## 最佳實務

1. **選擇正確的 SCD Type**：
   - 當你需要查詢歷史狀態時使用 Type 2
   - 當你只需要目前狀態或 deduplication 時使用 Type 1

2. **使用有意義的 sequence_by 欄位**：
   - 應該能反映變更真正發生的時間順序
   - 通常使用 `updated_timestamp`、`modified_at` 或 `event_timestamp`

3. **在 AUTO CDC 前先清理資料**：
   - 先進行型別轉換、驗證與過濾
   - AUTO CDC 在乾淨且型別明確的資料上效果最佳

4. **考量查詢模式**：
   - 如果分析師需要查歷史 → 使用 Type 2
   - 如果分析師只需要目前狀態 → 使用 Type 1
   - 如果經常要 join → 可考慮在 Silver 做 deduplication

5. **大型資料表使用選擇性追蹤**：
   - 只追蹤真正重要的欄位歷史
   - 可降低儲存量並提升查詢效能

---

## 常見問題

| 問題 | 解決方式 |
|-------|----------|
| **仍然出現重複資料** | 檢查 `keys` 是否包含所有 business key 欄位；確認 `sequence_by` 的排序是否正確 |
| **缺少 `__START_AT`/`__END_AT` 欄位** | 這些欄位只會出現在 SCD Type 2（integer），不會出現在 Type 1（string） |
| **延遲資料未被正確處理** | 確認已設定 `sequence_by` 欄位，且它能反映真實事件時間 |
| **Type 語法錯誤** | Type 2 使用 integer `2`，Type 1 使用 string `"1"` |
| **效能問題** | 使用 `track_history_column_list` 限制哪些欄位會觸發新版本 |