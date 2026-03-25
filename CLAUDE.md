# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 語言規範

所有程式碼**註解、docstring、文件（.md 檔）、commit 訊息、錯誤訊息**均須使用**繁體中文**。程式碼識別子（變數名、函式名、類別名）維持英文。詳細規範請參閱 `.claude/skills/project-guidelines/SKILL.md`。

## Commit 訊息格式

格式：`type: 描述（繁體中文）`，type 為 `feat`、`fix`、`docs`、`style`、`refactor`、`test`、`chore` 之一。

## 專案架構

四個主要元件，各自獨立運作但有依賴關係：

```
ai-dev-kit/
├── databricks-tools-core/   # Python 程式庫，提供高層次 Databricks 操作
├── databricks-mcp-server/   # MCP 伺服器，透過 FastMCP 公開工具
├── databricks-skills/       # Markdown skills，提供 Databricks 模式指引
└── databricks-builder-app/  # 全端 Web 應用（FastAPI + React）
```

**依賴關係：**
- `databricks-mcp-server` 依賴 `databricks-tools-core`（僅封裝其函式）
- `databricks-builder-app` 在本地開發時從 sibling 目錄以 editable 模式安裝兩者；在 Databricks Apps 部署時則透過 `packages/` 目錄打包

## 常用指令

### Lint 與格式化（databricks-tools-core / databricks-mcp-server）

```bash
# 檢查 lint 錯誤（line-length=120, Python 3.11）
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

### Lint 與格式化（databricks-builder-app）

Builder App 使用不同規則（line-length=100、indent-width=2、single quotes）：

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

### Builder App 開發

```bash
cd databricks-builder-app
./scripts/setup.sh          # 首次安裝（需設定 .env.local）
./scripts/start_dev.sh      # 啟動開發伺服器（後端 :8000 / 前端 :3000）
```

## MCP 伺服器架構

`databricks-mcp-server/databricks_mcp_server/server.py` 是入口點，透過**具副作用的匯入**（side-effectful imports）自動向 FastMCP 註冊工具——每個 `tools/` 模組都會在匯入時執行 `@mcp.tool` 裝飾器。

**Windows 特殊處理（`server.py`）：** Windows 的 `ProactorEventLoop` 與 FastMCP 的 stdio transport 有 deadlock 問題，因此伺服器對 `subprocess.run`/`Popen` 做了 monkey-patch（強制 stdin=DEVNULL），並將所有同步工具函式包裝進 `asyncio.to_thread()` 執行。新增工具時須注意此行為。

## Skills 結構

每個 `databricks-skills/<skill-name>/` 目錄必須包含 `SKILL.md`，且需有 YAML frontmatter：

```yaml
---
name: skill-name          # 小寫字母、數字、連字號；≤64 字元；禁用 "anthropic"、"claude"
description: 技能說明     # 非空；≤1024 字元；禁止 XML 標籤
---
```

新增 skill 後，務必在 `databricks-skills/install_skills.sh` 中的對應變數裡登記，否則 CI 的 validate_skills 步驟會失敗。

## Builder App 架構補充

### 前端技術棧

React + Vite + React Router + Tailwind CSS。路由結構（`client/src/App.tsx`）：

- `/` → `HomePage`（專案列表）
- `/projects/:projectId` → `ProjectPage`（聊天對話介面）
- `/doc` → `DocPage`（skills 文件瀏覽）

兩個全域 Context：
- `UserContext`：管理認證（host / token / 用戶資訊）
- `ProjectsContext`：管理專案列表狀態

### 資料庫（PostgreSQL via Lakebase）

Builder App 支援三種資料庫連線模式，優先順序如下：
1. `LAKEBASE_PG_URL`：靜態 URL（含密碼），用於本地開發
2. `LAKEBASE_ENDPOINT` + `LAKEBASE_DATABASE_NAME`：Lakebase Autoscale，動態 OAuth token（Databricks Apps）
3. `LAKEBASE_INSTANCE_NAME` + `LAKEBASE_DATABASE_NAME`：Lakebase Provisioned，動態 OAuth token（Databricks Apps）

資料庫未設定時應用程式仍可啟動，但對話紀錄不會持久化。

### Agent Service 事件迴圈設計

`server/services/agent.py` 使用 `claude-agent-sdk` 的 `query()` 驅動對話。由於 FastAPI/uvicorn 的 event loop 與 `subprocess transport` 存在相容性問題（issue #462），agent 在獨立執行緒中以全新 event loop 執行，透過 `queue.Queue` 與主執行緒溝通並串流結果。

### Databricks Tools 載入方式

Builder App 中 Databricks 工具**以 in-process 方式**從 `databricks-mcp-server` 載入（非透過 stdio pipe），並利用 `contextvars` 為每個 user 注入對應的 auth token，以支援多使用者情境。

### 長時間工具的非同步 operation_id 模式

`server/services/databricks_tools.py` 設有 `SAFE_EXECUTION_THRESHOLD = 10`（秒）。工具執行超過此閾值時，立即回傳 `operation_id` 讓 Claude 繼續輪詢，實際執行在背景執行緒持續進行。此設計避免 Anthropic API 50 秒串流 idle timeout。相關狀態由 `server/services/operation_tracker.py` 的 `TrackedOperation` 管理（TTL 1 小時）。新增長時間 tool 時需考量此模式。

### 獨立 MCP 伺服器的工作區切換

`databricks_tools_core/auth.py` 的模組層級全域變數 `_active_profile` / `_active_host` 在 `get_workspace_client()` 的優先順序 0（最高優先）生效，由 `manage_workspace` MCP 工具呼叫 `set_active_workspace()` 設定，讓使用者在不重啟 MCP 伺服器的情況下切換 Databricks 工作區。此機制僅適用於獨立 MCP 模式（單一使用者 stdio）；Builder App 使用 `contextvars` per-request auth，不走此路徑。

## 程式碼規範重點

- **非同步 I/O**：所有 API 呼叫、資料庫查詢必須使用 `async/await`，禁止 `time.sleep()` 或同步 `requests`
- **型別標注**：公開函式必須有型別標注
- **日誌**：使用 `logger` 而非 `print`
- **Builder App 格式**：line-length=100、indent-width=2、single quotes（見 `databricks-builder-app/pyproject.toml`）
