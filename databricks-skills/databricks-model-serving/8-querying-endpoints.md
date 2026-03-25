# 查詢端點

向已部署的 Model Serving 端點發送請求。

> **若 MCP 工具無法使用**，請使用下方的 Python SDK 或 REST API 範例。

## MCP 工具

### 確認端點狀態

查詢前先確認端點已就緒：

```
get_serving_endpoint_status(name="my-agent-endpoint")
```

回應：
```json
{
    "name": "my-agent-endpoint",
    "state": "READY",
    "served_entities": [
        {"name": "my_agent-1", "entity_name": "main.agents.my_agent", "deployment_state": "READY"}
    ]
}
```

### 查詢 Chat/Agent 端點

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500,
    temperature=0.7
)
```

回應：
```json
{
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "Databricks is a unified data intelligence platform..."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 150,
        "total_tokens": 160
    }
}
```

### 查詢 ML 模型端點

```
query_serving_endpoint(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720},
        {"age": 35, "income": 75000, "credit_score": 680}
    ]
)
```

回應：
```json
{
    "predictions": [0.85, 0.72]
}
```

### 列出所有端點

```
list_serving_endpoints(limit=20)
```

## Python SDK

### 查詢 Agent/Chat 端點

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

response = w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500
)

print(response.choices[0].message.content)
```

### 查詢 ML 模型

```python
response = w.serving_endpoints.query(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
)

print(response.predictions)
```

### 串流（Agent 端點）

```python
for chunk in w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
):
    if chunk.choices:
        print(chunk.choices[0].delta.content, end="")
```

## REST API

### 取得端點狀態

```bash
curl -X GET \
  "https://<workspace>.databricks.com/api/2.0/serving-endpoints/<endpoint-name>" \
  -H "Authorization: Bearer <token>"
```

### 查詢 Chat/Agent 端點

```bash
curl -X POST \
  "https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>/invocations" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
        {"role": "user", "content": "What is Databricks?"}
    ],
    "max_tokens": 500
  }'
```

### 查詢 ML 模型

```bash
curl -X POST \
  "https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>/invocations" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataframe_records": [
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
  }'
```

## 整合模式

### 在 Python 應用程式中

```python
from databricks.sdk import WorkspaceClient
import os

# 從環境變數使用 DATABRICKS_HOST 與 DATABRICKS_TOKEN
w = WorkspaceClient()

def ask_agent(question: str) -> str:
    response = w.serving_endpoints.query(
        name="my-agent-endpoint",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# 使用範例
answer = ask_agent("What is a Delta table?")
print(answer)
```

### 在另一個 Agent 中（Agent 串接）

```python
from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool

w = WorkspaceClient()

@tool
def ask_specialist_agent(question: str) -> str:
    """Ask a specialist agent for domain-specific answers."""
    response = w.serving_endpoints.query(
        name="specialist-agent-endpoint",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# 加入主 Agent 的工具清單
tools = [ask_specialist_agent]
```

### 與相容 OpenAI 的函式庫搭配使用

Databricks 端點相容 OpenAI：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>",
    api_key="<databricks-token>"
)

response = client.chat.completions.create(
    model="<endpoint-name>",  # 任何值均可，端點決定模型
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

## 錯誤處理

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, PermissionDenied

w = WorkspaceClient()

try:
    response = w.serving_endpoints.query(
        name="my-endpoint",
        messages=[{"role": "user", "content": "Test"}]
    )
except NotFound:
    print("找不到端點——確認名稱或等待部署完成")
except PermissionDenied:
    print("無權限查詢此端點")
except Exception as e:
    if "NOT_READY" in str(e):
        print("端點仍在啟動中")
    else:
        raise
```

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| **端點 NOT_READY** | 等待部署完成（Agent 約需 15 分鐘） |
| **404 Not Found** | 確認端點名稱，可能與模型名稱不同 |
| **Permission Denied** | 確認 token 具有服務端點權限 |
| **逾時** | 增加 timeout，減少 max_tokens |
| **空回應** | 確認模型簽章與輸入格式相符 |
