# MLflow Trace Ingestion in Unity Catalog

Working code patterns for setting up trace storage in Unity Catalog, logging traces from applications, and enabling production monitoring.

**Version**: MLflow 3.9.0+ (`mlflow[databricks]>=3.9.0`)
**Preview**: Requires "OpenTelemetry on Databricks" preview enabled
**Regions**: Currently available in `us-east-1` and `us-west-2` only

---

## Table of Contents

| # | Pattern | Description |
|---|---------|-------------|
| 1 | [Initial Setup](#pattern-1-initial-setup---link-uc-schema-to-experiment) | Link UC schema to experiment, create tables |
| 2 | [Access Control](#pattern-2-access-control---grant-permissions) | Grant required permissions on UC tables |
| 3 | [Set Trace Destination (Python API)](#pattern-3-set-trace-destination-via-python-api) | Configure where traces are sent |
| 4 | [Set Trace Destination (Env Var)](#pattern-4-set-trace-destination-via-environment-variable) | Configure destination via env var |
| 5 | [Log Traces with @mlflow.trace](#pattern-5-log-traces-with-mlflow-decorator) | Instrument functions with decorator |
| 6 | [Log Traces with start_span](#pattern-6-log-traces-with-context-manager) | Fine-grained span control |
| 7 | [Auto-Instrumentation](#pattern-7-automatic-tracing-with-autolog) | Framework auto-tracing (OpenAI, LangChain, etc.) |
| 8 | [Combined Instrumentation](#pattern-8-combined-auto-and-manual-tracing) | Mix auto + manual tracing |
| 9 | [Traces from Databricks Apps](#pattern-9-log-traces-from-databricks-apps) | Configure app service principal |
| 10 | [Traces from Model Serving](#pattern-10-log-traces-from-model-serving-endpoints) | Configure serving endpoints |
| 11 | [Traces from OTEL Clients](#pattern-11-log-traces-from-third-party-otel-clients) | Use OpenTelemetry OTLP exporter |
| 12 | [Enable Production Monitoring](#pattern-12-enable-production-monitoring) | Register and start scorers |
| 13 | [Manage Monitoring Scorers](#pattern-13-manage-monitoring-scorers) | List, update, stop, delete scorers |
| 14 | [Query UC Trace Tables](#pattern-14-query-traces-from-unity-catalog-tables) | SQL queries on ingested traces |
| 15 | [End-to-End Setup](#pattern-15-end-to-end-setup-script) | Complete setup from scratch |

---

## Pattern 1: Initial Setup - Link UC Schema to Experiment

Create an MLflow experiment and link it to a Unity Catalog schema. This automatically creates three tables for storing trace data.

```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location

# Step 1: Configure tracking
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"

# Step 2: Define names
experiment_name = "/Shared/my-agent-traces"
catalog_name = "my_catalog"
schema_name = "my_schema"

# Step 3: Create or retrieve experiment
if experiment := mlflow.get_experiment_by_name(experiment_name):
    experiment_id = experiment.experiment_id
else:
    experiment_id = mlflow.create_experiment(name=experiment_name)

# Step 4: Link UC schema to experiment
result = set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name=catalog_name,
        schema_name=schema_name
    ),
    experiment_id=experiment_id,
)
```

**Tables created automatically:**
- `{catalog}.{schema}.mlflow_experiment_trace_otel_logs`
- `{catalog}.{schema}.mlflow_experiment_trace_otel_metrics`
- `{catalog}.{schema}.mlflow_experiment_trace_otel_spans`

**CRITICAL**: Linking a UC schema hides pre-existing experiment traces stored in MLflow. Unlinking restores access to those traces.

---

## Pattern 2: Access Control - Grant Permissions

Users and service principals need explicit permissions on the UC trace tables. `ALL_PRIVILEGES` is **not sufficient**.

```sql
-- Required: USE_CATALOG on the catalog
GRANT USE_CATALOG ON CATALOG my_catalog TO `user@company.com`;

-- Required: USE_SCHEMA on the schema
GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `user@company.com`;

-- Required: MODIFY and SELECT on each trace table
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `user@company.com`;
```

**For service principals (Databricks Apps, Model Serving):**
```sql
-- Replace with the service principal's application ID
GRANT USE_CATALOG ON CATALOG my_catalog TO `<service-principal-app-id>`;
GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `<service-principal-app-id>`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `<service-principal-app-id>`;
```

---

## Pattern 3: Set Trace Destination via Python API

Configure where traces are sent using the Python API. Use this after the initial setup (Pattern 1) in your application code.

```python
import mlflow
from mlflow.entities import UCSchemaLocation

# Set trace destination to Unity Catalog
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# Now all traces from @mlflow.trace or autolog will go to UC
@mlflow.trace
def my_agent(query: str) -> str:
    # Traces are automatically sent to UC tables
    return process(query)
```

---

## Pattern 4: Set Trace Destination via Environment Variable

Alternative to Pattern 3 — configure destination via environment variable. Useful for deployment configurations.

```python
import os

# Set destination as "{catalog}.{schema}"
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
```

Or in shell:
```bash
export MLFLOW_TRACING_DESTINATION="my_catalog.my_schema"
```

---

## Pattern 5: Log Traces with MLflow Decorator

Use `@mlflow.trace` to instrument functions. Automatically captures inputs, outputs, latency, and exceptions.

```python
import mlflow
from mlflow.entities import SpanType

# Basic function tracing
@mlflow.trace
def my_agent(query: str) -> str:
    context = retrieve_context(query)
    return generate_response(query, context)

# With span type (enables enhanced UI and evaluation)
@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_context(query: str) -> list[dict]:
    """Mark retrieval functions with RETRIEVER span type."""
    return vector_store.search(query, top_k=5)

@mlflow.trace(span_type=SpanType.CHAIN)
def generate_response(query: str, context: list[dict]) -> str:
    """Mark orchestration with CHAIN span type."""
    return llm.invoke(query, context=context)

# With custom name and attributes
@mlflow.trace(name="safety_check", span_type=SpanType.TOOL)
def check_safety(text: str) -> bool:
    return safety_classifier.predict(text)
```

**Available SpanType values:**
- `SpanType.CHAIN` — Orchestration / pipeline steps
- `SpanType.CHAT_MODEL` — LLM chat completions
- `SpanType.LLM` — LLM calls (non-chat)
- `SpanType.RETRIEVER` — Document/data retrieval (special output schema)
- `SpanType.TOOL` — Tool/function execution
- `SpanType.AGENT` — Agent execution
- `SpanType.EMBEDDING` — Embedding generation

---

## Pattern 6: Log Traces with Context Manager

Use `mlflow.start_span()` for fine-grained control over spans. Manually set inputs, outputs, and attributes.

```python
import mlflow

def process_query(query: str) -> str:
    # 建立可手動控制的 span
    with mlflow.start_span(name="process_query") as span:
        span.set_inputs({"query": query})

        # 建立用於檢索的巢狀 span
        with mlflow.start_span(name="retrieve", span_type="RETRIEVER") as retriever_span:
            retriever_span.set_inputs({"query": query})
            docs = vector_store.search(query)
            retriever_span.set_outputs(docs)

        # 建立用於生成的巢狀 span
        with mlflow.start_span(name="generate", span_type="CHAIN") as gen_span:
            gen_span.set_inputs({"query": query, "doc_count": len(docs)})
            response = llm.generate(query, docs)
            gen_span.set_outputs({"response": response})

        # 設定供分析使用的屬性
        span.set_attribute("doc_count", len(docs))
        span.set_attribute("model", "gpt-4o")
        span.set_outputs({"response": response})

    return response
```

---

## 模式 7：使用 Autolog 自動追蹤

為支援的 framework 啟用自動追蹤。MLflow 會在不需修改程式碼的情況下擷取 LLM 呼叫、工具執行與 chain 操作。

```python
import mlflow

# 為特定 framework 啟用自動追蹤
mlflow.openai.autolog()        # OpenAI SDK 呼叫
mlflow.langchain.autolog()     # LangChain chains 與 agents
# 也支援：mlflow.anthropic.autolog()、mlflow.litellm.autolog() 等

# 設定 tracking 與目的地
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-agent-traces")

# Traces 會自動被擷取
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "你是一個樂於助人的助理。"},
        {"role": "user", "content": "什麼是 MLflow？"}
    ]
)
# ^ 這個呼叫會自動被追蹤
```

**支援 20+ 個 framework**，包括：
- OpenAI、Anthropic、Google GenAI
- LangChain、LlamaIndex、DSPy
- LiteLLM、Ollama、Bedrock
- CrewAI、AutoGen、Haystack

---

## 模式 8：結合自動與手動追蹤

將 framework 的自動追蹤與手動 decorators 結合，以取得完整覆蓋。

```python
import mlflow
from mlflow.entities import SpanType
from openai import OpenAI

# 啟用 OpenAI 自動追蹤
mlflow.openai.autolog()

client = OpenAI()

@mlflow.trace(span_type=SpanType.CHAIN)
def my_rag_pipeline(query: str) -> str:
    """手動 decorator 包住整個 pipeline。
    Auto-tracing 會擷取其中個別的 OpenAI 呼叫。"""

    # 這段檢索會以手動方式追蹤
    docs = retrieve_documents(query)

    # 這個 LLM 呼叫會由 mlflow.openai.autolog() 自動追蹤
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": f"請根據以下脈絡回答：{docs}"},
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message.content

@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_documents(query: str) -> list[dict]:
    """以手動方式追蹤的檢索函式。"""
    return vector_store.search(query, top_k=5)
```

---

## 模式 9：從 Databricks Apps 記錄 Traces

設定 Databricks App，將 traces 傳送至 Unity Catalog。

**先決條件：**
- App 使用 `mlflow[databricks]>=3.5.0`
- App 的 service principal 已在 trace 資料表上具備 MODIFY 與 SELECT 權限（請參閱模式 2）

**在你的 app 程式碼中：**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

# 選項 A：Python API
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# 選項 B：環境變數（於 app config 中設定）
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"

# 你的 app 程式碼 — traces 會送往 UC
@mlflow.trace
def handle_request(query: str) -> str:
    return my_agent.invoke(query)
```

**部署步驟：**
1. 在 **Authorization** 分頁中找到 app 的 service principal
2. 對三張 `mlflow_experiment_trace_*` 資料表授與 MODIFY 與 SELECT
3. 在 app 程式碼中設定 trace 目的地
4. 部署 app

---

## 模式 10：從 Model Serving Endpoints 記錄 Traces

設定 model serving endpoint，將 traces 傳送至 Unity Catalog。

**步驟 1：授與 user／service principal 權限**
```sql
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `serving-principal-id`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `serving-principal-id`;
```

**步驟 2：產生 Personal Access Token（PAT）**

為具備上述權限的身分建立 PAT。

**步驟 3：將環境變數加入 endpoint**

把以下內容加入 serving endpoint 設定：
```
DATABRICKS_TOKEN=<your-personal-access-token>
MLFLOW_TRACING_DESTINATION=my_catalog.my_schema
```

**步驟 4：在部署模型的程式碼中設定目的地**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# 模型的 predict 函式 — traces 會送往 UC
@mlflow.trace
def predict(model_input):
    return my_model.invoke(model_input)
```

---

## 模式 11：從第三方 OTEL Clients 記錄 Traces

透過 OTLP HTTP endpoint，將任何與 OpenTelemetry 相容的 client traces 傳送至 Unity Catalog。

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 設定指向 Databricks 的 OTLP exporter
otlp_trace_exporter = OTLPSpanExporter(
    endpoint="https://<workspace-url>/api/2.0/otel/v1/traces",
    headers={
        "content-type": "application/x-protobuf",
        "X-Databricks-UC-Table-Name": "my_catalog.my_schema.mlflow_experiment_trace_otel_spans",
        "Authorization": "Bearer <YOUR_API_TOKEN>",
    },
)

# 設定 tracer provider
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

# 使用標準 OpenTelemetry APIs 建立 spans
tracer = provider.get_tracer("my-application")
with tracer.start_as_current_span("my-operation") as span:
    span.set_attribute("query", "什麼是 MLflow？")
    result = process_query("什麼是 MLflow？")
    span.set_attribute("result_length", len(result))
```

**注意事項：**
- 透過 OTEL 匯入的 traces 若包含 root span，就會顯示在已連結的 experiments 中
- 使用 `X-Databricks-UC-Table-Name` header 指定目標 spans 資料表
- 標準 OTEL instrumentation libraries 可搭配此 endpoint 使用

---

## 模式 12：啟用正式環境監控

註冊 scorers，持續評估正式環境中的 traces。Scorers 會針對取樣的 traces 非同步執行。

```python
import mlflow
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

# 步驟 1：設定監控用的 SQL warehouse
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id="<SQL_WAREHOUSE_ID>",
    experiment_id="<EXPERIMENT_ID>"  # 選用 — 若省略則使用目前的 active experiment
)

# 步驟 2：設定 active experiment
mlflow.set_experiment("/Shared/my-agent-traces")

# 步驟 3：註冊並啟動 scorers

# Safety scorer — 評估 100% 的 traces
safety = Safety().register(name="production_safety")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)

# 自訂 guidelines — 評估 50% 的 traces
tone_check = Guidelines(
    name="professional_tone",
    guidelines="回應必須專業且有幫助"
).register(name="production_tone")
tone_check = tone_check.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
```

**關鍵**：你必須同時呼叫 `.register()` 與 `.start()` —— 只註冊並不會啟用監控。

**SQL Warehouse 要求：**
- User 必須對 SQL warehouse 具備 `CAN USE`
- User 必須對 experiment 具備 `CAN EDIT`
- 第一次註冊 scorer 時，系統會自動授與 monitoring job 所需權限

---

## 模式 13：管理監控 Scorers

列出、更新、停止與刪除正式環境監控 scorers。

```python
from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer, ScorerSamplingConfig

# 列出 active experiment 中所有已註冊的 scorers
scorers = list_scorers()
for s in scorers:
    print(f"  {s.name}: sample_rate={s.sampling_config.sample_rate if s.sampling_config else 'N/A'}")

# 取得特定 scorer
safety_scorer = get_scorer(name="production_safety")

# 更新取樣率（例如從 50% 提高到 80%）
safety_scorer = safety_scorer.update(
    sampling_config=ScorerSamplingConfig(sample_rate=0.8)
)

# 停止監控（保留註冊，之後可重新啟動）
safety_scorer = safety_scorer.stop()

# 重新啟動監控
safety_scorer = safety_scorer.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)

# 完全刪除（移除註冊）
delete_scorer(name="production_safety")
```

---

## 模式 14：從 Unity Catalog 資料表查詢 Traces

直接使用 SQL 查詢已匯入的 traces，以進行自訂分析與 dashboards。

```sql
-- 計算每日 trace 數量
SELECT
  DATE(timestamp) as trace_date,
  COUNT(DISTINCT trace_id) as trace_count
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL  -- 僅限 root spans
GROUP BY DATE(timestamp)
ORDER BY trace_date DESC;

-- 找出慢速 traces（root span 持續時間 > 10 秒）
SELECT
  trace_id,
  name as root_span_name,
  (end_time_unix_nano - start_time_unix_nano) / 1e9 as duration_seconds
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL
  AND (end_time_unix_nano - start_time_unix_nano) / 1e9 > 10
ORDER BY duration_seconds DESC
LIMIT 20;

-- 依 span 名稱計算錯誤率
SELECT
  name,
  COUNT(*) as total,
  SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) as errors,
  ROUND(SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as error_pct
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
GROUP BY name
HAVING COUNT(*) > 10
ORDER BY error_pct DESC;
```

**從 Python（透過 Spark）：**
```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

# 查詢 trace spans
spans_df = spark.sql("""
    SELECT trace_id, name, span_kind,
           (end_time_unix_nano - start_time_unix_nano) / 1e6 as duration_ms
    FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
    WHERE name LIKE '%retriever%'
    ORDER BY duration_ms DESC
    LIMIT 100
""")
spans_df.show()
```

---

## 模式 15：端對端設定腳本

新專案的完整設定腳本 —— 從建立 UC schema 連結，到記錄第一筆 trace 並啟用監控。

```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig

# ============================================================
# 設定 — 請更新這些值
# ============================================================
EXPERIMENT_NAME = "/Shared/my-agent-traces"
CATALOG_NAME = "my_catalog"
SCHEMA_NAME = "my_schema"
SQL_WAREHOUSE_ID = "abc123def456"  # 你的 SQL warehouse ID

# ============================================================
# 步驟 1：初始設定
# ============================================================
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = SQL_WAREHOUSE_ID

# 建立或取得 experiment
if experiment := mlflow.get_experiment_by_name(EXPERIMENT_NAME):
    experiment_id = experiment.experiment_id
else:
    experiment_id = mlflow.create_experiment(name=EXPERIMENT_NAME)

# 連結 UC schema（會自動建立 trace 資料表）
set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME
    ),
    experiment_id=experiment_id,
)
print(f"已將 experiment '{EXPERIMENT_NAME}' 連結到 {CATALOG_NAME}.{SCHEMA_NAME}")

# ============================================================
# 步驟 2：設定 Trace 目的地
# ============================================================
mlflow.set_experiment(EXPERIMENT_NAME)
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME,
    )
)

# ============================================================
# 步驟 3：啟用正式環境監控
# ============================================================
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id=SQL_WAREHOUSE_ID,
    experiment_id=experiment_id,
)

# 註冊並啟動 safety 監控（100% traces）
safety = Safety().register(name="safety_monitor")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)
print("已啟用 Safety 監控（100% 取樣率）")

# 註冊並啟動自訂 guidelines（50% traces）
tone = Guidelines(
    name="professional_tone",
    guidelines="回應必須專業、樂於助人且精簡"
).register(name="tone_monitor")
tone = tone.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
print("已啟用語氣監控（50% 取樣率）")

# ============================================================
# 步驟 4：使用測試 Trace 驗證
# ============================================================
@mlflow.trace
def test_agent(query: str) -> str:
    return f"針對以下內容的測試回應：{query}"

result = test_agent("哈囉，trace 是否正常運作？")
print(f"已記錄測試 trace。請至 Experiments UI 檢查：{EXPERIMENT_NAME}")
```

---

## 限制與配額

| 限制 | 數值 |
|-------|-------|
| Trace 匯入速率 | 每個 workspace 每秒 100 筆 traces |
| 資料表匯入吞吐量 | 每張資料表每秒 100 MB |
| 查詢吞吐量 | 每秒 200 次查詢 |
| UI 效能 | 資料量超過 2TB 時會下降 |
| Trace 刪除 | 不支援逐筆刪除（請使用 SQL） |
| MLflow MCP server | 不支援儲存在 UC 中的 traces |
| 區域可用性 | 僅限 `us-east-1` 與 `us-west-2`（Beta） |

---

## 在 UI 中檢視 Traces

1. 前往 Databricks workspace 中的 **Experiments** 頁面
2. 選取你的 experiment
3. 點選 **Traces** 分頁
4. 從下拉選單選取 **SQL warehouse**，以查詢儲存在 UC 中的 traces
5. 瀏覽 traces、檢視 spans，並查看輸入／輸出

**注意：** 你必須先選取 SQL warehouse，才能檢視儲存在 UC 中的 traces —— 系統不會自動載入。
## 模式 9：從 Databricks Apps 記錄 Trace

設定 Databricks App，將 trace 傳送到 Unity Catalog。

**先決條件：**
- App 使用 `mlflow[databricks]>=3.5.0`
- App 的 service principal 對 trace 資料表具備 MODIFY 與 SELECT 權限（請參閱模式 2）

**在 app 程式碼中：**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

# 選項 A：Python API
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# 選項 B：環境變數（在 app 設定中設定）
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"

# 你的 app 程式碼 —— trace 會送至 UC
@mlflow.trace
def handle_request(query: str) -> str:
    return my_agent.invoke(query)
```

**部署步驟：**
1. 在 **Authorization** 分頁下找到 app 的 service principal
2. 在三個 `mlflow_experiment_trace_*` 資料表上授予 MODIFY 與 SELECT
3. 在 app 程式碼中設定 trace 目的地
4. 部署 app

---

## 模式 10：從 Model Serving Endpoints 記錄 Trace

設定 model serving endpoint，將 trace 傳送到 Unity Catalog。

**步驟 1：授予使用者 / service principal 權限**
```sql
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `serving-principal-id`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `serving-principal-id`;
```

**步驟 2：產生 Personal Access Token (PAT)**

為具備上述權限的身分建立 PAT。

**步驟 3：將環境變數加入 endpoint**

將下列內容加入 serving endpoint 設定：
```
DATABRICKS_TOKEN=<your-personal-access-token>
MLFLOW_TRACING_DESTINATION=my_catalog.my_schema
```

**步驟 4：在提供服務的模型程式碼中設定目的地**
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation

mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="my_catalog",
        schema_name="my_schema",
    )
)

# 模型的 predict 函式 —— trace 會寫入 UC
@mlflow.trace
def predict(model_input):
    return my_model.invoke(model_input)
```

---

## 模式 11：從第三方 OTEL Client 記錄 Trace

透過 OTLP HTTP endpoint，將任何相容 OpenTelemetry 的 client 所產生的 trace 傳送到 Unity Catalog。

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 設定指向 Databricks 的 OTLP exporter
otlp_trace_exporter = OTLPSpanExporter(
    endpoint="https://<workspace-url>/api/2.0/otel/v1/traces",
    headers={
        "content-type": "application/x-protobuf",
        "X-Databricks-UC-Table-Name": "my_catalog.my_schema.mlflow_experiment_trace_otel_spans",
        "Authorization": "Bearer <YOUR_API_TOKEN>",
    },
)

# 設定 tracer provider
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))

# 使用標準 OpenTelemetry API 建立 span
tracer = provider.get_tracer("my-application")
with tracer.start_as_current_span("my-operation") as span:
    span.set_attribute("query", "What is MLflow?")
    result = process_query("What is MLflow?")
    span.set_attribute("result_length", len(result))
```

**注意：**
- 透過 OTEL 匯入的 trace，若包含 root span，會出現在已連結的 experiment 中
- 使用 `X-Databricks-UC-Table-Name` header 指定目標 spans 資料表
- 標準 OTEL instrumentation library 可搭配此 endpoint 使用

---

## 模式 12：啟用生產環境監控

註冊 scorer，以持續評估生產環境中的 trace。Scorer 會非同步地在抽樣 trace 上執行。

```python
import mlflow
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

# 步驟 1：設定用於監控的 SQL warehouse
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id="<SQL_WAREHOUSE_ID>",
    experiment_id="<EXPERIMENT_ID>"  # 選用——若省略則使用目前的 active experiment
)

# 步驟 2：設定 active experiment
mlflow.set_experiment("/Shared/my-agent-traces")

# 步驟 3：註冊並啟動 scorer

# Safety scorer —— 評估 100% 的 trace
safety = Safety().register(name="production_safety")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)

# 自訂 guidelines —— 評估 50% 的 trace
tone_check = Guidelines(
    name="professional_tone",
    guidelines="The response must be professional and helpful"
).register(name="production_tone")
tone_check = tone_check.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
```

**重要**：你必須同時執行 `.register()` 與 `.start()`——只有註冊並不會啟用監控。

**SQL Warehouse 需求：**
- 使用者必須對 SQL warehouse 擁有 `CAN USE`
- 使用者必須對 experiment 擁有 `CAN EDIT`
- 第一次註冊 scorer 時，系統會自動授予監控工作所需權限

---
## 模式 13：管理監控 Scorer

列出、更新、停止與刪除生產環境監控 scorer。

```python
from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer, ScorerSamplingConfig

# 列出 active experiment 的所有已註冊 scorer
scorers = list_scorers()
for s in scorers:
    print(f"  {s.name}: sample_rate={s.sampling_config.sample_rate if s.sampling_config else 'N/A'}")

# 取得特定 scorer
safety_scorer = get_scorer(name="production_safety")

# 更新抽樣率（例如從 50% 提高到 80%）
safety_scorer = safety_scorer.update(
    sampling_config=ScorerSamplingConfig(sample_rate=0.8)
)

# 停止監控（保留註冊，以便稍後重新啟動）
safety_scorer = safety_scorer.stop()

# 重新啟動監控
safety_scorer = safety_scorer.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)

# 完全刪除（移除註冊）
delete_scorer(name="production_safety")
```

---

## 模式 14：從 Unity Catalog 資料表查詢 Trace

直接使用 SQL 查詢已匯入的 trace，以進行自訂分析與 dashboard 製作。

```sql
-- 計算每日 trace 數量
SELECT
  DATE(timestamp) as trace_date,
  COUNT(DISTINCT trace_id) as trace_count
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL  -- 僅 root span
GROUP BY DATE(timestamp)
ORDER BY trace_date DESC;

-- 找出較慢的 trace（root span 持續時間 > 10 秒）
SELECT
  trace_id,
  name as root_span_name,
  (end_time_unix_nano - start_time_unix_nano) / 1e9 as duration_seconds
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
WHERE parent_span_id IS NULL
  AND (end_time_unix_nano - start_time_unix_nano) / 1e9 > 10
ORDER BY duration_seconds DESC
LIMIT 20;

-- 依 span 名稱統計錯誤率
SELECT
  name,
  COUNT(*) as total,
  SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) as errors,
  ROUND(SUM(CASE WHEN status_code = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as error_pct
FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
GROUP BY name
HAVING COUNT(*) > 10
ORDER BY error_pct DESC;
```

**從 Python（透過 Spark）：**
```python
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

# 查詢 trace span
spans_df = spark.sql("""
    SELECT trace_id, name, span_kind,
           (end_time_unix_nano - start_time_unix_nano) / 1e6 as duration_ms
    FROM my_catalog.my_schema.mlflow_experiment_trace_otel_spans
    WHERE name LIKE '%retriever%'
    ORDER BY duration_ms DESC
    LIMIT 100
""")
spans_df.show()
```

---

## 模式 15：端到端設定腳本

新專案的完整設定腳本——從建立 UC schema 連結，到記錄第一個 trace 與啟用監控。

```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig

# ============================================================
# 設定 —— 請更新這些值
# ============================================================
EXPERIMENT_NAME = "/Shared/my-agent-traces"
CATALOG_NAME = "my_catalog"
SCHEMA_NAME = "my_schema"
SQL_WAREHOUSE_ID = "abc123def456"  # 你的 SQL warehouse ID

# ============================================================
# 步驟 1：初始設定
# ============================================================
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = SQL_WAREHOUSE_ID

# 建立或取得 experiment
if experiment := mlflow.get_experiment_by_name(EXPERIMENT_NAME):
    experiment_id = experiment.experiment_id
else:
    experiment_id = mlflow.create_experiment(name=EXPERIMENT_NAME)

# 連結 UC schema（會自動建立 trace 資料表）
set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME
    ),
    experiment_id=experiment_id,
)
print(f"Linked experiment '{EXPERIMENT_NAME}' to {CATALOG_NAME}.{SCHEMA_NAME}")

# ============================================================
# 步驟 2：設定 Trace 目的地
# ============================================================
mlflow.set_experiment(EXPERIMENT_NAME)
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name=CATALOG_NAME,
        schema_name=SCHEMA_NAME,
    )
)

# ============================================================
# 步驟 3：啟用生產環境監控
# ============================================================
set_databricks_monitoring_sql_warehouse_id(
    warehouse_id=SQL_WAREHOUSE_ID,
    experiment_id=experiment_id,
)

# 註冊並啟動安全性監控（100% trace）
safety = Safety().register(name="safety_monitor")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=1.0)
)
print("Safety monitoring enabled (100% sample rate)")

# 註冊並啟動自訂 guidelines（50% trace）
tone = Guidelines(
    name="professional_tone",
    guidelines="The response must be professional, helpful, and concise"
).register(name="tone_monitor")
tone = tone.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
print("Tone monitoring enabled (50% sample rate)")

# ============================================================
# 步驟 4：使用測試 Trace 驗證
# ============================================================
@mlflow.trace
def test_agent(query: str) -> str:
    return f"Test response to: {query}"

result = test_agent("Hello, is tracing working?")
print(f"Test trace logged. Check the Experiments UI at: {EXPERIMENT_NAME}")
```

---

## 限制與配額

| 限制 | 數值 |
|-------|-------|
| Trace 匯入速率 | 每個 workspace 每秒 100 個 trace |
| 資料表匯入吞吐量 | 每個資料表每秒 100 MB |
| 查詢吞吐量 | 每秒 200 次查詢 |
| UI 效能 | 資料量超過 2TB 時會下降 |
| Trace 刪除 | 不支援逐筆刪除（請使用 SQL） |
| MLflow MCP server | 不支援儲存在 UC 中的 trace |
| 區域可用性 | 僅支援 `us-east-1` 與 `us-west-2`（Beta） |

---

## 在 UI 中檢視 Trace

1. 前往 Databricks workspace 中的 **Experiments** 頁面
2. 選取你的 experiment
3. 點選 **Traces** 分頁
4. 從下拉選單中選擇 **SQL warehouse**，以查詢儲存在 UC 中的 trace
5. 瀏覽 trace、檢查 span，以及查看輸入 / 輸出

**注意：** 你必須先選擇一個 SQL warehouse，才能檢視儲存在 UC 中的 trace——系統不會自動載入它們。
