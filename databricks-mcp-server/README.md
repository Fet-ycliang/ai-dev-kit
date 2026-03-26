# Databricks MCP Server

一個基於 [FastMCP](https://github.com/jlowin/fastmcp) 的 MCP 伺服器，將 Databricks 操作公開為 MCP 工具，供 Claude Code 等 AI 程式助手使用。

## 快速入門

### 步驟一：複製儲存庫

```bash
git clone https://github.com/Fet-ycliang/ai-dev-kit.git
cd ai-dev-kit
```

### 步驟二：安裝套件

```bash
# 安裝核心函式庫
uv pip install -e ./databricks-tools-core

# 安裝 MCP 伺服器
uv pip install -e ./databricks-mcp-server
```

### 步驟三：設定 Databricks 認證

```bash
# 方式一：環境變數
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"

# 方式二：使用 ~/.databrickscfg 中的設定檔
export DATABRICKS_CONFIG_PROFILE="your-profile"
```

### 步驟四：將 MCP 伺服器加入 AI 助手

**Claude Code**：在專案的 `.mcp.json` 中加入以下設定（若不存在則新建）。
**Cursor**：在專案的 `.cursor/mcp.json` 中加入。

```json
{
  "mcpServers": {
    "databricks": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ai-dev-kit", "python", "databricks-mcp-server/run_server.py"],
      "defer_loading": true
    }
  }
}
```

**請將 `/path/to/ai-dev-kit`** 替換為實際的複製路徑。

> **注意：** `"defer_loading": true` 可避免啟動時載入所有工具，改善啟動速度。

### 步驟五（建議）：安裝 Databricks Skills

MCP 伺服器搭配 **Databricks Skills** 效果最佳，Skills 提供 Claude 關於最佳實踐的知識：

```bash
# 在您的專案目錄（非 ai-dev-kit）執行
cd /path/to/your/project
curl -sSL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/databricks-skills/install_skills.sh | bash
```

### 步驟六：啟動 Claude Code

```bash
cd /path/to/your/project
claude
```

Claude 現在同時具備：
- **Skills（知識）** — 模式與最佳實踐，位於 `.claude/skills/`
- **MCP 工具（操作）** — 透過 MCP 伺服器執行 Databricks 操作

---

## 可用工具

### SQL 操作

| 工具 | 說明 |
|------|------|
| `execute_sql` | 在 Databricks SQL Warehouse 上執行 SQL 查詢 |
| `execute_sql_multi` | 平行執行多條 SQL 語句 |
| `list_warehouses` | 列出工作區中所有 SQL Warehouse |
| `get_best_warehouse` | 取得最佳可用 Warehouse 的 ID |
| `get_table_details` | 取得資料表的 Schema 與統計資訊 |

### 計算（Compute）

| 工具 | 說明 |
|------|------|
| `list_clusters` | 列出工作區中所有叢集 |
| `get_best_cluster` | 取得最佳可用叢集 |
| `execute_databricks_command` | 在 Databricks 叢集上執行程式碼 |
| `run_python_file_on_databricks` | 將本地 Python 檔案上傳並在叢集上執行 |

### 檔案操作

| 工具 | 說明 |
|------|------|
| `upload_folder` | 平行上傳本地資料夾至 Databricks Workspace |
| `upload_file` | 上傳單一檔案至 Workspace |

### Jobs

| 工具 | 說明 |
|------|------|
| `create_job` | 建立新 Job（預設使用無伺服器計算） |
| `get_job` | 取得 Job 詳細設定 |
| `list_jobs` | 列出 Jobs（可依名稱篩選） |
| `find_job_by_name` | 依精確名稱尋找 Job，回傳 Job ID |
| `update_job` | 更新 Job 設定 |
| `delete_job` | 刪除 Job |
| `run_job_now` | 觸發 Job 執行，回傳 Run ID |
| `get_run` | 取得 Run 狀態與詳細資訊 |
| `get_run_output` | 取得 Run 輸出與日誌 |
| `list_runs` | 列出 Runs（可依條件篩選） |
| `cancel_run` | 取消執行中的 Job |
| `wait_for_run` | 等待 Run 完成 |

### Spark 宣告式管道（SDP）

| 工具 | 說明 |
|------|------|
| `create_or_update_pipeline` | 依名稱建立或更新管道（自動偵測是否已存在） |
| `get_pipeline` | 依 ID 或名稱取得管道詳情，含最新狀態與事件；省略參數則列出所有管道 |
| `delete_pipeline` | 刪除管道 |
| `run_pipeline` | 啟動、停止或等待管道執行 |

### 知識助手（Knowledge Assistant）

| 工具 | 說明 |
|------|------|
| `manage_ka` | 管理知識助手（建立/更新、查詢、依名稱尋找、刪除） |

### Genie Spaces

| 工具 | 說明 |
|------|------|
| `create_or_update_genie` | 建立或更新 Genie Space（SQL 自然語言資料探索） |
| `get_genie` | 依 Space ID 取得 Genie Space 詳情 |
| `find_genie_by_name` | 依名稱尋找 Genie Space，回傳 Space ID |
| `delete_genie` | 刪除 Genie Space |

### Supervisor Agent（MAS）

| 工具 | 說明 |
|------|------|
| `manage_mas` | 管理 Supervisor Agent（建立/更新、查詢、依名稱尋找、刪除） |

### AI/BI 儀表板

| 工具 | 說明 |
|------|------|
| `create_or_update_dashboard` | 從 JSON 內容建立或更新 AI/BI 儀表板 |
| `get_dashboard` | 依 ID 取得儀表板詳情；省略 `dashboard_id` 則列出所有儀表板 |
| `delete_dashboard` | 軟刪除儀表板（移至垃圾桶） |
| `publish_dashboard` | 發佈或取消發佈儀表板（`publish=True/False`） |

### 模型服務（Model Serving）

| 工具 | 說明 |
|------|------|
| `get_serving_endpoint_status` | 取得模型服務端點狀態 |
| `query_serving_endpoint` | 以聊天或 ML 模型輸入查詢模型服務端點 |
| `list_serving_endpoints` | 列出工作區中所有模型服務端點 |

---

## 架構

```
┌─────────────────────────────────────────────────────────────┐
│                        Claude Code                          │
│                                                             │
│  Skills（知識）                  MCP 工具（操作）             │
│  └── .claude/skills/            └── .claude/mcp.json        │
│      ├── sdp-writer                 └── databricks server   │
│      ├── databricks-bundles                                 │
│      └── ...                                                │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP Protocol（stdio）
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              databricks-mcp-server（FastMCP）                │
│                                                             │
│  tools/sql.py ──────────────┐                               │
│  tools/compute.py ──────────┤                               │
│  tools/file.py ─────────────┤                               │
│  tools/jobs.py ─────────────┼──► @mcp.tool 裝飾器           │
│  tools/pipelines.py ────────┤                               │
│  tools/agent_bricks.py ─────┤                               │
│  tools/aibi_dashboards.py ──┤                               │
│  tools/serving.py ──────────┘                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Python 函式呼叫
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   databricks-tools-core                     │
│                                                             │
│  sql/         compute/       jobs/         pipelines/       │
│  └── 執行     └── 執行程式碼  └── 執行/等待  └── 建立/執行    │
└──────────────────────────────┬──────────────────────────────┘
                               │ Databricks SDK
                               ▼
                    ┌─────────────────────┐
                    │  Databricks         │
                    │  工作區             │
                    └─────────────────────┘
```

---

## 開發指南

伺服器設計刻意保持簡單——每個工具檔案只需從 `databricks-tools-core` 匯入函式，並以 `@mcp.tool` 裝飾即可。

**新增工具的步驟：**

1. 在 `databricks-tools-core` 新增業務函式
2. 在 `databricks_mcp_server/tools/` 建立對應的封裝模組
3. 在 `server.py` 匯入新模組

**範例：**

```python
# tools/my_module.py
from databricks_tools_core.my_module import my_function as _my_function
from ..server import mcp

@mcp.tool
def my_function(arg1: str, arg2: int = 10) -> dict:
    """工具說明，會顯示給 AI 助手參考。"""
    return _my_function(arg1=arg1, arg2=arg2)
```

---

## 使用追蹤（透過稽核日誌）

所有透過 MCP 伺服器發出的 API 呼叫，都會附帶自訂 `User-Agent` 標頭：

```
databricks-ai-dev-kit/0.1.0 databricks-sdk-py/... project/<自動偵測的儲存庫名稱>
```

專案名稱從 git remote URL 自動偵測（無需手動設定）。所有呼叫均可在 `system.access.audit` 系統資料表中依此篩選查詢。

> **注意：** 稽核日誌最多需要 2–10 分鐘才會出現。工作區須啟用 Unity Catalog 才能查詢 `system.access.audit`。

---

## 授權條款

© Databricks, Inc. 詳見 [LICENSE.md](../LICENSE.md)。
