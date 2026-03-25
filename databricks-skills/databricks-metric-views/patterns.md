# Metric View 模式與範例

建立與查詢 Metric Views 的常見模式。

## 模式 1：單一資料表的簡單指標

最基本的模式，使用直接欄位維度與標準聚合。

### 建立

```sql
CREATE OR REPLACE VIEW catalog.schema.product_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "產品銷售指標"
  source: catalog.schema.sales
  dimensions:
    - name: 產品名稱
      expr: product_name
    - name: 銷售日期
      expr: sale_date
  measures:
    - name: 售出件數
      expr: COUNT(1)
    - name: 總營收
      expr: SUM(price * quantity)
    - name: 平均價格
      expr: AVG(price)
$$
```

### 查詢

```sql
-- 依產品統計營收
SELECT
  `產品名稱`,
  MEASURE(`總營收`) AS revenue,
  MEASURE(`售出件數`) AS units
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY revenue DESC
LIMIT 10

-- 每月趨勢
SELECT
  DATE_TRUNC('MONTH', `銷售日期`) AS month,
  MEASURE(`總營收`) AS revenue
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY month
```

## 模式 2：使用 CASE 的衍生維度

將原始值轉換成較符合業務需求的類別。

```sql
CREATE OR REPLACE VIEW catalog.schema.order_kpis
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders
  dimensions:
    - name: 訂單月份
      expr: DATE_TRUNC('MONTH', order_date)
    - name: 優先等級
      expr: CASE
        WHEN priority <= 2 THEN '高'
        WHEN priority <= 4 THEN '中'
        ELSE '低'
        END
      comment: "已分桶的優先順序：高（1-2）、中（3-4）、低（5）"
    - name: 規模類別
      expr: CASE
        WHEN total_amount > 10000 THEN '大'
        WHEN total_amount > 1000 THEN '中'
        ELSE '小'
        END
  measures:
    - name: 訂單數
      expr: COUNT(1)
    - name: 總金額
      expr: SUM(total_amount)
$$
```

## 模式 3：比率量值

比率與單位化指標，可安全進行重新聚合。

```sql
CREATE OR REPLACE VIEW catalog.schema.efficiency_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "效率與單位化指標"
  source: catalog.schema.transactions
  dimensions:
    - name: 部門
      expr: department_name
    - name: 季度
      expr: DATE_TRUNC('QUARTER', transaction_date)
  measures:
    - name: 總營收
      expr: SUM(revenue)
    - name: 總成本
      expr: SUM(cost)
    - name: 利潤率
      expr: (SUM(revenue) - SUM(cost)) / SUM(revenue)
      comment: "利潤占營收的百分比"
    - name: 每位員工營收
      expr: SUM(revenue) / COUNT(DISTINCT employee_id)
    - name: 平均交易金額
      expr: SUM(revenue) / COUNT(1)
$$
```

## 模式 4：篩選量值（FILTER 子句）

建立只計算部分資料列的量值。

```sql
CREATE OR REPLACE VIEW catalog.schema.order_status_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders
  dimensions:
    - name: 訂單月份
      expr: DATE_TRUNC('MONTH', order_date)
    - name: 區域
      expr: region
  measures:
    - name: 訂單總數
      expr: COUNT(1)
    - name: 未完成訂單數
      expr: COUNT(1) FILTER (WHERE status = 'OPEN')
    - name: 已履約訂單數
      expr: COUNT(1) FILTER (WHERE status = 'FULFILLED')
    - name: 未完成訂單營收
      expr: SUM(amount) FILTER (WHERE status = 'OPEN')
      comment: "未履約訂單的風險營收"
    - name: 履約率
      expr: COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1)
      comment: "已履約訂單的百分比"
$$
```

### 查詢篩選量值

```sql
SELECT
  `訂單月份`,
  MEASURE(`訂單總數`) AS total,
  MEASURE(`未完成訂單數`) AS open_orders,
  MEASURE(`履約率`) AS fulfillment_rate
FROM catalog.schema.order_status_metrics
WHERE `區域` = 'EMEA'
GROUP BY ALL
ORDER BY ALL
```

