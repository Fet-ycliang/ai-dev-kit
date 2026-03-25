# 資料建模與 DBSQL 最佳實務

Databricks Lakehouse Platform 上資料建模模式、DBSQL 效能最佳化與操作最佳實務的完整參考。

---

## 資料建模最佳實務

### Lakehouse 中的 Star Schema 與去正規化

Databricks Lakehouse 完整支援維度建模。Star Schema 很適合映射到 Delta table，且相較於完全去正規化的方法，通常能提供更好的效能。

**Star Schema（Dimensional Modeling）：**
- 中央 fact table 連結多個去正規化的 dimension table
- 針對複雜分析與多維度彙總進行最佳化
- 提供直覺的業務流程對應，並能良好支援 SCD
- 最多可支援約 10 個篩選維度（5 個 table × 每個 2 個 clustering key）
- 清楚的職責分離有助於細緻化治理

**One Big Table (OBT)：**
- 以單一寬表預先連接所有屬性
- 省去 join，治理更簡單（只需管理一個 table）
- Liquid Clustering 僅限 1-4 個 key，因此有效篩選通常只限 1-3 個維度
- 隨著資料成長，全表掃描會成為瓶頸
- 缺乏結構化的業務流程對應
- 會讓細緻化存取控制與資料品質檢查變得更複雜

**關鍵發現：**在基準測試中，儘管維度模型需要 join，但因為需要掃描的檔案較少，仍優於 OBT（2.6s 對 3.5s）。不過，在套用 Liquid Clustering 後，OBT 可獲得超過 3 倍的改善（降至 1.13s）。兩種方法在首次執行後搭配自動快取，都能達到 500ms 以下。

**建議做法：**使用混合式 medallion architecture：
- Silver layer：使用 OBT 或 Data Vault 進行快速整合與清理
- Gold layer：以 Star Schema 維度模型作為經整理、可直接支援業務的 BI 與報表呈現層

### 何時該正規化或去正規化

| 使用情境 | 作法 |
|---|---|
| 用於 BI 報表的 Gold layer | Star Schema（dimension 去正規化、fact 正規化） |
| Silver layer 資料整合 | 正規化或 Data Vault |
| 單一用途的 IoT/日誌分析 | OBT（依 1-3 個維度篩選） |
| 多維度業務分析 | Star Schema |
| 快速演進的 schema | Silver 用 OBT，Gold 用 Star Schema |
| 高基數篩選（5+ 維度） | 每個 table 使用各自的 Liquid Clustering key 之 Star Schema |

**經驗法則：**dimension table 應高度去正規化（將多對一關係攤平到單一 dimension table 內）。fact table 則應在業務事件的 grain 上維持正規化。

### Databricks 中的 Kimball 風格建模

Kimball 維度建模是 Lakehouse 中 Gold layer 的建議作法：

1. **識別業務流程**（銷售、訂單、出貨）
2. **定義 grain**（每筆交易一列、每日一列等）
3. **選擇 dimension**（誰、什麼、哪裡、何時、為何、如何）
4. **識別 fact**（在既定 grain 上可量測的數值）

**Databricks 特定的實作細節：**
- 使用 Unity Catalog 組織維度模型（catalog.schema.table）
- 在 dimension surrogate key 上定義 PRIMARY KEY constraint
- 在 fact table 的 dimension key 上定義 FOREIGN KEY constraint，以協助 query 最佳化
- 在所有 table 與欄位上加入 COMMENT 以提升可發現性
- 套用 TAGS 進行治理（例如 PII 標記），以啟用下游 AI/BI 能力
- 在 dimension key 上使用 `ANALYZE TABLE ... COMPUTE STATISTICS FOR COLUMNS` 以支援 Adaptive Query Execution

**核心原則：**「資料前期建模做得越好，後續就越能直接輕鬆利用 AI。」良好的 schema 設計能啟用下游 AI/BI 能力。

### Fact Table 模式

**設計規則：**
- 在最細粒度的交易層級儲存可量化的數值指標
- 財務資料請使用 DECIMAL，不要使用浮點數
- 包含參照 dimension table 的 foreign key
- 包含 degenerate dimension（例如訂單編號等來源系統識別碼）
- 交易型 fact table 通常不會更新或版本化
- 依經常 join 的 dimension 之 foreign key 對 fact table 進行 cluster

