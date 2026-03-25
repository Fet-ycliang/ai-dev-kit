# UniForm 與相容性模式

UniForm 與相容性模式可讓外部引擎將 Delta 資料表當作 Iceberg 讀取 —— 無須轉換成原生 Iceberg 資料表。資料仍以 Delta 寫入，但系統會自動產生 Iceberg metadata，讓外部工具（Snowflake、PyIceberg、Spark、Trino）可透過 UC IRC 端點讀取。

---

## 外部 Iceberg 讀取（先前稱為 UniForm）（GA）

**需求**：Unity Catalog、DBR 14.3+、已啟用 column mapping、已停用 deletion vectors、Delta 資料表必須具備 minReaderVersion >= 2 與 minWriterVersion >= 7，且同時支援 managed 與 external tables。

UniForm 會為一般 Delta 資料表自動產生 Iceberg metadata。資料表在內部仍維持 Delta，但對外可被當作 Iceberg 讀取。

### 在新資料表上啟用 UniForm

```sql
CREATE TABLE my_catalog.my_schema.customers (
  customer_id BIGINT,
  name STRING,
  region STRING,
  updated_at TIMESTAMP
)
TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### 在現有資料表上啟用 UniForm

```sql
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### 需求與前置條件

UniForm 需要明確設定下列屬性：

| 需求 | 詳細說明 |
|-------------|---------|
| **Unity Catalog** | 資料表必須註冊在 UC 中 |
| **DBR 14.3+** | 最低 runtime 版本 |
| **必須停用 deletion vectors** | 啟用 UniForm 前，請先設定 `delta.enableDeletionVectors = false` |
| **不可有 column mapping 衝突** | 若資料表使用 `id` mode，請先移轉為 `name` mode |

若目前已啟用 deletion vectors：

```sql
-- 先停用 deletion vectors
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES ('delta.enableDeletionVectors' = 'false');

-- 重寫資料以移除既有的 deletion vectors
REORG TABLE my_catalog.my_schema.customers
APPLY (PURGE);

-- 接著啟用 UniForm
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### 非同步 metadata 產生

每次 Delta transaction 之後，Iceberg metadata 都會**以非同步方式**產生。外部引擎看到最新資料之前，會有一段短暫延遲（通常是幾秒，大型 transaction 偶爾可能到幾分鐘）。

### 檢查 UniForm 狀態

> 完整細節請參閱 [檢查 Iceberg metadata 產生狀態](https://docs.databricks.com/aws/en/delta/uniform#check-iceberg-metadata-generation-status)。


### 停用 UniForm

```sql
ALTER TABLE my_catalog.my_schema.customers
UNSET TBLPROPERTIES ('delta.universalFormat.enabledFormats');
```

---

## 相容性模式

**需求**：Unity Catalog、DBR 16.1+、SDP pipeline

相容性模式將 UniForm 延伸到由 Spark Declarative Pipelines（SDP）或 DBSQL 建立的 **串流資料表（STs）** 與 **具體化視圖（MVs）**。一般 UniForm 不適用於 STs/MVs —— 相容性模式是唯一選項。

**運作方式**：啟用相容性模式後，Databricks 會在你指定的 external location（`delta.universalFormat.compatibility.location`）中，為該物件建立一份獨立、唯讀的 **「compatibility version」**。這是一份以 Iceberg 相容格式儲存的完整資料副本 —— 不是指向原始 Delta 資料的指標。完成初始完整複製後，後續的 metadata 與資料產生會採用**增量式**方式（僅同步新資料或變更資料到 external location）。

> **儲存成本考量**：由於相容性模式會將資料另外複製一份到 external location，因此你會依資料表大小承擔額外的雲端儲存成本。對大型資料表啟用相容性模式前，請先將這點納入評估。

### 啟用相容性模式

相容性模式透過 table properties 設定：

**SQL 範例（串流資料表）**：

```sql
CREATE OR REFRESH STREAMING TABLE my_events
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>'
)
AS SELECT * FROM STREAM read_files('/Volumes/catalog/schema/raw/events/');
```

**SQL 範例（具體化視圖）**：

```sql
CREATE OR REFRESH MATERIALIZED VIEW daily_summary
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>'
)
AS SELECT event_date, COUNT(*) AS event_count
FROM my_events
GROUP BY event_date;
```

**Python 範例**：

```python
from pyspark import pipelines as dp

