# Databricks AI Dev Kit — 系統架構說明

本文件面向開發者，深入說明 `ai-dev-kit` 的系統架構、各元件職責及使用方式。
如需快速安裝，請參閱 [README.md](README.md)。

---

## 目錄

1. [專案概覽](#1-專案概覽)
2. [系統架構全景圖](#2-系統架構全景圖)
3. [元件詳細說明](#3-元件詳細說明)
   - [3.1 databricks-tools-core](#31-databricks-tools-core)
   - [3.2 databricks-mcp-server](#32-databricks-mcp-server)
   - [3.3 databricks-skills](#33-databricks-skills)
   - [3.4 databricks-builder-app](#34-databricks-builder-app)
4. [使用方式](#4-使用方式)
5. [開發指南（快速參考）](#5-開發指南快速參考)

---

## 1. 專案概覽

**AI Dev Kit** 是一個給 AI 程式助手（Claude Code、Cursor、Gemini CLI、Windsurf 等）使用的 **Databricks 開發工具套件**，讓開發者透過 AI 輔助更快速、更智慧地在 Databricks 平台上進行開發。

套件由四個獨立但有依賴關係的元件組成：

| 元件 | 類型 | 主要職責 |
|------|------|---------|
| `databricks-tools-core` | Python 函式庫 | 提供高層次 Databricks API 封裝，可獨立使用 |
| `databricks-mcp-server` | MCP 伺服器 | 將 tools-core 的函式公開為 50+ 個 MCP 工具 |
| `databricks-skills` | Markdown 知識庫 | 提供 Databricks 開發模式與最佳實踐指引 |
| `databricks-builder-app` | 全端 Web 應用 | 面向開發者的視覺化 AI 開發環境 |

---

## 2. 系統架構全景圖

```
使用者 ← 操作 → AI 程式助手（Claude Code / Cursor / Gemini CLI / Windsurf）
                         ↓ MCP Protocol（stdio transport）
            ┌────────────────────────────────────────────┐
            │   databricks-mcp-server（50+ MCP 工具）     │
            │   server.py → FastMCP + Windows 事件迴圈修補 │
            └────────────────────────────────────────────┘
                         ↓ 函式呼叫（Python）
            ┌────────────────────────────────────────────┐
            │   databricks-tools-core（核心 Python 函式庫）│
            │   16 個功能模組 + auth.py + client.py       │
            └────────────────────────────────────────────┘
                         ↓ Databricks SDK
            ┌────────────────────────────────────────────┐
            │   databricks-sdk（官方 Databricks Python SDK）│
            └────────────────────────────────────────────┘

獨立部署的 Web UI（可選）：
            ┌────────────────────────────────────────────┐
            │   databricks-builder-app                    │
            │   FastAPI（後端 :8000）+ React（前端 :3000）  │
            │   ├─ claude-agent-sdk 驅動對話              │
            │   ├─ in-process 載入 MCP 工具（非 stdio）   │
            │   └─ PostgreSQL（Lakebase）持久化對話紀錄    │
            └────────────────────────────────────────────┘

知識來源（純 Markdown，不含可執行程式碼）：
            ┌────────────────────────────────────────────┐
            │   databricks-skills（25 個 Skill）           │
            │   安裝至 .claude/skills/ 供 AI 助手參考      │
            └────────────────────────────────────────────┘
```

### 元件依賴關係

```
databricks-mcp-server
    └── 依賴 → databricks-tools-core（純封裝，無自身業務邏輯）

databricks-builder-app（本地開發）
    ├── 依賴 → databricks-tools-core（editable 模式安裝）
    └── 依賴 → databricks-mcp-server（in-process 載入工具）

databricks-skills
    └── 無程式碼依賴（純 Markdown 知識庫）
```

---

## 3. 元件詳細說明

### 3.1 databricks-tools-core

**定位**：核心 Python 函式庫。不依賴 MCP 協定，可獨立 `pip install` 後直接在任何 Python 專案中使用。

**功能模組（16 個）**：

| 模組路徑 | 主要功能 |
|---------|---------|
| `sql/` | SQL 語句執行、Warehouse 管理、表格統計分析 |
| `jobs/` | Job CRUD 操作、Run 觸發與執行監控 |
| `unity_catalog/` | 目錄、Schema、表格、Volume、連線、權限、Monitor、Tags |
| `spark_declarative_pipelines/` | SDP/DLT 管道建立與部署 |
| `serving/` | 模型服務端點管理 |
| `vector_search/` | 向量搜尋索引建立與查詢 |
| `agent_bricks/` | 知識助手、Genie Space、Supervisor Agent |
| `aibi_dashboards/` | AI/BI 儀表板建立與管理 |
| `apps/` | Databricks Apps 部署管理 |
| `compute/` | 無伺服器計算環境執行 |
| `file/` | Workspace 檔案操作 |
| `lakebase/` | Lakebase Provisioned 執行個體管理 |
| `lakebase_autoscale/` | Lakebase Autoscale 專案與連線管理 |
| `pdf/` | LLM 輔助 PDF 生成 |
| `dabs/` | Databricks Asset Bundle 操作 |
| `auth.py` | 認證管理與 WorkspaceClient 取得 |

**認證優先順序**（`auth.py` 中的 `get_workspace_client()`）：

| 優先序 | 來源 | 使用情境 |
|--------|------|---------|
| 0（最高）| `set_active_workspace()` 設定的工作區 | MCP 工作區切換工具 |
| 1 | `force_token` 參數（跨工作區強制 PAT） | 多工作區操作 |
| 2 | OAuth M2M（環境自動偵測） | Databricks Apps 部署環境 |
| 3 | `contextvars` 中的 PAT | Builder App per-request 多使用者認證 |
| 4（最低）| 環境變數 / `~/.databrickscfg` | 本地開發預設 |

---

### 3.2 databricks-mcp-server

**定位**：MCP 伺服器層。純粹封裝 `databricks-tools-core` 的函式，對外公開為 MCP 工具，不含自身業務邏輯。

**工具總數**：50+ 個，分佈於 18 個工具模組。

**工具模組一覽**：

| 模組 | 對應 tools-core 功能 |
|------|-------------------|
| `sql.py` | SQL 執行、Warehouse 操作 |
| `jobs.py` | Job 管理、Run 監控 |
| `unity_catalog.py` | Unity Catalog 完整操作 |
| `compute.py` | 無伺服器計算執行 |
| `pipelines.py` | Spark 宣告式管道（SDP/DLT） |
| `serving.py` | 模型服務端點 |
| `vector_search.py` | 向量搜尋 |
| `agent_bricks.py` | Agent Bricks（知識助手等） |
| `aibi_dashboards.py` | AI/BI 儀表板 |
| `apps.py` | Databricks Apps |
| `genie.py` | Genie Space 查詢 |
| `file.py` | Workspace 檔案管理 |
| `user.py` | 使用者資訊查詢 |
| `workspace.py` | 工作區管理（含 `manage_workspace` 切換工具） |
| `lakebase.py` | Lakebase Provisioned |
| `volume_files.py` | Volume 檔案操作 |
| `pdf.py` | PDF 生成 |
| `manifest.py` | MCP 工具清單 |

**架構特點**：

- **具副作用的匯入（Side-effectful imports）**：各 `tools/*.py` 模組被匯入時，模組頂層的 `@mcp.tool` 裝飾器會立即執行，自動向 FastMCP 實例 `mcp` 完成工具註冊。`server.py` 的角色只是依序 `import` 各模組，無需額外的顯式註冊呼叫。

- **Windows 事件迴圈修補**：Windows 的 `ProactorEventLoop` 與 FastMCP stdio transport 存在 deadlock 問題。`server.py` 以 monkey-patch 方式強制 `subprocess.run`/`Popen` 的 `stdin=DEVNULL`，並將所有同步工具函式包裝進 `asyncio.to_thread()` 執行。

- **工作區切換**：`manage_workspace` MCP 工具呼叫 `set_active_workspace()`，可在不重啟 MCP 伺服器的情況下於執行時切換目標 Databricks 工作區。

---

### 3.3 databricks-skills

**定位**：純 Markdown 知識庫，供 AI 程式助手參考使用。無程式碼依賴，可獨立安裝。

**技能總數**：25 個 Skill 目錄（含 `TEMPLATE`）。

**技能分類**：

| 分類 | Skill 名稱 |
|------|-----------|
| SQL 與資料 | `databricks-dbsql`、`databricks-unity-catalog`、`databricks-iceberg` |
| 管道與串流 | `databricks-spark-declarative-pipelines`、`databricks-spark-structured-streaming`、`spark-python-data-source` |
| AI / ML | `databricks-mlflow-evaluation`、`databricks-model-serving`、`databricks-vector-search`、`databricks-synthetic-data-gen` |
| 應用程式 | `databricks-app-python`、`databricks-agent-bricks`、`databricks-ai-functions`、`databricks-genie` |
| 基礎設施 | `databricks-bundles`、`databricks-jobs`、`databricks-config`、`databricks-python-sdk` |
| 資料庫 | `databricks-lakebase-autoscale`、`databricks-lakebase-provisioned`、`databricks-metric-views` |
| 其他 | `databricks-aibi-dashboards`、`databricks-docs`、`databricks-zerobus-ingest`、`databricks-unstructured-pdf-generation` |

**SKILL.md 格式要求**：每個 Skill 目錄的 `SKILL.md` 必須包含 YAML frontmatter：

```yaml
---
name: skill-name          # 小寫字母、數字、連字號；≤64 字元；禁用 "anthropic"、"claude"
description: 技能說明     # 非空；≤1024 字元；禁止 XML 標籤
---
```

新增 Skill 後，須在 `databricks-skills/install_skills.sh` 的對應變數中登記，否則 CI 的 `validate_skills` 步驟會失敗。

---

### 3.4 databricks-builder-app

**定位**：面向開發者的 Web UI，整合 Claude Agent SDK，提供視覺化的 Databricks 開發環境。

**技術棧**：
- **後端**：FastAPI + uvicorn（Python 3.11+）
- **前端**：React + Vite + React Router + Tailwind CSS
- **資料庫**：PostgreSQL（透過 Lakebase）
- **AI 引擎**：claude-agent-sdk

**後端 API 路由（FastAPI）**：

| 路由前綴 | 功能說明 |
|---------|---------|
| `GET /api/config/` | 使用者資訊、健康檢查、系統提示 |
| `GET /api/clusters/` | Databricks 叢集清單 |
| `GET /api/warehouses/` | SQL Warehouse 清單 |
| `CRUD /api/projects/` | 專案管理（建立、讀取、更新、刪除） |
| `CRUD /api/projects/{id}/conversations/` | 對話紀錄管理 |
| `POST /api/invoke_agent` | 啟動 Claude Agent（返回 `execution_id`） |
| `GET /api/stream_progress/{id}` | SSE 串流回傳執行結果（50 秒窗口） |
| `POST /api/stop_stream/{id}` | 停止正在執行的 Agent |
| `GET /api/skills/` | Skills 清單與內容查詢 |

**前端路由（React Router）**：

| URL | 頁面 | 說明 |
|-----|------|------|
| `/` | `HomePage` | 專案列表，入口頁面 |
| `/projects/:id` | `ProjectPage` | 聊天工作區，主要開發介面 |
| `/doc` | `DocPage` | Skills 文件瀏覽 |

**全域 Context**：
- `UserContext`：管理認證狀態（host / token / 用戶資訊）
- `ProjectsContext`：管理專案列表狀態

**資料庫連線模式**（依優先順序）：

| 優先序 | 環境變數 | 適用情境 |
|--------|---------|---------|
| 1 | `LAKEBASE_PG_URL` | 本地開發（靜態 URL 含密碼） |
| 2 | `LAKEBASE_ENDPOINT` + `LAKEBASE_DATABASE_NAME` | Databricks Apps（Lakebase Autoscale，動態 OAuth） |
| 3 | `LAKEBASE_INSTANCE_NAME` + `LAKEBASE_DATABASE_NAME` | Databricks Apps（Lakebase Provisioned，動態 OAuth） |

> 資料庫未設定時應用程式仍可啟動，但對話紀錄不會持久化。

**關鍵架構設計**：

1. **Agent 執行緒隔離**：`server/services/agent.py` 將 Claude Agent 在獨立執行緒中以全新 event loop 執行，透過 `queue.Queue` 與 FastAPI 主執行緒溝通並串流結果，解決 FastAPI/uvicorn event loop 與 subprocess transport 的相容性問題（[issue #462](https://github.com/anthropics/claude-code/issues/462)）。

2. **長時間工具的非同步 operation_id 模式**：`server/services/databricks_tools.py` 設有 `SAFE_EXECUTION_THRESHOLD = 10`（秒）。工具執行超過此閾值時，立即回傳 `operation_id` 讓 Claude 繼續輪詢，實際執行在背景執行緒持續進行。此設計避免 Anthropic API 50 秒串流 idle timeout。

3. **In-process MCP 工具載入**：Builder App 以 in-process 方式從 `databricks-mcp-server` 載入工具（非透過 stdio pipe），並利用 `contextvars` 為每個 request 注入對應的 auth token，以支援多使用者同時操作不同工作區。

---

## 4. 使用方式

### 4.1 安裝 AI Dev Kit 至現有專案（最常見用法）

將 MCP 工具與 Skills 安裝至您現有的工作目錄，AI 助手即可直接使用。

**Mac / Linux**：
```bash
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
```

**Windows PowerShell**：
```powershell
irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex
```

安裝完成後：
- Skills 複製至 `.claude/skills/`（或 `.cursor/rules/` 等，視您的 AI 工具而定）
- MCP 伺服器設定寫入 `.mcp.json`（或 `.cursor/mcp.json`）

### 4.2 啟動 Builder App（視覺化開發）

```bash
cd databricks-builder-app
cp .env.example .env.local
# 填入必填環境變數後執行：
./scripts/setup.sh
./scripts/start_dev.sh   # 後端 :8000、前端 :3000
```

**必填環境變數**：
```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# 擇一填入資料庫設定（不填則無對話持久化）：
LAKEBASE_PG_URL=postgresql://user:pass@host:port/db
# 或（Lakebase Autoscale）：
LAKEBASE_ENDPOINT=projects/.../endpoints/primary
LAKEBASE_DATABASE_NAME=databricks_postgres
```

### 4.3 直接使用 databricks-tools-core（Python 整合）

適合將 Databricks 操作整合至 LangChain、OpenAI Agents SDK 或其他 Python 框架。

```python
from databricks_tools_core.sql import execute_sql
from databricks_tools_core.jobs import create_job, run_job_now

# 使用環境變數或 ~/.databrickscfg 自動認證
results = execute_sql("SELECT * FROM my_catalog.schema.table LIMIT 10")
```

安裝方式：
```bash
pip install databricks-tools-core
# 或本地開發（editable 模式）：
cd databricks-tools-core && pip install -e .
```

### 4.4 安裝特定 Skills

僅安裝所需的 Skill，不安裝整套工具鏈：

```bash
cd databricks-skills
./install_skills.sh databricks-bundles databricks-python-sdk databricks-mlflow-evaluation
```

### 4.5 安裝 Skills 至 Genie Code（Databricks 原生 AI）

```bash
cd databricks-skills
./install_skills_to_genie_code.sh
# 進階：指定設定檔
./install_skills_to_genie_code.sh <profile_name>
```

安裝後 Skills 位於 `/Workspace/Users/<your_user>/.assistant/skills`，可自行修改或新增自訂 Skills。

---

## 5. 開發指南（快速參考）

### Lint 與格式化

**databricks-tools-core 與 databricks-mcp-server**（line-length=120、Python 3.11）：

```bash
# 檢查
uvx ruff@0.11.0 check \
  --select=E,F,B,PIE \
  --ignore=E401,E402,F401,F403,B017,B904,ANN,TCH \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/

# 自動修正
uvx ruff@0.11.0 check --fix \
  --select=E,F,B,PIE \
  --ignore=E401,E402,F401,F403,B017,B904,ANN,TCH \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/

# 格式化
uvx ruff@0.11.0 format \
  --line-length=120 \
  --target-version=py311 \
  databricks-tools-core/ databricks-mcp-server/
```

**databricks-builder-app**（line-length=100、indent-width=2、single quotes）：

```bash
cd databricks-builder-app
uv run ruff check server/
uv run ruff format server/
```

### 測試

```bash
# 整合測試（需連線至 Databricks workspace）
cd databricks-tools-core
uv run pytest tests/integration/ -v

# 單一整合測試
uv run pytest tests/integration/test_sql.py::test_execute_sql -v

# MCP 伺服器單元測試（不需要 Databricks 連線）
cd databricks-mcp-server
uv run pytest tests/ -v
```

### Skills 驗證

```bash
python .github/scripts/validate_skills.py
```

### Commit 訊息格式

```
type: 說明（繁體中文）
```

`type` 限定為：`feat`、`fix`、`docs`、`style`、`refactor`、`test`、`chore`

範例：
```
feat: 新增 Lakebase Autoscale 連線管理工具
fix: 修正 Windows 事件迴圈 deadlock 問題
docs: 更新系統架構說明文件
```

### 新增 MCP 工具的注意事項

1. 在 `databricks-tools-core` 新增業務函式
2. 在 `databricks-mcp-server/tools/` 新增對應封裝（以 `@mcp.tool` 裝飾）
3. 在 `server.py` 的 import 區段加入新模組的 import
4. 長時間執行（>10 秒）的工具需考量 `operation_id` 非同步模式
5. Windows 平台同步函式需透過 `asyncio.to_thread()` 呼叫

---

*最後更新：2026-03-24*