**Fact table 類型：**
- **交易型 fact：**每個事件一列（最常見）
- **定期快照型 fact：**每個實體於每個時間週期一列
- **累積快照型 fact：**每個實體生命週期一列，隨里程碑達成而更新

**Fact table 的 Liquid Clustering 策略：**
```sql
CREATE TABLE gold.sales.fact_orders (
  order_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_key BIGINT NOT NULL,
  product_key BIGINT NOT NULL,
  date_key INT NOT NULL,
  order_amount DECIMAL(18,2),
  quantity INT,
  CONSTRAINT fk_customer FOREIGN KEY (customer_key) REFERENCES gold.sales.dim_customer(customer_key),
  CONSTRAINT fk_product FOREIGN KEY (product_key) REFERENCES gold.sales.dim_product(product_key)
)
CLUSTER BY (date_key, customer_key);
```

### Dimension Table 模式

**設計規則：**
- surrogate key 請使用 `GENERATED ALWAYS AS IDENTITY` 或 hash 值
- 為了 join 效能，優先使用整數 surrogate key 而非字串
- 高度去正規化：將多對一關係攤平到單一 dimension table 中
- 支援複合型別：MAP 用於擴充性，STRUCT 用於巢狀屬性，ARRAY 用於多值屬性
- 避免將 ARRAY/MAP 欄位作為篩選條件（這些型別缺乏欄位層級統計資訊，無法進行 data skipping）
- 依 primary key 加上常見篩選欄位對 dimension table 進行 cluster

**Dimension table 範例：**
```sql
CREATE TABLE gold.sales.dim_customer (
  customer_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_id STRING NOT NULL COMMENT '來自來源系統的自然鍵',
  full_name STRING,
  email STRING,
  city STRING,
  state STRING,
  country STRING,
  segment STRING,
  effective_start_date TIMESTAMP,
  effective_end_date TIMESTAMP,
  is_current BOOLEAN,
  CONSTRAINT pk_customer PRIMARY KEY (customer_key)
)
CLUSTER BY (customer_key, segment)
COMMENT '含 SCD Type 2 歷史追蹤的客戶維度';
```
### Slowly Changing Dimensions (SCD) 模式

**SCD Type 1（覆寫）：**
- 直接原地更新，不追蹤歷史
- 使用 MERGE INTO 搭配 matched UPDATE
- 適合修正資料，或不需要保留歷史的屬性

**SCD Type 2（歷史追蹤）：**
- 使用 surrogate key 與 metadata 欄位對記錄做版本化
- 包含 `effective_start_date`、`effective_end_date` 與 `is_current` 欄位
- 在 DBSQL 中使用 MERGE INTO 實作 SCD Type 2 邏輯

**以 MERGE 實作 SCD Type 2：**
```sql
MERGE INTO gold.sales.dim_customer AS target
USING (
  SELECT * FROM silver.crm.customers_changes
) AS source
ON target.customer_id = source.customer_id AND target.is_current = TRUE
WHEN MATCHED AND (
  target.full_name != source.full_name OR
  target.city != source.city
) THEN UPDATE SET
  effective_end_date = current_timestamp(),
  is_current = FALSE
WHEN NOT MATCHED THEN INSERT (
  customer_id, full_name, email, city, state, country, segment,
  effective_start_date, effective_end_date, is_current
) VALUES (
  source.customer_id, source.full_name, source.email,
  source.city, source.state, source.country, source.segment,
  current_timestamp(), NULL, TRUE
);
-- 然後在第二個步驟中為已變更的記錄插入新版本
```

**Delta Lake Time Travel** 可在設定的 log 保留期間內提供歷史資料存取，作為 SCD 的輔助功能。

### Partitioning 策略

**Databricks 建議所有新 table 都優先使用 Liquid Clustering，而非傳統 partitioning。**

傳統 partitioning 的經驗法則（在確實需要時）：
- 將 partition 數量控制在 10,000 以下（理想情況是 distinct 值少於 5,000）
- 每個 partition 至少應包含 1 GB 資料
- 以低基數且常出現在 WHERE 子句中的欄位進行 partitioning（例如日期、區域）
- 最適合高度選擇性的單一 partition query（例如篩選某一天）

