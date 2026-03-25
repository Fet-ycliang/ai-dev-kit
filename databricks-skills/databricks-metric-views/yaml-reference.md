# 度量檢視 YAML 參考

Unity Catalog 度量檢視中使用的 YAML 規格的完整參考。

## 頂級欄位

| 欄位 | 必填 | 類型 | 描述 |
|------|------|------|------|
| `version` | 否 | string | YAML 規格版本。DBR 17.2+ 使用 `"1.1"`，DBR 16.4-17.1 使用 `"0.1"`。預設為 `1.1`。 |
| `source` | 是 | string | 來源表格、檢視或三級命名空間格式的 SQL 查詢。 |
| `comment` | 否 | string | 度量檢視的描述（v1.1+）。 |
| `filter` | 否 | string | 套用為全域 WHERE 子句的 SQL 布林表達式。 |
| `dimensions` | 是 | list | 維度定義陣列（至少一個）。 |
| `measures` | 是 | list | 測量定義陣列（至少一個）。 |
| `joins` | 否 | list | 星形/雪花型結構聯結定義。 |
| `materialization` | 否 | object | 預先計算配置（實驗性）。 |

## 維度

維度定義用於分組和篩選資料的分類屬性。

```yaml
dimensions:
  - name: Region               # 顯示名稱，在查詢中以反引號括起來
    expr: region_name           # 直接欄位參考
    comment: "銷售區域"          # 選填描述（v1.1+）

  - name: Order Month
    expr: DATE_TRUNC('MONTH', order_date)  # SQL 轉換

  - name: Order Year
    expr: EXTRACT(YEAR FROM `Order Month`)  # 可以參考其他維度

  - name: Customer Type
    expr: CASE
      WHEN customer_tier = 'A' THEN 'Enterprise'
      WHEN customer_tier = 'B' THEN 'Mid-Market'
      ELSE 'SMB'
      END                      # 支援多行 CASE 表達式

  - name: Nation
    expr: customer.c_name      # 參考已聯結表格的欄位
```

### 維度規則

- `name` 必填，在查詢中成為欄位名稱（含空格時需用反引號括起來）
- `expr` 必填，必須是有效的 SQL 表達式
- 可以參考來源欄位、SQL 函式、CASE 表達式和其他維度
- 可以使用 `join_name.column_name` 參考已聯結表格的欄位
- 不能使用聚合函式（那些屬於測量）

## 測量

測量定義在查詢時計算的聚合值。

```yaml
measures:
  - name: Total Revenue
    expr: SUM(total_price)
    comment: "所有訂單價格的總和"

  - name: Order Count
    expr: COUNT(1)

  - name: Average Order Value
    expr: AVG(total_price)

  - name: Unique Customers
    expr: COUNT(DISTINCT customer_id)

  - name: Revenue per Customer           # 比率測量
    expr: SUM(total_price) / COUNT(DISTINCT customer_id)

  - name: Open Order Revenue             # 篩選測量
    expr: SUM(total_price) FILTER (WHERE status = 'O')
    comment: "僅來自開啟訂單的收入"

  - name: Open Revenue per Customer      # 篩選比率
    expr: SUM(total_price) FILTER (WHERE status = 'O') / COUNT(DISTINCT customer_id) FILTER (WHERE status = 'O')
```

### 視窗測量（實驗性）

在測量中新增 `window` 區塊以進行視窗化、累積或半相加聚合。參見[視窗測量文件](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures)。

```yaml
measures:
  - name: Running Total
    expr: SUM(total_price)
    window:
      - order: date              # 排序視窗的維度
        range: cumulative        # 視窗範圍（見下方 range 值）
        semiadditive: last       # 當 order 維度不在 GROUP BY 中時如何摘要

  - name: 7-Day Customers
    expr: COUNT(DISTINCT customer_id)
    window:
      - order: date
        range: trailing 7 day    # 當前前 7 天，不包括當天
        semiadditive: last
```

**視窗 range 值：**

| Range | 描述 |
|-------|------|
| `current` | 僅符合當前排序值的列 |
| `cumulative` | 直到並包括當前列的所有列 |
| `trailing <N> <unit>` | 當前列之前的 N 個單位（不包括當前列） |
| `leading <N> <unit>` | 當前列之後的 N 個單位 |
| `all` | 所有列 |

**視窗規格欄位：**

| 欄位 | 必填 | 描述 |
|------|------|------|
| `order` | 是 | 決定視窗排序的維度名稱 |
| `range` | 是 | 視窗範圍（見上方值） |
| `semiadditive` | 是 | `first` 或 `last` - 當 order 維度不在 GROUP BY 中時要使用的值 |

**多個視窗**可以在單一測量中組成（例如，用於年度至今）：

```yaml
  - name: ytd_sales
    expr: SUM(total_price)
    window:
      - order: date
        range: cumulative
        semiadditive: last
      - order: year
        range: current
        semiadditive: last
```

**衍生測量**可以使用 `MEASURE()` 參考視窗測量：

