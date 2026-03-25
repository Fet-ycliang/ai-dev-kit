# SDP 效能調校

涵蓋 **Liquid Clustering**（現代化作法）、materialized view 重新整理、狀態管理與運算資源設定的效能最佳化策略。

---

## Liquid Clustering（建議）

**Liquid Clustering** 是建議使用的資料配置最佳化方式，可取代手動 `PARTITION BY` 與 `Z-ORDER`。

### 什麼是 Liquid Clustering？

- **自適應**：可依資料分布變化自動調整
- **多維度**：可同時依多個欄位進行 clustering
- **自動檔案大小調整**：維持最佳檔案大小
- **自我最佳化**：減少手動執行 OPTIMIZE 指令的需求

### 基本語法

**SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CAST(current_date() AS DATE) AS event_date
FROM read_files('/mnt/raw/events/', format => 'json');
```

**Python**:
```python
from pyspark import pipelines as dp

@dp.table(cluster_by=["event_type", "event_date"])
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

### 自動選擇叢集鍵

```sql
-- 讓 Databricks 根據查詢模式自行選擇
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (AUTO)
AS SELECT ...;
```

**何時使用 AUTO**：學習階段、存取模式未知、原型開發
**何時手動定義**：查詢模式明確、生產工作負載

---

## 依層級選擇叢集鍵

### Bronze 層

依事件類型 + 日期進行 clustering：

```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (event_type, ingestion_date)
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CAST(current_date() AS DATE) AS ingestion_date
FROM read_files('/mnt/raw/events/', format => 'json');
```

**原因**：Bronze 層通常會依事件類型篩選以進行處理，並依日期進行增量載入。

### Silver 層

依主鍵 + 業務維度進行 clustering：

```sql
CREATE OR REPLACE STREAMING TABLE silver_orders
CLUSTER BY (customer_id, order_date)
AS
SELECT
  order_id, customer_id, product_id, amount,
  CAST(order_timestamp AS DATE) AS order_date,
  order_timestamp
FROM STREAM bronze_orders;
```

**原因**：支援實體查找（依 ID）與時間區間查詢（依日期）。

### Gold 層

依聚合維度進行 clustering：

```sql
CREATE OR REPLACE MATERIALIZED VIEW gold_sales_summary
CLUSTER BY (product_category, year_month)
AS
SELECT
  product_category,
  DATE_FORMAT(order_date, 'yyyy-MM') AS year_month,
  SUM(amount) AS total_sales,
  COUNT(*) AS transaction_count,
  AVG(amount) AS avg_order_value
FROM silver_orders
GROUP BY product_category, DATE_FORMAT(order_date, 'yyyy-MM');
```

**原因**：符合儀表板常見篩選條件（類別、區域、時間區間）。

### 選擇指引

| 層級 | 適合的鍵 | 理由 |
|------|----------|------|
| **Bronze** | event_type, ingestion_date | 依類型篩選；依日期增量處理 |
| **Silver** | primary_key, business_date | 實體查找 + 時間區間 |
| **Gold** | aggregation_dimensions | 儀表板篩選 |

**最佳實務**：
- 第一個鍵：選擇性最高的篩選欄位（例如 customer_id）
- 第二個鍵：下一個常見篩選欄位（例如 date）
- 順序很重要：選擇性最高的欄位放前面
- 最多 4 個鍵：超過 4 個後效益會遞減
- **若不確定，請使用 AUTO**

---

## 從舊版 PARTITION BY 遷移

### 之前（舊版）

```sql
CREATE OR REPLACE STREAMING TABLE events
PARTITIONED BY (date DATE)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'user_id,event_type')
AS SELECT ...;
```

**問題**：鍵值固定、小檔案問題、資料分布偏斜，而且需要手動執行 OPTIMIZE。

### 之後（採用 Liquid Clustering 的現代作法）

```sql
CREATE OR REPLACE STREAMING TABLE events
CLUSTER BY (date, user_id, event_type)
AS SELECT ...;
```

**效益**：可自適應、避免 small files、自動最佳化，效能可提升 20-50%。