**傳統 partitioning 仍可能適用的情況：**
- 非常大的 table（數百 TB），且具有明確且穩定的 partition key
- query 一直以同一個低基數欄位作為篩選條件
- 資料生命週期管理需要 partition 層級的操作

### Liquid Clustering 與傳統 Partitioning

**Liquid Clustering 是所有新 Delta table 的預設建議作法**，包含 streaming table 與 materialized view。它可取代 partitioning 與 Z-ORDER。

| 面向 | Liquid Clustering | Partitioning + Z-ORDER |
|---|---|---|
| 欄位彈性 | 可隨時變更 clustering key | partition 欄位建立後即固定 |
| 維護 | 搭配 predictive optimization 可增量且自動維護 | 需要手動執行 OPTIMIZE + Z-ORDER |
| 篩選維度 | 最適合 1-4 個 clustering key | 一個 partition key + Z-ORDER 欄位 |
| 寫入額外成本 | 低（只重組未 cluster 的 ZCube） | Z-ORDER 會重組整個 table/partition |
| 最適合 | 大多數工作負載、存取模式持續變化的情境 | 非常大的 table，且篩選欄位穩定且低基數 |
| 效能 | 對變動型 query 可提升 30-60% 查詢速度 | 較適合單一 partition 查找 query |

**Liquid Clustering key 選擇最佳實務：**
- 選擇最常出現在 query 篩選與 join 中的欄位
- 限制在 1-4 個 key（對於 10 TB 以下的較小 table，key 越少通常越好）
- 對 fact table：依最常被篩選的 foreign key 進行 cluster
- 對 dimension table：依 primary key + 常用篩選欄位進行 cluster
- key 太多會稀釋 data skipping 的效益；對於 10 TB 以下的 table，2 個 key 往往比 4 個更好

**重要：**同一個 table 上，Liquid Clustering 與 partitioning 或 Z-ORDER 不相容。

### Z-ORDER 注意事項

Z-ORDER 是較舊的作法，現已被 Liquid Clustering 取代：

- Z-ORDER 在最佳化期間會重組整個 table/partition（寫入成本較高）
- 不會追蹤 ZCube ID，因此每次 OPTIMIZE 都會重新排序所有資料
- 較適合以讀取為主，且可接受寫入額外成本的工作負載
- 對新 table，一律優先使用 Liquid Clustering

**遷移路徑：**當將現有採用 partitioning + Z-ORDER 的 table 遷移到 Liquid Clustering 時：
1. 移除 partition 規格
2. 以選定的 key 啟用 Liquid Clustering
3. 執行 OPTIMIZE 以增量方式對資料進行 cluster
4. 之後交由 predictive optimization 持續維護資料布局

---

## DBSQL 效能

### Query 最佳化技巧

**引擎層級最佳化（DBSQL Serverless 會自動套用）：**
- **Predictive Query Execution (PQE)：**即時監控 task，動態調整 query 執行，以避免 skew、spill 與不必要的工作。與只有在 stage 完成後才會重新規劃的 Adaptive Query Execution (AQE) 不同，PQE 會在資料 skew 或記憶體 spill 等問題發生當下立即偵測並重規劃。
- **Photon Vectorized Shuffle：**讓資料維持緊湊的 columnar 格式，在 CPU cache 內排序，並使用 vectorized 指令，使 shuffle 吞吐量提高 1.5 倍。最適合 CPU-bound 工作負載（大型 join、寬表彙總）。
- **Low Shuffle Merge：**最佳化的 MERGE 實作，可降低多數常見工作負載的 shuffle 額外成本。

**手動最佳化動作：**
- 在 dimension key 與常用篩選欄位上執行 `ANALYZE TABLE ... COMPUTE STATISTICS FOR COLUMNS`，以支援 AQE 與 data skipping
- 設定 `'delta.dataSkippingStatsColumns'` table property，以指定要收集統計資訊的欄位
- 定義 PRIMARY KEY 與 FOREIGN KEY constraint，協助 query optimizer
- 使用 deterministic query（避免在 filter 中使用 `NOW()`、`CURRENT_TIMESTAMP()`），以受益於 query result caching
- 相較於先刪除再建立的模式，優先使用 `CREATE OR REPLACE TABLE`
- 財務計算請使用 `DECIMAL`，不要用 `FLOAT`/`DOUBLE`

