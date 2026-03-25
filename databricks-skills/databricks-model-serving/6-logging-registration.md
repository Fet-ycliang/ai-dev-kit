# 記錄與註冊

將模型記錄至 MLflow 並註冊至 Unity Catalog。

## 以檔案為基礎的記錄（Agent 建議方式）

從 Python 檔案而非類別實例記錄：

```python
# log_model.py
import mlflow
from agent import AGENT, LLM_ENDPOINT
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksFunction
from unitycatalog.ai.langchain.toolkit import UnityCatalogTool
from databricks_langchain import VectorSearchRetrieverTool

mlflow.set_registry_uri("databricks-uc")

# 收集資源以供自動認證
resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

# 新增 UC function 資源
from agent import tools  # 若 Agent 有匯出 tools
for tool in tools:
    if isinstance(tool, UnityCatalogTool):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
    elif isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)

# 輸入範例
input_example = {
    "input": [{"role": "user", "content": "What is Databricks?"}]
}

# 記錄模型
with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",  # 檔案路徑
        input_example=input_example,
        resources=resources,
        pip_requirements=[
            "mlflow==3.6.0",
            "databricks-langchain",
            "langgraph==0.3.4",
            "pydantic",
        ],
    )
    print(f"Model URI: {model_info.model_uri}")

# 註冊至 Unity Catalog
catalog = "main"
schema = "agents"
model_name = "my_agent"

uc_model_info = mlflow.register_model(
    model_uri=model_info.model_uri,
    name=f"{catalog}.{schema}.{model_name}"
)
print(f"Registered: {uc_model_info.name} version {uc_model_info.version}")
```

透過 MCP 執行：

```
run_python_file_on_databricks(file_path="./my_agent/log_model.py")
```

## 自動認證的資源類型

Databricks 會自動為以下資源類型佈建認證：

| 資源類型 | 匯入來源 | 用途 |
|---------|---------|------|
| `DatabricksServingEndpoint` | `mlflow.models.resources` | LLM 端點 |
| `DatabricksFunction` | `mlflow.models.resources` | UC SQL/Python 函式 |
| `DatabricksVectorSearchIndex` | `mlflow.models.resources` | Vector Search 索引 |
| `DatabricksLakebase` | `mlflow.models.resources` | Lakebase 實例 |

```python
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksFunction,
    DatabricksVectorSearchIndex,
    DatabricksLakebase,
)

resources = [
    DatabricksServingEndpoint(endpoint_name="databricks-meta-llama-3-3-70b-instruct"),
    DatabricksFunction(function_name="catalog.schema.my_function"),
    DatabricksVectorSearchIndex(index_name="catalog.schema.my_index"),
    DatabricksLakebase(database_instance_name="my-lakebase"),
]
```

## pip_requirements

### 建議版本（已測試）

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain",  # 最新版
    "langgraph==0.3.4",
    "pydantic",
    "databricks-agents",
]
```

### 含記憶體支援

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain[memory]",  # 包含 Lakebase 支援
    "langgraph==0.3.4",
]
```

### 動態取得當前版本

```python
from pkg_resources import get_distribution

pip_requirements=[
    f"mlflow=={get_distribution('mlflow').version}",
    f"databricks-langchain=={get_distribution('databricks-langchain').version}",
]
```

## 部署前驗證

部署前驗證模型可正常載入與執行：

```python
# 在本地驗證（使用 uv 快速建立環境）
mlflow.models.predict(
    model_uri=model_info.model_uri,
    input_data={"input": [{"role": "user", "content": "Test"}]},
    env_manager="uv",
)
```

透過 MCP 執行（在 log_model.py 或獨立檔案中）：

```python
# validate_model.py
import mlflow

# 從上一步取得 model URI
model_uri = "runs:/<run_id>/agent"  # 或從 UC：「models:/catalog.schema.model/1」

result = mlflow.models.predict(
    model_uri=model_uri,
    input_data={"input": [{"role": "user", "content": "Hello"}]},
    env_manager="uv",
)
print("Validation result:", result)
```

## 傳統 ML 記錄

傳統 ML 模型使用 autolog 自動處理所有事項：

```python
import mlflow
import mlflow.sklearn

mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name="main.models.my_model"
)

# 訓練——自動記錄並註冊
model.fit(X_train, y_train)
```

## 手動註冊（分開步驟）

若記錄時未一併註冊：

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")

# 從 run 註冊
mlflow.register_model(
    model_uri="runs:/<run_id>/agent",
    name="main.agents.my_agent"
)

# 從記錄的 model info 註冊
mlflow.register_model(
    model_uri=model_info.model_uri,
    name="main.agents.my_agent"
)
```

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| **服務時找不到套件** | 在 `pip_requirements` 中指定精確版本 |
| **存取端點時認證錯誤** | 將資源加入 `resources` 清單 |
| **模型簽章不符** | 提供符合輸入格式的 `input_example` |
| **模型載入緩慢** | 驗證時使用 `env_manager="uv"` 加速 |
| **找不到程式碼** | 使用 `code_paths=["file.py"]` 加入額外相依項 |
