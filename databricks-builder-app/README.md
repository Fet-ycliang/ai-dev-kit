# Databricks Builder App

一個提供 Claude Code 代理介面並整合 Databricks 工具的網頁應用程式。使用者可透過聊天介面與 Claude 互動，代理程式能在其 Databricks 工作區執行 SQL 查詢、管理 Pipeline、上傳檔案等操作。

> **✅ 事件迴圈修復已實作**
>
> 我們已針對 `claude-agent-sdk` [問題 #462](https://github.com/anthropics/claude-agent-sdk-python/issues/462) 實作修補方案，該問題曾導致代理程式在 FastAPI 環境中無法執行 Databricks 工具。
>
> **解決方案：** 代理程式現在於獨立執行緒中的全新事件迴圈執行，並正確複製 `contextvars` 以保留 Databricks 驗證資訊。詳情請參閱 [EVENT_LOOP_FIX.md](./EVENT_LOOP_FIX.md)。
>
> **狀態：** ✅ 完全正常運作 — 代理程式可成功執行所有 Databricks 工具

## 架構概覽

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Web Application                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  React Frontend (client/)           FastAPI Backend (server/)               │
│  ┌─────────────────────┐            ┌─────────────────────────────────┐     │
│  │ Chat UI             │◄──────────►│ /api/invoke_agent               │     │
│  │ Project Selector    │   SSE      │ /api/projects                   │     │
│  │ Conversation List   │            │ /api/conversations              │     │
│  └─────────────────────┘            └─────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Claude Code Session                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Each user message spawns a Claude Code agent session via claude-agent-sdk  │
│                                                                              │
│  Built-in Tools:              MCP Tools (Databricks):         Skills:       │
│  ┌──────────────────┐         ┌─────────────────────────┐    ┌───────────┐  │
│  │ Read, Write, Edit│         │ execute_sql             │    │ sdp       │  │
│  │ Glob, Grep, Skill│         │ create_or_update_pipeline    │ dabs      │  │
│  └──────────────────┘         │ upload_folder           │    │ sdk       │  │
│                               │ run_python_file         │    │ ...       │  │
│                               │ ...                     │    └───────────┘  │
│                               └─────────────────────────┘                   │
│                                          │                                  │
│                                          ▼                                  │
│                               ┌─────────────────────────┐                   │
│                               │ databricks-mcp-server   │                   │
│                               │ (in-process SDK tools)  │                   │
│                               └─────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Databricks Workspace                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  SQL Warehouses    │    Clusters    │    Unity Catalog    │    Workspace    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 運作原理

### 1. Claude Code 工作階段

當使用者傳送訊息時，後端會透過 `claude-agent-sdk` 建立一個 Claude Code 工作階段：

```python
from claude_agent_sdk import ClaudeAgentOptions, query

options = ClaudeAgentOptions(
    cwd=str(project_dir),           # Project working directory
    allowed_tools=allowed_tools,     # Built-in + MCP tools
    permission_mode='bypassPermissions',  # Auto-accept all tools including MCP
    resume=session_id,               # Resume previous conversation
    mcp_servers=mcp_servers,         # Databricks MCP server config
    system_prompt=system_prompt,     # Databricks-focused prompt
    setting_sources=['user', 'project'],  # Load skills from .claude/skills
)

async for msg in query(prompt=message, options=options):
    yield msg  # Stream to frontend
```

主要特性：
- **工作階段續接**：每個對話儲存 `claude_session_id`，以維持上下文連續性
- **串流傳輸**：所有事件（文字、思考、工具呼叫、工具結果）均即時串流至前端
- **專案隔離**：每個專案擁有獨立的工作目錄，具備沙盒式檔案存取控制

### 2. 驗證流程

本應用程式支援多使用者驗證，採用每次請求的個人憑證：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Authentication Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Production (Databricks Apps)         Development (Local)                   │
│  ┌──────────────────────────┐         ┌──────────────────────────┐          │
│  │ Request Headers:         │         │ Environment Variables:   │          │
│  │ X-Forwarded-User         │         │ DATABRICKS_HOST          │          │
│  │ X-Forwarded-Access-Token │         │ DATABRICKS_TOKEN         │          │
│  └────────────┬─────────────┘         └────────────┬─────────────┘          │
│               │                                    │                        │
│               └──────────────┬─────────────────────┘                        │
│                              ▼                                              │
│               ┌──────────────────────────┐                                  │
│               │ set_databricks_auth()    │  (contextvars)                   │
│               │ - host                   │                                  │
│               │ - token                  │                                  │
│               └────────────┬─────────────┘                                  │
│                            ▼                                                │
│               ┌──────────────────────────┐                                  │
│               │ get_workspace_client()   │  (used by all tools)             │
│               │ - Returns client with    │                                  │
│               │   context credentials    │                                  │
│               └──────────────────────────┘                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**運作方式：**

1. **接收請求** — FastAPI 後端擷取憑證：
   - **正式環境**：`X-Forwarded-User` 與 `X-Forwarded-Access-Token` 標頭（由 Databricks Apps Proxy 設定）
   - **開發環境**：退而使用 `DATABRICKS_HOST` 與 `DATABRICKS_TOKEN` 環境變數

2. **設定驗證情境** — 呼叫代理程式前：
   ```python
   from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

   set_databricks_auth(workspace_url, user_token)
   try:
       # All tool calls use this user's credentials
       async for event in stream_agent_response(...):
           yield event
   finally:
       clear_databricks_auth()
   ```

3. **工具使用情境** — 所有 Databricks 工具呼叫 `get_workspace_client()`，該函式會：
   - 優先從 contextvars 取得每次請求的憑證
   - 若未設定情境，則退而使用環境變數

這確保每位使用者的請求都採用其 Databricks 憑證，實現妥善的存取控制與稽核日誌記錄。

### 3. MCP 整合（Databricks 工具）

Databricks 工具透過 Claude Agent SDK 的 MCP Server 功能以同程序方式載入：

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

# Tools are dynamically loaded from databricks-mcp-server
server = create_sdk_mcp_server(name='databricks', tools=sdk_tools)

options = ClaudeAgentOptions(
    mcp_servers={'databricks': server},
    allowed_tools=['mcp__databricks__execute_sql', ...],
)
```

工具以 `mcp__databricks__<tool_name>` 形式公開，包含：
- SQL 執行（`execute_sql`、`execute_sql_multi`）
- Warehouse 管理（`list_warehouses`、`get_best_warehouse`）
- Cluster 執行（`execute_databricks_command`、`run_python_file_on_databricks`）
- Pipeline 管理（`create_or_update_pipeline`、`start_update` 等）
- 檔案操作（`upload_file`、`upload_folder`）

### 4. Skills 系統

Skills 為 Databricks 開發任務提供專業指導，是包含指令與範例的 Markdown 檔案，供 Claude 按需載入。

**Skills 載入流程：**
1. 啟動時，Skills 從 `../databricks-skills/` 複製至 `./skills/`
2. 建立專案時，Skills 複製至 `project/.claude/skills/`
3. 代理程式可使用 `Skill` 工具載入：`skill: "sdp"`

可用 Skills：
- **databricks-bundles**：DABs 設定
- **databricks-app-apx**：APX 框架全端應用程式（FastAPI + React）
- **databricks-app-python**：Dash、Streamlit、Flask Python 應用程式
- **databricks-python-sdk**：Python SDK 使用模式
- **databricks-mlflow-evaluation**：MLflow 評估與追蹤分析
- **databricks-spark-declarative-pipelines**：Spark 宣告式管線（SDP）開發
- **databricks-synthetic-data-gen**：建立測試資料集

### 5. 專案持久化

專案儲存於本機檔案系統，並自動備份至 PostgreSQL：

```
projects/
  <project-uuid>/
    .claude/
      skills/        # Copied skills for this project
    src/             # User's code files
    ...
```

**備份機制：**
- 每次代理程式互動後，專案被標記為待備份
- 背景工作者每 10 分鐘執行一次
- 專案打包成 ZIP 儲存至 PostgreSQL（Lakebase）
- 存取時，缺失的專案會從備份還原

## 安裝設定

### 前置需求

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) 套件管理工具
- Databricks 工作區，需包含：
  - SQL Warehouse（執行 SQL 查詢）
  - Cluster（執行 Python/PySpark）
  - 已啟用 Unity Catalog（建議）
- PostgreSQL 資料庫（Lakebase）用於專案持久化 — 自動擴充或固定容量

### 快速開始

#### 1. 執行安裝腳本

從倉庫根目錄執行：

```bash
cd databricks-builder-app
./scripts/setup.sh
```

此腳本會：

- 確認前置需求（uv、Node.js、npm）
- 從 `.env.example` 建立 `.env.local`（若尚不存在）
- 透過 `uv sync` 安裝後端 Python 相依套件
- 安裝同層套件（`databricks-tools-core`、`databricks-mcp-server`）
- 安裝前端 Node.js 相依套件

#### 2. 設定您的 `.env.local` 檔案

> **在啟動應用程式前必須完成此步驟。** 安裝腳本會從 `.env.example` 建立 `.env.local`，但所有值均為佔位符。請開啟 `.env.local` 並填入實際值。

`.env.local` 已加入 .gitignore，永遠不會被提交。至少需要設定以下項目：

```bash
# 必填：您的 Databricks 工作區
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# 必填：專案持久化資料庫（選擇一種方式）

# 方式 A — 自動擴充 Lakebase（建議，閒置時縮減至零）：
LAKEBASE_ENDPOINT=projects/<project-name>/branches/production/endpoints/primary
LAKEBASE_DATABASE_NAME=databricks_postgres

# 方式 B — 固定容量 Lakebase：
# LAKEBASE_INSTANCE_NAME=your-lakebase-instance
# LAKEBASE_DATABASE_NAME=databricks_postgres

# 方式 C — 靜態連線 URL（任何類型，本機開發最簡便）：
# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database?sslmode=require
```

應用程式會根據設定的變數自動偵測模式：
- `LAKEBASE_ENDPOINT` → 自動擴充模式（`client.postgres` API，主機自動查詢）
- `LAKEBASE_INSTANCE_NAME` → 固定容量模式（`client.database` API）
- `LAKEBASE_PG_URL` → 靜態 URL 模式（不需 OAuth token 重新整理）

所有可用設定（包含 LLM 提供者、Skills 設定與 MLflow 追蹤）請參閱 `.env.example`。應用程式啟動時載入 `.env.local`（非 `.env`）。

**取得 Databricks Token：**
1. 進入您的 Databricks 工作區
2. 點選使用者名稱 → 使用者設定
3. 前往 Developer → Access Tokens → Generate New Token
4. 複製 Token 值

#### 3. 啟動開發伺服器

```bash
./scripts/start_dev.sh
```

此指令在同一個終端機視窗同時啟動後端與前端。

若您希望分開啟動：

```bash
# 終端機 1 — 後端
uvicorn server.app:app --reload --port 8000 --reload-dir server

# 終端機 2 — 前端
cd client && npm run dev
```

#### 4. 存取應用程式

- **前端**：<http://localhost:3000>
- **後端 API**：<http://localhost:8000>
- **API 文件**：<http://localhost:8000/docs>

#### 5. （選用）透過 Databricks Model Serving 設定 Claude

若您要將 Claude API 呼叫透過 Databricks Model Serving 路由（而非直接呼叫 Anthropic），請在**倉庫根目錄**（非應用程式目錄）建立 `.claude/settings.json`：

```json
{
    "env": {
        "ANTHROPIC_MODEL": "databricks-claude-sonnet-4-5",
        "ANTHROPIC_BASE_URL": "https://your-workspace.cloud.databricks.com/serving-endpoints/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "dapi...",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "databricks-claude-opus-4-5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "databricks-claude-sonnet-4-5"
    }
}
```

注意事項：

- `ANTHROPIC_AUTH_TOKEN` 應填入 Databricks PAT，而非 Anthropic API Key
- `ANTHROPIC_BASE_URL` 應指向您的 Databricks Model Serving 端點
- 若此檔案不存在，應用程式將使用 `.env.local` 中的 `ANTHROPIC_API_KEY`

### 設定說明

#### Databricks 驗證模式

本應用程式支援兩種驗證模式：

**1. 本機開發（環境變數）**
- 使用 `.env.local` 中的 `DATABRICKS_HOST` 與 `DATABRICKS_TOKEN`
- 所有使用者共用相同憑證
- 適合本機開發與測試

**2. 正式環境（請求標頭）**
- 使用 `X-Forwarded-User` 與 `X-Forwarded-Access-Token` 標頭
- 由 Databricks Apps Proxy 自動設定
- 每位使用者擁有各自的憑證
- 完善的多使用者隔離

#### Skills 設定

Skills 從 `../databricks-skills/` 載入，並由 `ENABLED_SKILLS` 環境變數篩選：

- `databricks-python-sdk`：Databricks Python SDK 使用模式
- `databricks-spark-declarative-pipelines`：SDP/DLT Pipeline 開發
- `databricks-synthetic-data-gen`：建立測試資料集
- `databricks-app-apx`：APX 框架的全端應用程式（含 React）
- `databricks-app-python`：Dash、Streamlit、Flask Python 應用程式

**新增自訂 Skills：**
1. 在 `../databricks-skills/` 中建立新目錄
2. 新增包含前置資訊的 `SKILL.md` 檔案：
   ```markdown
   ---
   name: my-skill
   description: "技能說明"
   ---
   
   # 技能內容
   ```
3. 將技能名稱加入 `.env.local` 的 `ENABLED_SKILLS`

#### 資料庫設定

本應用程式使用 PostgreSQL（Lakebase）儲存：
- 專案 Metadata
- 對話歷史
- 訊息記錄
- 專案備份（打包的專案檔案）

**資料庫遷移：**
```bash
# 執行遷移（應用程式啟動時自動執行）
alembic upgrade head

# 建立新的遷移
alembic revision --autogenerate -m "description"
```

### 疑難排解

#### 「MCP 連線不穩定」或代理程式未執行工具

此為 `claude-agent-sdk` 在 FastAPI 環境中的已知問題，我們已實作修復：

- ✅ 代理程式在獨立執行緒的全新事件迴圈中執行
- ✅ 上下文變數（Databricks 驗證）正確傳播
- ✅ 所有 MCP 工具運作正常

技術細節請參閱 [EVENT_LOOP_FIX.md](./EVENT_LOOP_FIX.md)。

#### Skills 未載入

請確認：
1. `.env.local` 中的 `ENABLED_SKILLS` 環境變數
2. Skill 名稱與 `../databricks-skills/` 中的目錄名稱相符
3. 每個 Skill 目錄包含具有正確前置資訊的 `SKILL.md` 檔案
4. 查看日誌：`Copied X skills to ./skills`

#### Databricks 驗證失敗

請確認：
1. `DATABRICKS_HOST` 正確（末尾無斜線）
2. `DATABRICKS_TOKEN` 有效且未過期
3. Token 具備適當權限（Cluster 存取、SQL Warehouse 存取等）
4. 若使用 Databricks Model Serving，請確認 `.claude/settings.json` 設定

#### 埠號已被佔用

```bash
# 終止佔用 8000 與 3000 埠號的程序
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```

### 正式版建置

```bash
# 建置前端
cd client && npm run build && cd ..

# 以 uvicorn 執行
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## 專案結構

```
databricks-builder-app/
├── server/                 # FastAPI 後端
│   ├── app.py             # FastAPI 主程式
│   ├── db/                # 資料庫模型與遷移
│   │   ├── models.py      # SQLAlchemy 模型
│   │   └── database.py    # 工作階段管理
│   ├── routers/           # API 端點
│   │   ├── agent.py       # /api/agent/*（invoke 等）
│   │   ├── projects.py    # /api/projects/*
│   │   └── conversations.py
│   └── services/          # 業務邏輯
│       ├── agent.py       # Claude Code 工作階段管理
│       ├── databricks_tools.py  # 從 SDK 載入 MCP 工具
│       ├── user.py        # 使用者驗證（標頭/環境變數）
│       ├── skills_manager.py
│       ├── backup_manager.py
│       └── system_prompt.py
├── client/                # React 前端
│   ├── src/
│   │   ├── pages/         # 主要頁面（ProjectPage 等）
│   │   └── components/    # UI 元件
│   └── package.json
├── alembic/               # 資料庫遷移
├── scripts/               # 公用腳本
│   └── start_dev.sh       # 開發環境啟動腳本
├── skills/                # 快取 Skills（已加入 .gitignore）
├── projects/              # 專案工作目錄（已加入 .gitignore）
├── pyproject.toml         # Python 相依套件
└── .env.example           # 環境設定範本
```

## API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/me` | GET | 取得目前使用者資訊 |
| `/api/health` | GET | 健康狀態檢查 |
| `/api/system_prompt` | GET | 預覽系統提示詞 |
| `/api/projects` | GET | 列出所有專案 |
| `/api/projects` | POST | 建立新專案 |
| `/api/projects/{id}` | GET | 取得專案詳細資訊 |
| `/api/projects/{id}` | PATCH | 更新專案名稱 |
| `/api/projects/{id}` | DELETE | 刪除專案 |
| `/api/projects/{id}/conversations` | GET | 列出專案對話 |
| `/api/projects/{id}/conversations` | POST | 建立新對話 |
| `/api/projects/{id}/conversations/{cid}` | GET | 取得含訊息的對話 |
| `/api/projects/{id}/files` | GET | 列出專案目錄中的檔案 |
| `/api/invoke_agent` | POST | 啟動代理程式執行（回傳 execution_id） |
| `/api/stream_progress/{execution_id}` | POST | 代理程式事件的 SSE 串流 |
| `/api/stop_stream/{execution_id}` | POST | 取消進行中的執行 |
| `/api/projects/{id}/skills/available` | GET | 列出 Skills 及啟用狀態 |
| `/api/projects/{id}/skills/enabled` | PUT | 更新專案的已啟用 Skills |
| `/api/projects/{id}/skills/reload` | POST | 從來源重新載入 Skills |
| `/api/projects/{id}/skills/tree` | GET | 取得 Skills 檔案樹 |
| `/api/projects/{id}/skills/file` | GET | 取得 Skill 檔案內容 |
| `/api/clusters` | GET | 列出可用的 Databricks Cluster |
| `/api/warehouses` | GET | 列出可用的 SQL Warehouse |
| `/api/mlflow/status` | GET | 取得 MLflow 追蹤狀態 |

## 部署至 Databricks Apps

本節說明如何將 Builder App 部署至 Databricks Apps 平台供正式環境使用。

### 前置需求

部署前請確認：

1. 已安裝並驗證 **Databricks CLI**
2. 用於建置前端的 **Node.js 18+**
3. Databricks 工作區中的 **Lakebase 執行個體**（用於資料庫持久化）
4. 存取**完整倉庫**（非僅此目錄），因為應用程式依賴同層套件

### 快速部署

```bash
# 1. 使用 Databricks CLI 驗證身份
databricks auth login --host https://your-workspace.cloud.databricks.com

# 2. 建立 App（僅首次需要）
databricks apps create my-builder-app

# 3. 設定 app.yaml（複製並編輯範本）
cp app.yaml.example app.yaml
# 編輯 app.yaml — 設定 LAKEBASE_ENDPOINT（自動擴充）或 LAKEBASE_INSTANCE_NAME（固定容量）

# 4. （僅限固定容量 Lakebase）將 Lakebase 加入為 App 資源
#    若使用自動擴充可略過此步驟 — 它直接透過 OAuth 連線。
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>

# 5. 部署
./scripts/deploy.sh my-builder-app

# 6. 授予應用程式服務主體資料庫權限（請參閱第 7 節）
```

### 逐步部署指南

#### 1. 安裝並驗證 Databricks CLI

```bash
# 安裝 Databricks CLI
pip install databricks-cli

# 驗證身份（互動式瀏覽器登入）
databricks auth login --host https://your-workspace.cloud.databricks.com

# 確認驗證狀態
databricks auth describe
```

若您有多個設定檔，請在部署前設定：
```bash
export DATABRICKS_CONFIG_PROFILE=your-profile-name
```

#### 2. 建立 Databricks App

```bash
# 建立新 App
databricks apps create my-builder-app

# 確認已建立
databricks apps get my-builder-app
```

#### 3. 建立 Lakebase 執行個體

應用程式需要 PostgreSQL 資料庫（Lakebase）儲存專案、對話與訊息。

**自動擴充 Lakebase**（建議 — 閒置時縮減至零）：
1. 進入 Databricks 工作區 → **Catalog** → **Lakebase**
2. 點選 **Create** → 選擇 **Autoscale**
3. 記下端點資源名稱（例如：`projects/my-app/branches/production/endpoints/primary`）
4. 在 `app.yaml` 中設定：`LAKEBASE_ENDPOINT=projects/my-app/branches/production/endpoints/primary`

**固定容量 Lakebase**（固定容量）：
1. 前往 **Catalog** → **Lakebase** → **Create** → 選擇 **Provisioned**
2. 記下執行個體名稱（例如：`my-lakebase-instance`）
3. 在 `app.yaml` 中設定：`LAKEBASE_INSTANCE_NAME=my-lakebase-instance`

#### 4. 將 Lakebase 加入為 App 資源

**自動擴充 Lakebase**：略過此步驟。自動擴充透過 OAuth 使用 `LAKEBASE_ENDPOINT` 連線，無需 App 資源。

**固定容量 Lakebase**：將執行個體加入為 App 資源：

```bash
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>
```

這會自動設定資料庫連線環境變數（`PGHOST`、`PGPORT`、`PGUSER`、`PGPASSWORD`、`PGDATABASE`）。

#### 5. 設定 app.yaml

複製範本設定並自訂：

```bash
cp app.yaml.example app.yaml
```

編輯 `app.yaml` 填入您的設定：

```yaml
command:
  - "uvicorn"
  - "server.app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "$DATABRICKS_APP_PORT"

env:
  # 必填：Lakebase 資料庫（選擇一種方式）

  # 方式 A — 自動擴充 Lakebase（建議）：
  - name: LAKEBASE_ENDPOINT
    value: "projects/<project-name>/branches/production/endpoints/primary"
  - name: LAKEBASE_DATABASE_NAME
    value: "databricks_postgres"

  # 方式 B — 固定容量 Lakebase：
  # - name: LAKEBASE_INSTANCE_NAME
  #   value: "<your-lakebase-instance-name>"
  # - name: LAKEBASE_DATABASE_NAME
  #   value: "databricks_postgres"

  # 要啟用的 Skills（以逗號分隔）
  - name: ENABLED_SKILLS
    value: "databricks-agent-bricks,databricks-python-sdk,databricks-spark-declarative-pipelines"

  # MLflow 追蹤（選用）
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  # - name: MLFLOW_EXPERIMENT_NAME
  #   value: "/Users/your-email@company.com/claude-code-traces"

  # 其他設定
  - name: ENV
    value: "production"
  - name: PROJECTS_BASE_DIR
    value: "./projects"
```

#### 6. 部署 App

從 `databricks-builder-app` 目錄執行部署腳本：

```bash
./scripts/deploy.sh my-builder-app
```

部署腳本會：
1. 建置 React 前端
2. 打包伺服器程式碼
3. 捆綁同層套件（`databricks-tools-core`、`databricks-mcp-server`）
4. 從 `databricks-skills/` 複製 Skills
5. 上傳所有內容至 Databricks 工作區
6. 部署 App

**略過前端建置**（若已建置完成）：
```bash
./scripts/deploy.sh my-builder-app --skip-build
```

#### 7. 授予資料庫權限

首次部署後，應用程式的服務主體需要：
1. **Lakebase OAuth 角色**（以便透過 OAuth Token 驗證）
2. 在 `builder_app` Schema 的 **PostgreSQL 授權**（以便建立/讀取/寫入資料表）

##### 步驟 7a：找到服務主體的 Client ID

```bash
SP_CLIENT_ID=$(databricks apps get my-builder-app --output json | jq -r '.service_principal_client_id')
echo $SP_CLIENT_ID
```

##### 步驟 7b：為服務主體建立 Lakebase OAuth 角色

> **重要**：請勿直接使用 PostgreSQL `CREATE ROLE`。Lakebase 自動擴充需要透過 Databricks API 建立角色，OAuth 驗證層才能識別。

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Role, RoleRoleSpec, RoleAuthMethod, RoleIdentityType

w = WorkspaceClient()

# 以您的 Branch 路徑與服務主體 Client ID 取代以下值
branch = "projects/<project-id>/branches/<branch-id>"
sp_client_id = "<sp-client-id>"

w.postgres.create_role(
    parent=branch,
    role=Role(
        spec=RoleRoleSpec(
            postgres_role=sp_client_id,
            auth_method=RoleAuthMethod.LAKEBASE_OAUTH_V1,
            identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
        )
    ),
).wait()
```

或透過 CLI：

```bash
databricks postgres create-role \
  "projects/<project-id>/branches/<branch-id>" \
  --json '{
    "spec": {
      "postgres_role": "<sp-client-id>",
      "auth_method": "LAKEBASE_OAUTH_V1",
      "identity_type": "SERVICE_PRINCIPAL"
    }
  }'
