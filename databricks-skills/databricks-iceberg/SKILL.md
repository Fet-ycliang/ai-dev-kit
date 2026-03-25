---
name: databricks-iceberg
description: "Databricks 上的 Apache Iceberg 資料表——受管 Iceberg 資料表、外部 Iceberg 讀取（先前稱為 Uniform）、相容性模式、Iceberg REST Catalog（IRC）、Iceberg v3、Snowflake 互通性、PyIceberg、OSS Spark、外部引擎存取與憑證授予。當需要建立 Iceberg 資料表、在 Delta 資料表上啟用外部 Iceberg 讀取（uniform）（包括透過相容性模式支援的串流資料表與具體化視圖）、設定外部引擎透過 Unity Catalog IRC 讀取 Databricks 資料表、與 Snowflake catalog 整合以讀取 Foreign Iceberg 資料表時使用"
---

# Databricks 上的 Apache Iceberg

Databricks 提供多種使用 Apache Iceberg 的方式：原生受管 Iceberg 資料表、用於 Delta 與 Iceberg 互通的 UniForm，以及供外部引擎存取的 Iceberg REST Catalog（IRC）。

---

## 重要規則（請一律遵守）

- **MUST** 使用 Unity Catalog —— 所有 Iceberg 功能都需要啟用 UC 的工作區
- **MUST NOT** 在 Databricks Runtime 中安裝 Iceberg library（DBR 已內建 Iceberg 支援；額外加入 library 會造成版本衝突）
- **MUST NOT** 設定 `write.metadata.path` 或 `write.metadata.previous-versions-max` —— Databricks 會自動管理 metadata 位置；覆寫會導致損毀
- **MUST** 在撰寫程式碼前先判斷哪一種 Iceberg 模式符合使用情境 —— 請參閱下方的 [適用場景](#適用場景) 章節
- **MUST** 了解 `PARTITIONED BY` 與 `CLUSTER BY` 都會為外部引擎產生相同的 Iceberg metadata —— UC 會維護一份 Iceberg partition spec，其中的 partition fields 對應到 clustering keys，因此透過 IRC 讀取的外部引擎會看到一個已分割的 Iceberg 資料表（不是 Hive-style，而是正統的 Iceberg partition fields），並可依這些欄位進行 pruning；在內部，UC 會將這些欄位作為 liquid clustering keys 使用；兩種語法唯一的差異是：(1) `PARTITIONED BY` 是標準 Iceberg DDL（任何引擎都能建立該資料表），而 `CLUSTER BY` 是僅限 DBR 的 DDL；(2) `PARTITIONED BY` 會**自動處理** DV/row-tracking 屬性，而 `CLUSTER BY` 在 v2 上需要手動設定 TBLPROPERTIES
- **MUST NOT** 在受管 Iceberg 資料表上搭配 `PARTITIONED BY` 使用 expression-based partition transforms（`bucket()`, `years()`, `months()`, `days()`, `hours()`）—— 僅支援純欄位參照；expression transforms 會造成錯誤
- **MUST** 在 Iceberg v2 資料表上使用 `CLUSTER BY` 時停用 deletion vectors 與 row tracking —— 請在 TBLPROPERTIES 中設定 `'delta.enableDeletionVectors' = false` 與 `'delta.enableRowTracking' = false`（Iceberg v3 會自動處理；`PARTITIONED BY` 在 v2 與 v3 都會自動處理）

---

## 核心概念

| 概念 | 摘要 |
|---------|---------|
| **受管 Iceberg 資料表** | 使用 `USING ICEBERG` 建立的原生 Iceberg 資料表 —— 在 Databricks 與外部 Iceberg 引擎中都可完整讀寫 |
| **外部 Iceberg 讀取（Uniform）** | 會自動產生 Iceberg metadata 的 Delta 資料表 —— 對外以 Iceberg 讀取，對內以 Delta 寫入 |
| **相容性模式** | 用於 SDP pipeline 中串流資料表與具體化視圖的 UniForm 變體 |
| **Iceberg REST Catalog（IRC）** | Unity Catalog 內建、實作 Iceberg REST Catalog spec 的 REST 端點 —— 讓外部引擎（Spark、PyIceberg、Snowflake）可存取由 UC 管理的 Iceberg 資料 |
| **Iceberg v3** | 新一代格式（Beta，DBR 17.3+）—— 支援 deletion vectors、VARIANT 型別與 row lineage |

---

## 快速入門

### 建立受管 Iceberg 資料表

```sql
-- 不使用 clustering
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
AS SELECT * FROM raw_events;

-- PARTITIONED BY（建議用於跨平台）：標準 Iceberg 語法，可在 EMR/OSS Spark/Trino/Flink 使用
-- 會自動停用 DVs 和 row tracking —— 在 v2 與 v3 都不需要 TBLPROPERTIES
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
PARTITIONED BY (event_date)
AS SELECT * FROM raw_events;

-- Iceberg v2 上的 CLUSTER BY（僅限 DBR 語法）：必須手動停用 DVs 和 row tracking
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (event_date)
AS SELECT * FROM raw_events;

-- Iceberg v3 上的 CLUSTER BY（僅限 DBR 語法）：不需要 TBLPROPERTIES
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date)
AS SELECT * FROM raw_events;
```

### 在現有 Delta 資料表上啟用 UniForm

```sql
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

---

## 讀寫能力矩陣

| 資料表類型 | Databricks 讀取 | Databricks 寫入 | 外部 IRC 讀取 | 外部 IRC 寫入 |
|------------|:-:|:-:|:-:|:-:|
| 受管 Iceberg（`USING ICEBERG`） | 是 | 是 | 是 | 是 |
| Delta + UniForm | 是（以 Delta） | 是（以 Delta） | 是（以 Iceberg） | 否 |
| Delta + 相容性模式 | 是（以 Delta） | 是 | 是（以 Iceberg） | 否 |

---

## 參考檔案

| 檔案 | 摘要 | 關鍵字 |
|------|---------|----------|
| [1-managed-iceberg-tables.md](1-managed-iceberg-tables.md) | 建立與管理原生 Iceberg 資料表 —— DDL、DML、Liquid Clustering、預測性最佳化、Iceberg v3、限制事項 | CREATE TABLE USING ICEBERG, CTAS, MERGE, time travel, deletion vectors, VARIANT |
| [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md) | 讓 Delta 資料表可被當作 Iceberg 讀取 —— 一般資料表使用 UniForm，串流資料表與具體化視圖使用相容性模式 | UniForm, universalFormat, Compatibility Mode, streaming tables, materialized views, SDP |
| [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) | 透過 IRC 端點將 Databricks 資料表提供給外部引擎 —— auth、憑證授予、IP 存取清單 | IRC, REST Catalog, credential vending, EXTERNAL USE SCHEMA, PAT, OAuth |
| [4-snowflake-interop.md](4-snowflake-interop.md) | Snowflake 與 Databricks 的雙向整合 —— 目錄整合、Foreign Catalog、vended credentials | Snowflake, catalog integration, external volume, vended credentials, REFRESH_INTERVAL_SECONDS |
| [5-external-engine-interop.md](5-external-engine-interop.md) | 透過 IRC 連接 PyIceberg、OSS Spark、AWS EMR、Apache Flink 與 Kafka Connect | PyIceberg, OSS Spark, EMR, Flink, Kafka Connect, pyiceberg.yaml |

---

## 適用場景

- **建立新的 Iceberg 資料表** → [1-managed-iceberg-tables.md](1-managed-iceberg-tables.md)
- **讓現有 Delta 資料表可被當作 Iceberg 讀取** → [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md)
- **讓串流資料表或 MV 可被當作 Iceberg 讀取** → [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md)（相容性模式章節）
- **在 Managed Iceberg、UniForm 與相容性模式之間做選擇** → [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md) 中的決策表
- **透過 REST API 將 Databricks 資料表提供給外部引擎** → [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md)
- **將 Databricks 與 Snowflake 整合（任一方向）** → [4-snowflake-interop.md](4-snowflake-interop.md)
- **連接 PyIceberg、OSS Spark、Flink、EMR 或 Kafka** → [5-external-engine-interop.md](5-external-engine-interop.md)

---

## 常見問題

| 問題 | 解法 |
|-------|----------|
| **不支援 CDF（Change Data Feed）** | 受管 Iceberg 資料表不支援 CDF。若需要 CDF，請使用 Delta + UniForm。 |
| **UniForm 非同步延遲** | Iceberg metadata 產生是非同步的。寫入之後，外部引擎看到最新資料前可能會有短暫延遲。可用 `DESCRIBE EXTENDED table_name` 檢查狀態。 |
| **壓縮編碼變更** | 受管 Iceberg 資料表預設使用 `zstd` 壓縮（不是 `snappy`）。較舊且不支援 zstd 的 Iceberg reader 會失敗。請確認 reader 相容性，或將 `write.parquet.compression-codec` 設為 `snappy`。 |
| **Snowflake 的 1000-commit 限制** | Snowflake 的 Iceberg catalog integration 只能看到最近 1000 個 Iceberg commits。高頻率寫入者必須壓縮 metadata，否則 Snowflake 會失去對較舊資料的可見性。 |
| **UniForm 搭配 deletion vectors** | UniForm 要求停用 deletion vectors（`delta.enableDeletionVectors = false`）。若資料表已啟用 deletion vectors，請先停用再啟用 UniForm。 |
| **Iceberg 不支援 shallow clone** | Iceberg 資料表不支援 `SHALLOW CLONE`。請改用 `DEEP CLONE` 或 `CREATE TABLE ... AS SELECT`。 |
| **外部引擎版本不相容** | 請確保外部引擎使用的 Iceberg library 版本與資料表的 format version 相容。Iceberg v3 資料表需要 Iceberg library 1.9.0+。 |

---

## 相關技能

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** —— 目錄/schema 管理、治理與 system tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** —— SDP pipelines（搭配相容性模式的串流資料表與具體化視圖）
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** —— Databricks 作業使用的 Python SDK 與 REST API
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** —— SQL warehouse 功能與查詢模式

---

## 資源連結

- **[Iceberg 總覽](https://docs.databricks.com/aws/en/iceberg/)** —— Databricks 上 Iceberg 的主要入口
- **[UniForm](https://docs.databricks.com/aws/en/delta/uniform.html)** —— Delta Universal Format
- **[Iceberg REST Catalog](https://docs.databricks.com/aws/en/external-access/iceberg)** —— IRC 端點與外部引擎存取
- **[相容性模式](https://docs.databricks.com/aws/en/external-access/compatibility-mode)** —— 用於串流資料表與 MV 的 UniForm
- **[Iceberg v3](https://docs.databricks.com/aws/en/iceberg/iceberg-v3)** —— 新一代格式功能（Beta）
- **[外部資料表](https://docs.databricks.com/aws/en/query-data/foreign-tables.html)** —— 讀取外部 catalog 資料
