---
name: databricks-model-serving
description: "部署並查詢 Databricks Model Serving 端點。適用於：(1) 將 MLflow 模型或 AI Agent 部署至端點；(2) 建立 ChatAgent/ResponsesAgent；(3) 整合 UC Functions 或 Vector Search 工具；(4) 查詢已部署端點；(5) 確認端點狀態。涵蓋傳統 ML 模型、自訂 pyfunc 及 GenAI Agent。"
---

# Databricks Model Serving

將 MLflow 模型與 AI Agent 部署至可擴展的 REST API 端點。

## 快速決策：您要部署什麼？

| 模型類型 | 模式 | 參考文件 |
|---------|------|---------|
| **傳統 ML**（sklearn、xgboost） | `mlflow.sklearn.autolog()` | [1-classical-ml.md](1-classical-ml.md) |
| **自訂 Python 模型** | `mlflow.pyfunc.PythonModel` | [2-custom-pyfunc.md](2-custom-pyfunc.md) |
| **GenAI Agent**（LangGraph、工具呼叫） | `ResponsesAgent` | [3-genai-agents.md](3-genai-agents.md) |

## 前置需求

- 建議使用 **DBR 16.1+**（預裝 GenAI 套件）
- 已啟用 Unity Catalog 的工作區
- 已啟用 Model Serving

## Foundation Model API 端點

務必使用下表中的精確端點名稱。切勿猜測或縮寫。

### Chat / Instruct 模型

| 端點名稱 | 提供者 | 備注 |
|---------|--------|------|
| `databricks-gpt-5-2` | OpenAI | 最新 GPT，400K context |
| `databricks-gpt-5-1` | OpenAI | Instant + Thinking 模式 |
| `databricks-gpt-5-1-codex-max` | OpenAI | 程式碼專用（高效能） |
| `databricks-gpt-5-1-codex-mini` | OpenAI | 程式碼專用（成本最佳化） |
| `databricks-gpt-5` | OpenAI | 400K context，推理能力 |
| `databricks-gpt-5-mini` | OpenAI | 成本最佳化推理 |
| `databricks-gpt-5-nano` | OpenAI | 高吞吐量，輕量 |
| `databricks-gpt-oss-120b` | OpenAI | 開放權重，128K context |
| `databricks-gpt-oss-20b` | OpenAI | 輕量開放權重 |
| `databricks-claude-opus-4-6` | Anthropic | 最強大，1M context |
| `databricks-claude-sonnet-4-6` | Anthropic | 混合推理 |
| `databricks-claude-sonnet-4-5` | Anthropic | 混合推理 |
| `databricks-claude-opus-4-5` | Anthropic | 深度分析，200K context |
| `databricks-claude-sonnet-4` | Anthropic | 混合推理 |
| `databricks-claude-opus-4-1` | Anthropic | 200K context，32K 輸出 |
| `databricks-claude-haiku-4-5` | Anthropic | 最快速，高成本效益 |
| `databricks-claude-3-7-sonnet` | Anthropic | 2026 年 4 月退役 |
| `databricks-meta-llama-3-3-70b-instruct` | Meta | 128K context，多語言 |
| `databricks-meta-llama-3-1-405b-instruct` | Meta | 2026 年 5 月退役（PT） |
| `databricks-meta-llama-3-1-8b-instruct` | Meta | 輕量，128K context |
| `databricks-llama-4-maverick` | Meta | MoE 架構 |
| `databricks-gemini-3-1-pro` | Google | 1M context，混合推理 |
| `databricks-gemini-3-pro` | Google | 1M context，混合推理 |
| `databricks-gemini-3-flash` | Google | 快速，高成本效益 |
| `databricks-gemini-2-5-pro` | Google | 1M context，Deep Think |
| `databricks-gemini-2-5-flash` | Google | 1M context，混合推理 |
| `databricks-gemma-3-12b` | Google | 128K context，多語言 |
| `databricks-qwen3-next-80b-a3b-instruct` | Alibaba | 高效 MoE |

### Embedding 模型

| 端點名稱 | 維度 | 最大 Token 數 | 備注 |
|---------|------|--------------|------|
| `databricks-gte-large-en` | 1024 | 8192 | 英文，未正規化 |
| `databricks-bge-large-en` | 1024 | 512 | 英文，已正規化 |
| `databricks-qwen3-embedding-0-6b` | 最高 1024 | ~32K | 100+ 種語言，指令感知 |

### 常用預設值

- **Agent LLM**：`databricks-meta-llama-3-3-70b-instruct`（品質與成本的良好平衡）
- **Embedding**：`databricks-gte-large-en`
- **程式碼任務**：`databricks-gpt-5-1-codex-mini` 或 `databricks-gpt-5-1-codex-max`