```

**固定容量 Lakebase**：不需要此步驟 — 將執行個體加入為 App 資源（步驟 4）時，驗證已自動設定。

##### 步驟 7c：授予 PostgreSQL 權限

以您自己的使用者身份連線至 Lakebase 資料庫（透過 psql 或 Notebook）並執行：

```sql
-- 將 <sp-client-id> 替換為 service_principal_client_id

-- 1. 允許服務主體建立 builder_app Schema
GRANT CREATE ON DATABASE databricks_postgres TO "<sp-client-id>";

-- 2. 建立 Schema 並授予完整存取權
CREATE SCHEMA IF NOT EXISTS builder_app;
GRANT USAGE ON SCHEMA builder_app TO "<sp-client-id>";
GRANT ALL PRIVILEGES ON SCHEMA builder_app TO "<sp-client-id>";

-- 3. 授予現有資料表/序列的存取權（若已在本機執行過遷移則需要）
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA builder_app TO "<sp-client-id>";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA builder_app TO "<sp-client-id>";

-- 4. 確保服務主體能存取其他使用者未來建立的資料表/序列
ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app
  GRANT ALL ON TABLES TO "<sp-client-id>";
ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app
  GRANT ALL ON SEQUENCES TO "<sp-client-id>";
```

授予權限後，請重新部署應用程式以使新角色執行遷移。

#### 8. 存取您的應用程式

部署成功後，腳本將顯示您的 App URL：
```
App URL: https://my-builder-app-1234567890.aws.databricksapps.com
```

### 部署疑難排解

#### 「無法判斷 Databricks 工作區」

您的 Databricks CLI 驗證可能無效或使用了錯誤的設定檔：
```bash
# 查看可用設定檔
databricks auth profiles

