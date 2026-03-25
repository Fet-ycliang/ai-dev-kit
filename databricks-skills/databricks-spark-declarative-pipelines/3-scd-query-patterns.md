# SCD 查詢模式

如何有效查詢 SCD Type 2 歷程資料表，包含當前狀態查詢、時間點分析及異動追蹤。

---

## 了解 SCD Type 2 結構

建立 SCD Type 2 flow 後，系統會自動新增時序欄位：

```sql
CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM stream(customers_cdc_clean)
KEYS (customer_id)
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 2
TRACK HISTORY ON *;
```

**產生的資料表結構**（Lakeflow 使用雙底線時序欄位）：
```
customers_history
├── customer_id        -- 業務鍵
├── customer_name
├── email
├── phone
├── __START_AT         -- 此版本生效的時間（自動產生）
├── __END_AT           -- 此版本失效的時間（NULL 表示當前版本）
└── ...其他欄位
```

**重要：** 查詢時使用 `__START_AT` 與 `__END_AT`（雙底線），而非 `START_AT`/`END_AT`。

---

## 當前狀態查詢

### 所有當前記錄

```sql
-- __END_AT IS NULL 表示有效記錄（Lakeflow 使用雙底線）
CREATE OR REPLACE MATERIALIZED VIEW dim_customers_current AS
SELECT
  customer_id, customer_name, email, phone, address,
  __START_AT AS valid_from
FROM customers_history
WHERE __END_AT IS NULL;
```

### 特定客戶

```sql
SELECT *
FROM customers_history
WHERE customer_id = '12345'
  AND __END_AT IS NULL;
```

---

## 時間點查詢

### 指定日期的資料狀態

取得特定日期時的記錄狀態：

```sql
-- 2024 年 1 月 1 日時的產品資料（使用 __START_AT / __END_AT）
CREATE OR REPLACE MATERIALIZED VIEW products_as_of_2024_01_01 AS
SELECT
  product_id, product_name, price, category,
  __START_AT, __END_AT
FROM products_history
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL);
```

---

## 異動分析

### 追蹤實體的所有異動

```sql
-- 客戶的完整歷程（使用 __START_AT / __END_AT）
SELECT
  customer_id, customer_name, email, phone,
  __START_AT, __END_AT,
  COALESCE(
    DATEDIFF(DAY, __START_AT, __END_AT),
    DATEDIFF(DAY, __START_AT, CURRENT_TIMESTAMP())
  ) AS days_active
FROM customers_history
WHERE customer_id = '12345'
ORDER BY __START_AT DESC;
```

### 指定時間區間內的異動

```sql
-- 2024 年 Q1 異動的客戶（使用 __START_AT）
SELECT
  customer_id, customer_name,
  __START_AT AS change_timestamp,
  'UPDATE' AS change_type
FROM customers_history
WHERE __START_AT BETWEEN '2024-01-01' AND '2024-03-31'
  AND __START_AT != (
    SELECT MIN(__START_AT)
    FROM customers_history ch2
    WHERE ch2.customer_id = customers_history.customer_id
  )
ORDER BY __START_AT;
```

---

## 事實資料表與歷史維度的 Join

### 以交易時間的維度資料豐富事實資料

```sql
-- 以銷售當時的產品售價 join 銷售記錄
CREATE OR REPLACE MATERIALIZED VIEW sales_with_historical_prices AS
SELECT
  s.sale_id, s.product_id, s.sale_date, s.quantity,
  p.product_name, p.price AS unit_price_at_sale_time,
  s.quantity * p.price AS calculated_amount,
  p.category
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
  AND s.sale_date >= p.__START_AT
  AND (s.sale_date < p.__END_AT OR p.__END_AT IS NULL);
```

### 與當前維度 Join

```sql
-- 以當前產品資訊 join 銷售記錄
CREATE OR REPLACE MATERIALIZED VIEW sales_with_current_prices AS
SELECT
  s.sale_id, s.product_id, s.sale_date, s.quantity,
  s.amount AS amount_at_sale,
  p.product_name AS current_product_name,
  p.price AS current_price,
  p.category AS current_category
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
  AND p.__END_AT IS NULL;  -- 僅取當前版本
```

---

## 選擇性歷程追蹤

使用 `TRACK HISTORY ON specific_columns` 時：

```sql
-- 只有 price 異動才觸發新版本
CREATE FLOW products_scd2_flow AS
AUTO CDC INTO products_history
FROM stream(products_cdc_clean)
KEYS (product_id)
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 2
TRACK HISTORY ON price, cost;  -- 僅追蹤這些欄位
```

---

## 最佳化模式

### 預先過濾的物化視圖

```sql
-- 當前狀態視圖（最常見的模式）
CREATE OR REPLACE MATERIALIZED VIEW dim_products_current AS
SELECT * FROM products_history WHERE __END_AT IS NULL;

-- 僅最近的異動
CREATE OR REPLACE MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM products_history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;

-- 異動頻率統計
CREATE OR REPLACE MATERIALIZED VIEW product_change_stats AS
SELECT
  product_id,
  COUNT(*) AS version_count,
  MIN(__START_AT) AS first_seen,
  MAX(__START_AT) AS last_updated
FROM products_history
GROUP BY product_id;
```

---

## 最佳實踐

### 1. 當前記錄務必以 __END_AT 過濾（Lakeflow 使用雙底線）

```sql
-- ✅ 效率高
WHERE __END_AT IS NULL

-- ❌ 效率較低
WHERE __START_AT = (SELECT MAX(__START_AT) FROM table WHERE ...)
```

### 2. 使用包含下界、排除上界的模式

```sql
-- ✅ 標準模式
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL)
```

### 3. 為常用模式建立物化視圖

```sql
-- 當前狀態
CREATE OR REPLACE MATERIALIZED VIEW dim_current AS
SELECT * FROM history WHERE __END_AT IS NULL;

-- 最近異動
CREATE OR REPLACE MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;
```

---

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| 相同鍵出現多筆資料 | 查詢當前狀態時缺少 `__END_AT IS NULL` 過濾條件 |
| 時間點查詢無結果 | 使用 `__START_AT <= date AND (__END_AT > date OR __END_AT IS NULL)` |
| 時序 join 速度慢 | 為特定時間區間建立物化視圖 |
| 意外重複資料 | 同一天有多次異動——使用高精度的 SEQUENCE BY |
