# SDP 的串流模式

串流專用模式，包括去重、視窗彙總、延遲到達資料處理，以及狀態式操作。

---

## 去重模式

### 依 Key

```sql
-- Bronze：全部擷取（可能包含重複）
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT *, current_timestamp() AS _ingested_at
FROM read_stream(...);

-- Silver：依 event_id 去重
CREATE OR REPLACE STREAMING TABLE silver_events_dedup AS
SELECT
  event_id, user_id, event_type, event_timestamp, _ingested_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM STREAM bronze_events
)
WHERE rn = 1;
```

### 搭配時間視窗

在時間視窗內去重，以處理延遲到達的資料：

```sql
CREATE OR REPLACE STREAMING TABLE silver_events_dedup AS
SELECT
  event_id, user_id, event_type, event_timestamp,
  MIN(_ingested_at) AS first_seen_at
FROM STREAM bronze_events
GROUP BY
  event_id, user_id, event_type, event_timestamp,
  window(event_timestamp, '1 hour')  -- 在 1 小時視窗內去重
HAVING COUNT(*) >= 1;
```

### 複合 Key

```sql
CREATE OR REPLACE STREAMING TABLE silver_transactions_dedup AS
SELECT
  transaction_id, customer_id, amount, transaction_timestamp,
  MIN(_ingested_at) AS _ingested_at
FROM STREAM bronze_transactions
GROUP BY transaction_id, customer_id, amount, transaction_timestamp;
```

---

## 視窗彙總

### Tumbling Windows

```sql
-- 5 分鐘不重疊視窗
CREATE OR REPLACE STREAMING TABLE silver_sensor_5min AS
SELECT
  sensor_id,
  window(event_timestamp, '5 minutes') AS time_window,
  AVG(temperature) AS avg_temperature,
  MIN(temperature) AS min_temperature,
  MAX(temperature) AS max_temperature,
  COUNT(*) AS event_count
FROM STREAM bronze_sensor_events
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

### 多種視窗大小

```sql
-- 1 分鐘用於即時監控
CREATE OR REPLACE STREAMING TABLE gold_sensor_1min AS
SELECT
  sensor_id,
  window(event_timestamp, '1 minute').start AS window_start,
  window(event_timestamp, '1 minute').end AS window_end,
  AVG(value) AS avg_value,
  COUNT(*) AS event_count
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 minute');

-- 1 小時用於趨勢分析
CREATE OR REPLACE STREAMING TABLE gold_sensor_1hour AS
SELECT
  sensor_id,
  window(event_timestamp, '1 hour').start AS window_start,
  AVG(value) AS avg_value,
  STDDEV(value) AS stddev_value
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 hour');
```

---

## 延遲到達資料

### Event-Time 與 Processing-Time

業務邏輯一律使用事件時間戳記，而不是擷取時間戳記：

```sql
-- ✅ 使用事件時間戳記
CREATE OR REPLACE STREAMING TABLE silver_orders AS
SELECT
  order_id, order_timestamp,  -- 來源中的事件時間
  customer_id, amount,
  _ingested_at                -- 處理時間（僅供偵錯）
FROM STREAM bronze_orders;

-- 依事件時間分組
CREATE OR REPLACE STREAMING TABLE gold_daily_orders AS
SELECT
  CAST(order_timestamp AS DATE) AS order_date,  -- 事件時間
  COUNT(*) AS order_count,
  SUM(amount) AS total_amount
FROM STREAM silver_orders
GROUP BY CAST(order_timestamp AS DATE);
```

### 使用 SCD2 處理亂序資料

使用事件時間戳記搭配 `SEQUENCE BY`。**子句順序很重要**：請將 `APPLY AS DELETE WHEN` 放在 `SEQUENCE BY` 之前。`COLUMNS * EXCEPT (...)` 中只列出來源實際存在的欄位（除非 bronze 資料表使用 rescue data，否則不要列入 `_rescued_data`）。如果 `TRACK HISTORY ON *` 造成 parse error，請省略；預設行為等同於它。

```sql
CREATE OR REFRESH STREAMING TABLE silver_customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO silver_customers_history
FROM stream(bronze_customer_cdc)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY event_timestamp  -- 處理亂序資料
COLUMNS * EXCEPT (operation, _ingested_at, _source_file)
STORED AS SCD TYPE 2;
```

---

## 狀態式操作

### Stream-to-Stream Join

```sql
-- Join 兩個串流來源
CREATE OR REPLACE STREAMING TABLE silver_orders_with_payments AS
SELECT
  o.order_id, o.customer_id, o.order_timestamp, o.amount AS order_amount,
  p.payment_id, p.payment_timestamp, p.payment_method, p.amount AS payment_amount
FROM STREAM bronze_orders o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
  AND p.payment_timestamp BETWEEN o.order_timestamp AND o.order_timestamp + INTERVAL 1 HOUR;
```

### Stream-to-Static Join

使用維度資料表為串流資料補充資訊：

```sql
-- 靜態維度（不常變動）
CREATE OR REPLACE TABLE dim_products AS
SELECT * FROM catalog.schema.products;

-- Stream-to-static join
CREATE OR REPLACE STREAMING TABLE silver_sales_enriched AS
SELECT
  s.sale_id, s.product_id, s.quantity, s.sale_timestamp,
  p.product_name, p.category, p.price,
  s.quantity * p.price AS total_amount
