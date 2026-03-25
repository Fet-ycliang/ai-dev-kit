function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Content
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

$base = 'D:\azure_code\ai-dev-kit\databricks-skills\databricks-app-python'

Write-Utf8NoBom -Path (Join-Path $base 'SKILL.md') -Content @'
---
name: databricks-app-python
description: "使用 Dash、Streamlit、Gradio、Flask、FastAPI 或 Reflex 建置以 Python 為基礎的 Databricks 應用程式。處理 OAuth 授權（應用程式授權與使用者授權）、應用程式資源、SQL warehouse 與 Lakebase 連線、模型服務整合、foundation model APIs、LLM 整合與部署。當你要建置 Python web apps、儀表板、ML demos 或 Databricks 的 REST APIs，或使用者提到 Streamlit、Dash、Gradio、Flask、FastAPI、Reflex 或 Databricks app 時使用。"
---

# Databricks Python 應用程式

建置以 Python 為基礎的 Databricks 應用程式。若需完整範例與實作配方，請參閱 **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**。

---

## 重要規則（務必遵守）

- **MUST** 確認框架選擇，或使用下方的 [框架選擇](#框架選擇)
- **MUST** 使用 SDK `Config()` 進行驗證（絕不要硬編碼 tokens）
- **MUST** 以 `app.yaml` 的 `valueFrom` 設定資源（絕不要硬編碼 resource IDs）
- **MUST** 為 Dash app 的 layout 與 styling 使用 `dash-bootstrap-components`
- **MUST** 為 Streamlit 資料庫連線使用 `@st.cache_resource`
- **MUST** 以 Gunicorn 部署 Flask、以 uvicorn 部署 FastAPI（不可使用 dev servers）

## 必要步驟

複製此檢查清單並確認每個項目：
```
- [ ] 已選定框架
- [ ] 已決定授權策略：應用程式授權、使用者授權，或兩者皆用
- [ ] 已識別應用程式資源（SQL warehouse、Lakebase、serving endpoint 等）
- [ ] 已決定後端資料策略（SQL warehouse、Lakebase 或 SDK）
- [ ] 已決定部署方式：CLI 或 DABs
```

---

## 框架選擇

| Framework | 最適合 | app.yaml 指令 |
|-----------|--------|------------------|
| **Dash** | 生產環境儀表板、BI 工具、複雜互動 | `["python", "app.py"]` |
| **Streamlit** | 快速原型、data science apps、內部工具 | `["streamlit", "run", "app.py"]` |
| **Gradio** | ML demos、模型介面、聊天 UI | `["python", "app.py"]` |
| **Flask** | 自訂 REST APIs、輕量應用程式、webhooks | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| **FastAPI** | 非同步 APIs、自動產生的 OpenAPI 文件 | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| **Reflex** | 無需 JavaScript 的全端 Python apps | `["reflex", "run", "--env", "prod"]` |

**預設**：建議原型使用 **Streamlit**、生產環境儀表板使用 **Dash**、APIs 使用 **FastAPI**、ML demos 使用 **Gradio**。

---

## 快速參考

| 概念 | 詳細資訊 |
|---------|---------|
| **執行環境** | Python 3.11、Ubuntu 22.04、2 vCPU、6 GB RAM |
| **預先安裝** | Dash 2.18.1、Streamlit 1.38.0、Gradio 4.44.0、Flask 3.0.3、FastAPI 0.115.0 |
| **應用程式授權** | 透過服務主體使用 `Config()` — 自動注入 `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` |
| **使用者授權** | `x-forwarded-access-token` header — 請見 [1-authorization.md](1-authorization.md) |
| **資源** | `app.yaml` 中的 `valueFrom` — 請見 [2-app-resources.md](2-app-resources.md) |
| **Cookbook** | https://apps-cookbook.dev/ |
| **官方文件** | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/ |

---

## 詳細指南

**授權**：當設定應用程式或使用者授權時，請使用 [1-authorization.md](1-authorization.md) — 涵蓋服務主體授權、代理存取使用者權杖、OAuth scopes，以及各框架的程式碼範例。（關鍵字：OAuth, service principal, user auth, on-behalf-of, access token, scopes）

**應用程式資源**：當將 app 連接到 Databricks 資源時，請使用 [2-app-resources.md](2-app-resources.md) — 涵蓋 SQL warehouse、Lakebase、模型服務、機密、Volume，以及 `valueFrom` 模式。（關鍵字：resources, valueFrom, SQL warehouse, model serving, secrets, volumes, connections）

**框架**：Databricks 各框架專用模式請見 [3-frameworks.md](3-frameworks.md) — 涵蓋 Dash、Streamlit、Gradio、Flask、FastAPI 與 Reflex，包含授權整合、部署指令與 Cookbook links。（關鍵字：Dash, Streamlit, Gradio, Flask, FastAPI, Reflex, framework selection）

**部署**：部署 app 時請使用 [4-deployment.md](4-deployment.md) — 涵蓋 Databricks CLI、Asset Bundles (DABs)、`app.yaml` 設定與部署後驗證。（關鍵字：deploy, CLI, DABs, asset bundles, app.yaml, logs）

**Lakebase**：當使用 Lakebase（PostgreSQL）作為 app 的資料層時，請使用 [5-lakebase.md](5-lakebase.md) — 涵蓋自動注入的 env vars、psycopg2/asyncpg 模式，以及何時選擇 Lakebase 或 SQL warehouse。（關鍵字：Lakebase, PostgreSQL, psycopg2, asyncpg, transactional, PGHOST）

**MCP 工具**：使用 MCP 工具管理 app 生命週期時，請使用 [6-mcp-approach.md](6-mcp-approach.md) — 涵蓋以程式化方式建立、部署、監控與刪除 apps。（關鍵字：MCP, create app, deploy app, app logs）

**Foundation Models**：呼叫 Databricks foundation model APIs 時，請參閱 [examples/llm_config.py](examples/llm_config.py) — 涵蓋 OAuth M2M auth、相容 OpenAI 的 client wiring 與 token caching。（關鍵字：foundation model, LLM, OpenAI client, chat completions）

---

## 工作流程

1. 先判斷任務類型：

   **要從零開始建立新 app？** → 使用 [框架選擇](#框架選擇)，然後閱讀 [3-frameworks.md](3-frameworks.md)
   **正在設定授權？** → 閱讀 [1-authorization.md](1-authorization.md)
   **正在連接資料／資源？** → 閱讀 [2-app-resources.md](2-app-resources.md)
   **正在使用 Lakebase (PostgreSQL)？** → 閱讀 [5-lakebase.md](5-lakebase.md)
   **正在部署到 Databricks？** → 閱讀 [4-deployment.md](4-deployment.md)
   **正在使用 MCP 工具？** → 閱讀 [6-mcp-approach.md](6-mcp-approach.md)
   **正在呼叫 foundation model/LLM APIs？** → 請參閱 [examples/llm_config.py](examples/llm_config.py)

2. 遵循相關指南中的指示
3. 若需完整程式碼範例，請瀏覽 https://apps-cookbook.dev/

---

## 核心架構

所有 Python Databricks apps 都遵循此模式：

```
app-directory/
├── app.py                 # 主要應用程式（或框架專用名稱）
├── models.py              # Pydantic 資料模型
├── backend.py             # 資料存取層
├── requirements.txt       # 額外的 Python 依賴
├── app.yaml               # Databricks Apps 設定
└── README.md
```

### 後端切換模式

```python
import os
from databricks.sdk.core import Config

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

if USE_MOCK:
    from backend_mock import MockBackend as Backend
else:
    from backend_real import RealBackend as Backend

backend = Backend()
```

### SQL Warehouse 連線（所有框架共用）

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()  # 自動從環境偵測認證資訊
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)
```

### Pydantic 模型

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class Status(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"

class EntityOut(BaseModel):
    id: str
    name: str
    status: Status
    created_at: datetime

class EntityIn(BaseModel):
    name: str = Field(..., min_length=1)
    status: Status = Status.PENDING
```

---

## 常見問題

| 問題 | 解決方案 |
|-------|----------|
| **連線已耗盡** | 使用 `@st.cache_resource`（Streamlit）或 connection pooling |
| **找不到授權權杖** | 檢查 `x-forwarded-access-token` header — 只在部署後可用，不會在本機提供 |
| **App 無法啟動** | 檢查 `app.yaml` 指令是否與框架相符；檢查 `databricks apps logs <name>` |
| **無法存取資源** | 透過 UI 新增資源、確認 SP 具有權限，並在 `app.yaml` 使用 `valueFrom` |
| **部署時發生匯入錯誤** | 將缺少的套件加入 `requirements.txt`（預先安裝的套件不需列出） |
| **Lakebase app 啟動時當機** | `psycopg2`/`asyncpg` **並未**預先安裝 — **MUST** 加入 `requirements.txt` |
| **port 衝突** | Apps 必須繫結到 `DATABRICKS_APP_PORT` 環境變數（預設為 8000）。Streamlit 由 runtime 自動設定；其他框架請在程式碼中讀取該 env var，或在 `app.yaml` 指令中使用 8000。絕不要使用 8080 |
| **Streamlit：set_page_config 錯誤** | `st.set_page_config()` 必須是第一個 Streamlit 指令 |
| **Dash：layout 未套用樣式** | 加入 `dash-bootstrap-components`；使用 `dbc.themes.BOOTSTRAP` |
| **查詢緩慢** | 交易型／低延遲請使用 Lakebase；分析型查詢請使用 SQL warehouse |

---

## 平台限制

| 限制 | 詳細資訊 |
|------------|---------|
| **執行環境** | Python 3.11、Ubuntu 22.04 LTS |
| **運算資源** | 2 vCPUs、6 GB 記憶體（預設） |
| **預先安裝的框架** | Dash、Streamlit、Gradio、Flask、FastAPI、Shiny |
| **自訂套件** | 加到 app root 的 `requirements.txt` |
| **網路** | Apps 可存取 Databricks APIs；是否能對外連線取決於 workspace 設定 |
| **使用者授權** | Public Preview — 工作區管理員必須先啟用，才能新增 scopes |

---

## 官方文件

- **[Databricks Apps Overview](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)** — 主要文件入口
- **[Apps Cookbook](https://apps-cookbook.dev/)** — 可直接使用的程式碼片段（Streamlit、Dash、Reflex、FastAPI）
- **[Authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)** — 應用程式授權與使用者授權
- **[Resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)** — SQL warehouse、Lakebase、serving、機密
- **[app.yaml Reference](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)** — command 與 env 設定
- **[System Environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)** — 預先安裝的套件與 runtime 細節

## 相關 Skills

- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - 使用 FastAPI + React 的全端 apps
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - 透過 DABs 部署 apps
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - 後端 SDK 整合
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - 新增持久化的 PostgreSQL 狀態
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - 提供 ML models 以供 app 整合
'@

Write-Utf8NoBom -Path (Join-Path $base '1-authorization.md') -Content @'
# Databricks Apps 的授權

Databricks Apps 支援兩種互補的授權模型。可依 app 需求擇一使用或同時使用。

**官方文件**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth

---

## 應用程式授權（服務主體）

每個 app 都會取得專屬的服務主體。Databricks 會自動注入認證資訊：

- `DATABRICKS_CLIENT_ID` — OAuth client ID
- `DATABRICKS_CLIENT_SECRET` — OAuth client secret

**不需要手動讀取這些值。** SDK `Config()` 會自動偵測它們：

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()  # 自動從環境偵測 SP 認證資訊
conn = sql.connect(
    server_hostname=cfg.host,
    http_path="/sql/1.0/warehouses/<id>",
    credentials_provider=lambda: cfg.authenticate,
)
```

**適用於**：背景工作、共用資料存取、記錄日誌、呼叫外部服務。

**限制**：所有使用者共用相同權限 — 無法進行依使用者區分的存取控制。

---

## 使用者授權（On-Behalf-Of／代理存取）

讓 app 能以目前使用者的身分運作。Databricks 會透過 HTTP header 將使用者的存取權杖轉送給 app。

**適用於**：使用者專屬資料查詢、Unity Catalog 列／欄篩選、稽核軌跡。

**前置條件**：workspace admin 必須先啟用使用者授權（Public Preview）。在 UI 建立／編輯 app 時加入 scopes。

### 各框架取得使用者權杖的方式

```python
# Streamlit
import streamlit as st
user_token = st.context.headers.get("x-forwarded-access-token")

# Dash / Flask
from flask import request
user_token = request.headers.get("x-forwarded-access-token")

# Gradio
import gradio as gr
def handler(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")

# FastAPI
from fastapi import Request
async def endpoint(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")

# Reflex
user_token = session.http_conn.headers.get("x-forwarded-access-token")
```

### 使用使用者權杖查詢

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()
user_token = get_user_token()  # 使用上方各框架的方法

conn = sql.connect(
    server_hostname=cfg.host,
    http_path="/sql/1.0/warehouses/<id>",
    access_token=user_token,  # 使用者的權杖，不是 SP 認證資訊
)
```

---

## 結合兩種模型

共用操作使用應用程式授權，使用者專屬資料則使用使用者授權：

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()

def get_app_connection(warehouse_http_path: str):
    """應用程式授權 — 共用資料、記錄日誌、背景工作。"""
    return sql.connect(
        server_hostname=cfg.host,
        http_path=warehouse_http_path,
        credentials_provider=lambda: cfg.authenticate,
    )

def get_user_connection(warehouse_http_path: str, user_token: str):
    """使用者授權 — 遵循 Unity Catalog 列／欄篩選。"""
    return sql.connect(
        server_hostname=cfg.host,
        http_path=warehouse_http_path,
        access_token=user_token,
    )
```

---

## OAuth 範圍

新增使用者授權時，只選擇 app 需要的 scopes：

| Scope | 授予存取項目 |
|-------|-----------------|
| `sql` | SQL warehouse 查詢 |
| `files.files` | 檔案與目錄 |
| `dashboards.genie` | Genie spaces |
| `iam.access-control:read` | 存取控制（預設） |
| `iam.current-user:read` | 目前使用者身分（預設） |

**最佳實務**：要求最小必要 scopes。即使使用者具備更廣的權限，Databricks 仍會封鎖核准 scopes 之外的存取。

---

## 何時使用哪一種

| 情境 | 模型 |
|----------|-------|
| 所有使用者看到相同資料 | 僅應用程式授權 |
| 使用者專屬列／欄篩選 | 使用者授權 |
| 背景 jobs、記錄日誌 | 應用程式授權 |
| 依使用者區分的稽核軌跡 | 使用者授權 |
| 混合共用資料與個人資料 | 兩者皆用 |

---

## 最佳實務

- 絕對不要記錄、print，或將權杖寫入檔案
- 為服務主體授予資源上的最小必要權限
- 僅對受信任的開發人員使用 `CAN MANAGE`；app 使用者使用 `CAN USE`
- 在生產環境部署前，對 app 程式碼落實 peer review
- Cookbook 授權範例：[Streamlit](https://apps-cookbook.dev/docs/streamlit/authentication/users_get_current) · [Dash](https://apps-cookbook.dev/docs/dash/authentication/users_get_current) · [Reflex](https://apps-cookbook.dev/docs/reflex/authentication/users_get_current)
'@

Write-Utf8NoBom -Path (Join-Path $base '2-app-resources.md') -Content @'
# 應用程式資源與連線策略

Databricks Apps 透過受控連線整合平台資源。請使用資源，而不是硬編碼 IDs，以確保可攜性與安全性。

**官方文件**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources

---

## 支援的資源類型

| 資源 | 預設 Key | 權限 | 使用情境 |
|----------|-------------|-------------|----------|
| SQL warehouse | `sql-warehouse` | 可使用、可管理 | 查詢 Delta tables |
| Lakebase database | `database` | 可連線並建立 | 低延遲交易型資料 |
| Model serving endpoint | `serving-endpoint` | 可檢視、可查詢、可管理 | AI/ML 推論 |
| Secret | `secret` | 可讀取、可寫入、可管理 | API keys、權杖 |
| Unity Catalog volume | `volume` | 可讀取、可讀寫 | 檔案儲存 |
| Vector search index | `vector-search-index` | 可選取 | 語意搜尋 |
| Genie space | `genie-space` | 可檢視、可執行、可編輯 | 自然語言分析 |
| UC connection | `connection` | 使用 Connection | 外部資料來源 |
| UC function | `function` | 可執行 | SQL/Python functions |
| MLflow experiment | `experiment` | 可讀取、可編輯 | ML 實驗追蹤 |
| Lakeflow job | `job` | 可檢視、可管理執行 | 資料管線 |

---

## 在 app.yaml 中設定資源

使用 `valueFrom` 參照資源 — 絕不要硬編碼 IDs：

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse

  - name: SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint

  - name: DB_CONNECTION_STRING
    valueFrom: database
```

建立或編輯 app 時，透過 Databricks Apps UI 新增資源：
1. 前往 Configure 步驟
2. 點選 **+ Add resource**
3. 選擇資源類型並設定權限
4. 指派一個 key（供 `valueFrom` 參照）

---

## 連線策略

請根據存取模式選擇資料後端：

| 策略 | 適用時機 | 函式庫 | 連線模式 |
|----------|-------------|---------|-------------------|
| **SQL Warehouse** | 對 Delta tables 進行分析型查詢 | `databricks-sql-connector` | 搭配 `Config()` 使用 `sql.connect()` |
| **Lakebase (PostgreSQL)** | 低延遲交易型 CRUD | `psycopg2` / `asyncpg` | 透過自動注入的 env vars 使用標準 PostgreSQL |
| **Databricks SDK** | 平台 API 呼叫（jobs、clusters、UC） | `databricks-sdk` | `WorkspaceClient()` |
| **Model Serving** | AI/ML 推論請求 | `requests` 或 SDK | 對 serving endpoint 進行 REST 呼叫 |
| **Unity Catalog Functions** | 伺服器端運算（SQL/Python UDFs） | `databricks-sql-connector` | 透過 SQL warehouse 執行 |

### SQL Warehouse 模式

```python
import os
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)

with conn.cursor() as cursor:
    cursor.execute("SELECT * FROM catalog.schema.table LIMIT 100")
    rows = cursor.fetchall()
```

### Model Serving 模式

```python
import os, requests
from databricks.sdk.core import Config

cfg = Config()
headers = cfg.authenticate()
headers["Content-Type"] = "application/json"

endpoint = os.getenv("SERVING_ENDPOINT_NAME")
response = requests.post(
    f"https://{cfg.host}/serving-endpoints/{endpoint}/invocations",
    headers=headers,
    json={"inputs": [{"prompt": "你好"}]},
)
result = response.json()
```

### SDK 模式

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # 自動偵測認證資訊
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")
```

Lakebase 模式請參閱 [5-lakebase.md](5-lakebase.md)。

---

## 最佳實務

- 一律使用 `valueFrom` — 讓 apps 能在不同環境間保持可攜性
- 為服務主體授予最小必要權限（例如 SQL warehouse 使用 `CAN USE`，而非 `CAN MANAGE`）
- 交易型工作負載使用 Lakebase；分析型工作負載使用 SQL warehouse
- 對外部服務請使用 UC connections 或機密（絕不要硬編碼 API keys）
'@

Write-Utf8NoBom -Path (Join-Path $base '3-frameworks.md') -Content @'
# 支援的框架

以下所有框架都已**預先安裝**在 Databricks Apps runtime 中。Claude 已經知道如何使用它們 — 本指南只涵蓋 **Databricks 專屬**模式。若需完整範例與實作配方，請參閱 **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**。

---

## Dash

**最適合**：生產環境儀表板、BI 工具、複雜互動式視覺化。

**重要**：務必使用 `dash-bootstrap-components` 進行 layout 與 styling。

```python
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="我的儀表板",
)
```

| 項目 | 值 |
|--------|-------|
| 預先安裝版本 | 2.18.1 |
| app.yaml 指令 | `["python", "app.py"]` |
| 預設 port | 8050 — 在程式碼中覆寫：`app.run(port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))` |
| 授權 header | `request.headers.get('x-forwarded-access-token')`（底層為 Flask） |

**Databricks 提示**：
- 使用 `dbc.themes.BOOTSTRAP` 與 `dbc.icons.FONT_AWESOME` 維持一致樣式
- `dbc.Badge` 請使用 Bootstrap badge 色彩名稱（`"success"`、`"danger"`），不要使用 hex colors
- 對高成本 callbacks 使用 `prevent_initial_call=True`
- 使用 `dcc.Store` 進行 client-side caching

**Cookbook**: [apps-cookbook.dev/docs/category/dash](https://apps-cookbook.dev/docs/category/dash) — 資料表、Volume、AI/ML、工作流程、儀表板、運算、授權、外部服務。

---

## Streamlit

**最適合**：快速原型製作、data science apps、內部工具、從 notebook 到 app 的工作流程。

**重要**：務必對資料庫連線使用 `@st.cache_resource`。

```python
import streamlit as st
from databricks.sdk.core import Config
from databricks import sql

st.set_page_config(page_title="我的 App", layout="wide")  # 必須是第一個！

@st.cache_resource(ttl=300)
def get_connection():
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
```

| 項目 | 值 |
|--------|-------|
| 預先安裝版本 | 1.38.0 |
| app.yaml 指令 | `["streamlit", "run", "app.py"]` |
| 授權 header | `st.context.headers.get('x-forwarded-access-token')` |

**Databricks 提示**：
- `st.set_page_config()` **必須**是第一個 Streamlit 指令
- 連線／models 使用 `@st.cache_resource`；查詢結果使用 `@st.cache_data(ttl=...)`
- 使用 `st.form()` 批次處理輸入，避免每次按鍵都 rerun
- 對格式化 DataFrames（貨幣、日期）使用 `st.column_config`

**Cookbook**: [apps-cookbook.dev/docs/category/streamlit](https://apps-cookbook.dev/docs/category/streamlit) — 資料表、Volume、AI/ML、工作流程、視覺化、儀表板、運算、授權、外部服務。

---

## Gradio

**最適合**：ML model demos、聊天介面、影像／音訊／影片處理 UI。

**重要**：使用 `gr.Request` 參數存取授權 headers。

```python
import os
import gradio as gr
import requests
from databricks.sdk.core import Config

cfg = Config()

def predict(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")
    # 查詢 model serving endpoint
    headers = {**cfg.authenticate(), "Content-Type": "application/json"}
    resp = requests.post(
        f"https://{cfg.host}/serving-endpoints/my-model/invocations",
        headers=headers,
        json={"inputs": [{"prompt": message}]},
    )
    return resp.json()["predictions"][0]

demo = gr.Interface(fn=predict, inputs="text", outputs="text")
port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
demo.launch(server_name="0.0.0.0", server_port=port)
```

| 項目 | 值 |
|--------|-------|
| 預先安裝版本 | 4.44.0 |
| app.yaml 指令 | `["python", "app.py"]` |
| 預設 port | 7860 — 在程式碼中覆寫：`server_port=int(os.environ.get("DATABRICKS_APP_PORT", 8000))` |
| 授權 header | 透過 `gr.Request` 使用 `request.headers.get('x-forwarded-access-token')` |

**Databricks 提示**：
- 非常適合整合 model serving endpoint
- 對話式 AI demos 請使用 `gr.ChatInterface`
- 複雜多元件 layout 請使用 `gr.Blocks`

**官方文件**: [gradio.app/docs](https://www.gradio.app/docs)

---

## Flask

**最適合**：自訂 REST APIs、輕量 web apps、webhook receivers。

**重要**：請以 Gunicorn 部署 — 在生產環境絕不要使用 Flask 的 dev server。

```python
from flask import Flask, request, jsonify
from databricks.sdk.core import Config
from databricks import sql

app = Flask(__name__)
cfg = Config()

@app.route("/api/data")
def get_data():
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return jsonify(cursor.fetchall())
```

| 項目 | 值 |
|--------|-------|
| 預先安裝版本 | 3.0.3 |
| app.yaml 指令 | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| 授權 header | `request.headers.get('x-forwarded-access-token')` |

**Databricks 提示**：
- 使用 connection pooling（Flask 不會像 Streamlit 一樣快取連線）
- Gunicorn workers（`-w 4`）可處理並行 requests
- 使用 `request.headers` 取得使用者授權權杖

---

## FastAPI

**最適合**：現代非同步 APIs、自動產生的 OpenAPI/Swagger 文件、高效能後端。

**重要**：請以 uvicorn 部署。

```python
from fastapi import FastAPI, Request
from databricks.sdk.core import Config
from databricks import sql

app = FastAPI(title="我的 API")
cfg = Config()

@app.get("/api/data")
async def get_data(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        access_token=user_token,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return cursor.fetchall()
```

| 項目 | 值 |
|--------|-------|
| 預先安裝版本 | 0.115.0 |
| app.yaml 指令 | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| 授權 header | 透過 `Request` 使用 `request.headers.get('x-forwarded-access-token')` |

**Databricks 提示**：
- 會在 `/docs`（Swagger）與 `/redoc` 自動產生 OpenAPI 文件
- Databricks SQL connector 為同步式 — 非同步端點請使用 `asyncio.to_thread()`
- 很適合作為提供 APX (FastAPI + React) apps 的 API 後端

**Cookbook**: [apps-cookbook.dev/docs/category/fastapi](https://apps-cookbook.dev/docs/category/fastapi) — 入門與端點範例。

---

## Reflex

**最適合**：具反應式 UI 的全端 Python apps，無需 JavaScript。

```python
import reflex as rx
from databricks.sdk.core import Config

cfg = Config()

class State(rx.State):
    data: list[dict] = []

    def load_data(self):
        from databricks import sql
        conn = sql.connect(
            server_hostname=cfg.host,
            http_path="/sql/1.0/warehouses/<id>",
            credentials_provider=lambda: cfg.authenticate,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
            self.data = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
```

| 項目 | 值 |
|--------|-------|
| app.yaml 指令 | `["reflex", "run", "--env", "prod"]` |
| 授權 header | `session.http_conn.headers.get('x-forwarded-access-token')` |

**Cookbook**: [apps-cookbook.dev/docs/category/reflex](https://apps-cookbook.dev/docs/category/reflex) — 資料表、Volume、AI/ML、工作流程、儀表板、運算、授權、外部服務。

---

## 共通事項：所有框架

- 所有框架都已**預先安裝** — 無需將它們加入 `requirements.txt`
- 只需將 app 額外需要的套件加入 `requirements.txt`
- SDK `Config()` 會從注入的環境變數自動偵測認證資訊
- Apps 必須繫結到 `DATABRICKS_APP_PORT` env var（預設為 8000）。Streamlit 由 runtime 自動設定；其他框架請在程式碼中讀取該 env var，或在 `app.yaml` 指令中硬編碼 8000。絕不要使用 8080
- 各框架專用的部署指令請見 [4-deployment.md](4-deployment.md)
- 授權整合請見 [1-authorization.md](1-authorization.md)
'@

Write-Utf8NoBom -Path (Join-Path $base '4-deployment.md') -Content @'
# 部署 Databricks Apps

有三種部署選項：Databricks CLI（最簡單）、Asset Bundles（多環境），或 MCP 工具（程式化）。

**Cookbook 部署指南**: https://apps-cookbook.dev/docs/deploy

---

## 選項 1：Databricks CLI

**最適合**：快速部署、單一環境。

### 步驟 1：建立 app.yaml

```yaml
command:
  - "python"        # 依框架調整 — 請見下表
  - "app.py"

env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: USE_MOCK_BACKEND
    value: "false"
```

### 各框架的 app.yaml 指令

| Framework | 指令 |
|-----------|---------|
| Dash | `["python", "app.py"]` |
| Streamlit | `["streamlit", "run", "app.py"]` |
| Gradio | `["python", "app.py"]` |
| Flask | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| FastAPI | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| Reflex | `["reflex", "run", "--env", "prod"]` |

### 步驟 2：建立並部署

```bash
# 建立 app
databricks apps create <app-name>

# 上傳原始碼
databricks workspace mkdirs /Workspace/Users/<user>/apps/<app-name>
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>

# 部署
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>

# 透過 UI 新增資源（SQL warehouse、Lakebase 等）

# 檢查狀態與 URL
databricks apps get <app-name>
```

### 重新部署

```bash
databricks workspace delete /Workspace/Users/<user>/apps/<app-name> --recursive
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name>
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name>
```

---

## 選項 2：Databricks Asset Bundles (DABs)

**最適合**：多環境部署（dev/staging/prod）、版本控制的基礎架構。

**建議工作流程**：先透過 CLI 部署以驗證，再產生 bundle 設定。

### 從既有 App 產生 Bundle

```bash
databricks bundle generate app \
  --existing-app-name <app-name> \
  --key <resource_key>
```

這會建立：
- `resources/<key>.app.yml` — app 資源定義
- `src/app/` — 包含 `app.yaml` 的 app 原始檔

### 使用 Bundles 部署

```bash
# 驗證
databricks bundle validate -t dev

# 部署
databricks bundle deploy -t dev

# 啟動 app（部署後必須執行）
databricks bundle run <resource_key> -t dev

# 生產環境
databricks bundle deploy -t prod
databricks bundle run <resource_key> -t prod
```

**與其他資源的關鍵差異**：環境變數要放在 `src/app/app.yaml`，而不是 `databricks.yml`。

若需完整 DABs 指引，請使用 **databricks-bundles** skill。

---

## 選項 3：MCP 工具

若要以程式化方式管理 app 生命週期，請參閱 [6-mcp-approach.md](6-mcp-approach.md)。

---

## 部署後

### 檢查日誌

```bash
databricks apps logs <app-name>
```

**日誌中的重要模式**：
- `[SYSTEM]` — 部署狀態、檔案更新、依賴安裝
- `[APP]` — 應用程式輸出、框架訊息
- `部署成功` — app 已正確部署
- `App 啟動成功` — app 正在執行
- `錯誤：` — 檢查 stack traces

### 驗證

1. 存取 app URL（來自 `databricks apps get <app-name>`）
2. 檢查所有頁面是否正確載入
3. 驗證資料連線能力（查看 logs 中的後端初始化訊息）
4. 若已啟用，測試使用者授權流程

### 設定權限

- 為核准的使用者／群組設定 `CAN USE`
- 僅對受信任的開發人員設定 `CAN MANAGE`
- 確認服務主體具備所需的資源權限
'@

Write-Utf8NoBom -Path (Join-Path $base '5-lakebase.md') -Content @'
# Lakebase (PostgreSQL) 連線

Lakebase 透過受管的 PostgreSQL 介面，為 Databricks Apps 提供低延遲的交易型儲存。

**官方文件**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase

---

## 何時使用 Lakebase

| 使用情境 | 建議後端 |
|----------|-------------------|
| 對 Delta tables 進行分析型查詢 | SQL Warehouse |
| 低延遲交易型 CRUD | **Lakebase** |
| app 專屬 metadata/config | **Lakebase** |
| 使用者 session 資料 | **Lakebase** |
| 大規模資料探索 | SQL Warehouse |

---

## 設定

1. 在 Databricks UI 將 Lakebase 新增為 app 資源（資源類型：**Lakebase database**）
2. Databricks 會自動注入 PostgreSQL 連線 env vars：

| 變數 | 說明 |
|----------|-------------|
| `PGHOST` | 資料庫主機名稱 |
| `PGDATABASE` | 資料庫名稱 |
| `PGUSER` | PostgreSQL role（每個 app 皆會建立） |
| `PGPASSWORD` | role 密碼 |
| `PGPORT` | port（通常為 5432） |

3. 在 `app.yaml` 中參照：

```yaml
env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
```

---

## 連線模式

### psycopg2（同步）

```python
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    database=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT", "5432"),
)

with conn.cursor() as cur:
    cur.execute("SELECT * FROM my_table LIMIT 10")
    rows = cur.fetchall()

conn.close()
```

### asyncpg（非同步）

```python
import os
import asyncpg

async def get_data():
    conn = await asyncpg.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=int(os.getenv("PGPORT", "5432")),
    )
    rows = await conn.fetch("SELECT * FROM my_table LIMIT 10")
    await conn.close()
    return rows
```

### SQLAlchemy

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = (
    f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
    f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT', '5432')}"
    f"/{os.getenv('PGDATABASE')}"
)

engine = create_engine(DATABASE_URL)
```

---

## 搭配 Lakebase 的 Streamlit

```python
import streamlit as st
import psycopg2

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
    )
```

---

## 重要：requirements.txt

`psycopg2` 與 `asyncpg` 在 Databricks Apps runtime 中**並未預先安裝**。你 **MUST** 在 `requirements.txt` 中加入它們，否則 app 啟動時會當機：

```
psycopg2-binary
```

對於 async apps：
```
asyncpg
```

**這是 Lakebase app 失敗最常見的原因。**

## 備註

- Lakebase 為 **Public Preview**
- 每個 app 都有自己的 PostgreSQL role，具備 `Can connect and create` 權限
- Lakebase 很適合與 SQL warehouse 搭配使用：app 狀態使用 Lakebase，分析則使用 SQL warehouse
'@

Write-Utf8NoBom -Path (Join-Path $base '6-mcp-approach.md') -Content @'
# MCP 工具與 App 生命週期

使用 MCP 工具以程式化方式建立、部署與管理 Databricks Apps。這與 CLI 工作流程相對應，但可由 AI agents 呼叫。

---

## 工作流程

### 步驟 1：在本機撰寫 App 檔案

在本機資料夾中建立你的 app 檔案：

```
my_app/
├── app.py             # 主要應用程式
├── models.py          # Pydantic 模型
├── backend.py         # 資料存取層
├── requirements.txt   # 額外依賴
└── app.yaml           # Databricks Apps 設定
```

### 步驟 2：上傳到 Workspace

```python
# MCP 工具：upload_folder
upload_folder(
    local_folder="/path/to/my_app",
    workspace_folder="/Workspace/Users/user@example.com/my_app"
)
```

### 步驟 3：建立並部署 App

```python
# MCP 工具：create_or_update_app（必要時建立 + 部署）
result = create_or_update_app(
    name="my-dashboard",
    description="客戶分析儀表板",
    source_code_path="/Workspace/Users/user@example.com/my_app"
)
# 回傳：{"name": "my-dashboard", "url": "...", "created": True, "deployment": {...}}
```

### 步驟 4：驗證

```python
# MCP 工具：get_app（含 logs）
app = get_app(name="my-dashboard", include_logs=True)
# 回傳：{"name": "...", "url": "...", "status": "RUNNING", "logs": "...", ...}
```

### 步驟 5：反覆調整

1. 修正本機檔案中的問題
2. 使用 `upload_folder` 重新上傳
3. 使用 `create_or_update_app` 重新部署（會更新既有 app 並部署）
4. 使用 `get_app(name=..., include_logs=True)` 檢查錯誤
5. 重複以上步驟，直到 app 狀態健康

---

## 快速參考：MCP 工具

| 工具 | 說明 |
|------|-------------|
| **`create_or_update_app`** | 若 app 不存在則建立，並可選擇部署（傳入 `source_code_path`） |
| **`get_app`** | 依名稱取得 app 詳細資訊（使用 `include_logs=True` 可含 logs），或列出所有 apps |
| **`delete_app`** | 刪除 app |
| **`upload_folder`** | 將本機資料夾上傳到 workspace（共用工具） |

---

## 備註

- 建立 app 後，透過 Databricks Apps UI 新增資源（SQL warehouse、Lakebase 等）
- MCP 工具使用服務主體的權限 — 請確認它能存取所需資源
- 若要手動部署，請參閱 [4-deployment.md](4-deployment.md)
'@
