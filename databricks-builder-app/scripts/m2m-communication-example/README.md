# M2M Communication 範例 -- App-to-App 整合

這是一個精簡的 Databricks App，示範如何把 **Builder App** 當成 agent-as-a-service 來呼叫。內容涵蓋完整流程：M2M OAuth 認證、agent 呼叫，以及 SSE 回應串流。

## 運作方式

```
+------------------------+    Bearer token    +------------------------+
|  M2M Communication     | ----------------> |     Builder App        |
|  Example (this app)    | <-- SSE stream -- |     (agent API)        |
+------------------------+                   +------------------------+
```

1. 此 app 自動建立的 **service principal** 會透過 `WorkspaceClient().config.authenticate()` 向 builder app 完成認證，並產生 M2M OAuth Bearer token。
2. builder app 會透過 `WorkspaceClient(token=...).current_user.me()` 驗證 token，以解析呼叫端身分。
3. 此 app 會呼叫 agent（`POST /api/invoke_agent`），再把事件串流（`POST /api/stream_progress/{id}`）回傳到瀏覽器。

## 先決條件

- 必須先部署 **Builder App**（請參閱 `databricks-builder-app/README.md`）
- Python 3.11+
- 已啟用 apps 的 Databricks workspace

## 設定

### 1. 部署 Builder App

若尚未部署：

```bash
cd databricks-builder-app
./scripts/deploy.sh <builder-app-name>
```

### 2. 部署此 App

```bash
# 建立 app
databricks apps create m2m-communication-example

# 複製並設定 app.yaml
cp app.yaml.example app.yaml
# 編輯 app.yaml：將 BUILDER_APP_URL 設為 builder app 的 URL

# 上傳並部署
databricks workspace import-dir . /Workspace/Users/<you>/apps/m2m-communication-example --overwrite
databricks apps deploy m2m-communication-example --source-code-path /Workspace/Users/<you>/apps/m2m-communication-example
```

### 3. 授與權限（雙向）

每個 app 的 service principal 都必須對另一個 app 具有 **CAN USE** 權限，原因如下：

- **此 app 的 SP** 需要能存取 **builder app** 才能呼叫其 API 端點
- **builder app 的 SP** 需要能存取 **此 app**，以便在需要回呼時使用（以及進行 workspace 層級的 auth 解析）

請先在 Databricks UI 中找到各 app 的 service principal 名稱（Apps > 您的 app > Settings），再授與權限：

```bash
# 授與此 app 的 SP 存取 builder app
databricks apps update-permissions <builder-app-name> --json '{
  "access_control_list": [{
    "service_principal_name": "<m2m-example-sp-name>",
    "permission_level": "CAN_USE"
  }]
}'

# 授與 builder app 的 SP 存取此 app
databricks apps update-permissions m2m-communication-example --json '{
  "access_control_list": [{
    "service_principal_name": "<builder-app-sp-name>",
    "permission_level": "CAN_USE"
  }]
}'
```

> **注意：** 若 `users` 群組已對兩個 app 都具有 `CAN_USE`（預設情況），這些額外授權可能不需要。請先檢查 app 權限設定。

### 4. 驗證

在瀏覽器開啟此 app 的 URL，輸入訊息並點選 **Send**。您應可即時看到 agent 的回應串流。

## 本機開發

若要在本機測試，請在本機同時執行兩個 app：

### Terminal 1 -- 啟動 Builder App

```bash
cd databricks-builder-app
./scripts/start_dev.sh
```

builder app 會在 `http://localhost:8000` 執行。

### Terminal 2 -- 啟動此 App

```bash
cd databricks-builder-app/scripts/m2m-communication-example

# 安裝依賴
pip install -r requirements.txt

# 設定環境變數
export BUILDER_APP_URL=http://localhost:8000
export DATABRICKS_TOKEN=dapi...  # 您的 PAT

# 執行
uvicorn app:app --host 0.0.0.0 --port 8001
```

在瀏覽器開啟 `http://localhost:8001`。

## API 端點

| Method | Path | 說明 |
|--------|------|------|
| `GET` | `/` | HTML 示範 UI |
| `POST` | `/ask` | 傳送訊息並等待完整回應 |
| `POST` | `/invoke` | 啟動 agent，取得可串流使用的 `execution_id` |
| `GET` | `/stream/{execution_id}` | 即時串流的 SSE proxy |
| `GET` | `/health` | 健康檢查（也會 ping builder app） |

## 檔案結構

```
m2m-communication-example/
+-- app.py               # 含 HTML UI 與端點的 FastAPI app
+-- builder_client.py    # Builder App 的 HTTP client（auth、REST、SSE）
+-- app.yaml.example     # Databricks Apps 部署設定（複製成 app.yaml）
+-- requirements.txt     # Python 依賴
+-- README.md            # 本檔案
```

## Auth 細節

### 在 Databricks Apps 中（正式環境）

呼叫端 app 會使用自動建立的 service principal 完成認證：

```python
from databricks.sdk import WorkspaceClient

# SDK 會自動使用 app 的 SP 憑證
headers = WorkspaceClient().config.authenticate()
# headers = {"Authorization": "Bearer <m2m-oauth-token>"}
```

builder app 會透過驗證 token 來解析呼叫端身分：

```python
client = WorkspaceClient(host=host, token=bearer_token)
me = client.current_user.me()
# 回傳 service principal 的身分
```

### 在本機開發中

請使用 Personal Access Token（PAT）：

```bash
export DATABRICKS_TOKEN=dapi...
```

client 會以 `Authorization: Bearer <pat>` 傳送該 token。builder app 會用相同方式把 PAT 解析成您的使用者身分。

### Cross-Workspace（選用）

預設情況下，此 app 會使用自動建立的 SP，向 **同一個 workspace** 中的 builder app 完成認證。若要呼叫 **不同 workspace** 的 builder app，請在 `app.yaml` 中設定下列環境變數：

**選項 A -- PAT / token：**

```yaml
- name: BUILDER_DATABRICKS_HOST
  value: "https://other-workspace.cloud.databricks.com"
- name: BUILDER_DATABRICKS_TOKEN
  value: "<pat-for-remote-workspace>"
```

**選項 B -- SP 憑證（正式環境建議）：**

```yaml
- name: BUILDER_DATABRICKS_HOST
  value: "https://other-workspace.cloud.databricks.com"
- name: BUILDER_DATABRICKS_CLIENT_ID
  value: "<sp-client-id>"
- name: BUILDER_DATABRICKS_CLIENT_SECRET
  value: "<sp-client-secret>"
```

該 SP 必須存在於 **目標** workspace，且擁有呼叫 builder app 的權限。若未設定這些環境變數，系統會使用預設的同 workspace 自動認證模式。

## 疑難排解

### 「Failed to invoke agent」/ 403

- 請確認兩個 app 的 service principal 具有正確權限（請參閱上方步驟 3）
- 請確認 `BUILDER_APP_URL` 正確且可連線

### 「BUILDER_APP_URL environment variable is required」

- 請在 `app.yaml`（部署時）或環境變數（本機）中設定 `BUILDER_APP_URL`

### 連線逾時

- SSE 串流使用 60 秒 read timeout，以配合 builder app 50 秒的串流視窗
- 若 builder app 負載較高，回應開始時間可能會更久