## 模式 5：使用 Joins 的 Star Schema

將 fact table 與 dimension tables 連接。

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_analytics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "包含客戶與產品維度的銷售分析"
  source: catalog.schema.fact_sales

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      on: source.customer_id = customer.customer_id
    - name: product
      source: catalog.schema.dim_product
      on: source.product_id = product.product_id
    - name: store
      source: catalog.schema.dim_store
      on: source.store_id = store.store_id

  dimensions:
    - name: 客戶區隔
      expr: customer.segment
    - name: 產品類別
      expr: product.category
    - name: 門市城市
      expr: store.city
    - name: 銷售月份
      expr: DATE_TRUNC('MONTH', source.sale_date)

  measures:
    - name: 總營收
      expr: SUM(source.amount)
    - name: 不重複客戶數
      expr: COUNT(DISTINCT source.customer_id)
    - name: 平均客單價
      expr: SUM(source.amount) / COUNT(DISTINCT source.transaction_id)
$$
```

## 模式 6：Snowflake Schema（巢狀 Joins）

多層級維度階層。需要 DBR 17.1+。

```sql
CREATE OR REPLACE VIEW catalog.schema.geo_sales
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders

  joins:
    - name: customer
      source: catalog.schema.customer
      on: source.customer_key = customer.customer_key
      joins:
        - name: nation
          source: catalog.schema.nation
          on: customer.nation_key = nation.nation_key
          joins:
            - name: region
              source: catalog.schema.region
              on: nation.region_key = region.region_key

  dimensions:
    - name: 客戶名稱
      expr: customer.name
    - name: 國家
      expr: nation.name
    - name: 區域
      expr: region.name
    - name: 訂單年份
      expr: EXTRACT(YEAR FROM source.order_date)

  measures:
    - name: 總營收
      expr: SUM(source.total_price)
    - name: 訂單數
      expr: COUNT(1)
$$
```

### 跨階層層級查詢

```sql
-- 依區域統計營收（跨國家與客戶向上彙總）
SELECT
  `區域`,
  MEASURE(`總營收`) AS revenue
FROM catalog.schema.geo_sales
GROUP BY ALL

-- 特定區域內依國家統計營收
SELECT
  `國家`,
  MEASURE(`總營收`) AS revenue,
  MEASURE(`訂單數`) AS orders
FROM catalog.schema.geo_sales
WHERE `區域` = 'EUROPE'
GROUP BY ALL
ORDER BY revenue DESC
```

## 模式 7：Materialized Metric View

預先計算常用聚合以加快查詢。

```sql
CREATE OR REPLACE VIEW catalog.schema.ecommerce_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.transactions

  dimensions:
    - name: 類別
      expr: product_category
    - name: 日期
      expr: DATE_TRUNC('DAY', transaction_date)
    - name: 通路
      expr: sales_channel

  measures:
    - name: 營收
      expr: SUM(amount)
    - name: 交易數
      expr: COUNT(1)
    - name: 不重複買家數
      expr: COUNT(DISTINCT customer_id)

  materialization:
    schedule: every 1 hour
    mode: relaxed
    materialized_views:
      - name: daily_category
        type: aggregated
        dimensions:
          - 類別
          - 日期
        measures:
          - 營收
          - 交易數
      - name: full_model
        type: unaggregated
