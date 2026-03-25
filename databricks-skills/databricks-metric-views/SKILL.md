---
name: databricks-metric-views
description: "Unity Catalog 度量檢視：以 YAML 定義、建立、查詢和管理受治理的業務指標。當建立標準化 KPI、收入指標、訂單分析或任何需要跨團隊和工具一致定義的可重用業務指標時使用。"
---

# Unity Catalog 度量檢視

在 YAML 中定義可重用的受治理業務指標，將測量定義與維度分組分離，以實現靈活查詢。

## 使用時機

使用此技能時：
- 定義**標準化業務指標**（收入、訂單計數、轉換率）
- 建立**KPI 層**，在儀表板、Genie 和 SQL 查詢中共用
- 建立含有**複雜聚合**的指標（比率、不同計數、篩選測量）
- 定義**視窗測量**（移動平均、執行總計、期間對期間、年度至今）
- 建模**星形或雪花型結構**，並在度量定義中進行聯結
- 啟用**具體化**以預先計算度量聚合

## 先決條件

- **Databricks Runtime 17.2+**（用於 YAML 版本 1.1）
- 具有 `CAN USE` 權限的 SQL 倉庫
- 來源表的 `SELECT`、目標結構的 `CREATE TABLE` + `USE SCHEMA`

## 快速入門

### 建立度量檢視

```sql
CREATE OR REPLACE VIEW catalog.schema.orders_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "用於銷售分析的訂單 KPI"
  source: catalog.schema.orders
  filter: order_date > '2020-01-01'
  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
      comment: "訂單月份"
    - name: Order Status
      expr: CASE
        WHEN status = 'O' THEN 'Open'
        WHEN status = 'P' THEN 'Processing'
        WHEN status = 'F' THEN 'Fulfilled'
        END
      comment: "人類可讀的訂單狀態"
  measures:
    - name: Order Count
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(total_price)
      comment: "總價格的總和"
    - name: Revenue per Customer
      expr: SUM(total_price) / COUNT(DISTINCT customer_id)
      comment: "每個唯一客戶的平均收入"
$$
```

### 查詢度量檢視

所有測量必須使用 `MEASURE()` 函式。不支援 `SELECT *`。

```sql
SELECT
  `Order Month`,
  `Order Status`,
  MEASURE(`Total Revenue`) AS total_revenue,
  MEASURE(`Order Count`) AS order_count
FROM catalog.schema.orders_metrics
WHERE extract(year FROM `Order Month`) = 2024
GROUP BY ALL
ORDER BY ALL
```

## 參考檔案

| 主題 | 檔案 | 描述 |
|------|------|------|
| YAML 語法 | [yaml-reference.md](yaml-reference.md) | 完整 YAML 規格：維度、測量、聯結、具體化 |
| 模式與範例 | [patterns.md](patterns.md) | 常見模式：星形結構、雪花型、篩選測量、視窗測量、比率 |

## MCP 工具

使用 `manage_metric_views` 工具進行所有度量檢視操作：

| 動作 | 描述 |
|------|------|
| `create` | 建立含有維度和測量的度量檢視 |
| `alter` | 更新度量檢視的 YAML 定義 |
| `describe` | 取得完整定義和中繼資料 |
| `query` | 查詢按維度分組的測量 |
| `drop` | 捨棄度量檢視 |
| `grant` | 授予使用者/群組 SELECT 權限 |

### 透過 MCP 建立

```python
manage_metric_views(
    action="create",
    full_name="catalog.schema.orders_metrics",
    source="catalog.schema.orders",
    or_replace=True,
    comment="用於銷售分析的訂單 KPI",
    filter_expr="order_date > '2020-01-01'",
    dimensions=[
        {"name": "Order Month", "expr": "DATE_TRUNC('MONTH', order_date)", "comment": "訂單月份"},
        {"name": "Order Status", "expr": "status"},
    ],
    measures=[
        {"name": "Order Count", "expr": "COUNT(1)"},
        {"name": "Total Revenue", "expr": "SUM(total_price)", "comment": "總價格的總和"},
    ],
)
```

### 透過 MCP 查詢

