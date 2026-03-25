# Materialized Views、Temporary Tables/Views 與 Pipe Syntax

## 1. Databricks SQL 中的 Materialized Views

### 概觀

Materialized views (MVs) 是由 Unity Catalog 管理、會實體儲存預先計算查詢結果的資料表。不同於每次查詢都會重新計算的標準 views，MVs 會快取結果並自動更新——可依排程、上游資料變更或隨需觸發。

主要特性：
- **預先計算儲存**：結果會以 Delta tables 實體儲存，降低查詢延遲
- **自動更新**：來源資料表的變更會透過增量或完整重新整理傳播
- **Serverless pipelines**：每個 MV 都會自動建立一條 serverless pipeline，用於建立與重新整理
- **增量重新整理**：在特定條件下，只計算來源資料中已變更的部分

### 需求條件

- **Compute**：啟用 Unity Catalog 的 **Serverless** SQL warehouse
- **區域**：你的區域必須支援 Serverless SQL warehouse
- **權限**：
  - 建立者需要：對 base tables 的 `SELECT` 權限，以及 `USE CATALOG`、`USE SCHEMA`、`CREATE TABLE`、`CREATE MATERIALIZED VIEW`
  - 重新整理需要：擁有者身分或 `REFRESH` 權限；MV 擁有者必須持續保有對 base tables 的 `SELECT` 權限
  - 查詢需要：對 MV 的 `SELECT` 權限，以及 `USE CATALOG`、`USE SCHEMA`

### CREATE MATERIALIZED VIEW 語法

```sql
{ CREATE OR REPLACE MATERIALIZED VIEW | CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] }
  view_name
  [ column_list ]
  [ view_clauses ]
  AS query
```

**欄位清單**（可選）：
```sql
CREATE MATERIALIZED VIEW mv_name (
  col1 INT NOT NULL,
  col2 STRING,
  col3 DOUBLE,
  CONSTRAINT pk PRIMARY KEY (col1)
)
AS SELECT ...
```

**View 子句**（可選）：
- `PARTITIONED BY (col1, col2)` -- 依欄位分區
- `CLUSTER BY (col1, col2)` or `CLUSTER BY AUTO` -- liquid clustering（不可與 `PARTITIONED BY` 併用）
- `COMMENT 'description'` -- view 說明
- `TBLPROPERTIES ('key' = 'value')` -- 使用者自訂屬性
- `WITH ROW FILTER func ON (col1, col2)` -- 列層級安全
- `MASK func` on columns -- 欄位層級遮罩
- `SCHEDULE` clause -- 自動重新整理排程
- `TRIGGER ON UPDATE` clause -- 事件驅動重新整理

### 基本範例

```sql
-- 簡單的 materialized view
CREATE MATERIALIZED VIEW catalog.schema.daily_sales
  COMMENT '每日銷售彙總'
AS SELECT
    date,
    region,
    SUM(sales) AS total_sales,
    COUNT(*) AS num_transactions
FROM catalog.schema.raw_sales
GROUP BY date, region;

-- 具有明確欄位、限制條件與 clustering 的 MV
CREATE MATERIALIZED VIEW catalog.schema.customer_orders (
  customer_id INT NOT NULL,
  full_name STRING,
  order_count BIGINT,
  CONSTRAINT customer_pk PRIMARY KEY (customer_id)
)
CLUSTER BY AUTO
COMMENT '客戶訂單數量'
AS SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
INNER JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.full_name;
```

### 重新整理選項

MVs 支援四種重新整理策略：

#### 1. 手動重新整理

```sql
-- 同步（會阻塞直到完成）
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales;

-- 非同步（立即回傳）
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales ASYNC;
```

#### 2. 排程重新整理（SCHEDULE）

```sql
-- 每 N 小時／天／週
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.hourly_metrics
  SCHEDULE EVERY 1 HOUR
AS SELECT date_trunc('hour', event_time) AS hour, COUNT(*) AS events
FROM catalog.schema.raw_events
GROUP BY 1;

-- 以 Cron 為基礎的排程
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.nightly_report
  SCHEDULE CRON '0 0 2 * * ?' AT TIME ZONE 'America/New_York'
AS SELECT * FROM catalog.schema.daily_aggregates;
```

有效間隔為 1-72 小時、1-31 天、1-8 週。系統會自動為排程重新整理建立 Databricks Job。

#### 3. 事件驅動重新整理（TRIGGER ON UPDATE）

當上游資料變更時會自動重新整理：

```sql
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE
AS SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name;

-- 搭配節流設定以避免過度頻繁重新整理
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE AT MOST EVERY INTERVAL 5 MINUTES
AS SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name;
```

觸發限制：
- 最多 **10 個上游來源資料表** 與 **30 個上游 views**
- 最小間隔為 **1 分鐘**（預設值）
- 每個 workspace 最多 **1,000** 個以 trigger 為基礎的 MVs
- 支援 Delta tables、managed views 與 streaming tables 作為來源
- **不**支援 Delta Sharing shared tables

#### 4. 以 Job 為基礎的編排

可使用 SQL task 類型，將重新整理整合到既有的 Databricks Jobs：

```sql
-- 在 Databricks Job 的 SQL task 中
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales_summary;
```

### 建立後管理排程

```sql
-- 為既有 MV 新增排程
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD SCHEDULE EVERY 4 HOURS;

-- 新增 trigger 式重新整理
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD TRIGGER ON UPDATE;

-- 變更既有排程
ALTER MATERIALIZED VIEW catalog.schema.my_mv ALTER SCHEDULE EVERY 2 HOURS;

-- 移除排程
ALTER MATERIALIZED VIEW catalog.schema.my_mv DROP SCHEDULE;
```