$$
```

## 模式 8：使用 samples.tpch 快速示範

所有 Databricks workspace 都提供 TPC-H 範例資料集。

```sql
CREATE OR REPLACE VIEW catalog.schema.tpch_orders_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "TPC-H 訂單 KPI - 示範用 Metric View"
  source: samples.tpch.orders
  filter: o_orderdate > '1990-01-01'

  dimensions:
    - name: 訂單月份
      expr: DATE_TRUNC('MONTH', o_orderdate)
      comment: "訂單月份"
    - name: 訂單狀態
      expr: CASE
        WHEN o_orderstatus = 'O' THEN '開啟'
        WHEN o_orderstatus = 'P' THEN '處理中'
        WHEN o_orderstatus = 'F' THEN '已履約'
        END
      comment: "狀態：開啟、處理中或已履約"
    - name: 訂單優先順序
      expr: SPLIT(o_orderpriority, '-')[1]
      comment: "數字優先順序 1-5；1 最高"

  measures:
    - name: 訂單數
      expr: COUNT(1)
    - name: 總營收
      expr: SUM(o_totalprice)
      comment: "總價格加總"
    - name: 每位客戶營收
      expr: SUM(o_totalprice) / COUNT(DISTINCT o_custkey)
      comment: "每位不重複客戶的平均營收"
    - name: 未完成訂單營收
      expr: SUM(o_totalprice) FILTER (WHERE o_orderstatus = 'O')
      comment: "來自未完成訂單的潛在營收"
$$
```

### 示範查詢

```sql
-- 每月營收趨勢
SELECT
  `訂單月份`,
  MEASURE(`總營收`)::BIGINT AS revenue,
  MEASURE(`訂單數`) AS orders
FROM catalog.schema.tpch_orders_metrics
WHERE extract(year FROM `訂單月份`) = 1995
GROUP BY ALL
ORDER BY ALL

-- 依狀態統計營收
SELECT
  `訂單狀態`,
  MEASURE(`總營收`)::BIGINT AS revenue,
  MEASURE(`每位客戶營收`)::BIGINT AS rev_per_customer
FROM catalog.schema.tpch_orders_metrics
GROUP BY ALL

-- 未完成訂單風險評估
SELECT
  `訂單月份`,
  MEASURE(`未完成訂單營收`)::BIGINT AS at_risk_revenue,
  MEASURE(`總營收`)::BIGINT AS total_revenue
FROM catalog.schema.tpch_orders_metrics
WHERE extract(year FROM `訂單月份`) >= 1995
GROUP BY ALL
ORDER BY ALL
```

## 模式 9：Window Measures（實驗性）

Window measures 可支援移動平均、累計總額、期比變化與 semiadditive measures。將 `window` 區塊加到任何 measure 定義中。請參閱 [Window Measures 文件](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures)。

### Window Range 值

| 範圍 | 說明 |
|-------|-------------|
| `current` | 僅包含 window 排序值等於目前資料列的資料 |
| `cumulative` | 從起始到目前資料列（含目前列）的所有資料 |
| `trailing <N> <unit>` | 目前資料列之前 N 個單位的範圍（**不含**目前列） |
| `leading <N> <unit>` | 目前資料列之後 N 個單位的範圍 |
| `all` | 無論排序為何都包含所有資料列 |

### Trailing Window：7 日不重複客戶數

```sql
CREATE OR REPLACE VIEW catalog.schema.customer_activity
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: t7d_customers
      expr: COUNT(DISTINCT customer_id)
      window:
        - order: date
          range: trailing 7 day
          semiadditive: last
$$
```

**重點：** `trailing 7 day` 會包含每個日期**之前**的 7 天，**不含**當天。當 `date` 維度不在 GROUP BY 中時，`semiadditive: last` 會回傳最後一個值。

### 累計總額（Cumulative）

```sql
CREATE OR REPLACE VIEW catalog.schema.cumulative_sales
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: running_total_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: cumulative
          semiadditive: last
$$
```

### 期比：日增長率

使用衍生 measures 中的 `MEASURE()` 參照來組合 window measures。

```sql
CREATE OR REPLACE VIEW catalog.schema.daily_growth
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: previous_day_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: trailing 1 day
          semiadditive: last

    - name: current_day_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: current
          semiadditive: last

    - name: day_over_day_growth
      expr: (MEASURE(current_day_sales) - MEASURE(previous_day_sales)) / MEASURE(previous_day_sales) * 100