```python
manage_metric_views(
    action="query",
    full_name="catalog.schema.orders_metrics",
    query_measures=["Total Revenue", "Order Count"],
    query_dimensions=["Order Month"],
    where="extract(year FROM `Order Month`) = 2024",
    order_by="ALL",
    limit=100,
)
```

### 透過 MCP 描述

```python
manage_metric_views(
    action="describe",
    full_name="catalog.schema.orders_metrics",
)
```

### 授予存取權限

```python
manage_metric_views(
    action="grant",
    full_name="catalog.schema.orders_metrics",
    principal="data-consumers",
    privileges=["SELECT"],
)
```

## YAML 規格快速參考

```yaml
version: 1.1                    # 必填：DBR 17.2+ 使用 "1.1"
comment: "描述"                 # 選填：度量檢視描述
source: catalog.schema.table    # 必填：來源表格/檢視
filter: column > value          # 選填：全域 WHERE 篩選

dimensions:                     # 必填：至少一個
  - name: Display Name          # 在查詢中用反引號括起來
    expr: sql_expression        # 欄位參考或 SQL 轉換
    comment: "描述"              # 選填（v1.1+）

measures:                       # 必填：至少一個
  - name: Display Name          # 透過 MEASURE(`name`) 查詢
    expr: AGG_FUNC(column)      # 必須是聚合表達式
    comment: "描述"              # 選填（v1.1+）

joins:                          # 選填：星形/雪花型結構
  - name: dim_table
    source: catalog.schema.dim_table
    on: source.fk = dim_table.pk

materialization:                # 選填（實驗性）
  schedule: every 6 hours
  mode: relaxed
```

## 關鍵概念

### 維度 vs 測量

| | 維度 | 測量 |
|---|------|------|
| **目的** | 分類和分組資料 | 聚合數值 |
| **範例** | 區域、日期、狀態 | SUM(revenue)、COUNT(orders) |
| **在查詢中** | 用於 SELECT 和 GROUP BY | 包裝在 `MEASURE()` 中 |
| **SQL 表達式** | 任何 SQL 表達式 | 必須使用聚合函式 |

### 為什麼選擇度量檢視而不是標準檢視？

| 功能 | 標準檢視 | 度量檢視 |
|------|--------|--------|
| 聚合在建立時鎖定 | 是 | 否 - 查詢時靈活 |
| 比率的安全重新聚合 | 否 | 是 |
| 星形/雪花型結構聯結 | 手動 | YAML 聲明式 |
| 具體化 | 需要單獨 MV | 內建 |
| AI/BI Genie 整合 | 有限 | 原生 |

## 常見問題

| 問題 | 解決方案 |
|------|--------|
| **不支援 SELECT *** | 必須明確列出維度並對測量使用 MEASURE() |
| **「無法解析欄位」** | 含空格的維度/測量名稱需要反引號括起來 |
| **JOIN 在查詢時失敗** | 聯結必須在 YAML 定義中，不在 SELECT 查詢中 |
| **MEASURE() 必填** | 所有測量參考必須包裝：`MEASURE(\`name\`)` |
| **DBR 版本錯誤** | 需要 Runtime 17.2+ 用於 YAML v1.1，或 16.4+ 用於 v0.1 |
| **具體化不起作用** | 需要啟用無伺服器計算；目前為實驗性功能 |

## 整合

度量檢視原生支援：
- **AI/BI 儀表板** - 用作視覺化的資料集
- **AI/BI Genie** - 度量的自然語言查詢
- **警示** - 對測量設定基於閾值的警示
- **SQL 編輯器** - 使用 MEASURE() 直接 SQL 查詢
- **目錄瀏覽器 UI** - 視覺化建立和瀏覽

## 資源

- [度量檢視文件](https://docs.databricks.com/en/metric-views/)
- [YAML 語法參考](https://docs.databricks.com/en/metric-views/data-modeling/syntax)
- [聯結](https://docs.databricks.com/en/metric-views/data-modeling/joins)
- [視窗測量](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures)（實驗性）
- [具體化](https://docs.databricks.com/en/metric-views/materialization)
- [MEASURE() 函式](https://docs.databricks.com/en/sql/language-manual/functions/measure)