# 使用特定設定檔
export DATABRICKS_CONFIG_PROFILE=your-valid-profile

# 如需重新驗證
databricks auth login --host https://your-workspace.cloud.databricks.com
```

#### 「找不到建置目錄 client/out」

前端建置缺失。部署腳本應會自動建置，但您也可以手動建置：
```bash
cd client
npm install
npm run build
cd ..
```

#### 「找不到 Skill 'X'」

Skills 從同層 `databricks-skills/` 目錄複製。請確認：
1. 從完整倉庫執行部署腳本（非僅此目錄）
2. `ENABLED_SKILLS` 中的 Skill 名稱與 `databricks-skills/` 中的目錄名稱相符
3. Skill 目錄包含 `SKILL.md` 檔案

#### 「password authentication failed」或「Permission denied for table projects」

完整設定步驟請參閱[第 7 節：授予資料庫權限](#7-授予資料庫權限)。

常見原因：

| 錯誤 | 原因 | 修復方式 |
|------|------|---------|
| `password authentication failed` | Lakebase OAuth 角色缺失或透過 SQL 建立 | 透過 `w.postgres.create_role()` 以 `LAKEBASE_OAUTH_V1` 驗證建立角色（步驟 7b） |
| `permission denied for table` | 服務主體缺少 Schema/資料表的 PostgreSQL 授權 | 執行 GRANT 語句（步驟 7c） |
| `schema "builder_app" does not exist` | 服務主體缺少資料庫的 `CREATE` 權限 | `GRANT CREATE ON DATABASE databricks_postgres TO "<sp-client-id>"` |
| `relation does not exist` | 遷移尚未執行 | 重新部署應用程式，或在本機執行 `alembic upgrade head` |

> **自動擴充 Lakebase 注意事項**：請勿在 PostgreSQL 中直接使用 `CREATE ROLE ... LOGIN`。
> Lakebase 自動擴充需要透過 Databricks API 建立角色，OAuth Token 驗證才能正常運作。
> 手動建立的角色會得到 `NO_LOGIN` 驗證方式，導致「password authentication failed」錯誤。

#### 應用程式顯示空白頁面或「Not Found」

在 Databricks 中查看應用程式日誌：
```bash
databricks apps logs my-builder-app
```

常見原因：
- 前端檔案未正確部署（確認暫存中存在 `client/out`）
- 資料庫連線問題（確認已加入 Lakebase 資源）
- Python import 錯誤（查看日誌中的 traceback）

#### 重新部署後的變更

```bash
# 完整重新部署（重建前端）
./scripts/deploy.sh my-builder-app

# 快速重新部署（略過前端建置）
./scripts/deploy.sh my-builder-app --skip-build
```

### MLflow 追蹤

本應用程式支援 Claude Code 對話的 MLflow 追蹤。啟用方式：

1. 在 `app.yaml` 中設定 `MLFLOW_TRACKING_URI=databricks`
2. 可選擇性設定 `MLFLOW_EXPERIMENT_NAME` 指定特定實驗路徑

追蹤記錄將出現在 Databricks MLflow UI 中，包含：
- 使用者提示與 Claude 回應
- 工具使用情況與結果
- 工作階段 Metadata

詳情請參閱 [Databricks MLflow 追蹤文件](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code)。

## 嵌入至其他應用程式

若您希望將 Databricks 代理程式嵌入至自有應用程式，請參閱以下整合範例：

```
scripts/_integration-example/
```

此範例提供最小可運作示例與設定說明，說明如何將代理程式服務整合至外部框架。

## 相關套件

- **databricks-tools-core**：核心 MCP 功能與 SQL 操作
- **databricks-mcp-server**：公開 Databricks 工具的 MCP Server
- **databricks-skills**：Databricks 開發的 Skill 定義
