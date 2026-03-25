---
name: databricks-synthetic-data-gen
description: "使用 Spark + Faker 產生逼真的合成資料（強烈建議）。支援無伺服器執行、多種輸出格式（Parquet/JSON/CSV/Delta），可從數千筆擴展至數百萬筆。對於小型資料集（<10K 筆），可選擇在本地產生後上傳至 Volume。當使用者提及 'synthetic data'、'test data'、'generate data'、'demo dataset'、'Faker' 或 'sample data' 時使用。"
---

> Catalog 與 schema **一律由使用者提供**——絕不可預設任何值。若使用者尚未提供，請先詢問。任何寫入 UC 的操作，在寫入資料前都**一定要先建立 schema（若尚不存在）**。

# Databricks 合成資料產生

使用 **Spark + Faker + Pandas UDFs**（強烈建議）為 Databricks 產生逼真、具情境故事性的合成資料。

## 快速參考

| 主題 | 指南 | 使用時機 |
|-------|-------|-------------|
| **設定與執行** | [references/1-setup-and-execution.md](references/1-setup-and-execution.md) | 設定環境、選擇運算資源、安裝相依套件 |
| **產生方式** | [references/2-generation-approaches.md](references/2-generation-approaches.md) | 選擇 Spark UDFs 或本機 Polars、撰寫資料產生程式碼 |
| **資料模式** | [references/3-data-patterns.md](references/3-data-patterns.md) | 建立逼真的分布、參照完整性、時間模式 |
| **領域指引** | [references/4-domain-guidance.md](references/4-domain-guidance.md) | 電商、IoT、金融、支援/CRM 領域模式 |
| **輸出格式** | [references/5-output-formats.md](references/5-output-formats.md) | 選擇輸出格式、儲存到 volumes/tables |
| **疑難排解** | [references/6-troubleshooting.md](references/6-troubleshooting.md) | 修正錯誤、除錯問題 |
| **範例腳本** | [scripts/generate_synthetic_data.py](scripts/generate_synthetic_data.py) | 完整的 Spark + Pandas UDF 範例 |

## 套件管理工具

所有 Python 操作優先使用 `uv`。只有在 `uv` 無法使用時才退回 `pip`。

```bash
# 優先選用
uv pip install "databricks-connect>=16.4,<17.4" faker numpy pandas holidays
uv run python generate_data.py

# 若無法使用 uv，則改用此方式
pip install "databricks-connect>=16.4,<17.4" faker numpy pandas holidays
python generate_data.py
```

## 關鍵規則

1. **強烈建議使用 Spark + Faker + Pandas UDFs** 來產生資料（可擴展、可平行化）
2. **若使用者指定 local**，則在本機使用 Polars 取代 Spark；但若資料列數 > 30,000，請建議改用 Spark。
3. **在產生任何程式碼前，先提出計畫供使用者核准**
4. **詢問 catalog/schema** - 不可預設
5. **除非使用者明確要求 classic cluster，否則使用 serverless compute**
6. **只產生原始資料** - 不要預先彙總欄位（除非使用者要求）
7. **先建立 master tables** - 再產生具有有效 FK 的相關 tables
8. **在 serverless compute 上絕對不要使用 `.cache()` 或 `.persist()`** - 這些操作**不受支援**，並會以 `AnalysisException: serverless compute 不支援 PERSIST TABLE` 失敗。請改為先把 master tables 寫入 Delta，再讀回來進行 FK joins。

## 資料產生規劃流程

**在產生任何程式碼前，你都必須先提出計畫，讓使用者核准。**

### ⚠️ 必做：繼續前先確認 Catalog

**你必須明確詢問使用者要使用哪個 catalog。** 未經確認，不可自行假設或直接繼續。

提供給使用者的提示範例：
> 「這份資料要使用哪個 Unity Catalog？」

提出計畫時，務必把已選定的 catalog 清楚顯示：
```
📍 輸出位置：catalog_name.schema_name
   Volume：/Volumes/catalog_name/schema_name/raw_data/
```

這樣使用者就能快速發現並修正設定（如果有需要）。

### 步驟 1：蒐集需求

