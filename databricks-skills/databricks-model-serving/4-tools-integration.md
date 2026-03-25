# 工具整合

在 Agent 中新增 Unity Catalog Functions 與 Vector Search。

## Unity Catalog Functions（UCFunctionToolkit）

UC Functions 是在 Unity Catalog 中註冊的 SQL/Python UDF，Agent 可呼叫它們作為工具。

### 設定

```python
from databricks_langchain import UCFunctionToolkit

# 依名稱指定函式
uc_toolkit = UCFunctionToolkit(
    function_names=[
        "catalog.schema.my_function",
        "catalog.schema.another_function",
        "system.ai.python_exec",  # 內建 Python 直譯器
    ]
)

# 加入工具清單
tools = []
tools.extend(uc_toolkit.tools)
```

### 萬用字元選取

```python
# Schema 中的所有函式
uc_toolkit = UCFunctionToolkit(
    function_names=["catalog.schema.*"]
)
```

### 內建 UC 工具

| 函式 | 用途 |
|------|------|
| `system.ai.python_exec` | 執行 Python 程式碼 |

### 建立 UC Function

```sql
-- 在 Notebook 或 SQL 編輯器中
CREATE OR REPLACE FUNCTION catalog.schema.get_customer_info(customer_id STRING)
RETURNS TABLE(name STRING, email STRING, tier STRING)
LANGUAGE SQL
COMMENT 'Get customer information by ID'
RETURN
  SELECT name, email, tier
  FROM catalog.schema.customers
  WHERE id = customer_id;
```

### 為認證傳遞登記資源

記錄模型時，將 UC functions 加入 resources：

```python
from mlflow.models.resources import DatabricksFunction

resources = []
for tool in tools:
    if hasattr(tool, "uc_function_name"):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
```

## Vector Search（VectorSearchRetrieverTool）

使用 Databricks Vector Search 索引為 Agent 新增 RAG 能力。

### 設定

```python
from databricks_langchain import VectorSearchRetrieverTool

# 建立 retriever 工具
vs_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.my_vector_index",
    num_results=5,
    # 可選：過濾結果
    # filters={"category": "documentation"}
)

tools = [vs_tool]
```

### 含過濾條件

```python
vs_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.docs_index",
    num_results=10,
    filters={"doc_type": "technical", "status": "published"},
    columns=["content", "title", "url"],  # 要回傳的欄位
)
```

### 登記資源

Vector Search 工具會自動提供其資源：

```python
from mlflow.models.resources import DatabricksServingEndpoint

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

for tool in tools:
    if isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)  # 包含 VS 索引與 embedding 端點
```

## 使用 @tool 裝飾器建立自訂工具

為 Agent 建立自訂工具：

```python
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

@tool
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current time in the specified timezone.

    Args:
        timezone: The timezone (e.g., 'UTC', 'America/New_York')
    """
    from datetime import datetime
    import pytz

    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")

@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression like '2 + 2' or 'sqrt(16)'
    """
    import math
    # 使用數學函式安全執行 eval
    allowed = {k: v for k, v in math.__dict__.items() if not k.startswith('_')}
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)
    except Exception as e:
        return f"Error: {e}"

# 加入工具清單
tools = [get_current_time, calculate]
```

### 存取 Config 的工具

在工具中存取執行時 config（user_id 等）：

```python
@tool
def get_user_preferences(config: RunnableConfig) -> str:
    """Get preferences for the current user."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id:
        return "No user ID provided"

    # 從資料庫取得
    # ...
    return f"Preferences for {user_id}: ..."
```

## 結合所有工具類型

```python
from databricks_langchain import ChatDatabricks, UCFunctionToolkit, VectorSearchRetrieverTool
from langchain_core.tools import tool

# LLM
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

# 所有工具
tools = []

# 1. UC Functions
uc_toolkit = UCFunctionToolkit(function_names=["catalog.schema.*"])
tools.extend(uc_toolkit.tools)

# 2. Vector Search
vs_tool = VectorSearchRetrieverTool(index_name="catalog.schema.docs_index")
tools.append(vs_tool)

# 3. 自訂工具
@tool
def my_custom_tool(query: str) -> str:
    """Custom tool description."""
    return f"Result for: {query}"

tools.append(my_custom_tool)

# 綁定至 LLM
llm_with_tools = llm.bind_tools(tools)
```

## 模型記錄所需資源

收集所有資源以供自動認證：

```python
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksFunction,
    DatabricksVectorSearchIndex,
)
from unitycatalog.ai.langchain.toolkit import UnityCatalogTool

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

for tool in tools:
    # UC Functions
    if isinstance(tool, UnityCatalogTool):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
    # Vector Search
    elif isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)
    # 自訂工具不需要資源（在端點中執行）

# 記錄含資源的模型
mlflow.pyfunc.log_model(
    name="agent",
    python_model="agent.py",
    resources=resources,
    # ...
)
```

## 最佳實踐

1. **限制工具數量** — Agent 搭配 5–10 個專注的工具效果最佳
2. **清晰的描述** — 工具 docstring 會顯示給 LLM
3. **型別標注** — 參數務必加上型別標注
4. **錯誤處理** — 回傳錯誤訊息，不要拋出例外
5. **獨立測試工具** — 加入 Agent 前先確認每個工具正常運作
