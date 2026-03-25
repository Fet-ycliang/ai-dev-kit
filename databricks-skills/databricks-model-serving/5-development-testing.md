# 開發與測試工作流程

在 Databricks 上以 MCP 為基礎開發及測試 Agent 的工作流程。

> **若 MCP 工具無法使用**，請直接使用 Databricks CLI 或 Python SDK。`databricks workspace import` 與 `databricks clusters spark-submit` 指令請參閱 [Databricks CLI 文件](https://docs.databricks.com/dev-tools/cli/)。

## 概覽

```
┌─────────────────────────────────────────────────────────────┐
│ 步驟一：在本地撰寫 Agent 程式碼（agent.py）                  │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 步驟二：上傳至工作區                                         │
│   → upload_folder MCP 工具                                  │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 步驟三：安裝套件                                             │
│   → execute_databricks_command MCP 工具                     │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 步驟四：測試 Agent（迭代）                                   │
│   → run_python_file_on_databricks MCP 工具                  │
│   → 若出錯：在本地修正，重新上傳，重新執行                   │
└─────────────────────────────────────────────────────────────┘
```

## 步驟一：建立本地檔案

建立含 Agent 的專案資料夾：

```
my_agent/
├── agent.py           # Agent 實作（ResponsesAgent）
├── test_agent.py      # 本地測試腳本
├── log_model.py       # MLflow 記錄腳本
└── requirements.txt   # 相依套件（可選）
```

### agent.py

```python
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse
from databricks_langchain import ChatDatabricks

LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

class MyAgent(ResponsesAgent):
    def __init__(self):
        self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT)

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.input]
        response = self.llm.invoke(messages)
        # 關鍵：必須使用輔助方法輸出結果
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text=response.content, id="msg_1")]
        )

AGENT = MyAgent()
mlflow.models.set_model(AGENT)
```

### test_agent.py

```python
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# 測試請求
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "What is Databricks?"}],
    context=ChatContext(user_id="test@example.com")
)

# 執行預測
result = AGENT.predict(request)
print("Response:", result.model_dump(exclude_none=True))
```

## 步驟二：上傳至工作區

使用 `upload_folder` MCP 工具：

```
upload_folder(
    local_folder="./my_agent",
    workspace_folder="/Workspace/Users/you@company.com/my_agent"
)
```

所有檔案將平行上傳。

## 步驟三：安裝套件

使用 `execute_databricks_command` 安裝相依套件：

```
execute_databricks_command(
    code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic"
)
```

**重要：** 儲存回傳的 `cluster_id` 與 `context_id` 以供後續呼叫使用——重複使用同一 context 速度更快且套件保持安裝狀態。

### 後續指令（重複使用 Context）

```
execute_databricks_command(
    code="dbutils.library.restartPython()",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## 步驟四：測試 Agent

使用 `run_python_file_on_databricks`：

```
run_python_file_on_databricks(
    file_path="./my_agent/test_agent.py",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### 測試失敗時

1. 從輸出讀取錯誤訊息
2. 修正本地檔案（`agent.py` 或 `test_agent.py`）
3. 重新上傳：`upload_folder(...)`
4. 重新執行：`run_python_file_on_databricks(...)`

### 迭代技巧

- **保持 context 存活** — 重複使用 `cluster_id` 與 `context_id` 加快迭代速度
- **套件持久存在** — 安裝後套件在 context 中保持有效
- **先確認匯入** — 完整 Agent 測試前先執行最小化測試

## 快速除錯指令

### 確認套件是否已安裝

```
execute_databricks_command(
    code="import mlflow; print(mlflow.__version__)",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### 列出可用端點

```
execute_databricks_command(
    code="""
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
for ep in list(w.serving_endpoints.list())[:10]:
    print(f"{ep.name}: {ep.state.ready if ep.state else 'unknown'}")
    """,
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### 直接測試 LLM 端點

```
execute_databricks_command(
    code="""
from databricks_langchain import ChatDatabricks
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
response = llm.invoke([{"role": "user", "content": "Hello!"}])
print(response.content)
    """,
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## 工作流程摘要

| 步驟 | MCP 工具 | 用途 |
|------|---------|------|
| 上傳檔案 | `upload_folder` | 同步本地檔案至工作區 |
| 安裝套件 | `execute_databricks_command` | 設定相依套件 |
| 重啟 Python | `execute_databricks_command` | 套用套件變更 |
| 測試 Agent | `run_python_file_on_databricks` | 執行測試腳本 |
| 除錯 | `execute_databricks_command` | 快速確認 |

## 後續步驟

Agent 測試成功後：

1. **記錄至 MLflow** → 參閱 [6-logging-registration.md](6-logging-registration.md)
2. **部署端點** → 參閱 [7-deployment.md](7-deployment.md)
3. **查詢端點** → 參閱 [8-querying-endpoints.md](8-querying-endpoints.md)