### 何時仍應使用 PARTITION BY

**僅在以下情況使用**：
1. **法規要求**（需要實體隔離）
2. **資料生命週期管理**：需要以 `DROP` partitions 實作保留政策
3. **相容性**：較舊的 Delta Lake 版本（< DBR 13.3）
4. **既有大型資料表**：遷移成本高於效益

**其他情況請優先使用 Liquid Clustering。**

---

## 資料表屬性

### Auto-Optimize

```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
)
AS SELECT * FROM read_files(...);
```

**效益**：減少小檔案、改善讀取效能、自動執行 compact。

### Change Data Feed

```sql
CREATE OR REPLACE STREAMING TABLE silver_customers
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT * FROM STREAM bronze_customers;
```

**適用時機**：下游系統需要高效率的變更追蹤。

### 保留期間

```sql
CREATE OR REPLACE STREAMING TABLE bronze_high_volume
TBLPROPERTIES (
  'delta.logRetentionDuration' = '7 days',
  'delta.deletedFileRetentionDuration' = '7 days'
)
AS SELECT * FROM read_files(...);
```

**適用於**：高流量資料表，以降低儲存成本。

---

## Materialized View 重新整理

### 重新整理頻率

```sql
-- 接近即時（高頻率）
CREATE OR REPLACE MATERIALIZED VIEW gold_live_metrics
REFRESH EVERY 5 MINUTES
AS
SELECT
  metric_name,
  AVG(metric_value) AS avg_value,
  MAX(last_updated) AS freshness
FROM silver_metrics
GROUP BY metric_name;

-- 每日報表（排程）
CREATE OR REPLACE MATERIALIZED VIEW gold_daily_summary
REFRESH EVERY 1 DAY
AS
SELECT report_date, SUM(amount) AS total_amount
FROM silver_sales
GROUP BY report_date;
```

### 增量重新整理（自動）

materialized views 在可行時會自動使用增量重新整理：

```sql
-- 若來源啟用 row tracking，會以增量方式重新整理
CREATE OR REPLACE MATERIALIZED VIEW gold_aggregates AS
SELECT
  product_id,
  SUM(quantity) AS total_quantity,
  SUM(amount) AS total_amount
FROM silver_sales
GROUP BY product_id;
```

**需求**：來源已啟用 Delta row tracking、沒有 row filters，且使用受支援的 aggregations。

### 預先聚合

```sql
-- 避免反覆查詢大型資料表
CREATE OR REPLACE MATERIALIZED VIEW orders_monthly AS
SELECT
  customer_id,
  YEAR(order_date) AS year,
  MONTH(order_date) AS month,
  SUM(amount) AS total
FROM large_orders_table
GROUP BY customer_id, YEAR(order_date), MONTH(order_date);

-- 查詢 MV（快速）
SELECT * FROM orders_monthly WHERE year = 2024;
```

---

## Streaming 的狀態管理

### 了解狀態成長

```sql
-- 高狀態：每個唯一組合都會建立狀態
SELECT
  user_id,       -- 100 萬名使用者
  product_id,    -- 1 萬個產品
  session_id,    -- 1 億個工作階段
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_id, session_id;  -- 龐大的狀態！
```

### 降低狀態大小

**策略 1：降低基數**

```sql
-- 在較高層級進行聚合
SELECT
  user_id,
  product_category,  -- 100 個類別（不是 1 萬個產品）
  DATE(event_time) AS event_date,
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_category, DATE(event_time);
```

**策略 2：使用時間視窗**

```sql
-- 以視窗限制狀態範圍
SELECT
  user_id,
  window(event_time, '1 hour') AS time_window,
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, window(event_time, '1 hour');
```

**策略 3：具體化中介結果**

```sql
-- Streaming 聚合（會維護狀態）
CREATE OR REPLACE STREAMING TABLE user_daily_stats AS
SELECT
  user_id,
  DATE(event_time) AS event_date,
  COUNT(*) AS event_count
FROM STREAM bronze_events
GROUP BY user_id, DATE(event_time);

-- Batch 聚合（沒有 streaming 狀態）
CREATE OR REPLACE MATERIALIZED VIEW user_monthly_stats AS
SELECT
  user_id,
  DATE_TRUNC('month', event_date) AS month,
  SUM(event_count) AS total_events
FROM user_daily_stats
GROUP BY user_id, DATE_TRUNC('month', event_date);
```

