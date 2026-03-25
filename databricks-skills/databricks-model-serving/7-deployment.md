# 部署

將模型部署至服務端點。Agent 使用非同步以 Job 為基礎的方式（部署約需 15 分鐘）。

> **若 MCP 工具無法使用**，可在 Notebook 中直接使用 `databricks.agents.deploy()`，或透過 CLI 建立 Job：`databricks jobs create --json @job.json`

## 部署選項

| 模型類型 | 方式 | 所需時間 |
|---------|------|---------|
| **傳統 ML** | SDK/UI | 2–5 分鐘 |
| **GenAI Agent** | `databricks.agents.deploy()` | 約 15 分鐘 |

## GenAI Agent 部署（以 Job 為基礎）

Agent 部署約需 15 分鐘，使用 Job 可避免 MCP 逾時。

### 步驟一：建立部署腳本

```python
# deploy_agent.py
import sys
from databricks import agents

# 從 Job 或命令列取得參數
model_name = sys.argv[1] if len(sys.argv) > 1 else "main.agents.my_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"

print(f"Deploying {model_name} version {version}...")

# 部署——約需 15 分鐘
deployment = agents.deploy(
    model_name,
    version,
    tags={"source": "mcp", "environment": "dev"}
)

print(f"Deployment complete!")
print(f"Endpoint: {deployment.endpoint_name}")
```

### 步驟二：建立部署 Job（一次性）

使用 `manage_jobs` MCP 工具，action="create"：

```
manage_jobs(
    action="create",
    name="deploy-agent-job",
    tasks=[
        {
            "task_key": "deploy",
            "spark_python_task": {
                "python_file": "/Workspace/Users/you@company.com/my_agent/deploy_agent.py",
                "parameters": ["{{job.parameters.model_name}}", "{{job.parameters.version}}"]
            }
        }
    ],
    parameters=[
        {"name": "model_name", "default": "main.agents.my_agent"},
        {"name": "version", "default": "1"}
    ]
)
```

儲存回傳的 `job_id`。

### 步驟三：執行部署（非同步）

使用 `manage_job_runs`，action="run_now"——立即回傳：

```
manage_job_runs(
    action="run_now",
    job_id="<job_id>",
    job_parameters={"model_name": "main.agents.my_agent", "version": "1"}
)
```

儲存回傳的 `run_id`。

### 步驟四：確認狀態

確認 Job 執行狀態：

```
manage_job_runs(action="get", run_id="<run_id>")
```

或直接確認端點：

```
get_serving_endpoint_status(name="<endpoint_name>")
```

## 傳統 ML 部署

傳統 ML 模型部署速度較快，直接使用 SDK。

### 透過 MLflow Deployments SDK

```python
from mlflow.deployments import get_deploy_client

mlflow.set_registry_uri("databricks-uc")
client = get_deploy_client("databricks")

endpoint = client.create_endpoint(
    name="my-sklearn-model",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.my_model",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    }
)
```

### 透過 Databricks SDK

```python
from databricks.sdk import WorkspaceClient
from datetime import timedelta

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="my-sklearn-model",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.my_model",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    },
    timeout=timedelta(minutes=10)
)
```

## 端點命名與可見性

### 自動產生的名稱

呼叫 `agents.deploy()` 時，端點名稱從 UC 模型路徑自動衍生，將點號替換為連字號並加上 `agents_` 前綴：

| UC 模型路徑 | 自動產生的端點名稱 |
|------------|-----------------|
| `main.agents.my_agent` | `agents_main-agents-my_agent` |
| `catalog.schema.model` | `agents_catalog-schema-model` |
| `users.jane.demo_bot` | `agents_users-jane-demo_bot` |

實際格式可能有所差異。為避免意外，**務必明確指定端點名稱**：

```python
deployment = agents.deploy(
    "main.agents.my_agent",
    "1",
    endpoint_name="my-agent-endpoint",  # 自行控制名稱
    tags={"source": "mcp", "environment": "dev"}
)
```

### 在 UI 中尋找端點

透過 `agents.deploy()` 建立的端點會顯示在 Databricks UI 的 **Serving** 下。若找不到端點：

1. **確認過濾條件** — Serving 頁面預設顯示「Owned by me」。若部署以 service principal 執行（例如透過 Job），請切換至「All」。
2. **透過 API 確認** — 使用 `list_serving_endpoints()` 或 `get_serving_endpoint_status(name="...")` 確認端點存在並確認其狀態。
3. **確認名稱** — 自動產生的名稱可能與預期不同。在部署腳本中列印 `deployment.endpoint_name`，或確認 Job 執行輸出。

### 含明確命名的部署腳本

```python
# deploy_agent.py — 建議模式
import sys
from databricks import agents

model_name = sys.argv[1] if len(sys.argv) > 1 else "main.agents.my_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"
endpoint_name = sys.argv[3] if len(sys.argv) > 3 else None

deploy_kwargs = {
    "tags": {"source": "mcp", "environment": "dev"}
}
if endpoint_name:
    deploy_kwargs["endpoint_name"] = endpoint_name

print(f"Deploying {model_name} version {version}...")
deployment = agents.deploy(model_name, version, **deploy_kwargs)

print(f"Deployment complete!")
print(f"Endpoint name: {deployment.endpoint_name}")
print(f"Query URL: {deployment.query_endpoint}")
```

## 部署 Job 範本

可重複使用的 Agent 部署完整 Job 定義：

```yaml
# resources/deploy_agent_job.yml（用於 Asset Bundles）
resources:
  jobs:
    deploy_agent:
      name: "[${bundle.target}] Deploy Agent"
      parameters:
        - name: model_name
          default: ""
        - name: version
          default: "1"
      tasks:
        - task_key: deploy
          spark_python_task:
            python_file: ../src/deploy_agent.py
            parameters:
              - "{{job.parameters.model_name}}"
              - "{{job.parameters.version}}"
          new_cluster:
            spark_version: "16.1.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 0
            spark_conf:
              spark.master: "local[*]"
```

## 更新現有端點

以新版本模型更新端點：

```python
from mlflow.deployments import get_deploy_client

client = get_deploy_client("databricks")

client.update_endpoint(
    endpoint="my-agent-endpoint",
    config={
        "served_entities": [
            {
                "entity_name": "main.agents.my_agent",
                "entity_version": "2",  # 新版本
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ],
        "traffic_config": {
            "routes": [
                {"served_model_name": "my_agent-2", "traffic_percentage": 100}
            ]
        }
    }
)
```

## 工作流程摘要

| 步驟 | MCP 工具 | 是否等待完成 |
|------|---------|------------|
| 上傳部署腳本 | `upload_folder` | 是 |
| 建立 Job（一次性） | `manage_jobs`（action="create"） | 是 |
| 執行部署 | `manage_job_runs`（action="run_now"） | **否**——立即回傳 |
| 確認 Job 狀態 | `manage_job_runs`（action="get"） | 是 |
| 確認端點狀態 | `get_serving_endpoint_status` | 是 |

## 部署後

端點 READY 後：

1. **以 MCP 測試**：`query_serving_endpoint(name="...", messages=[...])`
2. **分享給團隊**：Databricks UI 中的端點 URL
3. **整合至應用程式**：使用 REST API 或 SDK