**DBSQL 的 SQL 撰寫技巧：**
- 儘早篩選、延後彙總：讓 WHERE 子句盡可能靠近資料來源
- 相較於 SELECT *，優先使用明確的欄位清單
- 為了可讀性可使用 CTE，但要注意 optimizer 可能會將其 inline
- 當已有原生 SQL function 時，避免使用 Python/Scala UDF（UDF 需要在 Python 與 Spark 之間進行 serialization，會大幅拖慢 query）
- 能用 window function 時，就不要使用 self-join
- 善用 QUALIFY 子句，在 window function 之後進行列層級篩選
### Warehouse 規模建議

**Databricks 建議大多數工作負載使用 serverless SQL warehouse。**Serverless 會使用 Intelligent Workload Management (IWM) 自動管理 query 工作負載。

**規模策略：**
- 先使用單一且較大的 warehouse，並讓 serverless 功能管理併發
- 若有需要再往下調整規模，而不是從太小開始再慢慢放大
- 如果 query 發生 spill 到磁碟，請增加 cluster 規模

**擴展設定：**
- 低併發（1-2 個 query）：將 max_clusters 維持在較低值
- 無法預期的尖峰：將 max_num_clusters 設高，並讓 target_utilization 約為 70%
- 對負載變動大或不頻繁的 dashboard：啟用積極的 auto-scaling 與 auto-stopping

**Serverless 優勢：**
- 可在數秒內啟動並擴展
- 比非 serverless warehouse 更早縮減規模
- 只在 query 執行時付費
- 30-60 秒的 cold start 延遲（與不需閒置待機所節省的成本相比，影響非常小）
- 所有 2025 年最佳化（PQE、Photon Vectorized Shuffle）都會自動提供

### 快取策略

**Query Result Cache：**
- DBSQL 會針對每個 cluster 快取所有 query 的結果
- 底層 Delta 資料變更時，快取會失效
- 為了最大化快取命中率，請使用 deterministic query（不要用 `NOW()`、`RAND()` 等）
- OBT 與 Star Schema 在首次執行後，透過自動快取都能達到 500ms 以下

**Delta Cache（Disk Cache）：**
- 會自動以 columnar 格式將遠端資料快取到本機 SSD
- 在 serverless warehouse 上，無需手動設定即可加速資料讀取
- 對同一批 table 進行重複掃描時特別有效

**最佳實務：**設計 dashboard 與報表時，請使用能命中相同底層模式的參數化 query，以最大化快取重用。

### Photon Engine 優勢

Photon 是以 C++ 撰寫、原生執行於 Databricks 的 vectorized query engine：

- 預設在所有 DBSQL serverless warehouse 上啟用
- 使用 CPU vector 指令（SIMD）以 columnar batch 方式處理資料
- 特別擅長：大型 join、寬表彙總、字串處理、資料 shuffle
- 2025 年的 vectorized shuffle 可帶來 1.5 倍更高的 shuffle 吞吐量
- 搭配 PQE 時，可在既有 5 倍效益之上再讓 query 最多加快 25%

### 近期效能改進（2025）

| 改進項目 | 影響 |
|---|---|
| 整體生產工作負載 | 最多快 40%（自動套用，無需調校） |
| Photon Vectorized Shuffle | shuffle 吞吐量提高 1.5 倍 |
| PQE + Photon Vectorized Shuffle 組合 | 在既有 5 倍效益之上，最多再快 25% |
| Spatial SQL query | 最多快 17 倍（R-tree indexing、最佳化的 spatial join） |
| AI function | 對大型 batch 工作負載最多快 85 倍 |
| 端到端 Unity Catalog 延遲 | 最多改善 10 倍 |
| 3 年累積改善 | 客戶工作負載整體快 5 倍 |

所有改進都已在 DBSQL Serverless 上線，無需額外啟用。

### 成本最佳化模式

