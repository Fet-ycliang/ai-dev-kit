# AI Dev Kit 整合範例

此目錄示範如何將 `ai-dev-kit` 嵌入您自己的應用程式。

**您可獲得的內容：** 與 `databricks-builder-app` 相同、以 Claude Agent SDK 為基礎的 agent，並包含：
- Databricks MCP tools（SQL、clusters、jobs、pipelines、Unity Catalog 等）
- 透過 Skills 提供的引導式開發支援（SDP、SDK patterns、MLflow 等）
- 透過 contextvars 實作的多使用者認證支援

## 先決條件

- Python 3.11+
- 建議使用 [uv](https://github.com/astral-sh/uv) 套件管理器，也可使用 pip
- Databricks workspace，且具備：
  - SQL warehouse（用於 SQL 查詢）
  - Personal Access Token（PAT）
- Claude API 存取能力（Anthropic API key 或 Databricks Model Serving 皆可）

## 快速開始

### 1. 將此目錄複製到您的專案

```bash
cp -r _integration-example /path/to/your/project/
cd /path/to/your/project/_integration-example
```

### 2. 執行設定

```bash
./setup.sh
```

此步驟會建立虛擬環境、安裝依賴，並設定 skills。

### 3. 設定憑證

建立 `.env` 檔案：

```bash
# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# Claude API（選項 A：直接使用 Anthropic）
ANTHROPIC_API_KEY=sk-ant-...

# Claude API（選項 B：Databricks Model Serving）
# ANTHROPIC_BASE_URL=https://your-workspace.cloud.databricks.com/serving-endpoints/anthropic
# ANTHROPIC_AUTH_TOKEN=dapi...  # 使用您的 Databricks PAT
# ANTHROPIC_MODEL=databricks-claude-sonnet-4
```

### 4. 執行範例

```bash
source .venv/bin/activate
python example_integration.py
```

## 整合指南

### 底層機制

此整合使用：
- **Claude Agent SDK** (`claude-agent-sdk`)：Anthropic 用來讓 Claude 以 agent 形式運作的 SDK
- **Databricks MCP Tools** (`databricks-mcp-server`)：透過 MCP protocol 以 in-process 方式載入的工具
- **Skills**：位於 `.claude/skills/` 的 Markdown 檔案，提供領域專屬指引

`stream_agent_response` 函式與 `databricks-builder-app` 使用的是同一套實作。

### 匯入方式

```python
# Agent 服務（內部使用 claude-agent-sdk）
from server.services.agent import stream_agent_response

# 每個請求的 Databricks 憑證工具
from databricks_tools_core import set_databricks_auth, clear_databricks_auth
```

### 基本用法

```python
import asyncio

async def run_agent(message: str):
    # 為此請求設定 Databricks auth（傳遞給 MCP tools）
    set_databricks_auth(
        host="https://your-workspace.cloud.databricks.com",
        token="dapi..."
    )

    try:
        async for event in stream_agent_response(
            project_id="my-project",
            message=message,
        ):
            # 處理事件
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool_use":
                print(f"
[Tool: {event['tool_name']}]")
            elif event["type"] == "tool_result":
                print(f"[Result: {event['content'][:100]}...]")
            elif event["type"] == "error":
                print(f"Error: {event['error']}")
    finally:
        clear_databricks_auth()

asyncio.run(run_agent("List my SQL warehouses"))
```

### 事件類型

agent 會串流下列事件類型：

| Event Type | 說明 | 主要欄位 |
|------------|------|----------|
| `text_delta` | 逐 token 文字輸出 | `text` |
| `text` | 完整文字區塊 | `text` |
| `thinking_delta` | 逐 token thinking | `thinking` |
| `thinking` | 完整 thinking 區塊 | `thinking` |
| `tool_use` | 工具呼叫開始 | `tool_name`, `tool_input`, `tool_id` |
| `tool_result` | 工具執行完成 | `content`, `is_error`, `tool_use_id` |
| `result` | 工作階段完成 | `session_id`, `duration_ms`, `total_cost_usd` |
| `error` | 發生錯誤 | `error` |
| `keepalive` | 連線 keepalive | `elapsed_since_last_event` |

### 可用工具

agent 可透過 MCP 使用 Databricks 工具：

- **SQL**：`execute_sql`, `execute_sql_multi`, `list_warehouses`, `get_table_details`
- **Compute**：`list_clusters`, `execute_databricks_command`, `run_python_file_on_databricks`
- **Jobs**：`create_job`, `run_job_now`, `wait_for_run`, `list_runs`
- **Pipelines**：`create_or_update_pipeline`, `start_update`, `get_update`
- **Files**：`upload_file`, `upload_folder`
- **Unity Catalog**：catalog、schema、table、volume 相關操作

### 設定 Context

您可以傳入額外 context，幫助 agent 更有效工作：

```python
async for event in stream_agent_response(
    project_id="my-project",
    message="Create a table",
    # 選用 context
    warehouse_id="abc123",           # 預設 SQL warehouse
    cluster_id="def456",             # 預設 Python 執行 cluster
    default_catalog="my_catalog",    # 預設 Unity Catalog
    default_schema="my_schema",      # 預設 schema
    workspace_folder="/Users/me/",   # 檔案上傳用的 workspace folder
):
    ...
```

### 工作階段管理

可使用 session ID 延續對話：

```python
# 第一則訊息 - 從 result 事件取得 session_id
session_id = None
async for event in stream_agent_response(project_id="demo", message="Hello"):
    if event["type"] == "result":
        session_id = event["session_id"]

# 後續訊息 - 傳入 session_id 以延續對話
async for event in stream_agent_response(
    project_id="demo",
    message="What did I just ask?",
    session_id=session_id,  # 接續工作階段
):
    ...
```

## 自訂方式

### 新增自訂 Skills

Skills 是提供專門指引的 Markdown 檔案。若要新增 skill：

1. 在您的專案中建立 `.claude/skills/my-skill/SKILL.md`
2. agent 會自動發現並使用它們

### 修改 System Prompt

若要自訂 agent 行為，您可以包裝 `stream_agent_response`，並透過 `ClaudeAgentOptions` 的 `system_prompt` 參數注入自訂的 system prompt。

## 疑難排解

### 「Module not found」錯誤

請確認您已啟用虛擬環境：
```bash
source .venv/bin/activate
```

### 認證失敗

請確認 `DATABRICKS_HOST` 結尾沒有 `/`，且 token 仍然有效。

### Tools 逾時

長時間執行的工具（>10 秒）會自動切換為 async 模式。agent 會回傳 `operation_id`，您可使用 `check_operation_status` 查詢結果。

## 檔案結構

```
_integration-example/
├── README.md               # 本檔案
├── requirements.txt        # 依賴
├── setup.sh                # 一鍵設定
├── example_integration.py  # 可運作範例
└── .claude/
    └── skills/             # 由 setup.sh 安裝
```
