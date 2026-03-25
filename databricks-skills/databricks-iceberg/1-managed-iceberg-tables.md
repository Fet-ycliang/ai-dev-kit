# 受管 Iceberg 資料表

受管 Iceberg 資料表是建立並儲存在 Unity Catalog 中的原生 Apache Iceberg 資料表。它們支援在 Databricks 中完整讀寫，並可透過 UC Iceberg REST Catalog（IRC）端點供外部引擎存取。

**需求**：Unity Catalog、DBR 16.4 LTS+（Managed Iceberg v2）、DBR 17.3+（Managed Iceberg v3 Beta）

---

## 建立資料表

### 基本 DDL

```sql
-- 建立空的 Iceberg 資料表（不使用 clustering）
CREATE TABLE my_catalog.my_schema.events (
  event_id BIGINT,
  event_type STRING,
  event_date DATE,
  payload STRING
)
USING ICEBERG;
```

### Create Table As Select（CTAS）

```sql
-- 從現有資料建立（不使用 clustering）
CREATE TABLE my_catalog.my_schema.events_archive
USING ICEBERG
AS SELECT * FROM my_catalog.my_schema.events
WHERE event_date < '2025-01-01';
```

### Liquid Clustering

受管 Iceberg 資料表使用 **Liquid Clustering** 進行資料版面配置最佳化。`PARTITIONED BY` 與 `CLUSTER BY` 都會產生 Liquid Clustered 資料表 —— **不會建立傳統的 Hive-style partitions**。Unity Catalog 會將 partition 子句解讀為 clustering keys。

| 語法 | DDL（建立資料表） | 透過 IRC 讀取 | 外部引擎可見的 Iceberg partition fields | DV/row-tracking 處理方式 |
|--------|--------------------|---------------|------------------------------------------------------|--------------------------|
| `PARTITIONED BY (col)` | DBR + EMR、OSS Spark、Trino、Flink | 是 | 是 —— UC 會公開對應 clustering keys 的 Iceberg partition fields；外部引擎可進行 pruning | **自動處理** |
| `CLUSTER BY (col)` | 僅限 DBR | 是 | 是 —— 相同；不論使用哪種 DDL，UC 都會根據 clustering keys 維護 Iceberg partition spec | v2 需手動，v3 自動 |

> **兩種語法都會為外部引擎產生相同的 Iceberg metadata。** UC 會維護一份 Iceberg partition spec（partition fields 對應到 clustering keys），供外部引擎透過 IRC 讀取。這是 Iceberg 風格的 partitioning —— 不是舊式 Hive-style 目錄分割。外部引擎會看到一個已分割的 Iceberg 資料表，並受益於 partition pruning。在內部，UC 會將這些 partition fields 作為 liquid clustering keys 使用。

> **`PARTITIONED BY` 的限制**：僅支援純欄位參照。不支援 expression transforms（`bucket()`, `years()`, `months()`, `days()`, `hours()`），否則會報錯。

> **Iceberg v2 上的 `CLUSTER BY`**：必須明確設定 `'delta.enableDeletionVectors' = false` 與 `'delta.enableRowTracking' = false`，否則會出現：`[MANAGED_ICEBERG_ATTEMPTED_TO_ENABLE_CLUSTERING_WITHOUT_DISABLING_DVS_OR_ROW_TRACKING]`

**`PARTITIONED BY` —— 建議用於跨平台**（會自動處理所有必要屬性）：

```sql
-- 單欄位（v2 或 v3 —— 不需要 TBLPROPERTIES）
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
PARTITIONED BY (order_date);

-- 多欄位
CREATE TABLE orders (
  order_id BIGINT,
  region STRING,
  order_date DATE
)
USING ICEBERG
PARTITIONED BY (region, order_date);
```

**Iceberg v2 上的 `CLUSTER BY`**（僅限 DBR；必須手動停用 DVs 和 row tracking）：

```sql
-- 單欄位 clustering（v2）
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (order_date);
```

**Iceberg v3 上的 `CLUSTER BY`**（不需要額外的 TBLPROPERTIES）：

```sql
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (order_date);
```

---

## DML 操作

受管 Iceberg 資料表支援所有標準 DML 操作：

```sql
-- INSERT
INSERT INTO my_catalog.my_schema.events
VALUES (1, 'click', '2025-06-01', '{"page": "home"}');

-- 從查詢結果 INSERT
INSERT INTO my_catalog.my_schema.events
SELECT * FROM staging_events WHERE event_date = current_date();

-- UPDATE
UPDATE my_catalog.my_schema.events
SET event_type = 'page_view'
WHERE event_id = 1;

-- DELETE
DELETE FROM my_catalog.my_schema.events
WHERE event_date < '2024-01-01';

-- MERGE（upsert）
MERGE INTO my_catalog.my_schema.events AS target
USING staging_events AS source
ON target.event_id = source.event_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

---

## 時間旅行（查詢）

可透過 timestamp 或 snapshot ID 查詢歷史快照：

```sql
-- 依 timestamp 查詢
SELECT * FROM my_catalog.my_schema.events TIMESTAMP AS OF '2025-06-01T00:00:00Z';

