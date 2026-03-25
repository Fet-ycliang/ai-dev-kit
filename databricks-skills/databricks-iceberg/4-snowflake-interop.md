# Snowflake 互通性

Databricks 與 Snowflake 可以雙向共享 Iceberg 資料。此檔案涵蓋兩個方向：Snowflake 讀取 Databricks 管理的資料表，以及 Databricks 讀取 Snowflake 管理的 Iceberg 資料表。

**雲端範圍**：以 AWS 為主的範例。Azure/GCS 的差異會在相關處註明。

---

## 方向 1：Snowflake 讀取 Databricks

Snowflake 可透過連接 Databricks Iceberg REST Catalog（IRC）的 **Catalog Integration**，讀取 Databricks 管理的 Iceberg 資料表（managed Iceberg + UniForm + 相容性模式）。

### 步驟 1：在 Snowflake 中建立 Catalog Integration

在 AWS 上必須設定 `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`，Snowflake 才能從 Databricks IRC 取得臨時 STS 憑證。若未設定，Snowflake 將無法存取底層 Parquet 檔案。

**PAT / Bearer token：**

```sql
-- 在 Snowflake 中
CREATE OR REPLACE CATALOG INTEGRATION databricks_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_schema'        -- UC schema（預設 namespace）
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-workspace-url>/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = '<catalog-name>'          -- UC catalog 名稱
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<databricks-pat-token>'
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;
```

**OAuth（建議用於正式環境）：**

```sql
CREATE OR REPLACE CATALOG INTEGRATION databricks_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_schema'
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-workspace-url>/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = '<catalog-name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<service-principal-client-id>'
    OAUTH_CLIENT_SECRET = '<service-principal-secret>'
    OAUTH_TOKEN_URI = 'https://<databricks-workspace-url>/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;
```

> **Databricks 端的授權**：用於驗證的 principal 必須在 Unity Catalog 中具備以下權限：
> - catalog 上的 `USE CATALOG`
> - schema 上的 `USE SCHEMA`
> - schema 上的 `EXTERNAL USE SCHEMA` —— 這是允許外部引擎透過 IRC 存取資料表的關鍵權限
> - 目標資料表上的 `SELECT`（或對 schema/catalog 授與更廣泛的存取權）
>
> 缺少 `EXTERNAL USE SCHEMA` 會導致 Snowflake 出現 `Failed to retrieve credentials` 錯誤。

### 步驟 2：External Volume（僅 Azure/GCS）

在 **AWS 搭配 vended credentials** 的情況下，不需要 external volume —— Databricks IRC 會自動授予臨時 STS 憑證。

在 **Azure** 或 **GCS** 上，由於這些雲端不支援 vended credentials，因此你必須在 Snowflake 中建立 external volume：

```sql
-- Azure 範例（在 Snowflake 中）
CREATE OR REPLACE EXTERNAL VOLUME databricks_ext_vol
  STORAGE_LOCATIONS = (
    (
      NAME = 'azure_location'
      STORAGE_BASE_URL = 'azure://myaccount.blob.core.windows.net/my-container/iceberg/'
      AZURE_TENANT_ID = '<tenant-id>'
    )
  );
```

### 步驟 3：在 Snowflake 中公開資料表

有兩種作法可選。**Linked catalog** 為建議方案 —— 它可一次公開 namespace 中的所有資料表，並自動更新。

**選項 A：Linked Catalog Database（建議）**

```sql
-- 確認 namespaces 可見（應回傳你的 UC schemas）
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('databricks_catalog_int', '', 0);

-- 建立 linked catalog database，一次公開 namespace 中的所有資料表
CREATE DATABASE my_snowflake_db
  LINKED_CATALOG = (
    CATALOG = 'databricks_catalog_int',
    ALLOWED_NAMESPACES = ('my_schema')   -- UC schema
  );

-- 檢查連結健康狀態（executionState 應為 "RUNNING"，且 failureDetails 應為空）
SELECT SYSTEM$CATALOG_LINK_STATUS('my_snowflake_db');

-- 查詢
SELECT * FROM my_snowflake_db."my_schema"."my_table"
WHERE event_date >= '2025-01-01';
```

**選項 B：單一資料表參照（舊作法）**

```sql
-- AWS（vended creds —— 不需要 EXTERNAL_VOLUME）
CREATE ICEBERG TABLE my_snowflake_db.my_schema.events
  CATALOG = 'databricks_catalog_int'
  CATALOG_TABLE_NAME = 'events';

-- Azure/GCS（需要 EXTERNAL_VOLUME）
CREATE ICEBERG TABLE my_snowflake_db.my_schema.events
  CATALOG = 'databricks_catalog_int'
  CATALOG_TABLE_NAME = 'events'
  EXTERNAL_VOLUME = 'databricks_ext_vol';

-- 查詢
SELECT * FROM my_snowflake_db.my_schema.events
WHERE event_date >= '2025-01-01';
```

### 關鍵注意事項

#### 工作區 IP 存取清單必須允許 Snowflake 的 Egress IP

