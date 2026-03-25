# 設定與認證

Zerobus Ingest 的完整設定指南：端點設定、service principal 建立、資料表準備、SDK 安裝與防火牆需求。

---

## 1. 判定你的伺服器端點

Zerobus 伺服器端點格式取決於你的雲端供應商：

| 雲端 | 伺服器端點格式 | 工作區 URL 格式 |
|-------|------------------------|----------------------|
| **AWS** | `<workspace-id>.zerobus.<region>.cloud.databricks.com` | `https://<instance>.cloud.databricks.com` |
| **Azure** | `<workspace-id>.zerobus.<region>.azuredatabricks.net` | `https://<instance>.azuredatabricks.net` |

**範例（AWS）：**
```
伺服器端點: 1234567890123456.zerobus.us-west-2.cloud.databricks.com
工作區 URL:   https://dbc-a1b2c3d4-e5f6.cloud.databricks.com
```

**尋找 workspace ID 的方式：** 從你的 workspace URL 或 workspace 設定頁面擷取數字 ID。它是伺服器端點的第一個區段。

---

## 2. 建立目標資料表

Zerobus **不會**建立或變更資料表。你必須先在 Unity Catalog 中預先建立目標資料表，且它必須是 **managed Delta 資料表**：

```sql
CREATE TABLE catalog.schema.my_events (
    event_id     STRING,
    device_name  STRING,
    temp         INT,
    humidity     LONG,
    event_time   TIMESTAMP
);
```

**限制：**
- 必須是 **managed** Delta 資料表（不可使用 external storage）
- 資料表名稱僅限 ASCII 字母、數字與底線
- 最多 2000 個欄位
- 資料表必須位於[支援區域](#支援區域)

---

## 3. 建立 Service Principal

Zerobus 透過 OAuth2 service principal（M2M）進行認證。你可以透過 Databricks UI 或 CLI 建立：

### 透過 UI
1. 前往 **Settings > Identity and Access > Service principals**
2. 點選 **Add service principal**
3. 產生 OAuth secret：記下 **client ID** 與 **client secret**

### 透過 Databricks CLI
```bash
databricks service-principals create --display-name "zerobus-producer"
```

### 授與資料表權限

Service principal 需要具備 catalog、schema 與資料表的存取權：

```sql
-- 授與 catalog 存取權
GRANT USE CATALOG ON CATALOG my_catalog TO `<service-principal-uuid>`;

-- 授與 schema 存取權
GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `<service-principal-uuid>`;

-- 授與資料表寫入權限
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.my_events TO `<service-principal-uuid>`;
```

**提示：** 若需要更廣泛的存取權（例如可寫入某個 schema 中的多個資料表），請改為在 schema 層級授與 `MODIFY` 與 `SELECT`。

**重要：** 對 Zerobus 而言，除了 catalog/schema 存取權外，請一律在資料表層級明確授與 `MODIFY` 與 `SELECT` 權限。對 Zerobus 使用的 OAuth `authorization_details` flow 而言，schema 層級繼承的授權可能不足。

---

## 4. 安裝 SDK

### Python（3.9+）

```bash
pip install databricks-zerobus-ingest-sdk>=1.0.0
```

或搭配虛擬環境：
```bash
uv pip install databricks-zerobus-ingest-sdk>=1.0.0
```

**注意：** Zerobus SDK 無法在 Databricks serverless compute 上以 pip 安裝。請改用 classic compute clusters，或使用 [Zerobus REST API](https://docs.databricks.com/aws/en/ingestion/zerobus-rest-api)（Beta）在 notebook 中進行無 SDK 的資料攝取。

### Java（8+）

Maven:
```xml
<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-ingest-sdk</artifactId>
    <version>0.1.0</version>
</dependency>
```

Gradle:
```groovy
implementation 'com.databricks:zerobus-ingest-sdk:0.1.0'
```

### Go（1.21+）

```bash
go get github.com/databricks/zerobus-sdk-go
```

### TypeScript / Node.js（16+）

```bash
npm install @databricks/zerobus-ingest-sdk
```

### Rust（1.70+）

```bash
cargo add databricks-zerobus-ingest-sdk
cargo add tokio --features macros,rt-multi-thread
```

---

## 5. 設定環境變數

請將認證資訊儲存為環境變數，而非直接寫死在程式碼中：

```bash
export ZEROBUS_SERVER_ENDPOINT="1234567890123456.zerobus.us-west-2.cloud.databricks.com"
export DATABRICKS_WORKSPACE_URL="https://dbc-a1b2c3d4-e5f6.cloud.databricks.com"
export ZEROBUS_TABLE_NAME="my_catalog.my_schema.my_events"
export DATABRICKS_CLIENT_ID="<service-principal-client-id>"
export DATABRICKS_CLIENT_SECRET="<service-principal-client-secret>"
```

---

## 6. 防火牆 Allowlist

若你的 client 應用程式位於防火牆後方，請先將該區域的 Zerobus IP 位址加入 allowlist，再測試連線能力。請聯絡你的 Databricks 代表，或參閱 [Zerobus 文件](https://docs.databricks.com/aws/en/ingestion/zerobus-overview) 以取得目前的 IP 範圍。

---

## 支援區域

工作區與目標資料表都必須位於你的雲端供應商所支援的區域中。

### AWS

| 區域代碼 | 位置 |
|-------------|----------|
| `us-east-1` | 美國東部（N. Virginia） |
| `us-east-2` | 美國東部（Ohio） |
| `us-west-2` | 美國西部（Oregon） |
| `eu-central-1` | 歐洲（Frankfurt） |
| `eu-west-1` | 歐洲（Ireland） |
| `ap-southeast-1` | 亞太地區（Singapore） |
| `ap-southeast-2` | 亞太地區（Sydney） |
| `ap-northeast-1` | 亞太地區（Tokyo） |
| `ca-central-1` | 加拿大（Central） |

### Azure

| 區域代碼 | 位置 |
|-------------|----------|
| `canadacentral` | 加拿大中部 |
| `westus` | 美國西部 |
| `eastus` | 美國東部 |
| `eastus2` | 美國東部 2 |
| `centralus` | 美國中部 |
| `northcentralus` | 美國北部中部 |
| `swedencentral` | 瑞典中部 |
| `westeurope` | 西歐 |
| `northeurope` | 北歐 |
| `australiaeast` | 澳洲東部 |
| `southeastasia` | 東南亞 |

---

## 驗證檢查清單

在寫入第一筆記錄之前，請確認：

```
- [ ] 伺服器端點與你的雲端供應商及區域相符
- [ ] 工作區 URL 正確
- [ ] 目標資料表已存在，且為 managed Delta 資料表
- [ ] Service principal 具有 USE CATALOG、USE SCHEMA、MODIFY、SELECT 授權
- [ ] 已為目標語言安裝 SDK
- [ ] 已設定環境變數（或已在程式碼中設定認證）
- [ ] 防火牆允許連往 Zerobus 端點的對外連線（如適用）
```