---

## Join 最佳化

### Stream-to-Static（高效率）

```sql
-- 小型靜態維度搭配大型 streaming 事實表
CREATE OR REPLACE STREAMING TABLE sales_enriched AS
SELECT
  s.sale_id, s.product_id, s.amount,
  p.product_name, p.category  -- 來自小型靜態資料表
FROM STREAM bronze_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

**最佳實務**：靜態維度請保持精簡（<10K 列），以利 broadcast。

### Stream-to-Stream（具狀態）

```sql
-- 以時間界限限制狀態保留
CREATE OR REPLACE STREAMING TABLE orders_with_payments AS
SELECT
  o.order_id, o.amount AS order_amount,
  p.payment_id, p.amount AS payment_amount
FROM STREAM bronze_orders o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
  AND p.payment_time BETWEEN o.order_time AND o.order_time + INTERVAL 1 HOUR;
```

**最佳化方式**：在 join 條件中加入時間界限。

---

## 運算資源設定

### Serverless 與 Classic

| 面向 | Serverless | Classic |
|------|------------|---------|
| 啟動 | 快（數秒） | 較慢（數分鐘） |
| 擴縮 | 自動、即時 | 手動／自動擴縮 |
| 成本 | 按使用量計費 | 依叢集執行時間計費 |
| 最適合 | 變動型工作負載、dev/test | 穩定型工作負載 |

### Serverless（建議）

在管線層級啟用：

```yaml
execution_mode: continuous  # 或 triggered
serverless: true
```

**優點**：不需管理叢集、可即時擴縮，對突發型工作負載成本更低。

---

## 查詢最佳化

### 及早過濾

```sql
-- ✅ 在來源端過濾
CREATE OR REPLACE STREAMING TABLE silver_recent AS
SELECT *
FROM STREAM bronze_events
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;

-- ❌ 延後過濾
CREATE OR REPLACE STREAMING TABLE silver_all AS
SELECT * FROM STREAM bronze_events;

CREATE OR REPLACE MATERIALIZED VIEW gold_recent AS
SELECT * FROM silver_all
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;
```

### 選取特定欄位

```sql
-- ❌ 讀取所有欄位
SELECT * FROM large_table;

-- ✅ 只讀取需要的欄位
SELECT customer_id, order_date, amount FROM large_table;
```

### 優先使用 GROUP BY 而非 DISTINCT

```sql
-- ❌ 在高基數資料上成本高
SELECT DISTINCT transaction_id FROM huge_table;

-- ✅ 較佳
SELECT transaction_id, COUNT(*) FROM huge_table GROUP BY transaction_id;
```

---

## 監控

追蹤關鍵指標：

```sql
-- 資料新鮮度
SELECT
  table_name,
  MAX(event_timestamp) AS latest_event,
  CURRENT_TIMESTAMP() AS now,
  TIMESTAMPDIFF(MINUTE, MAX(event_timestamp), CURRENT_TIMESTAMP()) AS lag_minutes
FROM pipeline_monitoring.table_metrics
GROUP BY table_name;
```

**請檢查**：
1. 速度慢的 streaming tables（處理延遲高）
2. 大型狀態操作（記憶體用量高）
3. 成本高的 joins（處理時間長）
4. 小檔案（Delta 中存在大量小檔案）

---

## 常見問題

| 問題 | 解法 |
|------|------|
| 管線執行緩慢 | 檢查 partitioning、狀態大小與 join 模式 |
| 記憶體使用量高 | 無界狀態：加入時間視窗、降低基數 |
| 小檔案很多 | 啟用 auto-optimize，執行 OPTIMIZE 指令 |
| 大型資料表查詢成本高 | 加入 clustering，建立已過濾的 MVs |
| MV 重新整理緩慢 | 在來源啟用 row tracking，並確認使用增量重新整理 |