$$
```

**重點：** 衍生的 `day_over_day_growth` measure 會使用 `MEASURE()` 參照其他 window measures。它**不需要**自己的 `window` 區塊。

### 年初至今（組合多個 Windows）

單一 measure 可以有多個 window spec，用來建立 period-to-date 計算。

```sql
CREATE OR REPLACE VIEW catalog.schema.ytd_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2023-01-01'

  dimensions:
    - name: date
      expr: order_date
    - name: year
      expr: DATE_TRUNC('year', order_date)

  measures:
    - name: ytd_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: cumulative
          semiadditive: last
        - order: year
          range: current
          semiadditive: last
$$
```

**重點：** 第一個 window 會在 `date` 上做累積加總。第二個 window 會把範圍限制在 `current` 年。兩者結合後即可得到年初至今的結果。

### Semiadditive Measure：銀行餘額

適用於像餘額這類不應跨時間相加的量值。

```sql
CREATE OR REPLACE VIEW catalog.schema.account_balances
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.daily_balances

  dimensions:
    - name: date
      expr: date
    - name: customer
      expr: customer_id

  measures:
    - name: balance
      expr: SUM(balance)
      window:
        - order: date
          range: current
          semiadditive: last
$$
```

**重點：** `semiadditive: last` 可避免跨日期相加（改為回傳最後日期的值），但此量值**仍會跨其他維度聚合**，例如 `customer`。依日期分組時，你會得到該日所有客戶的總餘額；未依日期分組時，你會得到最近日期的餘額。

### 查詢 window measures

Window measures 使用相同的 `MEASURE()` 語法查詢：

```sql
SELECT
  date,
  MEASURE(t7d_customers) AS trailing_7d_customers,
  MEASURE(running_total_sales) AS running_total
FROM catalog.schema.customer_activity
WHERE date >= DATE'2024-06-01'
GROUP BY ALL
ORDER BY ALL
```

## MCP 工具範例

### 建立含 joins 的 Metric View

```python
manage_metric_views(
    action="create",
    full_name="catalog.schema.sales_metrics",
    source="catalog.schema.fact_sales",
    or_replace=True,
    joins=[
        {
            "name": "customer",
            "source": "catalog.schema.dim_customer",
            "on": "source.customer_id = customer.id"
        },
        {
            "name": "product",
            "source": "catalog.schema.dim_product",
            "on": "source.product_id = product.id"
        }
    ],
    dimensions=[
        {"name": "客戶區隔", "expr": "customer.segment"},
        {"name": "產品類別", "expr": "product.category"},
        {"name": "銷售月份", "expr": "DATE_TRUNC('MONTH', source.sale_date)"},
    ],
    measures=[
        {"name": "總營收", "expr": "SUM(source.amount)"},
        {"name": "訂單數", "expr": "COUNT(1)"},
        {"name": "不重複客戶數", "expr": "COUNT(DISTINCT source.customer_id)"},
    ],
)
```

### 修改以新增新 measure

```python
manage_metric_views(
    action="alter",
    full_name="catalog.schema.sales_metrics",
    source="catalog.schema.fact_sales",
    joins=[
        {"name": "customer", "source": "catalog.schema.dim_customer", "on": "source.customer_id = customer.id"},
    ],
    dimensions=[
        {"name": "客戶區隔", "expr": "customer.segment"},
        {"name": "銷售月份", "expr": "DATE_TRUNC('MONTH', source.sale_date)"},
    ],
    measures=[
        {"name": "總營收", "expr": "SUM(source.amount)"},
        {"name": "訂單數", "expr": "COUNT(1)"},
        {"name": "平均訂單金額", "expr": "AVG(source.amount)"},  # 新量值
    ],
)
```

### 搭配篩選條件查詢

```python
manage_metric_views(
    action="query",
    full_name="catalog.schema.sales_metrics",
    query_measures=["總營收", "訂單數"],
    query_dimensions=["客戶區隔", "銷售月份"],
    where="`客戶區隔` = 'Enterprise'",
    order_by="ALL",
    limit=50,
)
```