1. **使用 serverless SQL warehouse：**只在 query 執行時付費，並可自動擴縮與自動停止
2. **啟用 predictive optimization：**自動在 Unity Catalog managed table 上執行 OPTIMIZE 與 VACUUM
3. **正確設定 warehouse 規模：**先從較大的規模開始，再依實際使用模式往下調整
4. **避免閒置 warehouse：**針對低頻負載的 dashboard，使用積極的 auto-stop
5. **善用快取：**設計 deterministic query 以最大化 result cache 命中率
6. **使用 Liquid Clustering：**減少掃描量，讓每個 query 消耗更少 DBU
7. **收集統計資訊：**`ANALYZE TABLE` 可產生更好的 query plan，降低浪費的運算
8. **使用 Query Profile 監控：**找出高成本操作、spill 與 skew
9. **對經常重算的彙總使用 materialized view**
10. **避免使用 UDF：**原生 function 速度快很多，且沒有 serialization 額外成本

---

## DBSQL 的 Delta Lake 最佳化

### OPTIMIZE、VACUUM 與 ANALYZE

**建議執行順序：**OPTIMIZE -> VACUUM -> ANALYZE

**OPTIMIZE：**
- 將小檔案壓實成較大的檔案（預設目標為 1 GB）
- 對有大量小檔案的 table 應頻繁執行（尤其是 streaming write 之後）
- 可透過 `delta.targetFileSize` table property 設定目標大小
- 搭配 Liquid Clustering 時：只會重組尚未 cluster 的 ZCube（增量處理）

**VACUUM：**
- 移除 transaction log 中已不再使用的舊檔案
- 降低儲存成本
- 使用 compute-optimized instance（AWS C5、Azure F-series、GCP C2）
- 預設保留期：7 天（可透過 `delta.deletedFileRetentionDuration` 設定）
- 切勿將保留期設得低於最長執行 query 的持續時間

**ANALYZE TABLE：**
- 為 query 最佳化計算欄位層級統計資訊
- 在 table overwrite 或重大資料變更後立刻執行
- 專注於 WHERE 子句、JOIN 與 GROUP BY 會使用到的欄位

**Predictive optimization（建議）：**

> **注意：**在 serverless SQL warehouse 上，`delta.enableOptimizeWrite` 與 `delta.autoOptimize.autoCompact` 會自動管理，且無法手動設定（否則會引發 `DELTA_UNKNOWN_CONFIGURATION`）。下列 property 僅適用於 classic compute。對 serverless 而言，只需在 catalog/schema 層級啟用 predictive optimization。

```sql
-- 僅限 classic compute：
ALTER TABLE catalog.schema.table_name
SET TBLPROPERTIES ('delta.enableOptimizeWrite' = 'true');
-- 對於 Unity Catalog managed table，predictive optimization
-- 會自動處理 OPTIMIZE 與 VACUUM
```
### 檔案大小與壓實

- **Auto-compaction：**寫入後會自動在 partition 內合併小檔案
- **Optimized writes：**寫入前透過 shuffle 重新平衡資料，以減少小檔案
- **目標檔案大小：**預設 1 GB；可透過 `delta.targetFileSize` 針對特定工作負載調整
- 對於有大量小檔案的 table（streaming ingest），請排程固定的 OPTIMIZE job

### 效能相關 Table Property

> **注意：**`delta.enableOptimizeWrite` 與 `delta.autoOptimize.autoCompact` 僅適用於 classic compute。在 serverless SQL warehouse 上，這些設定會自動管理，手動設定會引發 `DELTA_UNKNOWN_CONFIGURATION`。其餘 property 則同時適用於 classic 與 serverless。

```sql
-- 僅限 classic compute（serverless 會自動管理這些設定）：
-- 'delta.enableOptimizeWrite' = 'true',
-- 'delta.autoOptimize.autoCompact' = 'true',

-- classic 與 serverless 都適用：
ALTER TABLE catalog.schema.my_table SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableChangeDataFeed' = 'true',
  'delta.deletedFileRetentionDuration' = '30 days',
  'delta.dataSkippingStatsColumns' = 'col1,col2,col3'
);
```

---

## Unity Catalog 整合模式

### 組織最佳實務

- 使用三層命名空間：`catalog.schema.table`
- 在 catalog 層級依環境（dev/staging/prod）進行組織
- 在 schema 層級依業務領域進行組織
- 使用 managed table（不要用 external table），以受益於 predictive optimization 與增強的治理能力

### 資料建模的治理功能

- **Primary/Foreign Key constraint：**讓 query optimizer 了解 table 關係
- **Row filter 與 column mask：**提供 table 層級的細緻化存取控制
- **Tag：**對 table 與欄位套用治理標籤（例如 PII、敏感度等級）
- **Comment：**為所有 table 與欄位撰寫說明，以利 AI/BI 發現
- **Lineage tracking：**自動追蹤 lineage，以理解 medallion architecture 中的資料流

