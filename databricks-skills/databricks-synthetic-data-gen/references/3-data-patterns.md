# 資料模式指南

使用 Spark + Pandas UDF 建立逼真、一致的合成資料。

## 5 個關鍵原則

1. **使用 Spark + Faker + Pandas UDF** 進行所有產生
2. **參照完整性** - 主表格優先、加權取樣
3. **非線性分佈** - 對數常態、帕累托、指數分佈
4. **基於時間的模式** - 工作日/週末、假日、季節性
5. **列一致性** - 每列內相關聯的屬性

---

## 原則 1：使用 Spark + Faker + Pandas UDF

針對所有使用案例使用 Spark + Faker 產生資料。Pandas UDF 提供高效、分佈式 Faker 呼叫，可無縫擴展從數千到數百萬列。

### 定義 Pandas UDF

```python
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from faker import Faker
import pandas as pd
import numpy as np

@F.pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_address(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.address().replace('\n', ', ') for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(mean=7.5, sigma=0.8)))
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.7)))
        else:
            amounts.append(float(np.random.lognormal(mean=4.0, sigma=0.6)))
    return pd.Series(amounts)
```

### 使用 Spark 產生

```python
# 根據規模調整 numPartitions：<100K 為 8，1M+ 為 32
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=16)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_company(F.col("id")).alias("name"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

---

## 原則 2：參照完整性

優先產生主表格，然後對其進行迭代以建立具有相符 ID 的相關表格。

> **重要：** 不要使用 `.cache()` 或 `.persist()` 搭配無伺服器計算 - 這些操作不受支援並將失敗。改為首先將主表格寫入 Delta，然後讀取以進行外鍵連接。

### 模式：按層級加權取樣

```python
from pyspark.sql.window import Window

# 1. 產生顧客（主表格）並使用索引進行外鍵對應
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.col("id").alias("customer_idx"),  # 保留索引以進行外鍵連接
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        F.when(F.rand(SEED) < 0.6, "Free")
         .when(F.rand(SEED) < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
)

# 2. 寫入 Delta 表格（不要搭配無伺服器計算使用 cache！）
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 3. 讀取以進行外鍵查詢
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select(
    "customer_idx", "customer_id", "tier"
)

# 4. 使用有效外鍵產生訂單
orders_df = spark.range(0, N_ORDERS, numPartitions=PARTITIONS)

# 使用雜湊型分佈將訂單對應到顧客
orders_df = orders_df.select(
    F.concat(F.lit("ORD-"), F.lpad(F.col("id").cast("string"), 6, "0")).alias("order_id"),
    (F.abs(F.hash(F.col("id"), F.lit(SEED))) % N_CUSTOMERS).alias("customer_idx"),
)

# 連接以取得有效外鍵
orders_with_fk = orders_df.join(customer_lookup, on="customer_idx", how="left")
```

### 反面模式：隨機外鍵產生

```python
# 不好 - 可能產生不存在的顧客 ID
orders_df = spark.range(0, N_ORDERS).select(
    F.concat(F.lit("CUST-"), (F.rand() * 99999).cast("int")).alias("customer_id")  # 錯誤！
)
```

---

## 原則 3：非線性分佈

**永遠不要使用均勻分佈** - 真實資料很少均勻分佈。

### 分佈類型

| 分佈 | 使用案例 | 範例 |
|------|---------|------|
| **對數常態** | 價格、薪資、訂單金額 | `np.random.lognormal(mean=4.5, sigma=0.8)` |
| **帕累托/冪律** | 人氣、財富、頁面檢視 | `(np.random.pareto(a=2.5) + 1) * 10` |
| **指數** | 事件之間的時間、解決時間 | `np.random.exponential(scale=24)` |
| **加權分類** | 狀態、地區、層級 | `np.random.choice(vals, p=[0.4, 0.3, 0.2, 0.1])` |

### 用於對數常態金額的 Pandas UDF

```python
@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    """根據層級使用對數常態分佈產生金額。"""
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(mean=7.5, sigma=0.8)))  # ~$1800 平均
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(mean=5.5, sigma=0.7)))  # ~$245 平均
        else:
            amounts.append(float(np.random.lognormal(mean=4.0, sigma=0.6)))  # ~$55 平均
    return pd.Series(amounts)