如果 Databricks 工作區已啟用 **IP access lists**，就必須將 Snowflake 的 outbound NAT IP 加入 allowlist。Snowflake 會透過 HTTPS（port 443）連到 Databricks IRC 端點（`/api/2.1/unity-catalog/iceberg-rest`），而被封鎖的 IP 會造成連線逾時或 `403` 錯誤，看起來很像 auth 失敗。


> **診斷提示**：若 catalog integration 顯示 `ENABLED = TRUE`，但 `SYSTEM$CATALOG_LINK_STATUS` 回傳的是連線錯誤（不是 credentials 錯誤），第一個就應該檢查 IP access lists。

#### REFRESH_INTERVAL_SECONDS 是以 Integration 為單位，不是以資料表為單位

catalog integration 上的 `REFRESH_INTERVAL_SECONDS` 設定，會控制 Snowflake 多久輪詢一次 Databricks IRC 以取得 metadata 變更。這會套用到使用該 integration 的**所有資料表** —— 你無法為每個資料表設定不同的 refresh interval。

- 較低的值 = 資料更新更即時，但 API 呼叫也更多
- 預設：300 秒（5 分鐘）
- 最小值：60 秒

#### 1000-commit 限制

對於由 object storage 中 Delta files 建立的 Iceberg 資料表，Snowflake 每次使用 CREATE/ALTER ICEBERG TABLE … REFRESH 或自動重新整理資料表時，最多只會處理 1000 個 Delta commit files；若自上次 checkpoint 以來資料表超過 1000 個 commit files，可多次執行 refresh，且每次都會從前一次停止之處繼續。1000-commit 限制僅適用於最新 Delta checkpoint file 之後的 Delta commit files，並不限制 catalog integration 最終透過多次 refresh 可同步的 commit 數量

**緩解方式**：
- 啟用 Predictive Optimization（自動 compaction 可降低 commit 頻率）
- 以批次寫入取代高頻率 micro-batches
- 視需要執行 `OPTIMIZE` 與 `VACUUM`，手動整併 metadata。

---

## 方向 2：Databricks 讀取 Snowflake

Databricks 可透過連接 Snowflake Iceberg catalog 的 **foreign catalog**，讀取由 Snowflake 管理的 Iceberg 資料表。Snowflake Iceberg 資料表儲存在 external volumes（雲端儲存體）中，因此 Databricks 會直接讀取 Iceberg 的 Parquet 檔案 —— 不需要 Snowflake compute。

**前提假設**：已存在一個由 Snowflake 管理的 Iceberg 資料表，並以 `CATALOG = 'SNOWFLAKE'` 指向 external volume：

```sql
-- 在 Snowflake 中 —— 前置資料表
CREATE ICEBERG TABLE sensor_readings (
  device_id    INT,
  device_value STRING
)
  CATALOG         = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'ICEBERG_SHARED_VOL'
  BASE_LOCATION   = 'sensor_readings/';

INSERT INTO sensor_readings VALUES (1, 'value01'), (2, 'value02');

SELECT * FROM sensor_readings;
```

`CATALOG = 'SNOWFLAKE'` 代表 Iceberg metadata 由 Snowflake 管理。資料檔會寫入 external volume 中 `BASE_LOCATION` 的子路徑。下列步驟將設定 Databricks 來讀取此資料表。

### 步驟 1：找出 Snowflake External Volume 路徑

在設定 Databricks 端之前，請先在 Snowflake 中執行下列指令，以取得 Snowflake 儲存 Iceberg 資料的 S3/ADLS/GCS 路徑。你會在步驟 2 與步驟 4 用到此路徑。

```sql
-- 在 Snowflake 中
DESCRIBE EXTERNAL VOLUME <your-external-volume-name>;
-- 記下 STORAGE_BASE_URL 的值（例如 s3://my-bucket/snowflake-iceberg/）
```

### 步驟 2：建立 Storage Credential

為 Snowflake 儲存 Iceberg 資料的雲端儲存體建立 storage credential。假設 IAM role 已存在。詳細資訊請參閱文件（https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual）

```bash
# 在 Databricks CLI 中（AWS 範例）
databricks storage-credentials create snowflake_storage_cred \
  --aws-iam-role-arn "arn:aws:iam::123456789012:role/snowflake-data-access"
```

### 步驟 3：建立 External Location

external location 必須指向 bucket 的**根目錄**（不是子路徑），這樣所有 Snowflake external volume 路徑才會落在其範圍內。

> **Fallback mode**：你不需要啟用這個 external-location fallback 才能透過 catalog federation 讀取 Snowflake 建立的 Iceberg 資料表。它只會影響路徑如何解析 storage credentials，不會影響 Snowflake Iceberg federation 是否可運作。

```sql
-- 在 Databricks 中（URL 應為 bucket 根目錄，而非子路徑）
CREATE EXTERNAL LOCATION snowflake_data
URL 's3://snowflake-iceberg-bucket/'
WITH (CREDENTIAL snowflake_storage_cred);
```