詢問使用者以下事項：
- **Catalog/Schema** - 要使用哪個 catalog？
- 是什麼領域/情境？（電商、支援工單、IoT 感測器等）
- 需要幾個 tables？它們之間有什麼關聯？
- 每個 table 的大約列數？
- 偏好的輸出格式？（預設為 Delta table）

### 步驟 2：提出 Table 規格

用清楚的規格呈現，並**把你的假設攤開來說明**。一開始務必先列出輸出位置：

```
📍 輸出位置：{user_catalog}.ecommerce_demo
   Volume：/Volumes/{user_catalog}/ecommerce_demo/raw_data/
```

| 資料表 | 欄位 | 說明 | 資料列數 | 主要假設 |
|-------|---------|-------------|------|-----------------|
| customers | customer_id, name, email, tier, region | 合成客戶輪廓資料 | 5,000 | Tier：Free 60%、Pro 30%、Enterprise 10% |
| orders | order_id, customer_id (FK), amount, status | 客戶購買交易資料 | 15,000 | Enterprise customers 產生的訂單數量是其他客戶的 5 倍 |

在計畫中加入欄位層級的說明（這些會成為 Unity Catalog 中的 column comments）：

| 資料表 | 欄位 | 註解 |
|-------|--------|---------|
| customers | customer_id | 唯一 customer 識別碼（CUST-XXXXX） |
| customers | tier | 客戶 tier：Free、Pro、Enterprise |
| orders | customer_id | 連到 customers.customer_id 的 FK |
| orders | amount | 訂單總金額（USD） |

**我目前的假設：**
- 金額分布：依 tier 採用對數常態分布（Enterprise 約 $1800、Pro 約 $245、Free 約 $55）
- 狀態分布：65% delivered、15% shipped、10% processing、5% pending、5% cancelled

**詢問使用者**：「這樣看起來正確嗎？catalog、tables 或分布有需要調整的地方嗎？」

### 步驟 3：詢問資料特性

- [x] Skew（非均勻分布）- **預設啟用**
- [x] Joins（參照完整性）- **預設啟用**
- [ ] Bad data injection（用於資料品質測試）
- [ ] 多語系文字
- [ ] Incremental mode（append 或 overwrite）

### 產生前檢查清單

- [ ] **Catalog 已確認** - 使用者已明確核准要使用哪個 catalog
- [ ] 計畫中已明顯顯示輸出位置（便於辨識/修改）
- [ ] Table 規格已展示並取得核准
- [ ] 已確認分布相關假設
- [ ] 使用者已確認運算資源偏好（建議 serverless）
- [ ] 已選定資料特性

**在使用者核准整體計畫（包含 catalog）之前，不可進入程式碼產生階段。**

## 快速開始：Spark + Faker + Pandas UDFs

```python
from databricks.connect import DatabricksSession, DatabricksEnv
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType
import pandas as pd
import numpy as np

# 使用 managed dependencies 進行設定（databricks-connect 16.4+）
env = DatabricksEnv().withDependencies("faker", "pandas", "numpy")
spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()

# 定義 Pandas UDFs
@F.pandas_udf(StringType())
def fake_name(ids: pd.Series) -> pd.Series:
    from faker import Faker
    fake = Faker()
    return pd.Series([fake.name() for _ in range(len(ids))])

@F.pandas_udf(DoubleType())
def generate_amount(tiers: pd.Series) -> pd.Series:
    amounts = []
    for tier in tiers:
        if tier == "Enterprise":
            amounts.append(float(np.random.lognormal(7.5, 0.8)))
        elif tier == "Pro":
            amounts.append(float(np.random.lognormal(5.5, 0.7)))
        else:
            amounts.append(float(np.random.lognormal(4.0, 0.6)))
    return pd.Series(amounts)

# 產生 customers
customers_df = (
    spark.range(0, 10000, numPartitions=16)
    .select(
        F.concat(F.lit("CUST-"), F.lpad(F.col("id").cast("string"), 5, "0")).alias("customer_id"),
        fake_name(F.col("id")).alias("name"),
        F.when(F.rand() < 0.6, "Free")
         .when(F.rand() < 0.9, "Pro")
         .otherwise("Enterprise").alias("tier"),
    )
    .withColumn("arr", generate_amount(F.col("tier")))
)

# 儲存到 Unity Catalog
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
customers_df.write.mode("overwrite").parquet(f"/Volumes/{CATALOG}/{SCHEMA}/raw_data/customers")
```