FROM STREAM bronze_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

### 增量彙總

```sql
-- 依客戶計算累積總額（stateful）
CREATE OR REPLACE STREAMING TABLE silver_customer_running_totals AS
SELECT
  customer_id,
  SUM(amount) AS total_spent,
  COUNT(*) AS transaction_count,
  MAX(transaction_timestamp) AS last_transaction_at
FROM STREAM bronze_transactions
GROUP BY customer_id;
```

---

## Session Windows

根據非活動間隔將事件分組為 session：

```sql
-- 30 分鐘非活動逾時
CREATE OR REPLACE STREAMING TABLE silver_user_sessions AS
SELECT
  user_id,
  session_window(event_timestamp, '30 minutes') AS session,
  MIN(event_timestamp) AS session_start,
  MAX(event_timestamp) AS session_end,
  COUNT(*) AS event_count,
  COLLECT_LIST(event_type) AS event_sequence
FROM STREAM bronze_user_events
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

---

## 異常偵測

### 即時離群值偵測

```sql
CREATE OR REPLACE STREAMING TABLE silver_sensor_with_anomalies AS
SELECT
  sensor_id, event_timestamp, temperature,
  AVG(temperature) OVER (
    PARTITION BY sensor_id ORDER BY event_timestamp
    ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
  ) AS rolling_avg_100,
  STDDEV(temperature) OVER (
    PARTITION BY sensor_id ORDER BY event_timestamp
    ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
  ) AS rolling_stddev_100,
  CASE
    WHEN temperature > rolling_avg_100 + (3 * rolling_stddev_100) THEN 'HIGH_OUTLIER'
    WHEN temperature < rolling_avg_100 - (3 * rolling_stddev_100) THEN 'LOW_OUTLIER'
    ELSE 'NORMAL'
  END AS anomaly_flag
FROM STREAM bronze_sensor_events;

-- 將異常資料導向告警流程
CREATE OR REPLACE STREAMING TABLE silver_sensor_anomalies AS
SELECT *
FROM STREAM silver_sensor_with_anomalies
WHERE anomaly_flag IN ('HIGH_OUTLIER', 'LOW_OUTLIER');
```

### 依閾值篩選

```sql
CREATE OR REPLACE STREAMING TABLE silver_high_value_transactions AS
SELECT transaction_id, customer_id, amount, transaction_timestamp
FROM STREAM bronze_transactions
WHERE amount > 10000;
```

---

## 執行模式

在 pipeline 層級設定（不要在 SQL 中設定）：

**Continuous**（即時、次秒級延遲）：
```yaml
execution_mode: continuous
serverless: true
```

**Triggered**（排程、成本最佳化）：
```yaml
execution_mode: triggered
schedule: "0 * * * *"  # 每小時
```

**何時使用**：
- **Continuous**：即時儀表板、告警、次分鐘級 SLA
- **Triggered**：每日／每小時報表、批次處理

---

## 關鍵模式

### 1. 使用事件時間戳記

```sql
-- ✅ 以事件時間戳記作為邏輯依據
GROUP BY date_trunc('hour', event_timestamp)

-- ❌ 使用處理時間戳記
GROUP BY date_trunc('hour', _ingested_at)
```

### 2. 視窗大小選擇

- **1-5 分鐘**：即時監控
- **15-60 分鐘**：營運儀表板
- **1-24 小時**：分析報表

### 3. State 管理

較高 cardinality = 較多 state：

```sql
-- 高 state：1M users × 10K products × 100M sessions
GROUP BY user_id, product_id, session_id

-- 較低 state：1M users × 100 categories × days
GROUP BY user_id, product_category, DATE(event_time)
```

使用時間視窗限制 state 保留量。

### 4. 儘早去重

套用於 bronze → silver 轉換：

```sql
-- Bronze：接受重複資料
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT * FROM read_stream(...);

-- Silver：立即去重
CREATE OR REPLACE STREAMING TABLE silver_events AS
SELECT DISTINCT event_id, event_type, event_timestamp, user_id
FROM STREAM bronze_events;

-- Gold：使用乾淨資料
CREATE OR REPLACE STREAMING TABLE gold_metrics AS
SELECT ... FROM STREAM silver_events;
```

### 5. 監控 Lag

```sql
CREATE OR REPLACE STREAMING TABLE monitoring_lag AS
SELECT
  'kafka_events' AS source,
  MAX(kafka_timestamp) AS max_event_timestamp,
  current_timestamp() AS processing_timestamp,
  (unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp))) AS lag_seconds
FROM STREAM bronze_kafka_events
GROUP BY window(kafka_timestamp, '1 minute');
```

---

## 常見問題

| 問題 | 解法 |
|-------|----------|
| 視窗處理導致記憶體使用過高 | 使用更大的視窗，降低 group-by cardinality |
| 輸出中出現重複事件 | 依唯一 key 明確加入去重邏輯 |
| 缺少延遲到達事件 | 增大視窗大小或使用更長的 retention |
| Stream-to-stream join 結果為空 | 確認 join 條件與時間界線 |
| state 隨時間持續成長 | 加入時間視窗、降低 cardinality、materialize 中介結果 |
