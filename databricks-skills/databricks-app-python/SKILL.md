---
name: databricks-app-python
description: "使用 Dash、Streamlit、Gradio、Flask、FastAPI 或 Reflex 建構 Python 版 Databricks 應用程式。處理 OAuth 授權（應用程式授權與使用者授權）、應用程式資源、SQL Warehouse 及 Lakebase 連線、模型服務整合、基礎模型 API、LLM 整合與部署。適用於建立 Python 網頁應用、儀表板、ML 示範，或 Databricks 的 REST API；或使用者提及 Streamlit、Dash、Gradio、Flask、FastAPI、Reflex 或 Databricks app 時。"
---

# Databricks Python 應用程式

建構 Python 版 Databricks 應用程式。如需完整範例與食譜，請參閱 **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**。

---

## 重要規則（務必遵守）

- **必須**確認框架選擇，或使用下方的[框架選擇](#框架選擇)
- **必須**使用 SDK `Config()` 進行認證（絕不硬編碼 token）
- **必須**在 `app.yaml` 中使用 `valueFrom` 引用資源（絕不硬編碼資源 ID）
- **必須**使用 `dash-bootstrap-components` 進行 Dash 應用程式的版面與樣式設計
- **必須**使用 `@st.cache_resource` 處理 Streamlit 資料庫連線
- **必須**以 Gunicorn 部署 Flask，以 uvicorn 部署 FastAPI（不使用開發伺服器）

## 必要步驟

複製此清單並逐項確認：
```
- [ ] 已選擇框架
- [ ] 已決定授權策略：app 授權、使用者授權，或兩者皆用
- [ ] 已識別應用程式資源（SQL Warehouse、Lakebase、serving endpoint 等）
- [ ] 已決定後端資料策略（SQL Warehouse、Lakebase 或 SDK）
- [ ] 部署方式：CLI 或 DABs
```

---

## 框架選擇

| 框架 | 最適用於 | app.yaml 指令 |
|------|---------|---------------|
| **Dash** | 生產級儀表板、BI 工具、複雜互動 | `["python", "app.py"]` |
| **Streamlit** | 快速原型、資料科學應用、內部工具 | `["streamlit", "run", "app.py"]` |
| **Gradio** | ML 示範、模型介面、對話 UI | `["python", "app.py"]` |
| **Flask** | 自訂 REST API、輕量應用、webhook | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| **FastAPI** | 非同步 API、自動產生 OpenAPI 文件 | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| **Reflex** | 不需 JavaScript 的全端 Python 應用 | `["reflex", "run", "--env", "prod"]` |

**預設建議**：原型使用 **Streamlit**，生產儀表板使用 **Dash**，API 使用 **FastAPI**，ML 示範使用 **Gradio**。

---

## 快速參考

| 概念 | 說明 |
|------|------|
| **Runtime** | Python 3.11、Ubuntu 22.04、2 vCPU、6 GB RAM |
| **預裝套件** | Dash 2.18.1、Streamlit 1.38.0、Gradio 4.44.0、Flask 3.0.3、FastAPI 0.115.0 |
| **App 授權** | Service principal 透過 `Config()`——自動注入 `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` |
| **使用者授權** | `x-forwarded-access-token` 標頭——參見 [1-authorization.md](1-authorization.md) |
| **資源** | `app.yaml` 中的 `valueFrom`——參見 [2-app-resources.md](2-app-resources.md) |
| **Cookbook** | https://apps-cookbook.dev/ |
| **官方文件** | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/ |

---

## 詳細指引

**授權**：設定 app 授權或使用者授權時請讀 [1-authorization.md](1-authorization.md)——涵蓋 service principal 授權、代理使用者 token、OAuth scope 及各框架的程式碼範例。（關鍵字：OAuth、service principal、user auth、on-behalf-of、access token、scopes）

**應用程式資源**：連接 Databricks 資源時請讀 [2-app-resources.md](2-app-resources.md)——涵蓋 SQL Warehouse、Lakebase、model serving、secrets、volumes 及 `valueFrom` 模式。（關鍵字：resources、valueFrom、SQL warehouse、model serving、secrets、volumes、connections）

**框架**：各框架的 Databricks 專屬模式請見 [3-frameworks.md](3-frameworks.md)——涵蓋 Dash、Streamlit、Gradio、Flask、FastAPI 及 Reflex 的授權整合、部署指令及 Cookbook 連結。（關鍵字：Dash、Streamlit、Gradio、Flask、FastAPI、Reflex、framework selection）

**部署**：部署應用程式時請讀 [4-deployment.md](4-deployment.md)——涵蓋 Databricks CLI、Asset Bundles（DABs）、app.yaml 設定及部署後驗證。（關鍵字：deploy、CLI、DABs、asset bundles、app.yaml、logs）

**Lakebase**：以 Lakebase（PostgreSQL）作為資料層時請讀 [5-lakebase.md](5-lakebase.md)——涵蓋自動注入的環境變數、psycopg2/asyncpg 模式，以及何時選擇 Lakebase 而非 SQL Warehouse。（關鍵字：Lakebase、PostgreSQL、psycopg2、asyncpg、transactional、PGHOST）

**MCP 工具**：透過 MCP 工具管理應用程式生命週期時請讀 [6-mcp-approach.md](6-mcp-approach.md)——涵蓋以程式化方式建立、部署、監控及刪除應用程式。（關鍵字：MCP、create app、deploy app、app logs）

**基礎模型**：呼叫 Databricks 基礎模型 API 請見 [examples/llm_config.py](examples/llm_config.py)——涵蓋 OAuth M2M 認證、相容 OpenAI 的 client 設定及 token 快取。（關鍵字：foundation model、LLM、OpenAI client、chat completions）

---

## 工作流程

1. 確定任務類型：

   **從零建立新應用程式？** → 使用[框架選擇](#框架選擇)，再讀 [3-frameworks.md](3-frameworks.md)
   **設定授權？** → 讀 [1-authorization.md](1-authorization.md)
   **連接資料／資源？** → 讀 [2-app-resources.md](2-app-resources.md)
   **使用 Lakebase（PostgreSQL）？** → 讀 [5-lakebase.md](5-lakebase.md)
   **部署至 Databricks？** → 讀 [4-deployment.md](4-deployment.md)
   **使用 MCP 工具？** → 讀 [6-mcp-approach.md](6-mcp-approach.md)
   **呼叫基礎模型／LLM API？** → 見 [examples/llm_config.py](examples/llm_config.py)

2. 依照相關指引的說明操作
3. 完整程式碼範例請瀏覽 https://apps-cookbook.dev/

---

## 核心架構

所有 Python Databricks 應用程式均遵循此結構：

```
app-directory/
├── app.py                 # 主應用程式（或各框架對應的名稱）
├── models.py              # Pydantic 資料模型
├── backend.py             # 資料存取層
├── requirements.txt       # 額外的 Python 套件依賴
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

### SQL Warehouse 連線（各框架通用）

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

| 問題 | 解決方式 |
|------|---------|
| **連線耗盡** | 使用 `@st.cache_resource`（Streamlit）或連線池 |
| **找不到 auth token** | 檢查 `x-forwarded-access-token` 標頭——僅部署後可用，本地無法取得 |
| **應用程式無法啟動** | 確認 `app.yaml` 的指令與框架相符；查看 `databricks apps logs <name>` |
| **無法存取資源** | 透過 UI 新增資源，確認 SP 有權限，在 app.yaml 中使用 `valueFrom` |
| **部署時 import 錯誤** | 在 `requirements.txt` 中新增缺少的套件（預裝套件不需列出） |
| **Lakebase app 啟動時崩潰** | `psycopg2`/`asyncpg` **未**預裝——必須加入 `requirements.txt` |
| **Port 衝突** | 應用程式必須綁定 `DATABRICKS_APP_PORT` 環境變數（預設 8000）。絕不使用 8080。Streamlit 由 runtime 自動設定；其他框架請在程式碼中讀取該環境變數，或在 app.yaml 指令中使用 8000 |
| **Streamlit：set_page_config 錯誤** | `st.set_page_config()` 必須是第一個 Streamlit 指令 |
| **Dash：版面無樣式** | 加入 `dash-bootstrap-components`；使用 `dbc.themes.BOOTSTRAP` |
| **查詢緩慢** | 交易性／低延遲需求使用 Lakebase；分析查詢使用 SQL Warehouse |

---

## 平台限制

| 限制 | 說明 |
|------|------|
| **Runtime** | Python 3.11、Ubuntu 22.04 LTS |
| **運算** | 2 vCPU、6 GB 記憶體（預設） |
| **預裝框架** | Dash、Streamlit、Gradio、Flask、FastAPI、Shiny |
| **自訂套件** | 加入應用程式根目錄的 `requirements.txt` |
| **網路** | 應用程式可存取 Databricks API；對外存取取決於 workspace 設定 |
| **使用者授權** | 公開預覽版——workspace 管理員須在新增 scope 前先啟用 |

---

## 官方文件

- **[Databricks Apps 概覽](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)** — 主要文件中心
- **[Apps Cookbook](https://apps-cookbook.dev/)** — 即用程式碼片段（Streamlit、Dash、Reflex、FastAPI）
- **[授權](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)** — app 授權與使用者授權
- **[資源](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)** — SQL Warehouse、Lakebase、serving、secrets
- **[app.yaml 參考](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)** — 指令與環境設定
- **[系統環境](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)** — 預裝套件、runtime 詳細資訊

## 相關 Skills

- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** — 以 FastAPI + React 建立全端應用程式
- **[databricks-bundles](../databricks-bundles/SKILL.md)** — 透過 DABs 部署應用程式
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — 後端 SDK 整合
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** — 新增持久化 PostgreSQL 狀態
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — 提供 ML 模型供應用程式整合
