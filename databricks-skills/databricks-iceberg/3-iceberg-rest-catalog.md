# Iceberg REST Catalog（IRC）

Iceberg REST Catalog（IRC）是一個 REST API 端點，可讓外部引擎使用標準 Apache Iceberg REST Catalog protocol 讀寫 Databricks 管理的 Iceberg 資料。外部工具會連線至 IRC 端點、完成驗證，並取得授予的憑證，以便直接存取雲端儲存體。

**端點**：`https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest`

> **舊版端點警告**：較舊的 `/api/2.1/unity-catalog/iceberg` 端點目前處於 maintenance mode，不應再用於新的整合。那是最早為 UniForm 文件化的唯讀端點。所有新的整合 —— 無論是 UniForm（具備 Iceberg 讀取能力的 Delta）或受管 Iceberg 資料表 —— 都必須使用 `/api/2.1/unity-catalog/iceberg-rest`。

**需求**：Unity Catalog、工作區已啟用 external data access、DBR 16.1+

---

## 前置條件

### 1. 啟用 External Data Access

你的工作區必須啟用 external data access。這通常由工作區管理員進行設定。

### 2. 具備對 IRC 端點的網路存取能力

外部引擎必須能透過 HTTPS（port 443）連到 Databricks 工作區。若工作區已啟用 **IP 存取清單**，則必須明確允許 Iceberg client 的 CIDR 範圍 —— 否則即使憑證或權限都正確，連線仍會失敗。

檢查與管理 IP 存取清單：
- 管理主控台：**Settings → Security → IP access list**
- REST API：使用 `GET /api/2.0/ip-access-lists` 檢查，使用 `POST /api/2.0/ip-access-lists` 新增範圍

> **常見症狀**：即使憑證有效且權限正確，連線仍會逾時或回傳 `403 Forbidden`。IP 存取清單設定錯誤是常見根因 —— 在除錯 auth 之前，請先檢查這一點。

### 3. 授予 EXTERNAL USE SCHEMA

連線使用的 principal（使用者或 service principal）必須在欲存取的每個 schema 上具備 `EXTERNAL USE SCHEMA` 權限：

```sql
-- 授權給使用者
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `user@example.com`;

-- 授權給 service principal
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `my-service-principal`;

-- 授權給群組
GRANT EXTERNAL USE SCHEMA ON SCHEMA my_catalog.my_schema TO `data-engineers`;
```

> **重要**：`EXTERNAL USE SCHEMA` 與 `SELECT` 或 `MODIFY` 權限是分開的。使用者必須同時具備資料權限與 external use grant。

---

## 驗證

### PAT（個人存取權杖）

```
Authorization: Bearer <pat-token>
```

### OAuth（M2M）

對於服務對服務驗證，請搭配 service principal 使用 OAuth：

1. 在 Databricks account 中建立 service principal
2. 產生 OAuth secret
3. 使用 OAuth token 端點取得 access token
4. 將 access token 作為 Bearer token 傳遞

---

## 讀寫能力矩陣

| 資料表類型 | IRC 讀取 | IRC 寫入 |
|------------|:-:|:-:|
| 受管 Iceberg（`USING ICEBERG`） | 是 | 是 |
| Delta + UniForm | 是 | 否 |
| Delta + 相容性模式 | 是 | 否 |
| Foreign Iceberg 資料表 | 否 | 否 |

> **核心觀念**：只有受管 Iceberg 資料表支援透過 IRC 寫入。UniForm 與相容性模式資料表都是唯讀，因為其底層格式仍是 Delta。

---

## 憑證授予

當外部引擎透過 IRC 連線時，Databricks 會**授予臨時雲端憑證**（AWS 的短效 STS token、Azure 的 SAS token），讓引擎能直接在雲端儲存體中讀寫資料檔。這對 client 來說是透明的 —— IRC protocol 會自動處理。

優點：
- 不需要在外部引擎中設定雲端憑證
- 憑證的範圍會限縮在特定資料表與操作
- 憑證會自動過期（通常為 1 小時）

---

## 常見設定參考

| 參數 | 值 |
|-----------|-------|
| **Catalog type** | `rest` |
| **URI** | `https://<workspace-url>/api/2.1/unity-catalog/iceberg-rest` |
| **Warehouse** | Unity Catalog catalog 名稱（例如 `my_catalog`） |
| **Token** | Databricks PAT 或 OAuth access token |
| **憑證授予** | 自動（由 REST protocol 處理） |


---

## 相關內容

- [4-snowflake-interop.md](4-snowflake-interop.md) —— Snowflake 透過 catalog integration 讀取 Databricks（使用 IRC）
- [5-external-engine-interop.md](5-external-engine-interop.md) —— 各引擎的連線設定：PyIceberg、OSS Spark、EMR、Flink、Kafka Connect、DuckDB、Trino