### 實體關係視覺化

當定義 primary key 與 foreign key constraint 時，Unity Catalog 會繪製實體關係圖，為維度模型提供視覺化文件。

---

## 監控與可觀測性

- **Query Profile：**分析執行計畫、識別瓶頸、spill 與資料 skew
- **Query History：**追蹤 query 隨時間變化的效能趨勢
- **Warehouse monitoring：**追蹤使用率、排隊時間與擴縮事件
- **System table：**查詢 `system.billing`、`system.access` 與 `system.query` 以取得操作洞察
- **Alert：**設定 SQL alert 進行資料品質檢查與 SLA 監控

---

## 應避免的常見 Anti-pattern

### 資料建模 Anti-pattern

1. **在 Gold layer 略過維度建模：**OBT 可用於 Silver，但 Gold 應使用 Star Schema 進行多維度分析
2. **過度 partitioning：**超過 5,000-10,000 個 partition 會降低效能；請改用 Liquid Clustering
3. **使用字串 surrogate key：**為了更好的 join 效能，請使用整數 IDENTITY 欄位
4. **缺少 constraint：**未定義 PK/FK constraint 會讓 optimizer 無法取得關聯資訊
5. **缺少 comment 與 tag：**會降低 AI/BI 工具與治理流程的可發現性
6. **財務資料使用 FLOAT：**請使用 DECIMAL 以避免精度誤差
7. **在 ARRAY/MAP 欄位上篩選：**這些型別缺乏欄位層級統計資訊，無法進行 data skipping

### Query 與效能 Anti-pattern

1. **先刪除再重建 table：**請改用 `CREATE OR REPLACE TABLE`，以保留 time travel 並避免中斷讀取者
2. **在已有原生 function 時仍使用 Python/Scala UDF：**serialization 額外成本會大幅拖慢 query
3. **未收集統計資訊：**缺少 `ANALYZE TABLE` 會導致次佳的 query plan
4. **在可快取 query 中使用 non-deterministic function：**`NOW()`、`RAND()` 等會阻止 query result caching
5. **以錯誤欄位進行 partitioning：**若 partition 欄位不會出現在 filter 中，將導致全表掃描
6. **Liquid Clustering key 過多：**對於 10 TB 以下的 table，2 個 key 常比 4 個 key 更好
7. **在未啟用 predictive optimization 的情況下手動執行 OPTIMIZE/VACUUM：**對 Unity Catalog managed table 應啟用 predictive optimization

### 操作層面的 Anti-pattern

1. **閒置 warehouse：**務必啟用 auto-stop；變動型工作負載請使用 serverless
2. **warehouse 規模過小：**query spill 到磁碟所浪費的 DBU，往往比使用較大 warehouse 更多
3. **managed table 足夠卻仍使用 external table：**external table 無法享有 predictive optimization 與增強治理能力
4. **略過 VACUUM：**無限制的檔案成長會提高儲存成本並拖慢 metadata 操作
5. **VACUUM 的保留期設得過短：**可能破壞長時間執行的 query 與 time travel

---

## 快速參考：提供給 AI Agent 的 SQL 模式

為 Databricks 產生 SQL 時，優先採用以下模式：

```sql
-- 使用 CREATE OR REPLACE（不要用 DROP + CREATE）
CREATE OR REPLACE TABLE catalog.schema.my_table AS
SELECT ...;

-- upsert 請使用 MERGE（不要用 DELETE + INSERT）
MERGE INTO target USING source
ON target.key = source.key
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...;

-- window function 篩選請使用 QUALIFY（不要用 subquery）
SELECT *, ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts DESC) AS rn
FROM my_table
QUALIFY rn = 1;

-- 金額請使用 DECIMAL
SELECT CAST(amount AS DECIMAL(18,2)) AS revenue FROM orders;

-- 載入後收集統計資訊
ANALYZE TABLE catalog.schema.my_table COMPUTE STATISTICS FOR ALL COLUMNS;

-- 啟用 predictive optimization（僅限 classic compute；serverless 會自動管理）
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.enableOptimizeWrite' = 'true');
```