@dp.table(
    name="my_events",
    table_properties={
        "delta.universalFormat.enabledFormats": "compatibility",
        "delta.universalFormat.compatibility.location": "<external-location-url>",
    },
)
def my_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/catalog/schema/raw/events/")
    )
```

### 相容性模式的考量事項

| 考量事項 | 詳細說明 |
|---------------|---------|
| **External location** | `delta.universalFormat.compatibility.location` 必須指向已設定好的 external location，作為 Iceberg metadata 輸出路徑 |
| **僅限 SDP pipeline** | 只適用於在 SDP pipeline 中定義的串流資料表與 MV |
| **初次產生時間** | 大型資料表第一次產生 metadata 可能需要長達 1 小時 |
| **Unity Catalog** | 必要條件 |
| **DBR 16.1+** | SDP pipeline 的最低 runtime 版本 |

### 重新整理機制

相容性模式的 metadata 可手動重新整理，也可透過 `delta.universalFormat.compatibility.targetRefreshInterval` 屬性控制：

```sql
CREATE OR REFRESH STREAMING TABLE my_events
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>',
  'delta.universalFormat.compatibility.targetRefreshInterval' = '0 MINUTES'
)
AS SELECT * FROM STREAM read_files('/Volumes/catalog/schema/raw/events/');
```

| 間隔值 | 行為 |
|----------------|----------|
| `0 MINUTES` | 每次 commit 後都會檢查是否有變更，必要時觸發重新整理 —— 這是串流資料表與 MV 的預設值 |
| `1 HOUR` | 非 SDP 資料表的預設值；最多每小時重新整理一次 |
| 低於 `1 HOUR` 的值（例如 `30 MINUTES`） | 不建議 —— 實際上不會讓重新整理頻率高於每小時一次 |

也可手動觸發 metadata 產生：

```sql
REFRESH TABLE my_catalog.my_schema.my_events;
```

### 未來模式

未來版本預期會為串流資料表與具體化視圖提供更有效率的模式。

---

## 決策表：該選哪一種方式？

| 條件 | 受管 Iceberg | UniForm | 相容性模式 |
|----------|:-:|:-:|:-:|
| **完整 Iceberg 讀寫** | 是 | 唯讀（以 Iceberg） | 唯讀（以 Iceberg） |
| **可搭配 Delta 功能（CDF）** | 否 | 部分支援* | 部分支援*  |
| **串流資料表 / MVs** | 否 | 否 | 是 |
| **外部引擎可透過 IRC 寫入** | 是 | 否 | 否 |
| **既有 Delta 投資** | 需要移轉 | 不需移轉 | 不需移轉 |
| **Predictive Optimization** | 自動啟用 | 自動啟用（Delta） | 自動啟用（Delta） |
| **DBR 需求** | 16.1+ | 14.3+ | 16.1+ |

*由於 Iceberg 沒有 CDF，因此依賴該功能的特性不受支援，例如
串流資料表、具體化視圖、資料分類、向量搜尋、資料剖析。對於 Synced tables to Lakebase，僅支援 snapshot mode。
### 何時該選擇各方案

- **受管 Iceberg**：你希望使用原生 Iceberg 資料表，並同時讓 Databricks 與外部引擎都能完整讀寫。你不需要 Delta 專屬功能（例如 CDF）。
- **UniForm**：你已有現成的 Delta 資料表，希望在不移轉的情況下讓外部引擎能以 Iceberg 讀取，同時保留內部的 Delta 功能。
- **相容性模式**：你有需要讓外部引擎以 Iceberg 讀取的串流資料表或具體化視圖。