### 步驟 4：建立 Snowflake Connection

```sql
-- 在 Databricks 中
CREATE CONNECTION snowflake_conn
TYPE SNOWFLAKE
OPTIONS (
  'host' = '<account>.snowflakecomputing.com',
  'user' = '<username>',
  'password' = '<password>',
  'sfWarehouse' = '<warehouse-name>'
);
```

### 步驟 5：建立 Foreign Catalog

除 `database` 之外，還有兩個必填欄位：

- **`authorized_paths`**：Snowflake 儲存 Iceberg 資料表檔案的路徑 —— 取自 `DESCRIBE EXTERNAL VOLUME` 的 `STORAGE_BASE_URL`。Databricks 只能讀取資料位於這些路徑下的 Iceberg 資料表。
- **`storage_root`**：Databricks 儲存 Iceberg 讀取 catalog metadata 的位置。必須指向現有的 external location。這是必填欄位 —— 若未提供，建立 foreign catalog 會失敗。

```sql
-- 在 Databricks 中
CREATE FOREIGN CATALOG snowflake_iceberg
USING CONNECTION snowflake_conn
OPTIONS (
  'catalog' = '<snowflake-database>',
  'authorized_paths' = 's3://snowflake-iceberg-bucket/snowflake-iceberg/',
  'storage_root' = 's3://snowflake-iceberg-bucket/uc-metadata/'
);
```

> **UI 工作流程說明**：Databricks 連線精靈（Catalog Explorer → Add connection → Snowflake）會在表單中要求輸入 authorized paths 與 storage location，並自動建立 foreign catalog。上面的 SQL 就是對應的 DDL。

### 步驟 6：重新整理、驗證與查詢

```sql
-- 重新整理以發現資料表
REFRESH FOREIGN CATALOG snowflake_iceberg;

-- 在大規模查詢前先確認 provider 類型：
--   Provider = Iceberg → Databricks 直接從雲端儲存體讀取（成本低）
--   Provider = Snowflake → 透過 JDBC 產生雙重 compute（Snowflake + Databricks）
DESCRIBE EXTENDED snowflake_iceberg.my_schema.my_table;

-- 查詢
SELECT * FROM snowflake_iceberg.my_schema.my_table
WHERE created_at >= '2025-01-01';
```

### Compute Cost Matrix

| Snowflake 資料表類型 | Databricks 讀取 | Compute 成本 |
|---------------------|:-:|---|
| **Snowflake Iceberg 資料表** | 是 | 僅需 Databricks compute（直接從雲端儲存體讀取資料檔） |
| **Snowflake 原生資料表** | 是（透過 federation） | 雙重 compute —— Snowflake 執行查詢，Databricks 處理結果 |

> **關鍵洞察**：從 Databricks 讀取 Snowflake Iceberg 資料表的成本更低，因為 Databricks 會直接讀取 Parquet 檔案。對於原生 Snowflake 資料表，則必須由 Snowflake 執行掃描。


---

## 完整 AWS 範例：Snowflake 讀取 Databricks

```sql
-- ========================================
-- DATABRICKS 端（在 Databricks 中執行）
-- ========================================

-- 1. 建立受管 Iceberg 資料表（v2 —— CLUSTER BY 需停用 DVs 和 row tracking）
CREATE TABLE main.sales.orders (
  order_id BIGINT,
  customer_id BIGINT,
  amount DECIMAL(10,2),
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (order_date);

-- 2. 對 Snowflake catalog integration 使用的 service principal 授與 external access
GRANT EXTERNAL USE SCHEMA ON SCHEMA main.sales TO `snowflake-service-principal`;

-- ========================================
-- SNOWFLAKE 端（在 Snowflake 中執行）
-- ========================================

-- 3. 建立 catalog integration（AWS 上的 vended creds 需要 ACCESS_DELEGATION_MODE）
CREATE OR REPLACE CATALOG INTEGRATION databricks_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'sales'
  REST_CONFIG = (
    CATALOG_URI = 'https://my-workspace.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = 'main'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<service-principal-client-id>'
    OAUTH_CLIENT_SECRET = '<service-principal-secret>'
    OAUTH_TOKEN_URI = 'https://my-workspace.cloud.databricks.com/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;

-- 4. 確認 schemas 可見
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('databricks_int', '', 0);

-- 5. 建立 linked catalog database（公開 namespace 中的所有資料表）
CREATE DATABASE analytics
  LINKED_CATALOG = (
    CATALOG = 'databricks_int',
    ALLOWED_NAMESPACES = ('sales')
  );

-- 6. 檢查連結健康狀態
SELECT SYSTEM$CATALOG_LINK_STATUS('analytics');

-- 7. 查詢（schema 與 table 名稱區分大小寫）
SELECT order_date, SUM(amount) AS daily_revenue
FROM analytics."sales"."orders"
GROUP BY order_date
ORDER BY order_date DESC;
```

---

## 相關內容

- [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) —— IRC 端點細節與驗證
