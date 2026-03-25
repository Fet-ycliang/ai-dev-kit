# `ai_forecast` — 完整參考

**文件：** https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_forecast

> `ai_forecast` 是**資料表值型函式**——它回傳的是資料列組成的資料表，而不是純量。請使用 `SELECT * FROM ai_forecast(...)` 呼叫。

## 需求條件

- **Pro 或 Serverless SQL warehouse**——Classic 或 Starter 不提供
- 輸入資料必須具有 DATE 或 TIMESTAMP 時間欄位，以及至少一個數值欄位

## 語法

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(...) or query,
    horizon                    => 'YYYY-MM-DD' or TIMESTAMP,
    time_col                   => 'column_name',
    value_col                  => 'column_name',
    [group_col                 => 'column_name'],
    [prediction_interval_width => 0.95]
)
```

## 參數

| 參數 | 型別 | 說明 |
|---|---|---|
| `observed` | TABLE 參照或子查詢 | 含時間 + 數值欄位的訓練資料 |
| `horizon` | DATE、TIMESTAMP 或 STRING | 預測期間的結束日期／時間 |
| `time_col` | STRING | `observed` 中 DATE 或 TIMESTAMP 欄位的名稱 |
| `value_col` | STRING | 要預測的一個或多個數值欄位（每個 group 最多 100 個） |
| `group_col` | STRING（選填） | 依欄位分組預測——每個 group 值各產生一條預測序列 |
| `prediction_interval_width` | DOUBLE（選填，預設 0.95） | 介於 0 到 1 之間的信賴區間寬度 |

## 輸出欄位

對於每個名為 `metric` 的 `value_col`，輸出包含：

| 欄位 | 型別 | 說明 |
|---|---|---|
| time_col | DATE 或 TIMESTAMP | 預測時間戳（與輸入型別相同） |
| `metric_forecast` | DOUBLE | 點預測值 |
| `metric_upper` | DOUBLE | 信賴區間上界 |
| `metric_lower` | DOUBLE | 信賴區間下界 |
| group_col | 原始型別 | 指定 `group_col` 時才會出現 |

## 模式

### 單一指標預測

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT order_date, revenue FROM daily_revenue),
    horizon   => '2026-12-31',
    time_col  => 'order_date',
    value_col => 'revenue'
);
-- 回傳：order_date, revenue_forecast, revenue_upper, revenue_lower
```

### 多群組預測

會為 `group_col` 的每個不同值產生一條預測序列：

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, region, sales FROM regional_sales),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales',
    group_col => 'region'
);
-- 回傳：date, region, sales_forecast, sales_upper, sales_lower
-- 每個 region 的每個日期各一列
```

### 多個數值欄位

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(SELECT date, units, revenue FROM daily_kpis),
    horizon   => '2026-06-30',
    time_col  => 'date',
    value_col => 'units,revenue'   -- 以逗號分隔
);
-- 回傳：date, units_forecast, units_upper, units_lower,
--                revenue_forecast, revenue_upper, revenue_lower
```

### 自訂信賴區間

```sql
SELECT *
FROM ai_forecast(
    observed                   => TABLE(SELECT ts, sensor_value FROM iot_readings),
    horizon                    => '2026-03-31',
    time_col                   => 'ts',
    value_col                  => 'sensor_value',
    prediction_interval_width  => 0.80   -- 較窄的區間 = 較不保守
);
```

### 篩選輸入資料（Subquery）

```sql
SELECT *
FROM ai_forecast(
    observed  => TABLE(
        SELECT date, sales
        FROM daily_sales
        WHERE region = 'BR' AND date >= '2024-01-01'
    ),
    horizon   => '2026-12-31',
    time_col  => 'date',
    value_col => 'sales'
);
```

### PySpark — 使用 `spark.sql()`

`ai_forecast` 是資料表值型函式，因此必須透過 `spark.sql()` 呼叫：

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, sales FROM catalog.schema.daily_sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'sales'
    )
""")
result.display()
```

### 將預測結果儲存至 Delta 資料表

```python
result = spark.sql("""
    SELECT *
    FROM ai_forecast(
        observed  => TABLE(SELECT date, region, revenue FROM catalog.schema.sales),
        horizon   => '2026-12-31',
        time_col  => 'date',
        value_col => 'revenue',
        group_col => 'region'
    )
""")
result.write.format("delta").mode("overwrite").saveAsTable("catalog.schema.revenue_forecast")
```

## 注意事項

- 底層模型是類似 prophet 的分段線性 + 季節性模型——適合具有趨勢與每週／每年季節性的商業時間序列
- 可處理「任意數量的群組」，但每個群組最多 **100 個指標**
- 輸出時間欄位會保留輸入型別（DATE 仍為 DATE，TIMESTAMP 仍為 TIMESTAMP）
- 無論輸入型別為何，數值欄位在輸出中一律轉型為 DOUBLE