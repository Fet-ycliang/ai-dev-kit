# 資料產生方法

根據規模和需求選擇您的方法。**強烈偏好使用 Spark + Faker + Pandas UDF** 用於所有情況。

## 決策表

| 案例 | 建議方法 |
|------|---------|
| **預設 - 任何資料產生** | **Spark + Faker + Pandas UDF** |
| 大型資料集（100K+ 列） | **Spark + Faker + Pandas UDF** |
| 中型資料集（10K-100K 列） | **Spark + Faker + Pandas UDF** |
| 小型資料集（<10K 列） | **Spark + Faker + Pandas UDF**（或若使用者偏好本地則使用 Polars） |

**規則：** 除非使用者明確要求本地產生 <10K 列，否則始終使用 Spark + Faker + Pandas UDF。

---

## 方法 1：Spark + Faker + Pandas UDF（強烈推薦）

**適用於：** 所有資料集大小、直接寫入統一目錄

**為什麼使用此方法：**
- 從數千到數百萬列進行擴展
- 透過 Spark 進行平行執行
- 與統一目錄直接整合
- 無需中間檔案或上傳
- 適用於無伺服器和經典計算

### 基本模式

```python
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
from faker import Faker
import pandas as pd
import numpy as np

# 定義用於 Faker 資料的 Pandas UDF（批次處理以實現平行性）
@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_company(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.company() for _ in range(len(ids))])

@F.pandas_udf(StringType())
def fake_email(ids: pd.Series) -> pd.Series:
    fake = Faker()
    return pd.Series([fake.email() for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_lognormal_amount(tiers: pd.Series) -> pd.Series:
    """根據層級使用對數常態分佈產生金額。"""
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

### 使用 Spark + Pandas UDF 產生資料

```python
# 設定
N_CUSTOMERS = 100_000
PARTITIONS = 16  # 根據資料大小調整：<100K 為 8，1M+ 為 32
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 使用 Spark + Pandas UDF 產生顧客
customers_df = (
    spark.range(0, N_CUSTOMERS, numPartitions=PARTITIONS)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        fake_company(F.col("id")).alias("company"),
        fake_email(F.col("id")).alias("email"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
        F.when(F.rand() < 0.4, "North")
         .when(F.rand() < 0.65, "South")
         .when(F.rand() < 0.85, "East")
         .otherwise("West").alias("region"),
    )
)

# 新增基於層級的金額
customers_df = customers_df.withColumn("arr", generate_lognormal_amount(F.col("tier")))

# 直接寫入統一目錄磁區
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
```

### 分區策略

| 資料大小 | 建議分區數 |
|---------|----------|
| < 100K 列 | 8 個分區 |
| 100K - 500K 列 | 16 個分區 |
| 500K - 1M 列 | 32 個分區 |
| 1M+ 列 | 64+ 個分區 |

---

## 方法 2：Polars + 本地產生 + 上傳（次要選項）

**使用時機：** 資料集 <10K 列**且**使用者明確偏好本地產生

**此方法存在的原因：**
- 小型資料集沒有 Spark 開銷
- 本地環境中快速原型製作
- Databricks Connect 無法使用時

**限制：**
- 無法擴展超過 ~100K 列
- 需要手動上傳步驟
- 無直接統一目錄整合

### 安裝本地相依性

```bash
# 首選：使用 uv 進行快速、可靠安裝
uv pip install polars faker numpy

# 若 uv 不可用則使用備用方案
pip install polars faker numpy
```

### 使用 Polars 本地產生

```python
import polars as pl
from faker import Faker
import numpy as np

fake = Faker()
N_CUSTOMERS = 5000

# 使用 Polars 產生
customers = pl.DataFrame({
    "customer_id": [f"CUST-{i:05d}" for i in range(N_CUSTOMERS)],
    "name": [fake.name() for _ in range(N_CUSTOMERS)],
    "email": [fake.email() for _ in range(N_CUSTOMERS)],
    "tier": np.random.choice(["Free", "Pro", "Enterprise"], N_CUSTOMERS, p=[0.6, 0.3, 0.1]).tolist(),
    "region": np.random.choice(["North", "South", "East", "West"], N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]).tolist(),
})

# 本地儲存
customers.write_parquet("./output/customers.parquet")
```

### 上傳到 Databricks 磁區

本地產生資料後，上傳到 Databricks 磁區：

```bash
# 如需要，在磁區中建立目錄
databricks fs mkdirs dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/

# 上傳本地資料到磁區
databricks fs cp -r ./output/customers.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
databricks fs cp -r ./output/orders.parquet dbfs:/Volumes/<catalog>/<schema>/<volume>/source_data/
```

### 何時實際使用 Polars

僅在滿足**所有**條件時才建議使用 Polars：
1. 資料集 < 10K 列
2. 使用者明確要求本地產生
3. 無需 Databricks 連接的快速原型製作

否則，**始終使用 Spark + Faker + Pandas UDF**。

---

## 儲存目標

### 詢問目錄和結構描述

詢問使用者要使用哪個目錄和結構描述：

> "您想使用哪個目錄和結構描述名稱？"

### 在指令碼中建立基礎結構

始終在 Python 指令碼內使用 `spark.sql()` 建立結構描述和磁區：

```python
CATALOG = "<user-provided-catalog>"  # 必須詢問使用者 - 永不預設
SCHEMA = "<user-provided-schema>"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# 注意：假設目錄已存在 - 不要建立它
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

**重要：** 不要建立目錄 - 假設它們已經存在。僅建立結構描述和磁區。