## 常見模式

### 加權 Tier 分布
```python
F.when(F.rand() < 0.6, "Free")
 .when(F.rand() < 0.9, "Pro")
 .otherwise("Enterprise").alias("tier")
```

### 對數常態金額分布（較貼近真實定價）
```python
@F.pandas_udf(DoubleType())
def generate_amount(tiers: pd.Series) -> pd.Series:
    return pd.Series([
        float(np.random.lognormal({"Enterprise": 7.5, "Pro": 5.5, "Free": 4.0}[t], 0.7))
        for t in tiers
    ])
```

### 日期範圍（最近 6 個月）
```python
from datetime import datetime, timedelta
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=180)

F.date_add(F.lit(START_DATE.date()), (F.rand() * 180).cast("int")).alias("order_date")
```

### 建立基礎設施
```python
# 一律寫在 script 中 - 假設 catalog 已存在
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

## 執行模式

| 模式 | 最適合 | 設定方式 |
|------|----------|-------|
| **DB Connect 16.4+ Serverless** | 本機開發、Python 3.12+ | `DatabricksEnv().withDependencies(...)` |
| **Serverless Job** | 正式環境、排程執行 | 使用包含 `environments` 參數的 Job |
| **Classic Cluster** | 僅作為備援 | 使用 Databricks CLI 安裝 libraries。`databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'` |

詳細設定說明請參閱 [references/1-setup-and-execution.md](references/1-setup-and-execution.md)。

## 輸出格式

| 格式 | 使用案例 | 程式碼 |
|--------|----------|------|
| **Parquet**（預設） | SDP pipeline 輸入 | `df.write.parquet(path)` |
| **JSON** | 類似 log 的資料匯入 | `df.write.json(path)` |
| **CSV** | 舊式系統 | `df.write.option("header", "true").csv(path)` |
| **Delta Table** | 直接分析 | `df.write.saveAsTable("catalog.schema.table")` |

詳細選項請參閱 [references/5-output-formats.md](references/5-output-formats.md)。

## 最佳實務摘要

### 執行
- 使用 serverless（立即啟動，無需等待 cluster）
- 詢問 catalog/schema
- 在產生前先提出計畫

### 資料產生
- 所有情況都使用 **Spark + Faker + Pandas UDFs**
- 先建立 master tables，再建立具有有效 FK 的相關 tables
- 使用非線性分布（對數常態、Pareto、指數分布）
- 加入時間模式（平日/週末、假日、季節性）
- 確保列內一致性（具關聯性的屬性）

### 輸出
- 在 script 中建立基礎設施（`CREATE SCHEMA/VOLUME IF NOT EXISTS`）
- **不要**建立 catalogs - 假設它們已存在
- 預設使用 Delta tables
- 為 table 與 column 加上註解，以提高在 Unity Catalog 中的可發現性（請參閱 [references/5-output-formats.md](references/5-output-formats.md)）

## 相關 Skills

- **databricks-unity-catalog** - 管理 catalogs、schemas 與 volumes
- **databricks-bundles** - 用於正式部署的 DABs

## 常見問題

| 問題 | 解法 |
|-------|----------|
| `ModuleNotFoundError: faker` | 請參閱 [references/1-setup-and-execution.md](references/1-setup-and-execution.md) |
| Faker UDF 執行速度慢 | 使用 `pandas_udf` 進行批次處理 |
| 記憶體不足 | 增加 `spark.range()` 中的 `numPartitions` |
| 參照完整性錯誤 | 先將 master table 寫入 Delta，再讀回進行 FK joins |
| `serverless 不支援 PERSIST TABLE` | **絕對不要在 serverless 上使用 `.cache()` 或 `.persist()`** - 先寫入 Delta table，再讀回使用 |
| 混淆 `F.window` 與 `Window` | 針對 `row_number()`、`rank()` 等情境，請使用 `from pyspark.sql.window import Window`。`F.window` 僅適用於 streaming。 |

完整的疑難排解指南請參閱 [references/6-troubleshooting.md](references/6-troubleshooting.md)。
