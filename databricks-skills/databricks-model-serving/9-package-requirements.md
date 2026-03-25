# 套件需求

Databricks Runtime 版本與 pip 套件相容性說明。

## 建議的 Databricks Runtime

| DBR 版本 | 狀態 | 備注 |
|---------|------|------|
| **16.1+** | 建議 | 最新 GenAI 套件已預裝 |
| **15.4 LTS** | 支援 | 可能需要更多 pip 安裝 |
| **14.x** | 舊版 | 缺少許多 GenAI 功能 |

**Agent 開發請使用 DBR 16.1+** — 大多數套件已預裝。

## 預裝套件（DBR 16.1+）

以下套件無需 `%pip install` 即可使用：

- `mlflow`（3.x）
- `langchain`
- `pydantic`
- `pandas`、`numpy`、`scipy`
- `scikit-learn`
- `databricks-sdk`

## 需要安裝的套件

GenAI Agent 請安裝以下套件：

```python
%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic
dbutils.library.restartPython()
```

### 套件說明

| 套件 | 用途 | 版本 |
|------|------|------|
| `mlflow` | 模型記錄、服務 | `==3.6.0` |
| `databricks-langchain` | ChatDatabricks、UCFunctionToolkit | 最新版 |
| `langgraph` | Agent 圖形框架 | `==0.3.4` |
| `databricks-agents` | `agents.deploy()` | 最新版 |
| `pydantic` | 資料驗證 | 最新版 |

### 含記憶體/Lakebase 支援

```python
%pip install -U mlflow==3.6.0 databricks-langchain[memory] langgraph==0.3.4 databricks-agents
```

### 用於 Vector Search

```python
%pip install -U mlflow==3.6.0 databricks-langchain databricks-vectorsearch langgraph==0.3.4
```

### 最小化測試安裝

```python
%pip install -U mlflow-skinny[databricks] databricks-agents
```

## 模型記錄的 pip_requirements

記錄模型時，請指定精確版本：

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain",
    "langgraph==0.3.4",
    "pydantic",
]
```

### 動態取得當前版本

```python
from pkg_resources import get_distribution

pip_requirements=[
    f"mlflow=={get_distribution('mlflow').version}",
    f"databricks-langchain=={get_distribution('databricks-langchain').version}",
    f"langgraph=={get_distribution('langgraph').version}",
]
```

## 已測試的組合

### Agent 開發（建議）

```
mlflow==3.6.0
databricks-langchain>=0.3.0
langgraph==0.3.4
databricks-agents>=0.20.0
pydantic>=2.0
```

### LangChain Tracing

```
mlflow==2.14.0
langchain==0.2.1
langchain-openai==0.1.8
langchain-community==0.2.1
```

### 傳統 ML

```
mlflow>=2.10.0
scikit-learn>=1.3.0
pandas>=2.0.0
```

## 常見版本問題

| 問題 | 原因 | 解決方式 |
|------|------|---------|
| **ImportError: ResponsesAgent** | mlflow 版本過舊 | `pip install mlflow>=3.0` |
| **LangGraph 錯誤** | 版本不相符 | 固定至 `langgraph==0.3.4` |
| **Pydantic 驗證錯誤** | v1 與 v2 不相容 | 使用 `pydantic>=2.0` |
| **找不到 ChatDatabricks** | 缺少套件 | `pip install databricks-langchain` |
| **agents.deploy 失敗** | 缺少套件 | `pip install databricks-agents` |

## 環境變數

設定以下環境變數進行認證：

```bash
# 選項一：Host + Token
export DATABRICKS_HOST="https://your-workspace.databricks.com"
export DATABRICKS_TOKEN="your-token"

# 選項二：Profile
export DATABRICKS_CONFIG_PROFILE="your-profile"
```

## 透過 MCP 安裝套件

使用 `execute_databricks_command`：

```
execute_databricks_command(
    code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic"
)
```

接著重啟 Python：

```
execute_databricks_command(
    code="dbutils.library.restartPython()",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## 確認已安裝版本

```python
import pkg_resources

packages = ['mlflow', 'langchain', 'langgraph', 'pydantic', 'databricks-langchain']
for pkg in packages:
    try:
        version = pkg_resources.get_distribution(pkg).version
        print(f"{pkg}: {version}")
    except pkg_resources.DistributionNotFound:
        print(f"{pkg}: NOT INSTALLED")
```

透過 MCP：

```
execute_databricks_command(
    code="""
import pkg_resources
for pkg in ['mlflow', 'langchain', 'langgraph', 'pydantic', 'databricks-langchain']:
    try:
        print(f"{pkg}: {pkg_resources.get_distribution(pkg).version}")
    except:
        print(f"{pkg}: NOT INSTALLED")
    """
)
```
