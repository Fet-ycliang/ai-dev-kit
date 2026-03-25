# MLflow 3 GenAI 關鍵介面參考

**版本**：MLflow 3.1.0+（mlflow[databricks]>=3.1.0）
**最後更新**：依據 Databricks 官方文件

## 目錄

- [核心評估 API](#核心評估-api)
- [資料 Schema](#資料-schema)
- [內建 Scorer（預建）](#內建-scorer預建)
- [自訂 Scorer](#自訂-scorer)
- [Judges API（低階）](#judges-api低階)
- [Trace API](#trace-api)
- [評估 Dataset（MLflow 管理）](#評估-datasetmlflow-管理)
- [Unity Catalog 中的 Trace 攝取](#unity-catalog-中的-trace-攝取)
- [生產監控](#生產監控)
- [關鍵常數](#關鍵常數)
- [安裝](#安裝)
- [設定](#設定)

---

## 核心評估 API

### mlflow.genai.evaluate()

```python
import mlflow

results = mlflow.genai.evaluate(
    data=eval_dataset,        # List[dict]、DataFrame 或 EvalDataset
    predict_fn=my_app,        # 接收 **inputs 並回傳 outputs 的 Callable
    scorers=[scorer1, scorer2] # Scorer 物件清單
)

# 回傳：EvaluationResult，包含：
#   - results.run_id: str — MLflow run ID（存放評估結果）
#   - results.metrics: dict — 彙總指標
```

**重要事項**：
- `predict_fn` 接收 **解包後** 的 `inputs` dict 作為 kwargs
- 若 `data` 已包含預先計算的 `outputs`，`predict_fn` 為選填
- 每筆資料列都會自動建立 trace

---

## 資料 Schema

### 評估 Dataset 記錄格式

```python
# 正確格式
record = {
    "inputs": {                    # 必填——傳入 predict_fn
        "customer_name": "Acme",
        "query": "What is X?"
    },
    "outputs": {                   # 選填——預先計算的輸出
        "response": "X is..."
    },
    "expectations": {              # 選填——供 scorer 使用的基準答案
        "expected_facts": ["fact1", "fact2"],
        "expected_response": "X is...",
        "guidelines": ["Must be concise"]
    }
}
```

**重要的 Schema 規則**：
- `inputs` 為**必填**——包含傳入應用程式的資料
- `outputs` 為**選填**——若提供，則跳過 predict_fn
- `expectations` 為**選填**——供 Correctness、ExpectationsGuidelines 使用

---

## 內建 Scorer（預建）

### Import 路徑
```python
from mlflow.genai.scorers import (
    Guidelines,
    ExpectationsGuidelines,
    Correctness,
    RelevanceToQuery,
    RetrievalGroundedness,
    Safety,
)
```

### Guidelines Scorer
```python
Guidelines(
    name="my_guideline",              # 必填——唯一名稱
    guidelines="Response must...",     # 必填——str 或 List[str]
    model="databricks:/endpoint-name"  # 選填——自訂 judge 模型
)

# Guidelines 會自動從 trace 中提取 'request' 與 'response'
# 在 guidelines 中參照：「The response must address the request」
```

### ExpectationsGuidelines Scorer
```python
ExpectationsGuidelines()  # 無需參數

# 需要每筆資料列的 expectations.guidelines：
record = {
    "inputs": {...},
    "outputs": {...},
    "expectations": {
        "guidelines": ["Must mention X", "Must not include Y"]
    }
}
```

### Correctness Scorer
```python
Correctness(
    model="databricks:/endpoint-name"  # 選填
)

# 需要 expectations.expected_facts 或 expectations.expected_response：
record = {
    "inputs": {...},
    "outputs": {...},
    "expectations": {
        "expected_facts": ["MLflow is open-source", "Manages ML lifecycle"]
        # 或
        "expected_response": "MLflow is an open-source platform..."
    }
}
```

### Safety Scorer
```python
Safety(
    model="databricks:/endpoint-name"  # 選填
)
# 無需 expectations——評估輸出是否含有有害內容
```

### RelevanceToQuery Scorer
```python
RelevanceToQuery(
    model="databricks:/endpoint-name"  # 選填
)
# 檢查回應是否有回應使用者的請求
```

### RetrievalGroundedness Scorer
```python
RetrievalGroundedness(
    model="databricks:/endpoint-name"  # 選填
)
# 需要：trace 中有 RETRIEVER span 類型
# 檢查回應是否以檢索到的文件為根據
```

---

## 自訂 Scorer

### 函式型 Scorer（裝飾器）

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def my_scorer(
    inputs: dict,          # 來自資料記錄
    outputs: dict,         # 應用程式輸出或預先計算值
    expectations: dict,    # 來自資料記錄（選填）
    trace: Trace = None    # 完整的 MLflow Trace 物件（選填）
) -> Feedback | bool | int | float | str | list[Feedback]:
    """自訂 scorer 實作"""

    # 回傳選項：
    # 1. 簡單值（指標名稱 = 函式名稱）
    return True

    # 2. 含自訂名稱的 Feedback 物件
    return Feedback(
        name="custom_metric",
        value="yes",  # 或 "no"、True/False、int、float
        rationale="分數說明"
    )

    # 3. 多個 Feedback
    return [
        Feedback(name="metric_1", value=True),
        Feedback(name="metric_2", value=0.85)
    ]
```

### 類別型 Scorer

```python
from mlflow.genai.scorers import Scorer
from mlflow.entities import Feedback
from typing import Optional

class MyScorer(Scorer):
    name: str = "my_scorer"  # 必填
    threshold: int = 50      # 自訂欄位（Pydantic）

    def __call__(
        self,
        outputs: str,
        inputs: dict = None,
        expectations: dict = None,
        trace = None
    ) -> Feedback:
        if len(outputs) > self.threshold:
            return Feedback(value=True, rationale="符合長度要求")
        return Feedback(value=False, rationale="太短")

# 使用方式
my_scorer = MyScorer(threshold=100)
```

---

## Judges API（低階）

### Import 路徑
```python
from mlflow.genai.judges import (
    meets_guidelines,
    is_correct,
    is_safe,
    is_context_relevant,
    is_grounded,
    make_judge,
)
```

### meets_guidelines()
```python
from mlflow.genai.judges import meets_guidelines

feedback = meets_guidelines(
    name="my_check",                    # 選填，顯示名稱
    guidelines="Must be professional",   # str 或 List[str]
    context={                           # 包含待評估資料的 dict
        "request": "使用者問題",
        "response": "應用程式回應",
        "retrieved_documents": [...]     # 可包含任意鍵值
    },
    model="databricks:/endpoint"        # 選填，自訂模型
)
# 回傳：Feedback(value="yes"|"no", rationale="...")
```

### is_correct()
```python
from mlflow.genai.judges import is_correct

feedback = is_correct(
    request="What is MLflow?",
    response="MLflow is an open-source platform...",
    expected_facts=["MLflow is open-source"],  # 或 expected_response
    model="databricks:/endpoint"               # 選填
)
```

### make_judge() — 自訂 LLM Judge
```python
from mlflow.genai.judges import make_judge

issue_judge = make_judge(
    name="issue_resolution",
    instructions="""
    Evaluate if the customer's issue was resolved.
    User's messages: {{ inputs }}
    Agent's responses: {{ outputs }}

    Rate and respond with exactly one of:
    - 'fully_resolved'
    - 'partially_resolved'
    - 'needs_follow_up'
    """,
    model="databricks:/databricks-gpt-5-mini"  # 選填
)

# 用於評估
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[issue_judge]
)
```

### 基於 Trace 的 Judge（含 {{ trace }}）
```python
# instructions 中包含 {{ trace }} 可啟用 trace 探索
tool_judge = make_judge(
    name="tool_correctness",
    instructions="""
    Analyze the execution {{ trace }} to determine if appropriate tools were called.
    Respond with true or false.
    """,
    model="databricks:/databricks-gpt-5-mini"  # trace judge 必填
)
```

---

## Trace API

### 搜尋 Trace
```python
import mlflow

traces_df = mlflow.search_traces(
    filter_string="attributes.status = 'OK'",
    order_by=["attributes.timestamp_ms DESC"],
    max_results=100,
    run_id="optional-run-id"  # 篩選特定評估 run
)

# 常用篩選條件：
# "attributes.status = 'OK'" 或 "attributes.status = 'ERROR'"
# "attributes.timestamp_ms > {毫秒時間戳}"
# "attributes.execution_time_ms > 5000"
# "tags.environment = 'production'"
# "tags.`mlflow.traceName` = 'my_function'"
```

### 存取 Trace 物件
```python
from mlflow.entities import Trace, SpanType

@scorer
def trace_scorer(trace: Trace) -> Feedback:
    # 依類型搜尋 span
    llm_spans = trace.search_spans(span_type=SpanType.CHAT_MODEL)
    retriever_spans = trace.search_spans(span_type=SpanType.RETRIEVER)

    # 存取 span 資料
    for span in llm_spans:
        duration = (span.end_time_ns - span.start_time_ns) / 1e9
        inputs = span.inputs
        outputs = span.outputs
```

---

## 評估 Dataset（MLflow 管理）

### 建立 Dataset
```python
import mlflow.genai.datasets
from databricks.connect import DatabricksSession

# MLflow 管理的 dataset 必須先初始化 Spark
spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

eval_dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_eval_dataset"
)
```

### 新增記錄
```python
# 從 dict 清單新增
records = [
    {"inputs": {"query": "..."}, "expectations": {"expected_facts": [...]}},
]
eval_dataset.merge_records(records)

# 從 trace 新增
traces_df = mlflow.search_traces(filter_string="...")
eval_dataset.merge_records(traces_df)
```

### 用於評估
```python
results = mlflow.genai.evaluate(
    data=eval_dataset,  # 直接傳入 dataset 物件
    predict_fn=my_app,
    scorers=[...]
)
```

---

## Unity Catalog 中的 Trace 攝取

**版本**：MLflow 3.9.0+（`mlflow[databricks]>=3.9.0`）

### 設定 — 將 UC Schema 連結至 Experiment
```python
import os
import mlflow
from mlflow.entities import UCSchemaLocation
from mlflow.tracing.enablement import set_experiment_trace_location

mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"

experiment_id = mlflow.create_experiment(name="/Shared/my-traces")

set_experiment_trace_location(
    location=UCSchemaLocation(
        catalog_name="<CATALOG>",
        schema_name="<SCHEMA>"
    ),
    experiment_id=experiment_id,
)
# 建立：mlflow_experiment_trace_otel_logs、_metrics、_spans
```

### 設定 Trace Destination
```python
# 方式 A：Python API
from mlflow.entities import UCSchemaLocation
mlflow.tracing.set_destination(
    destination=UCSchemaLocation(
        catalog_name="<CATALOG>",
        schema_name="<SCHEMA>",
    )
)

# 方式 B：環境變數
os.environ["MLFLOW_TRACING_DESTINATION"] = "<CATALOG>.<SCHEMA>"
```

### 所需權限
- 在 catalog 上：`USE_CATALOG`
- 在 schema 上：`USE_SCHEMA`
- 在每個 `mlflow_experiment_trace_*` 資料表上：`MODIFY` 與 `SELECT`
- **重要**：`ALL_PRIVILEGES` **不足以**提供所需權限

---

## 生產監控

### 設定監控 SQL Warehouse
```python
from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id

set_databricks_monitoring_sql_warehouse_id(
    warehouse_id="<SQL_WAREHOUSE_ID>",
    experiment_id="<EXPERIMENT_ID>"  # 選填
)
# 替代方式：os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<ID>"
```

### Register 並 Start Scorer
```python
from mlflow.genai.scorers import Safety, Guidelines, ScorerSamplingConfig

# 將 scorer register 至 experiment
safety = Safety().register(name="safety_monitor")

# 以取樣率啟動監控
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)  # 50% 的 trace
)
```

### 管理 Scorer
```python
from mlflow.genai.scorers import list_scorers, get_scorer, delete_scorer

# 列出所有已 register 的 scorer
scorers = list_scorers()

# 取得特定 scorer
my_scorer = get_scorer(name="safety_monitor")

# 更新取樣率
my_scorer = my_scorer.update(
    sampling_config=ScorerSamplingConfig(sample_rate=0.8)
)

# 停止監控（保留 registration）
my_scorer = my_scorer.stop()

# 完全刪除
delete_scorer(name="safety_monitor")
```

---

## 關鍵常數

### Span 類型
```python
from mlflow.entities import SpanType

SpanType.CHAT_MODEL      # LLM 呼叫
SpanType.RETRIEVER       # RAG 檢索
SpanType.TOOL            # 工具／函式呼叫
SpanType.AGENT           # Agent 執行
SpanType.CHAIN           # Chain 執行
```

### Feedback 值
```python
# LLM judge 通常回傳：
"yes" | "no"     # 通過／失敗評估

# 自訂 scorer 可回傳：
True | False     # 布林值
0.0 - 1.0        # 浮點數分數
int              # 整數分數
str              # 類別值
```

---

## 安裝

```bash
pip install --upgrade "mlflow[databricks]>=3.1.0" openai
```

## 設定

```python
import mlflow

# 啟用自動 tracing
mlflow.openai.autolog()  # 或 mlflow.langchain.autolog() 等

# 設定 tracking URI
mlflow.set_tracking_uri("databricks")

# 設定 experiment
mlflow.set_experiment("/Shared/my-experiment")
```
