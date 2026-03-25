# 使用 ResponsesAgent 建立 GenAI Agent

使用 MLflow 3 的 ResponsesAgent 介面建立並部署 LLM 驅動的 Agent。

## ResponsesAgent 概覽

`ResponsesAgent` 是 MLflow 3 建議用於建立對話型 Agent 的介面，提供：

- 標準化的輸入/輸出格式（相容 OpenAI）
- 串流支援
- 與 Databricks 功能整合（tracing、evaluation）

## 基本 Agent 結構

```python
# agent.py
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)
from typing import Generator

class MyAgent(ResponsesAgent):
    def __init__(self):
        from databricks_langchain import ChatDatabricks
        self.llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        """非串流預測。"""
        messages = [{"role": m.role, "content": m.content} for m in request.input]
        response = self.llm.invoke(messages)
        # 必須使用輔助方法輸出結果
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text=response.content, id="msg_1")]
        )

    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        """串流預測。"""
        # 簡化起見，從非串流收集結果
        result = self.predict(request)
        for item in result.output:
            yield ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=item
            )

# 匯出供 MLflow 使用
AGENT = MyAgent()
mlflow.models.set_model(AGENT)
```

## LangGraph Agent 模式

含工具與複雜邏輯的 Agent，使用 LangGraph：

```python
# agent.py
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
    to_chat_completions_input,
)
from databricks_langchain import ChatDatabricks, UCFunctionToolkit
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt.tool_node import ToolNode
from typing import Annotated, Any, Generator, Sequence, TypedDict

# 設定
LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"
SYSTEM_PROMPT = "You are a helpful assistant."

# 狀態定義
class AgentState(TypedDict):
    messages: Annotated[Sequence, add_messages]

class LangGraphAgent(ResponsesAgent):
    def __init__(self):
        self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
        self.tools = []

        # 新增 UC Function 工具
        # uc_toolkit = UCFunctionToolkit(function_names=["catalog.schema.function"])
        # self.tools.extend(uc_toolkit.tools)

        self.llm_with_tools = self.llm.bind_tools(self.tools) if self.tools else self.llm

    def _build_graph(self):
        def should_continue(state):
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and last.tool_calls:
                return "tools"
            return "end"

        def call_model(state):
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + state["messages"]
            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        graph = StateGraph(AgentState)
        graph.add_node("agent", RunnableLambda(call_model))

        if self.tools:
            graph.add_node("tools", ToolNode(self.tools))
            graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
            graph.add_edge("tools", "agent")
        else:
            graph.add_edge("agent", END)

        graph.set_entry_point("agent")
        return graph.compile()

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        # 從串流收集輸出項目
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs)

    # 從 ResponsesAgent 繼承的輔助方法：
    # - self.create_text_output_item(text, id) — 文字回應
    # - self.create_function_call_item(id, call_id, name, arguments) — 工具呼叫
    # - self.create_function_call_output_item(call_id, output) — 工具執行結果

    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        messages = to_chat_completions_input([m.model_dump() for m in request.input])
        graph = self._build_graph()

        for event in graph.stream({"messages": messages}, stream_mode=["updates"]):
            if event[0] == "updates":
                for node_data in event[1].values():
                    if node_data.get("messages"):
                        yield from output_to_responses_items_stream(node_data["messages"])

# 匯出
mlflow.langchain.autolog()
AGENT = LangGraphAgent()
mlflow.models.set_model(AGENT)
```

## 使用 Databricks 託管模型

使用 [SKILL.md](SKILL.md#foundation-model-api-端點) 中參考表格的精確端點名稱。

```python
from databricks_langchain import ChatDatabricks

# Foundation Model API（按 token 計費）——使用精確端點名稱
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
llm = ChatDatabricks(endpoint="databricks-claude-sonnet-4-6")
llm = ChatDatabricks(endpoint="databricks-gpt-5-1")
llm = ChatDatabricks(endpoint="databricks-gemini-3-flash")

# 自訂微調模型端點
llm = ChatDatabricks(endpoint="my-finetuned-model-endpoint")

# 含參數
llm = ChatDatabricks(
    endpoint="databricks-meta-llama-3-3-70b-instruct",
    temperature=0.1,
    max_tokens=1000,
)
```

## ChatContext 取得使用者/對話資訊

```python
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# 含 context 的請求
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "Hello!"}],
    context=ChatContext(
        user_id="user@company.com",
        conversation_id="conv-123"
    )
)

# 在 Agent 中存取
class MyAgent(ResponsesAgent):
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        user_id = request.context.user_id if request.context else None
        conv_id = request.context.conversation_id if request.context else None
        # 用於個人化、記憶等功能
```

## 本地測試 Agent

```python
# test_agent.py
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# 測試請求
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "What is Databricks?"}],
    context=ChatContext(user_id="test@example.com")
)

# 非串流
result = AGENT.predict(request)
print(result.model_dump(exclude_none=True))

# 串流
for event in AGENT.predict_stream(request):
    print(event)
```

透過 MCP 執行：

```
run_python_file_on_databricks(file_path="./my_agent/test_agent.py")
```

## 記錄 Agent

完整說明請參閱 [6-logging-registration.md](6-logging-registration.md)。

```python
import mlflow
from agent import AGENT, LLM_ENDPOINT
from mlflow.models.resources import DatabricksServingEndpoint

mlflow.set_registry_uri("databricks-uc")

resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",
        resources=resources,
        pip_requirements=[
            "mlflow==3.6.0",
            "databricks-langchain",
            "langgraph==0.3.4",
        ],
        input_example={
            "input": [{"role": "user", "content": "Hello!"}]
        },
        registered_model_name="main.agents.my_agent"
    )
```

## 部署

非同步以 Job 為基礎的部署方式請參閱 [7-deployment.md](7-deployment.md)。

```python
from databricks import agents

agents.deploy(
    "main.agents.my_agent",
    version="1",
    tags={"source": "mcp"}
)
# 約需 15 分鐘
```

## 查詢已部署 Agent

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "What is Databricks?"}],
    max_tokens=500
)
```