```yaml
  - name: day_over_day_growth
    expr: (MEASURE(current_day_sales) - MEASURE(previous_day_sales)) / MEASURE(previous_day_sales) * 100
```

### 測量規則

- `name` 必填，透過 `MEASURE(\`name\`)` 查詢
- `expr` 必須包含聚合函式（SUM、COUNT、AVG、MIN、MAX 等）
- 支援 `FILTER (WHERE ...)` 用於條件聚合
- 支援聚合的比率
- 衍生測量可透過 `MEASURE()` 參考其他測量（與視窗測量一起使用）
- 視窗測量使用 `version: 0.1`（實驗性功能）
- 度量檢視上的 `SELECT *` 不支援；必須明確使用 `MEASURE()`

## 聯結

### 星形結構（單級）

```yaml
source: catalog.schema.fact_orders
joins:
  - name: customer
    source: catalog.schema.dim_customer
    on: source.customer_id = customer.id

  - name: product
    source: catalog.schema.dim_product
    on: source.product_id = product.id
```

### 帶 USING 的星形結構

```yaml
joins:
  - name: customer
    source: catalog.schema.dim_customer
    using:
      - customer_id
      - region_id
```

### 雪花型結構（巢狀聯結，DBR 17.1+）

```yaml
source: catalog.schema.orders
joins:
  - name: customer
    source: catalog.schema.customer
    on: source.customer_id = customer.id
    joins:
      - name: nation
        source: catalog.schema.nation
        on: customer.nation_id = nation.id
        joins:
          - name: region
            source: catalog.schema.region
            on: nation.region_id = region.id
```

### 聯結規則

- `name` 必填，用於參考已聯結的欄位：`name.column`
- `source` 是完整限定的表格/檢視名稱
- 使用 `on`（表達式）或 `using`（欄位列表），不可同時使用
- 在 `on` 中，將事實表格參考為 `source`，已聯結表格參考其 `name`
- 巢狀 `joins` 建立雪花型結構（需要 DBR 17.1+）
- 已聯結表格不能包含 MAP 類型欄位

## 篩選

套用於所有查詢的全域篩選作為 WHERE 子句。

```yaml
filter: order_date > '2020-01-01'

# 多個條件
filter: order_date > '2020-01-01' AND status != 'CANCELLED'

# 使用已聯結欄位
filter: customer.active = true
```

## 具體化（實驗性）

預先計算聚合以提升查詢效能。使用 Lakeflow Spark 聲明式管道的底層實現。

```yaml
materialization:
  schedule: every 6 hours           # 與 MV 排程子句相同的語法
  mode: relaxed                     # 目前只支援 "relaxed"

  materialized_views:
    - name: baseline
      type: unaggregated            # 完整非聚合資料模型

    - name: revenue_breakdown
      type: aggregated              # 預先計算聚合
      dimensions:
        - category
        - region
      measures:
        - total_revenue
        - order_count

    - name: daily_summary
      type: aggregated
      dimensions:
        - order_date
      measures:
        - total_revenue
```

### 具體化類型

| 類型 | 描述 | 使用時機 |
|------|------|--------|
| `unaggregated` | 具體化完整資料模型（來源 + 聯結 + 篩選） | 昂貴的來源檢視或許多聯結 |
| `aggregated` | 預先計算特定維度/測量組合 | 經常查詢的組合 |

### 具體化需求

- 必須啟用無伺服器計算
- Databricks Runtime 17.2+
- 不支援 `TRIGGER ON UPDATE` 子句
- 排程使用與具體化檢視排程相同的語法

### 重新整理具體化

```python
# 找尋並重新整理管道
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
pipeline_id = "your-pipeline-id"
w.pipelines.start_update(pipeline_id)
```

## 完整範例

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "含客戶和產品維度的全面銷售指標"
  source: catalog.schema.fact_sales
  filter: sale_date >= '2023-01-01'

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      on: source.customer_id = customer.id
      joins:
        - name: region
          source: catalog.schema.dim_region
          on: customer.region_id = region.id
    - name: product
      source: catalog.schema.dim_product
      on: source.product_id = product.id

  dimensions:
    - name: Sale Month
      expr: DATE_TRUNC('MONTH', sale_date)
      comment: "銷售月份"
    - name: Customer Name
      expr: customer.name
    - name: Region
      expr: region.name
      comment: "地理區域"
    - name: Product Category
      expr: product.category

  measures:
    - name: Total Revenue
      expr: SUM(amount)
      comment: "銷售金額的總和"
    - name: Transaction Count
      expr: COUNT(1)
    - name: Unique Customers
      expr: COUNT(DISTINCT customer_id)
    - name: Average Transaction
      expr: AVG(amount)
    - name: Revenue per Customer
      expr: SUM(amount) / COUNT(DISTINCT customer_id)
      comment: "每個唯一客戶的平均收入"

  materialization:
    schedule: every 1 hour
    mode: relaxed
    materialized_views:
      - name: hourly_region
        type: aggregated
        dimensions:
          - Sale Month
          - Region
        measures:
          - Total Revenue
          - Transaction Count
$$
```
