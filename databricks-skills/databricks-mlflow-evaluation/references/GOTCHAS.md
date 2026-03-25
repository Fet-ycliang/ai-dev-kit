# MLflow 3 GenAI — 常見錯誤與陷阱

**重要**：撰寫任何評估程式碼前請先閱讀本文。以下是最常見的錯誤類型，會直接導致執行失敗。

## 目錄

- [開發時使用 Model Serving Endpoint](#-錯誤開發時使用-model-serving-endpoint)
- [錯誤的 API Import](#-錯誤的-api-import)
- [錯誤的評估函式](#-錯誤的評估函式)
- [錯誤的資料格式](#-錯誤的資料格式)
- [錯誤的 predict_fn 簽章](#-錯誤的-predict_fn-簽章)
- [錯誤的 Scorer 裝飾器用法](#-錯誤的-scorer-裝飾器用法)
- [錯誤的 Feedback 回傳值](#-錯誤的-feedback-回傳值)
- [錯誤的 Guidelines Scorer 設定](#-錯誤的-guidelines-scorer-設定)
- [錯誤的 Trace 搜尋語法](#-錯誤的-trace-搜尋語法)
- [錯誤的 Expectations 用法](#-錯誤的-expectations-用法)
- [錯誤的 RetrievalGroundedness 用法](#-錯誤的-retrievalgroundedness-用法)
- [錯誤的自訂 Scorer Import](#-錯誤的自訂-scorer-import)
- [Scorer 中錯誤的型別提示](#-scorer-中錯誤的型別提示)
- [錯誤的 Dataset 建立方式](#-錯誤的-dataset-建立方式)
- [多 Feedback 名稱衝突](#-多-feedback-名稱衝突)
- [Guidelines 中錯誤的 Context 變數參照](#-guidelines-中錯誤的-context-變數參照)
- [錯誤的生產監控設定](#-錯誤的生產監控設定)
- [錯誤的自訂 Judge 模型格式](#-錯誤的自訂-judge-模型格式)
- [無效的聚合值名稱](#-無效的聚合值名稱)
- [錯誤的 Trace 攝取設定](#-錯誤的-trace-攝取設定)
- [錯誤的 Trace Destination 格式](#-錯誤的-trace-destination-格式)
- [Trace 攝取使用過舊的 MLflow 版本](#-trace-攝取使用過舊的-mlflow-版本)
- [缺少 SQL Warehouse 即連結 UC Schema](#-缺少-sql-warehouse-即連結-uc-schema)
- [Label Schema 名稱錯誤 — 對齊將失敗](#-label-schema-名稱錯誤--對齊將失敗)
- [誤解對齊後的 Judge 分數](#-誤解對齊後的-judge-分數)
- [MemAlign Embedding Model 選擇不當 — Token 成本](#-memalign-embedding-model-選擇不當--token-成本)
- [MemAlign Episodic Memory — 延遲載入](#-memalign-episodic-memory--延遲載入)
- [GEPA 最佳化資料集缺少 expectations](#-gepa-最佳化資料集缺少-expectations)
- [總結檢查清單](#總結檢查清單)

---

## ❌ 錯誤：開發時使用 Model Serving Endpoint

### 錯誤：呼叫已部署的 endpoint 進行初始測試
```python
# ❌ 錯誤——開發階段不應使用 model serving endpoint
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
client = w.serving_endpoints.get_open_ai_client()

def predict_fn(messages):
    response = client.chat.completions.create(
        model="my-agent-endpoint",  # 已部署的 endpoint
        messages=messages
    )
    return {"response": response.choices[0].message.content}
```

### ✅ 正確：直接 import 並在本地測試 Agent
```python
# ✅ 正確——直接 import agent，加快疊代速度
from plan_execute_agent import AGENT  # 您的本地 agent 模組

def predict_fn(messages):
    result = AGENT.predict({"messages": messages})
    # 從 ResponsesAgent 格式中取出回應
    if isinstance(result, dict) and "messages" in result:
        for msg in reversed(result["messages"]):
            if msg.get("role") == "assistant":
                return {"response": msg.get("content", "")}
    return {"response": str(result)}
```

**原因：**
- 本地測試無需部署，疊代速度更快
- 可取得完整堆疊追蹤以利除錯
- 無 serving endpoint 費用
- 可直接存取 agent 內部狀態

**何時使用 endpoint**：僅用於生產監控、壓力測試，或對已部署版本進行 A/B 測試時。

---

## ❌ 錯誤的 API Import

### 錯誤：使用舊版 MLflow 2 的 import
```python
# ❌ 錯誤——MLflow 3 GenAI 中不存在這些 import
from mlflow.evaluate import evaluate
from mlflow.metrics import genai
import mlflow.llm
```

### ✅ 正確：MLflow 3 GenAI 的 import 方式
```python
# ✅ 正確
import mlflow.genai
from mlflow.genai.scorers import Guidelines, Safety, Correctness, scorer
from mlflow.genai.judges import meets_guidelines, is_correct, make_judge
from mlflow.entities import Feedback, Trace
```

---

## ❌ 錯誤的評估函式

### 錯誤：使用 mlflow.evaluate()
```python
# ❌ 錯誤——這是傳統 ML 使用的舊 API
results = mlflow.evaluate(
    model=my_model,
    data=eval_data,
    model_type="text"
)
```

### ✅ 正確：使用 mlflow.genai.evaluate()
```python
# ✅ 正確——MLflow 3 GenAI 評估
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[Guidelines(name="test", guidelines="...")]
)
```

---

## ❌ 錯誤的資料格式

### 錯誤：扁平資料結構
```python
# ❌ 錯誤——缺少巢狀結構
eval_data = [
    {"query": "What is X?", "expected": "X is..."}
]
```

### ✅ 正確：正確的巢狀結構
```python
# ✅ 正確——必須包含 'inputs' 鍵
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {"expected_response": "X is..."}
    }
]
```

---

## ❌ 錯誤的 predict_fn 簽章

### 錯誤：函式接收 dict
```python
# ❌ 錯誤——predict_fn 接收的是解包後的 inputs
def my_app(inputs):  # 接收 dict
    query = inputs["query"]
    return {"response": "..."}
```

### ✅ 正確：函式接收關鍵字引數
```python
# ✅ 正確——inputs 會以 kwargs 方式解包傳入
def my_app(query, context=None):  # 接收個別鍵值
    return {"response": f"Answer to {query}"}

# 若 inputs = {"query": "What is X?", "context": "..."}
# 則呼叫方式為：my_app(query="What is X?", context="...")
```

---

## ❌ 錯誤的 Scorer 裝飾器用法

### 錯誤：缺少裝飾器
```python
# ❌ 錯誤——不加裝飾器無法作為 scorer 運作
def my_scorer(inputs, outputs):
    return True
```

### ✅ 正確：使用 @scorer 裝飾器
```python
# ✅ 正確
from mlflow.genai.scorers import scorer

@scorer
def my_scorer(inputs, outputs):
    return True
```

---

## ❌ 錯誤的 Feedback 回傳值

### 錯誤：回傳錯誤的型別
```python
@scorer
def bad_scorer(outputs):
    # ❌ 錯誤——不能回傳 dict
    return {"score": 0.5, "reason": "..."}

    # ❌ 錯誤——不能回傳 tuple
    return (True, "rationale")
```

### ✅ 正確：回傳 Feedback 或基本型別
```python
from mlflow.entities import Feedback

@scorer
def good_scorer(outputs):
    # ✅ 正確——回傳基本型別
    return True
    return 0.85
    return "yes"

    # ✅ 正確——回傳 Feedback 物件
    return Feedback(
        value=True,
        rationale="說明"
    )

    # ✅ 正確——回傳 Feedback 清單
    return [
        Feedback(name="metric_1", value=True),
        Feedback(name="metric_2", value=0.9)
    ]
```

---

## ❌ 錯誤的 Guidelines Scorer 設定

### 錯誤：缺少必填參數
```python
# ❌ 錯誤——缺少 'name' 參數
scorer = Guidelines(guidelines="Must be professional")
```

### ✅ 正確：同時提供 name 與 guidelines
```python
# ✅ 正確
scorer = Guidelines(
    name="professional_tone",  # 必填
    guidelines="The response must be professional"  # 必填
)
```

---

## ❌ 錯誤的 Trace 搜尋語法

### 錯誤：缺少前綴或使用錯誤的引號
```python
# ❌ 錯誤——缺少前綴
mlflow.search_traces("status = 'OK'")

# ❌ 錯誤——使用雙引號
mlflow.search_traces('attributes.status = "OK"')

# ❌ 錯誤——含點號的名稱未加反引號
mlflow.search_traces("tags.mlflow.traceName = 'my_app'")

# ❌ 錯誤——不支援 OR
mlflow.search_traces("attributes.status = 'OK' OR attributes.status = 'ERROR'")
```

### ✅ 正確：正確的篩選語法
```python
# ✅ 正確——使用前綴與單引號
mlflow.search_traces("attributes.status = 'OK'")

# ✅ 正確——含點號的名稱加反引號
mlflow.search_traces("tags.`mlflow.traceName` = 'my_app'")

# ✅ 正確——支援 AND
mlflow.search_traces("attributes.status = 'OK' AND tags.env = 'prod'")

# ✅ 正確——時間使用毫秒
import time
cutoff = int((time.time() - 3600) * 1000)  # 1 小時前
mlflow.search_traces(f"attributes.timestamp_ms > {cutoff}")
```

---

## ❌ 錯誤的 Expectations 用法

### 錯誤：使用 Correctness 但未提供 expectations
```python
# ❌ 錯誤——Correctness 需要 expected_facts 或 expected_response
eval_data = [
    {"inputs": {"query": "What is X?"}}
]
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[Correctness()]  # 將失敗——無基準答案！
)
```

### ✅ 正確：為 Correctness 提供 expectations
```python
# ✅ 正確
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "expectations": {
            "expected_facts": ["X is a platform", "X is open-source"]
        }
    }
]
```

---

## ❌ 錯誤的 RetrievalGroundedness 用法

### 錯誤：應用程式中無 RETRIEVER span
```python
# ❌ 錯誤——應用程式沒有 RETRIEVER span 類型
@mlflow.trace
def my_rag_app(query):
    docs = get_documents(query)  # 未標記為 retriever
    return generate_response(docs, query)

# RetrievalGroundedness 將失敗——找不到 retriever span
```

### ✅ 正確：以正確的 span type 標記檢索步驟
```python
# ✅ 正確——使用 span_type="RETRIEVER"
@mlflow.trace(span_type="RETRIEVER")
def retrieve_documents(query):
    return [doc1, doc2]

@mlflow.trace
def my_rag_app(query):
    docs = retrieve_documents(query)  # 現在有 RETRIEVER span
    return generate_response(docs, query)
```

---

## ❌ 錯誤的自訂 Scorer Import

### 錯誤：在模組層級使用外部 import
```python
# ❌ 錯誤——生產監控的 scorer 不可在函式外部 import
import my_custom_library

@scorer
def production_scorer(outputs):
    return my_custom_library.process(outputs)
```

### ✅ 正確：在函式內部 import（生產 scorer 適用）
```python
# ✅ 正確——在函式內部 import 以利序列化
@scorer
def production_scorer(outputs):
    import json  # 在函式內部 import，供生產監控使用
    return len(json.dumps(outputs)) > 100
```

---

## ❌ Scorer 中錯誤的型別提示

### 錯誤：型別提示需要在函式簽章中 import
```python
# ❌ 錯誤——型別提示會破壞生產監控的序列化
from typing import List

@scorer
def bad_scorer(outputs: List[str]) -> bool:
    return True
```

### ✅ 正確：避免複雜型別提示，或使用 dict
```python
# ✅ 正確——簡單型別可使用
@scorer
def good_scorer(outputs):
    return True

# ✅ 正確——dict 可使用
@scorer
def good_scorer(outputs: dict) -> bool:
    return True
```

---

## ❌ 錯誤的 Dataset 建立方式

### 錯誤：建立 MLflow 管理的 Dataset 前未初始化 Spark
```python
# ❌ 錯誤——MLflow 管理的 dataset 需要 Spark
import mlflow.genai.datasets

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
# 錯誤：找不到 Spark session
```

### ✅ 正確：先初始化 Spark
```python
# ✅ 正確
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.remote(serverless=True).getOrCreate()

dataset = mlflow.genai.datasets.create_dataset(
    uc_table_name="catalog.schema.my_dataset"
)
```

---

## ❌ 多 Feedback 名稱衝突

### 錯誤：多個 Feedback 未指定唯一名稱
```python
@scorer
def bad_multi_scorer(outputs):
    # ❌ 錯誤——Feedback 將互相衝突
    return [
        Feedback(value=True),
        Feedback(value=0.8)
    ]
```

### ✅ 正確：為每個 Feedback 指定唯一名稱
```python
@scorer
def good_multi_scorer(outputs):
    # ✅ 正確——每個均有唯一名稱
    return [
        Feedback(name="check_1", value=True),
        Feedback(name="check_2", value=0.8)
    ]
```

---

## ❌ Guidelines 中錯誤的 Context 變數參照

### 錯誤：使用錯誤的變數名稱
```python
# ❌ 錯誤——Guidelines 使用 'request' 與 'response'，不是自訂鍵名
Guidelines(
    name="check",
    guidelines="The output must address the query"  # 'output' 和 'query' 不可用
)
```

### ✅ 正確：使用 'request' 與 'response'
```python
# ✅ 正確——這兩個變數會自動從 trace 中提取
Guidelines(
    name="check",
    guidelines="The response must address the request"
)
```

---

## ❌ 錯誤的生產監控設定

### 錯誤：只 register 忘記 start
```python
# ❌ 錯誤——已 register 但未 start
from mlflow.genai.scorers import Safety

safety = Safety().register(name="safety_check")
# Scorer 存在但未執行！
```

### ✅ 正確：register 後再 start
```python
# ✅ 正確——必須 register 並 start
from mlflow.genai.scorers import Safety, ScorerSamplingConfig

safety = Safety().register(name="safety_check")
safety = safety.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.5)
)
```

---

## ❌ 錯誤的自訂 Judge 模型格式

### 錯誤：模型格式錯誤
```python
# ❌ 錯誤——缺少 provider 前綴
Guidelines(name="test", guidelines="...", model="gpt-4o")

# ❌ 錯誤——分隔符號錯誤
Guidelines(name="test", guidelines="...", model="databricks:gpt-4o")
```

### ✅ 正確：使用 provider:/model 格式
```python
# ✅ 正確——使用 :/ 分隔符號
Guidelines(name="test", guidelines="...", model="databricks:/my-endpoint")
Guidelines(name="test", guidelines="...", model="openai:/gpt-4o")
```

---

## ❌ 無效的聚合值名稱

### 錯誤：使用不存在的聚合名稱
```python
# ❌ 錯誤——p50、p99、sum 均不合法
@scorer(aggregations=["mean", "p50", "p99", "sum"])
def my_scorer(outputs) -> float:
    return 0.5
```

### ✅ 正確：使用合法的聚合名稱
```python
# ✅ 正確——僅以下 6 個合法
@scorer(aggregations=["min", "max", "mean", "median", "variance", "p90"])
def my_scorer(outputs) -> float:
    return 0.5
```

**合法的聚合名稱：**
- `min` — 最小值
- `max` — 最大值
- `mean` — 平均值
- `median` — 第 50 百分位數（**不是** `p50`）
- `variance` — 統計變異數
- `p90` — 第 90 百分位數（僅 p90，**不支援** p50 或 p99）

---

## ❌ 錯誤的 Trace 攝取設定

### 錯誤：使用 ALL_PRIVILEGES 而非明確的授權
```sql
-- ❌ 錯誤——ALL_PRIVILEGES 不包含所需權限
GRANT ALL_PRIVILEGES ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
```

### ✅ 正確：明確授予 MODIFY 與 SELECT
```sql
-- ✅ 正確——必須明確授予 MODIFY 與 SELECT
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs
  TO `user@company.com`;
GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics
  TO `user@company.com`;
```

---

## ❌ 錯誤的 Trace Destination 格式

### 錯誤：環境變數格式錯誤
```python
# ❌ 錯誤——缺少 schema 或分隔符號錯誤
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog"
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog/my_schema"
```

### ✅ 正確：使用 catalog.schema 格式
```python
# ✅ 正確——以點號分隔的 catalog.schema
os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
```

---

## ❌ Trace 攝取使用過舊的 MLflow 版本

### 錯誤：UC trace 攝取使用 MLflow < 3.9.0
```bash
# ❌ 錯誤——Trace 攝取需要 3.9.0+
pip install mlflow[databricks]>=3.1.0
```

### ✅ 正確：UC trace 使用 MLflow 3.9.0+
```bash
# ✅ 正確
pip install "mlflow[databricks]>=3.9.0" --upgrade --force-reinstall
```

---

## ❌ 缺少 SQL Warehouse 即連結 UC Schema

### 錯誤：未設定 SQL warehouse 就連結
```python
# ❌ 錯誤——未設定 SQL warehouse
mlflow.set_tracking_uri("databricks")
# 缺少：os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "..."
set_experiment_trace_location(location=UCSchemaLocation(...), ...)
```

### ✅ 正確：先設定 SQL warehouse 再連結
```python
# ✅ 正確——先設定 warehouse ID
mlflow.set_tracking_uri("databricks")
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"
set_experiment_trace_location(location=UCSchemaLocation(...), ...)
```

---

## ❌ Label Schema 名稱錯誤 — 對齊將失敗

### 錯誤：Label schema 名稱與 evaluate() 中的 judge 名稱不一致
```python
# ❌ 錯誤——judge 名稱與 label schema 名稱不相符
# evaluate() 中 judge 以 "domain_quality_base" 名稱註冊
domain_quality_judge = make_judge(name="domain_quality_base", ...)
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)

# 但 label schema 使用了不同的名稱
feedback_schema = label_schemas.create_label_schema(
    name="domain_quality_rating",    # ❌ 與 judge 名稱不符
    type="feedback",
    ...
)
# align() 將無法將 SME 回饋與 LLM judge 分數配對
```

### ✅ 正確：Label schema 名稱與 judge 名稱完全一致
```python
# ✅ 正確——judge 名稱與 label schema 名稱完全相同
JUDGE_NAME = "domain_quality_base"

domain_quality_judge = make_judge(name=JUDGE_NAME, ...)
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)

feedback_schema = label_schemas.create_label_schema(
    name=JUDGE_NAME,                 # ✅ 與 judge 名稱完全一致
    type="feedback",
    ...
)
```

**原因：** `align()` 函式透過比對 label schema 名稱與同一 trace 上的 judge 名稱，來配對 SME 回饋與 LLM judge 分數。若名稱不一致，`align()` 無法找到對應的分數配對，對齊將失敗或產生錯誤結果。

---

## ❌ 誤解對齊後的 Judge 分數

### 錯誤：以為對齊後分數下降代表 Agent 退步
```python
# ❌ 錯誤的解讀——看到對齊後 judge 給出較低分數就恐慌
# 未對齊的 judge：平均 4.2/5.0
# 對齊後的 judge：平均 3.1/5.0
# 「Agent 退步了！」——不，是 judge 變得更精準了。
```

### ✅ 正確：理解較低的對齊後分數代表更準確的評估
```python
# ✅ 正確的解讀
# 對齊後的 judge 現在以領域專家的標準評估，而非通用的最佳實踐。
# 來自更精準 judge 的較低分數，遠比來自不了解您領域的 judge 的虛高分數更有參考價值。
# 未對齊的 judge 評估標準不夠明確。
# 請使用 optimize_prompts() 搭配已對齊的 judge 來改善 agent。
```

**原因：** 未對齊的 judge 以通用最佳實踐評估，往往給出虛高的分數。一旦以 SME 回饋完成對齊，judge 會套用更嚴格的領域特定標準。較低的分數不是 Agent 品質下滑；而是更誠實的評估。最佳化階段（`optimize_prompts()`）將根據這個更精準的標準來改善 Agent。

---

## ❌ MemAlign Embedding Model 選擇不當 — Token 成本

### 錯誤：未意識到預設 embedding model 的成本
```python
# ❌ 成本高——大量 trace 時預設 embedding model 可能非常昂貴
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,
    retrieval_k=5,
    # 未指定 embedding_model → 預設使用 "openai/text-embedding-3-small"
)
```

### ✅ 正確：使用 Databricks 託管的 embedding model，並縮小 trace 集的範圍
```python
# ✅ 正確——使用託管模型控制成本；將 trace 集限縮至已標記的 trace
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,
    retrieval_k=5,
    embedding_model="databricks:/databricks-gte-large-en",
)

# ✅ 同樣正確——只篩選已標記/已標注的 trace，而非整個 experiment 的 trace
traces = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",  # 只包含相關 trace
    return_type="list",
)
aligned_judge = base_judge.align(traces=traces, optimizer=optimizer)
```

**原因：** MemAlign 為每次評估的最近鄰檢索（`retrieval_k`）嵌入所有 trace。大量 trace 搭配昂貴的 embedding model 會使成本快速累積。使用 Databricks 託管模型（`databricks:/databricks-gte-large-en`）可將費用保留在平台內。

---

## ❌ MemAlign Episodic Memory — 延遲載入

### 錯誤：期望 get_scorer() 後立即能取得 episodic memory
```python
# ❌ 錯誤——episodic memory 看起來是空的，誤以為對齊失敗
retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
print(retrieved_judge._episodic_memory)  # 輸出：[] — 具有誤導性！
print(retrieved_judge._semantic_memory)  # 輸出：[] — 同樣是空的！
```

### ✅ 正確：Episodic memory 為延遲載入——先使用 judge，再檢查
```python
# ✅ 正確——semantic guidelines 已載入；episodic memory 在首次使用時才載入
retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)

# instructions 欄位已包含精煉後的 guidelines——應檢查此欄位
print(retrieved_judge.instructions)  # ✅ 顯示含 guidelines 的完整對齊 instructions

# 若要驗證 episodic memory，先在範本上執行 judge，再檢查
# Memory 在 judge 於評分時需要檢索相似範例時才會延遲載入
```

**原因：** MemAlign 的 episodic memory（儲存的範例）在 judge 評分時需要檢索相似範例才會按需載入。反序列化後 `_episodic_memory` 清單為空。`get_scorer()` 後可靠的檢查對象是 `instructions` 欄位（包含精煉後的 semantic guidelines）。

---

## ❌ GEPA 最佳化資料集缺少 expectations

### 錯誤：使用只有 inputs 的評估資料集執行 optimize_prompts()
```python
# ❌ 錯誤——GEPA 需要 expectations；缺少時最佳化將失敗或效果不佳
optimization_dataset = [
    {"inputs": {"input": [{"role": "user", "content": "How does the offense attack the blitz?"}]}},
    {"inputs": {"input": [{"role": "user", "content": "What are 3rd down tendencies?"}]}},
]

result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,   # ❌ 缺少 expectations
    prompt_uris=[prompt.uri],
    optimizer=GepaPromptOptimizer(...),
    scorers=[aligned_judge],
)
```

### ✅ 正確：最佳化資料集的每筆記錄都必須包含 expectations
```python
# ✅ 正確——每筆記錄必須同時包含 inputs 與 expectations
optimization_dataset = [
    {
        "inputs": {
            "input": [{"role": "user", "content": "How does the offense attack the blitz?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should analyze blitz performance metrics, compare success "
                "rates across pressure packages, and provide concrete tactical recommendations."
            )
        }
    },
    {
        "inputs": {
            "input": [{"role": "user", "content": "What are 3rd down tendencies?"}]
        },
        "expectations": {
            "expected_response": (
                "The agent should call the appropriate tool with down=3 parameters, "
                "summarize the play distribution, and give defensive recommendations."
            )
        }
    },
]
```

**原因：** GEPA 在反思階段使用 `expectations` 欄位——將 agent 的輸出與預期行為進行比較，以產生有針對性的 prompt 改善建議。沒有 `expectations`，GEPA 無法判斷當前 prompt *為何* 表現不佳。這是最佳化效果不佳最常見的原因。

---

## 總結檢查清單

執行評估前，請確認：

- [ ] 使用 `mlflow.genai.evaluate()`（不是 `mlflow.evaluate()`）
- [ ] 資料有 `inputs` 鍵（巢狀結構）
- [ ] `predict_fn` 接收 **kwargs（非 dict）
- [ ] Scorer 有 `@scorer` 裝飾器
- [ ] Guidelines 同時提供 `name` 與 `guidelines`
- [ ] Correctness 有 `expectations.expected_facts` 或 `expected_response`
- [ ] RetrievalGroundedness 在 trace 中有 `RETRIEVER` span
- [ ] Trace 篩選器使用 `attributes.` 前綴與單引號
- [ ] 生產 scorer 在函式內部 import
- [ ] 多個 Feedback 均有唯一名稱
- [ ] 聚合使用合法名稱：min、max、mean、median、variance、p90
- [ ] UC trace 攝取使用 `mlflow[databricks]>=3.9.0`
- [ ] UC 資料表有明確的 MODIFY + SELECT 授權（不是 ALL_PRIVILEGES）
- [ ] 連結 UC schema 前已設定 `MLFLOW_TRACING_SQL_WAREHOUSE_ID`
- [ ] `MLFLOW_TRACING_DESTINATION` 使用 `catalog.schema` 格式（點號分隔）
- [ ] 生產監控 scorer 已 register 且 start
- [ ] MemAlign `embedding_model` 可明確指定（大量 trace 時不依賴預設值）
- [ ] 對 MemAlign judge 呼叫 `get_scorer()` 後，檢查 `.instructions` 而非 `._episodic_memory`（episodic memory 為延遲載入）
- [ ] GEPA `train_data` 每筆記錄都有 `inputs` 與 `expectations`
- [ ] Label schema `name` 與 `evaluate()` 中的 judge `name` 完全一致（`align()` 配對分數所需）
- [ ] 對齊後的 judge 分數可能低於未對齊時——若 judge 更精準，這是預期行為
- [ ] MemAlign 與 scorer 無關（適用於任何 `feedback_value_type`——float、bool、categorical）