> 這些是每個工作區皆可使用的按 token 計費端點。生產環境請考慮使用 provisioned throughput 模式。參閱[支援的模型清單](https://docs.databricks.com/aws/en/machine-learning/foundation-model-apis/supported-models)。

## 參考文件

| 主題 | 檔案 | 何時閱讀 |
|------|------|---------|
| 傳統 ML | [1-classical-ml.md](1-classical-ml.md) | sklearn、xgboost、autolog |
| 自訂 PyFunc | [2-custom-pyfunc.md](2-custom-pyfunc.md) | 自訂前處理、簽章 |
| GenAI Agent | [3-genai-agents.md](3-genai-agents.md) | ResponsesAgent、LangGraph |
| 工具整合 | [4-tools-integration.md](4-tools-integration.md) | UC Functions、Vector Search |
| 開發與測試 | [5-development-testing.md](5-development-testing.md) | MCP 工作流程、迭代 |
| 記錄與註冊 | [6-logging-registration.md](6-logging-registration.md) | mlflow.pyfunc.log_model |
| 部署 | [7-deployment.md](7-deployment.md) | 以 Job 為基礎的非同步部署 |
| 查詢端點 | [8-querying-endpoints.md](8-querying-endpoints.md) | SDK、REST、MCP 工具 |
| 套件需求 | [9-package-requirements.md](9-package-requirements.md) | DBR 版本、pip |

---

## 快速入門：部署 GenAI Agent

### 步驟一：安裝套件（在 Notebook 中或透過 MCP）

```python
%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic
dbutils.library.restartPython()
```

或透過 MCP：
```
execute_databricks_command(code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic")
```

### 步驟二：建立 Agent 檔案

使用 `ResponsesAgent` 模式在本地建立 `agent.py`（參閱 [3-genai-agents.md](3-genai-agents.md)）。

### 步驟三：上傳至工作區

```
upload_folder(
    local_folder="./my_agent",
    workspace_folder="/Workspace/Users/you@company.com/my_agent"
)
```

### 步驟四：測試 Agent

```
run_python_file_on_databricks(
    file_path="./my_agent/test_agent.py",
    cluster_id="<cluster_id>"
)
```

### 步驟五：記錄模型

```
run_python_file_on_databricks(
    file_path="./my_agent/log_model.py",
    cluster_id="<cluster_id>"
)
```

### 步驟六：部署（透過 Job 非同步）

以 Job 為基礎的部署方式可避免逾時，詳見 [7-deployment.md](7-deployment.md)。

### 步驟七：查詢端點

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

## 快速入門：部署傳統 ML 模型

```python
import mlflow
import mlflow.sklearn
from sklearn.linear_model import LogisticRegression

# 啟用 autolog 並自動註冊
mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name="main.models.my_classifier"
)

# 訓練——模型自動記錄並註冊
model = LogisticRegression()
model.fit(X_train, y_train)
```

接著透過 UI 或 SDK 部署。參閱 [1-classical-ml.md](1-classical-ml.md)。

---

## MCP 工具

> **若 MCP 工具無法使用**，請使用下方參考文件中的 SDK/CLI 範例。

### 開發與測試

| 工具 | 用途 |
|------|------|
| `upload_folder` | 上傳 Agent 檔案至工作區 |
| `run_python_file_on_databricks` | 測試 Agent、記錄模型 |
| `execute_databricks_command` | 安裝套件、快速測試 |

### 部署

| 工具 | 用途 |
|------|------|
| `manage_jobs`（action="create"） | 建立部署 Job（一次性） |
| `manage_job_runs`（action="run_now"） | 啟動部署（非同步） |
| `manage_job_runs`（action="get"） | 確認部署 Job 狀態 |

### 查詢

| 工具 | 用途 |
|------|------|
| `get_serving_endpoint_status` | 確認端點是否 READY |
| `query_serving_endpoint` | 向端點發送請求 |
| `list_serving_endpoints` | 列出所有端點 |

---

## 常見工作流程

### 部署後確認端點狀態

```
get_serving_endpoint_status(name="my-agent-endpoint")
```

回傳：
```json
{
    "name": "my-agent-endpoint",
    "state": "READY",
    "served_entities": [...]
}
```

### 查詢 Chat/Agent 端點

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500
)
```

### 查詢傳統 ML 端點

```
query_serving_endpoint(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
)
```

---

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| **輸出格式無效** | 使用 `self.create_text_output_item(text, id)`——不可使用原始 dict！ |
| **端點 NOT_READY** | 部署約需 15 分鐘。使用 `get_serving_endpoint_status` 輪詢。 |
| **找不到套件** | 記錄模型時在 `pip_requirements` 中指定精確版本 |
| **工具逾時** | 使用以 Job 為基礎的部署，而非同步呼叫 |
| **端點認證錯誤** | 確認記錄模型時 `resources` 中已指定自動認證傳遞的資源 |
| **找不到模型** | 確認 Unity Catalog 路徑：`catalog.schema.model_name` |

### 重要：ResponsesAgent 輸出格式

**錯誤**——原始 dict 無法使用：
```python
return ResponsesAgentResponse(output=[{"role": "assistant", "content": "..."}])
```

**正確**——使用輔助方法：
```python
return ResponsesAgentResponse(
    output=[self.create_text_output_item(text="...", id="msg_1")]
)
```

可用輔助方法：
- `self.create_text_output_item(text, id)` — 文字回應
- `self.create_function_call_item(id, call_id, name, arguments)` — 工具呼叫
- `self.create_function_call_output_item(call_id, output)` — 工具執行結果

---

## 相關 Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — 可部署至 model serving 端點的預建 Agent 模組
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — 建立作為 Agent 檢索工具的向量索引
- **[databricks-genie](../databricks-genie/SKILL.md)** — Genie Space 可在多 Agent 架構中作為 Agent 使用
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** — 部署前評估模型與 Agent 品質
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Agent 端點使用的以 Job 為基礎的非同步部署

## 參考資源

- [Model Serving 文件](https://docs.databricks.com/machine-learning/model-serving/)
- [MLflow 3 ResponsesAgent](https://mlflow.org/docs/latest/llms/responses-agent-intro/)
- [Agent Framework](https://docs.databricks.com/generative-ai/agent-framework/)