```

### 反面模式：均勻分佈

```python
# 不好 - 均勻分佈（不逼真）
prices = np.random.uniform(10, 1000, size=N_ORDERS)

# 好 - 對數常態（逼真的價格）
prices = np.random.lognormal(mean=4.5, sigma=0.8, size=N_ORDERS)
```

---

## 原則 4：基於時間的模式

新增工作日/週末效應、假日、季節性和事件尖峰。

### 假日和工作日乘數

```python
import holidays
from datetime import datetime, timedelta

# 載入假日日曆
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

def get_daily_multiplier(date):
    """計算給定日期的音量乘數。"""
    multiplier = 1.0

    # 週末下跌
    if date.weekday() >= 5:
        multiplier *= 0.6

    # 假日下跌（甚至低於週末）
    if date in US_HOLIDAYS:
        multiplier *= 0.3

    # Q4 季節性（10 月至 12 月時更高）
    multiplier *= 1 + 0.15 * (date.month - 6) / 6

    # 事件尖峰（如適用）
    if INCIDENT_START <= date <= INCIDENT_END:
        multiplier *= 3.0

    # 隨機雜訊
    multiplier *= np.random.normal(1, 0.1)

    return max(0.1, multiplier)
```

### 日期範圍：最後 6 個月

始終為以目前日期結束的最後 ~6 個月產生資料：

```python
from datetime import datetime, timedelta

END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)
```

---

## 原則 5：列一致性

列內的屬性應邏輯相關。

### 一致的票務產生

```python
@F.pandas_udf("struct<priority:string,resolution_hours:double,csat_score:int>")
def generate_coherent_ticket(tiers: pd.Series) -> pd.DataFrame:
    """產生屬性相關聯的一致票務。"""
    results = []
    for tier in tiers:
        # 優先順序與層級相關
        if tier == 'Enterprise':
            priority = np.random.choice(['Critical', 'High', 'Medium'], p=[0.3, 0.5, 0.2])
        else:
            priority = np.random.choice(['Critical', 'High', 'Medium', 'Low'], p=[0.05, 0.2, 0.45, 0.3])

        # 解決時間與優先順序相關
        resolution_scale = {'Critical': 4, 'High': 12, 'Medium': 36, 'Low': 72}
        resolution_hours = np.random.exponential(scale=resolution_scale[priority])

        # 顧客滿意度與解決時間相關
        if resolution_hours < 4:
            csat = np.random.choice([4, 5], p=[0.3, 0.7])
        elif resolution_hours < 24:
            csat = np.random.choice([3, 4, 5], p=[0.2, 0.5, 0.3])
        else:
            csat = np.random.choice([1, 2, 3, 4], p=[0.1, 0.3, 0.4, 0.2])

        results.append({
            "priority": priority,
            "resolution_hours": round(resolution_hours, 1),
            "csat_score": int(csat),
        })

    return pd.DataFrame(results)
```

### 相關範例

| 屬性 A | 屬性 B | 相關性 |
|--------|--------|--------|
| 顧客層級 | 訂單金額 | Enterprise = 更高金額 |
| 票務優先順序 | 解決時間 | Critical = 更快解決 |
| 解決時間 | 顧客滿意度 | 更快 = 更高滿意度 |
| 地區 | 產品偏好 | 地區變化 |
| 一天中的時間 | 交易類型 | 營業時間 = B2B |

---

## 聚合資料量

產生足夠的資料，使模式在下游聚合後仍可見：

| 粒度 | 最少記錄數 | 基本原理 |
|------|-----------|---------|
| 每日時間序列 | 50-100/天 | 週匯總後看到趨勢 |
| 每個類別 | 每個類別 500+ | 統計顯著性 |
| 每個顧客 | 5-20 個事件/顧客 | 客戶層級分析 |
| 總列 | 最少 10K-50K | 模式在 GROUP BY 後存活 |

```python
# 範例：180 天內 8000 張票務 = ~44/天平均
# 週匯總後：~310 條記錄/週
N_TICKETS = 8000
N_CUSTOMERS = 2500  # 每個平均有 ~3 張票務
N_ORDERS = 25000    # ~10 個訂單/顧客平均
```
