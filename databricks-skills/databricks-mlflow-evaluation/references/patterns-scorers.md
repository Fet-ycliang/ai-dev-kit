# MLflow 3 Scorer 模式

在 MLflow 3 GenAI 中建立與使用 Scorers 的可執行程式碼模式。

## 目錄

| # | 模式 | 說明 |
|---|------|------|
| 1 | [內建 Guidelines Scorer](#模式-1內建-guidelines-scorer) | 自然語言準則評估 |
| 2 | [使用 Ground Truth 的 Correctness Scorer](#模式-2使用-ground-truth-的-correctness-scorer) | 預期答案／事實驗證 |
| 3 | [使用 RetrievalGroundedness 的 RAG 評估](#模式-3使用-retrievalgroundedness-的-rag-評估) | 檢查回應是否以脈絡為依據 |
| 4 | [簡單自訂 Scorer（Boolean）](#模式-4簡單自訂-scorerboolean) | 通過／失敗檢查 |
| 5 | [含 Feedback Object 的自訂 Scorer](#模式-5含-feedback-object-的自訂-scorer) | 回傳 rationale 與自訂名稱 |
| 6 | [具有多個 Metrics 的自訂 Scorer](#模式-6具有多個-metrics-的自訂-scorer) | 一個 Scorer，多個 metrics |
| 7 | [包裝 LLM Judge 的自訂 Scorer](#模式-7包裝-llm-judge-的自訂-scorer) | 為內建 judges 提供自訂脈絡 |
| 8 | [以 Trace 為基礎的 Scorer](#模式-8以-trace-為基礎的-scorer) | 分析執行細節 |
| 9 | [含 Configuration 的 Class-Based Scorer](#模式-9含-configuration-的-class-based-scorer) | 可配置／具狀態的 Scorers |
| 10 | [依輸入條件進行評分](#模式-10依輸入條件進行評分) | 依輸入類型套用不同規則 |
| 11 | [具有 Aggregations 的 Scorer](#模式-11具有-aggregations-的-scorer) | 數值統計（mean、median、p90） |
| 12 | [自訂 Make Judge](#模式-12自訂-make-judge) | 複雜多層次評估 |
| 13 | [各階段／元件準確率 Scorer](#模式-13各階段元件準確率-scorer) | 多代理元件驗證 |
| 14 | [工具選擇準確率 Scorer](#模式-14工具選擇準確率-scorer) | 驗證是否呼叫正確工具 |
| 15 | [階段延遲 Scorer（多個 Metrics）](#模式-15階段延遲-scorer多個-metrics) | 各階段延遲 metrics |
| 16 | [元件準確率 Factory](#模式-16元件準確率-factory) | 可重用的 Scorer Factory |

---

## 模式 1：內建 Guidelines Scorer

適用於依自然語言準則進行評估。

```python
from mlflow.genai.scorers import Guidelines
import mlflow

# 單一準則
tone_scorer = Guidelines(
    name="professional_tone",
    guidelines="回應必須全程維持專業且樂於協助的語氣"
)

# 多個準則（一起評估）
quality_scorer = Guidelines(
    name="response_quality",
    guidelines=[
        "回應必須精簡且少於 200 個字",
        "回應必須直接回答使用者的問題",
        "回應不得包含杜撰資訊"
    ]
)

# 搭配自訂 judge model
custom_scorer = Guidelines(
    name="custom_check",
    guidelines="回應必須遵循公司政策",
    model="databricks:/databricks-gpt-oss-120b"
)

# 用於評估
results = mlflow.genai.evaluate(
    data=eval_dataset,
    predict_fn=my_app,
    scorers=[tone_scorer, quality_scorer]
)
```

---

## 模式 2：使用 Ground Truth 的 Correctness Scorer

當你有預期答案或事實時使用。

```python
from mlflow.genai.scorers import Correctness

# 含有預期事實的資料集
eval_data = [
    {
        "inputs": {"question": "什麼是 MLflow？"},
        "expectations": {
            "expected_facts": [
                "MLflow 是開源的",
                "MLflow 管理機器學習生命週期",
                "MLflow 包含實驗追蹤"
            ]
        }
    },
    {
        "inputs": {"question": "誰建立了 MLflow？"},
        "expectations": {
            "expected_response": "MLflow 由 Databricks 建立，並於 2018 年 6 月發布。"
        }
    }
]

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[Correctness()]
)
```

---

## 模式 3：使用 RetrievalGroundedness 的 RAG 評估

適用於 RAG 應用程式，用來檢查回應是否根據擷取到的脈絡。

```python
from mlflow.genai.scorers import RetrievalGroundedness, RelevanceToQuery
import mlflow
from mlflow.entities import Document

# App 必須具有 RETRIEVER span type
@mlflow.trace(span_type="RETRIEVER")
def retrieve_docs(query: str) -> list[Document]:
    """以 RETRIEVER span type 標記的擷取函式。"""
    # 你的擷取邏輯
    return [
        Document(
            id="doc1",
            page_content="這裡是擷取到的內容...",
            metadata={"source": "knowledge_base"}
        )
    ]

@mlflow.trace
def rag_app(query: str):
    docs = retrieve_docs(query)
    context = "
".join([d.page_content for d in docs])

    response = generate_response(query, context)
    return {"response": response}

# 使用 RAG 專用 Scorers 進行評估
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=rag_app,
    scorers=[
        RetrievalGroundedness(),  # 檢查回應與擷取文件是否一致
        RelevanceToQuery(),        # 檢查回應是否回答查詢
    ]
)
```

---

## 模式 4：簡單自訂 Scorer（Boolean）

適用於簡單的通過／失敗檢查。

```python
from mlflow.genai.scorers import scorer

@scorer
def contains_greeting(outputs):
    """檢查回應是否包含問候語。"""
    response = outputs.get("response", "").lower()
    greetings = ["你好", "嗨", "哈囉", "您好"]
    return any(g in response for g in greetings)

@scorer
def response_not_empty(outputs):
    """檢查回應是否非空。"""
    return len(str(outputs.get("response", ""))) > 0

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[contains_greeting, response_not_empty]
)
```

---

## 模式 5：含 Feedback Object 的自訂 Scorer

當你需要 rationale 或自訂名稱時使用。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def response_length_check(outputs):
    """檢查回應長度是否適當。"""
    response = str(outputs.get("response", ""))
    word_count = len(response.split())

    if word_count < 10:
        return Feedback(
            value="no",
            rationale=f"回應過短：{word_count} 個詞（至少需要 10 個詞）"
        )
    elif word_count > 500:
        return Feedback(
            value="no",
            rationale=f"回應過長：{word_count} 個詞（上限為 500 個詞）"
        )
    else:
        return Feedback(
            value="yes",
            rationale=f"回應長度可接受：{word_count} 個詞"
        )
```

---

## 模式 6：具有多個 Metrics 的自訂 Scorer

適用於單一 Scorer 需要產生多個 metrics 的情況。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback

@scorer
def comprehensive_check(inputs, outputs):
    """從單一 Scorer 回傳多個 metrics。"""
    response = str(outputs.get("response", ""))
    query = inputs.get("query", "")

    feedbacks = []

    # 檢查 1：回應是否存在
    feedbacks.append(Feedback(
        name="has_response",
        value=len(response) > 0,
        rationale="有回應" if response else "沒有回應"
    ))

    # 檢查 2：詞數
    word_count = len(response.split())
    feedbacks.append(Feedback(
        name="word_count",
        value=word_count,
        rationale=f"回應包含 {word_count} 個詞"
    ))

    # 檢查 3：查詢詞是否出現在回應中
    query_terms = set(query.lower().split())
    response_terms = set(response.lower().split())
    overlap = len(query_terms & response_terms) / len(query_terms) if query_terms else 0
    feedbacks.append(Feedback(
        name="query_coverage",
        value=round(overlap, 2),
        rationale=f"回應中涵蓋了 {overlap*100:.0f}% 的查詢詞"
    ))

    return feedbacks
```

---

## 模式 7：包裝 LLM Judge 的自訂 Scorer

當你需要為內建 judges 提供自訂脈絡時使用。

```python
from mlflow.genai.scorers import scorer
from mlflow.genai.judges import meets_guidelines

@scorer
def custom_grounding_check(inputs, outputs, trace=None):
    """透過自訂脈絡檢查回應是否有根據。"""

    # 從 inputs/outputs 擷取所需內容
    query = inputs.get("query", "")
    response = outputs.get("response", "")

    # 從 outputs 取得擷取文件（或從 trace 擷取）
    retrieved_docs = outputs.get("retrieved_documents", [])

    # 以自訂脈絡呼叫 judge
    return meets_guidelines(
        name="factual_grounding",
        guidelines=[
            "回應只能使用 retrieved_documents 中的事實",
            "回應不得提出 retrieved_documents 未支持的主張"
        ],
        context={
            "request": query,
            "response": response,
            "retrieved_documents": retrieved_docs
        }
    )
```

---

## 模式 8：以 Trace 為基礎的 Scorer

當你需要分析執行細節時使用。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace, SpanType

@scorer
def llm_latency_check(trace: Trace) -> Feedback:
    """檢查 LLM 回應時間是否可接受。"""

    # 在 Trace 中尋找 LLM spans
    llm_spans = trace.search_spans(span_type=SpanType.CHAT_MODEL)

    if not llm_spans:
        return Feedback(
            value="no",
            rationale="在 Trace 中找不到 LLM 呼叫"
        )

    # 計算 LLM 總時間
    total_llm_time = 0
    for span in llm_spans:
        duration = (span.end_time_ns - span.start_time_ns) / 1e9
        total_llm_time += duration

    max_acceptable = 5.0  # 秒

    if total_llm_time <= max_acceptable:
        return Feedback(
            value="yes",
            rationale=f"LLM 延遲 {total_llm_time:.2f}s 在 {max_acceptable}s 限制內"
        )
    else:
        return Feedback(
            value="no",
            rationale=f"LLM 延遲 {total_llm_time:.2f}s 超過 {max_acceptable}s 限制"
        )

@scorer
def tool_usage_check(trace: Trace) -> Feedback:
    """檢查是否呼叫了適當的工具。"""

    tool_spans = trace.search_spans(span_type=SpanType.TOOL)

    tool_names = [span.name for span in tool_spans]

    return Feedback(
        value=len(tool_spans) > 0,
        rationale=f"已呼叫的工具：{tool_names}" if tool_names else "未呼叫任何工具"
    )
```

---

## 模式 9：含 Configuration 的 Class-Based Scorer

當 Scorer 需要持久狀態或設定時使用。

```python
from mlflow.genai.scorers import Scorer
from mlflow.entities import Feedback
from typing import Optional, List

class KeywordRequirementScorer(Scorer):
    """可配置的 Scorer，用來檢查是否包含必要關鍵字。"""

    name: str = "keyword_requirement"
    required_keywords: List[str] = []
    case_sensitive: bool = False

    def __call__(self, outputs) -> Feedback:
        response = str(outputs.get("response", ""))

        if not self.case_sensitive:
            response = response.lower()
            keywords = [k.lower() for k in self.required_keywords]
        else:
            keywords = self.required_keywords

        missing = [k for k in keywords if k not in response]

        if not missing:
            return Feedback(
                value="yes",
                rationale=f"所有必要關鍵字皆已出現：{self.required_keywords}"
            )
        else:
            return Feedback(
                value="no",
                rationale=f"缺少關鍵字：{missing}"
            )

# 以不同設定使用
product_scorer = KeywordRequirementScorer(
    name="product_mentions",
    required_keywords=["MLflow", "Databricks"],
    case_sensitive=False
)

compliance_scorer = KeywordRequirementScorer(
    name="compliance_terms",
    required_keywords=["服務條款", "隱私權政策"],
    case_sensitive=True
)

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[product_scorer, compliance_scorer]
)
```

---

## 模式 10：依輸入條件進行評分

當不同輸入需要不同評估方式時使用。

```python
from mlflow.genai.scorers import scorer, Guidelines

@scorer
def conditional_scorer(inputs, outputs):
    """依查詢類型套用不同的準則。"""

    query = inputs.get("query", "").lower()

    if "技術" in query or "如何" in query:
        # 技術型查詢需要詳細回應
        judge = Guidelines(
            name="technical_quality",
            guidelines=[
                "回應必須包含逐步操作說明",
                "適用時回應必須包含程式碼範例"
            ]
        )
    elif "價格" in query or "費用" in query:
        # 價格型查詢需要具體資訊
        judge = Guidelines(
            name="pricing_quality",
            guidelines=[
                "回應必須包含具體價格資訊",
                "回應必須提及任何條件或限制"
            ]
        )
    else:
        # 一般查詢
        judge = Guidelines(
            name="general_quality",
            guidelines=[
                "回應必須直接回答問題",
                "回應必須清楚且精簡"
            ]
        )

    return judge(inputs=inputs, outputs=outputs)
```

---

## 模式 11：具有 Aggregations 的 Scorer

適用於需要彙總統計的數值型 Scorers。

```python
from mlflow.genai.scorers import scorer

@scorer(aggregations=["mean", "min", "max", "median", "p90"])
def response_latency(outputs) -> float:
    """回傳回應生成時間。"""
    return outputs.get("latency_ms", 0) / 1000.0  # 轉換為秒

@scorer(aggregations=["mean", "min", "max"])
def token_count(outputs) -> int:
    """回傳回應的 token 數。"""
    response = str(outputs.get("response", ""))
    # 粗略估算 token 數
    return len(response.split())

# 有效的 aggregations：min、max、mean、median、variance、p90
# 注意：p50、p99、sum 都不是有效值，請以 median 取代 p50
```

---

## 模式 12：自訂 Make Judge

適用於需要自訂指示的複雜多層次評估。

```python
from mlflow.genai.judges import make_judge

# 含多種結果的問題解決 judge
resolution_judge = make_judge(
    name="issue_resolution",
    instructions="""
    評估客戶的問題是否已被解決。

    使用者訊息：{{ inputs }}
    Agent 回應：{{ outputs }}

    請評估解決狀態，並只回覆以下其中一個值：
    - 'fully_resolved'：問題已完整處理，且提供明確解決方案
    - 'partially_resolved'：已有部分協助，但尚未完全解決
    - 'needs_follow_up'：問題未被充分處理

    你的回覆必須完全是這三個值之一。
    """,
    model="databricks:/databricks-gpt-5-mini"  # 可選
)

# 用於評估
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=support_agent,
    scorers=[resolution_judge]
)
```

---

## 結合多種 Scorer 類型

```python
from mlflow.genai.scorers import (
    Guidelines, Safety, Correctness,
    RelevanceToQuery, scorer
)
from mlflow.entities import Feedback

# 內建 Scorers
safety = Safety()
relevance = RelevanceToQuery()

# Guidelines Scorers
tone = Guidelines(name="tone", guidelines="必須保持專業")
format_check = Guidelines(name="format", guidelines="列出清單時必須使用項目符號")

# 自訂程式碼 Scorer
@scorer
def has_cta(outputs):
    """檢查是否包含行動呼籲。"""
    response = outputs.get("response", "").lower()
    ctas = ["聯絡我們", "了解更多", "立即開始", "註冊"]
    return any(cta in response for cta in ctas)

# 全部組合
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[
        safety,
        relevance,
        tone,
        format_check,
        has_cta
    ]
)
```

---

## 模式 13：各階段／元件準確率 Scorer

適用於多代理或多階段管線，用來驗證每個元件是否正確運作。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import Dict, Any

@scorer
def classifier_accuracy(
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    expectations: Dict[str, Any],
    trace: Trace
) -> Feedback:
    """檢查 classifier 是否正確識別查詢類型。"""

    expected_type = expectations.get("expected_query_type")

    if expected_type is None:
        return Feedback(
            name="classifier_accuracy",
            value="skip",
            rationale="expectations 中沒有 expected_query_type"
        )

    # 依名稱模式在 Trace 中尋找 classifier span
    classifier_spans = [
        span for span in trace.search_spans()
        if "classifier" in span.name.lower()
    ]

    if not classifier_spans:
        return Feedback(
            name="classifier_accuracy",
            value="no",
            rationale="在 Trace 中找不到 classifier span"
        )

    # 從 span outputs 擷取實際值
    span_outputs = classifier_spans[0].outputs or {}
    actual_type = span_outputs.get("query_type") if isinstance(span_outputs, dict) else None

    if actual_type is None:
        return Feedback(
            name="classifier_accuracy",
            value="no",
            rationale="classifier outputs 中沒有 query_type"
        )

    is_correct = actual_type == expected_type

    return Feedback(
        name="classifier_accuracy",
        value="yes" if is_correct else "no",
        rationale=f"預期為 '{expected_type}'，實際得到 '{actual_type}'"
    )
```

---

## 模式 14：工具選擇準確率 Scorer

檢查在 Agent 執行期間是否呼叫了正確的工具。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace, SpanType
from typing import Dict, Any, List

@scorer
def tool_selection_accuracy(
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    expectations: Dict[str, Any],
    trace: Trace
) -> Feedback:
    """檢查是否呼叫了正確的工具。"""

    expected_tools = expectations.get("expected_tools", [])

    if not expected_tools:
        return Feedback(
            name="tool_selection_accuracy",
            value="skip",
            rationale="expectations 中沒有 expected_tools"
        )

    # 從 TOOL spans 取得實際工具呼叫
    tool_spans = trace.search_spans(span_type=SpanType.TOOL)
    actual_tools = {span.name for span in tool_spans}

    # 正規化名稱（處理像是 "catalog.schema.func" 的完整名稱）
    def normalize(name: str) -> str:
        return name.split(".")[-1] if "." in name else name

    expected_normalized = {normalize(t) for t in expected_tools}
    actual_normalized = {normalize(t) for t in actual_tools}

    # 檢查是否已呼叫所有預期工具
    missing = expected_normalized - actual_normalized
    extra = actual_normalized - expected_normalized

    all_expected_called = len(missing) == 0

    rationale = f"預期：{list(expected_normalized)}，實際：{list(actual_normalized)}"
    if missing:
        rationale += f" | 缺少：{list(missing)}"
    if extra:
        rationale += f" | 額外：{list(extra)}"

    return Feedback(
        name="tool_selection_accuracy",
        value="yes" if all_expected_called else "no",
        rationale=rationale
    )
```

---

## 模式 15：階段延遲 Scorer（多個 Metrics）

量測各管線階段的延遲並找出瓶頸。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import List

@scorer
def stage_latency_scorer(trace: Trace) -> List[Feedback]:
    """量測每個管線階段的延遲。"""

    feedbacks = []
    all_spans = trace.search_spans()

    # Trace 總時間
    root_spans = [s for s in all_spans if s.parent_id is None]
    if root_spans:
        root = root_spans[0]
        total_ms = (root.end_time_ns - root.start_time_ns) / 1e6
        feedbacks.append(Feedback(
            name="total_latency_ms",
            value=round(total_ms, 2),
            rationale=f"總執行時間：{total_ms:.2f}ms"
        ))

    # 各階段延遲（請依你的管線自訂模式）
    stage_patterns = ["classifier", "rewriter", "executor", "retriever"]
    stage_times = {}

    for span in all_spans:
        span_name_lower = span.name.lower()
        for pattern in stage_patterns:
            if pattern in span_name_lower:
                duration_ms = (span.end_time_ns - span.start_time_ns) / 1e6
                stage_times[pattern] = stage_times.get(pattern, 0) + duration_ms
                break

    for stage, time_ms in stage_times.items():
        feedbacks.append(Feedback(
            name=f"{stage}_latency_ms",
            value=round(time_ms, 2),
            rationale=f"階段 '{stage}' 花費 {time_ms:.2f}ms"
        ))

    # 找出瓶頸
    if stage_times:
        bottleneck = max(stage_times, key=stage_times.get)
        feedbacks.append(Feedback(
            name="bottleneck_stage",
            value=bottleneck,
            rationale=f"最慢的階段：'{bottleneck}'，耗時 {stage_times[bottleneck]:.2f}ms"
        ))

    return feedbacks
```

---

## 模式 16：元件準確率 Factory

為任何元件／欄位組合建立可重用的 Scorers。

```python
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback, Trace
from typing import Dict, Any

def component_accuracy(
    component_name: str,
    output_field: str,
    expected_key: str = None
):
    """元件專用準確率 Scorer 的 Factory。

    參數:
        component_name: 用來比對 span 名稱的模式（例如 "classifier"）
        output_field: 要檢查的 span outputs 欄位（例如 "query_type"）
        expected_key: expectations 中的鍵（預設為 f"expected_{output_field}"）

    範例:
        router_accuracy = component_accuracy("router", "route", "expected_route")
    """
    if expected_key is None:
        expected_key = f"expected_{output_field}"

    @scorer
    def _scorer(
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        expectations: Dict[str, Any],
        trace: Trace
    ) -> Feedback:
        expected = expectations.get(expected_key)

        if expected is None:
            return Feedback(
                name=f"{component_name}_{output_field}_accuracy",
                value="skip",
                rationale=f"expectations 中沒有 {expected_key}"
            )

        # 尋找元件 span
        spans = [
            s for s in trace.search_spans()
            if component_name.lower() in s.name.lower()
        ]

        if not spans:
            return Feedback(
                name=f"{component_name}_{output_field}_accuracy",
                value="no",
                rationale=f"找不到 {component_name} span"
            )

        actual = spans[0].outputs.get(output_field) if isinstance(spans[0].outputs, dict) else None

        return Feedback(
            name=f"{component_name}_{output_field}_accuracy",
            value="yes" if actual == expected else "no",
            rationale=f"預期為 '{expected}'，實際得到 '{actual}'"
        )

    return _scorer

# 使用範例：
classifier_accuracy = component_accuracy("classifier", "query_type", "expected_query_type")
router_accuracy = component_accuracy("router", "route", "expected_route")
intent_accuracy = component_accuracy("intent", "intent_type", "expected_intent")