-- 依 snapshot ID 查詢
SELECT * FROM my_catalog.my_schema.events VERSION AS OF 1234567890;

-- 僅限外部引擎：檢視 snapshot 歷程
SELECT * FROM my_catalog.my_schema.events.snapshots;
```

---

## 預測性最佳化

對受管 Iceberg 資料表而言，**建議**啟用 Predictive Optimization —— 它不會自動啟用，必須明確開啟。啟用後會自動執行：

- **Compaction** —— 合併小檔案
- **Vacuum** —— 移除過期 snapshots 與孤兒檔案
- **統計資料收集** —— 讓欄位統計維持最新，以利查詢最佳化

可在 catalog 或 schema 層級啟用。若有需要，仍可手動執行相關作業：

```sql
-- 手動執行 Compaction
OPTIMIZE my_catalog.my_schema.events;

-- 手動執行 VACUUM
VACUUM my_catalog.my_schema.events;

-- 手動收集統計資料
ANALYZE TABLE my_catalog.my_schema.events COMPUTE STATISTICS FOR ALL COLUMNS;
```

---

## Iceberg v3（Beta）

**需求**：DBR 17.3+

Iceberg v3 在 v2 之上引入了新的能力：

| 功能 | 說明 |
|---------|-------------|
| **Deletion Vectors** | 無需重寫資料檔即可執行列層級刪除 —— 可更快速地進行 UPDATE/DELETE/MERGE |
| **VARIANT 型別** | 半結構化資料欄位（類似 Delta 的 VARIANT） |
| **Row Lineage** | 追蹤轉換過程中的列層級來源關係 |

### 建立 Iceberg v3 資料表

```sql
CREATE TABLE my_catalog.my_schema.events_v3 (
  event_id BIGINT,
  event_date DATE,
  data VARIANT
)
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date);
```

### 重要注意事項

- **無法降版**：資料表一旦升級到 v3，就無法再降回 v2
- **外部引擎相容性**：外部引擎必須使用 Iceberg library 1.9.0+ 才能讀取 v3 資料表
- **Deletion vectors**：v3 資料表預設啟用。外部 reader 必須支援 deletion vectors
- **Beta 狀態**：Iceberg v3 目前仍為 Beta，尚不建議用於正式工作負載

### 將現有資料表升級到 v3

```sql
ALTER TABLE my_catalog.my_schema.events
SET TBLPROPERTIES ('format-version' = '3');
```

> **警告**：此操作無法還原。請先使用非正式環境資料測試。

---

## 限制事項

| 限制事項 | 詳細說明 |
|------------|---------|
| **不支援 Vector Search** | Iceberg 資料表不支援 Vector Search 索引 |
| **不支援 CDF（Change Data Feed）** | CDF 是 Delta 專屬功能；若需要 CDF，請使用 Delta + UniForm |
| **僅支援 Parquet** | Databricks 上的 Iceberg 資料表以 Parquet 作為底層檔案格式 |
| **不支援 shallow clone** | 不支援 `SHALLOW CLONE`；請使用 `DEEP CLONE` 或 CTAS |
| **`PARTITIONED BY` 會對應到 Liquid Clustering** | 支援 `PARTITIONED BY`，且建議用於跨平台情境 —— 它會對應到 Liquid Clustering，而不是傳統分割。僅支援純欄位參照；不支援 expression transforms（`bucket()`, `years()`, 等）。 |
| **沒有 Structured Streaming sink** | 無法使用 `writeStream` 直接寫入 Iceberg 資料表；請在 batch 或 SDP 中使用 `INSERT INTO` 或 `MERGE` |
| **壓縮** | 預設壓縮為 `zstd`；較舊的 reader 可能需要 `snappy` —— 若有需要，請設定 `write.parquet.compression-codec` |
| **不要設定 metadata path** | 絕對不要設定 `write.metadata.path` 或 `write.metadata.previous-versions-max` |
| **不要安裝 Iceberg library** | DBR 已內建支援；安裝 Iceberg JAR 會造成衝突 |

---

## 從其他格式轉換

### 從 Delta 轉成 Iceberg（透過 DEEP CLONE）

```sql
CREATE TABLE my_catalog.my_schema.events_iceberg
USING ICEBERG
DEEP CLONE my_catalog.my_schema.events_delta;
```

### 從 Foreign Iceberg 轉成受管 Iceberg

```sql
-- 搭配 Liquid Clustering（v2 —— 必須停用 DVs 和 row tracking）
CREATE TABLE my_catalog.my_schema.events_managed
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (event_date)
AS SELECT * FROM foreign_catalog.foreign_schema.events;

-- 搭配 Liquid Clustering（v3 —— 不需要額外的 TBLPROPERTIES）
CREATE TABLE my_catalog.my_schema.events_managed
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date)
AS SELECT * FROM foreign_catalog.foreign_schema.events;
```


