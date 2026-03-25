# MLflow 3 使用 MemAlign 進行評審員對齊

使用 MemAlign 將 LLM 評審員對齊至領域專家偏好的模式。對齊後的評審員在評估執行中更準確、在生產監控中更具意義，也能更好地引導提示最佳化——但這三種用途是相互獨立的。

**實作前請先閱讀 `GOTCHAS.md`，尤其是 MemAlign 的相關章節。**

---

## 何時使用評審員對齊

在以下情況時對齊評審員：
- 內建評分器無法捕捉領域特定的品質（例如「優秀」代表專家級的戰術分析）
- LLM 評審員與人工評分者對相同範例的評判結果不一致
- 您擁有可對一批代理輸出進行評分的領域專家
- 您希望生產監控能反映實際的專家標準

您**不需要**進行提示最佳化也能受益於對齊的評審員——更準確的評審員會改善您之後所有的評估執行和監控設定。

---

## 模式 1：設計並註冊基礎評審員

MemAlign 不依賴特定評分器，可搭配任何 `feedback_value_type`（float、boolean、categorical）使用。此範例使用 Likert 量表（1-5 float），但您可以使用任何適合您領域的評分方案。

```python
import mlflow
from mlflow.genai.judges import make_judge
from mlflow.genai import evaluate

mlflow.set_experiment(experiment_id=EXPERIMENT_ID)

# 使用 make_judge 定義基礎評審員 —— MemAlign 可搭配任何回饋類型使用
# 此範例使用 Likert 量表（1-5 float），但 boolean 或 categorical 也同樣適用
domain_quality_judge = make_judge(
    name="domain_quality_base",
    instructions=(
        "評估 {{ outputs }} 中的回應是否適當地分析了可用資料，"
        "並針對 {{ inputs }} 中的問題提供可行的建議。"
        "回應應準確、與情境相關，並為提問者提供策略優勢。"
        "您的評分標準："
        " 1：完全無法接受。資料解讀錯誤或未提供建議。"
        " 2：大部分無法接受。回饋不相關或流於表面，建議的策略優勢極低。"
        " 3：部分可接受。提供了相關回饋，具有一定的策略優勢。"
        " 4：大部分可接受。提供了相關回饋，具有強烈的策略優勢。"
        " 5：完全可接受。提供了相關回饋，具有優異的策略優勢。"
    ),
    feedback_value_type=float,   # 此範例使用 Likert 量表；MemAlign 可搭配任何回饋類型使用
    model=JUDGE_MODEL,
)

# 註冊至實驗 —— 建立 align() 所使用的持久性記錄
registered_base_judge = domain_quality_judge.register(experiment_id=EXPERIMENT_ID)
print(f"已註冊基礎評審員：{registered_base_judge.name}")
```

---

## 模式 2：執行評估並標記追蹤記錄

執行評估以產生一組供領域專家審閱的追蹤記錄。標記在此 `evaluate()` 工作中**成功評估**的追蹤記錄（即代理已產生回應，且評審員在無錯誤的情況下完成評分）。

```python
from mlflow.genai import evaluate

# 評估資料集：僅含輸入（此階段不需要期望值）
eval_data = [
    {"inputs": {"input": [{"role": "user", "content": question}]}}
    for question in example_questions
]

results = evaluate(
    data=eval_data,
    predict_fn=lambda input: AGENT.predict({"input": input}),
    scorers=[domain_quality_judge],
)

# 標記在此 evaluate() 工作中成功評估的追蹤記錄
# "OK" 狀態表示代理已回應且評審員無誤地完成評分
ok_trace_ids = results.result_df.loc[results.result_df["state"] == "OK", "trace_id"]
for trace_id in ok_trace_ids:
    mlflow.set_trace_tag(trace_id=trace_id, key="eval", value="complete")

print(f"已標記 {len(ok_trace_ids)} 筆成功評估的追蹤記錄以供標記")
```

---

## 模式 3：建立評估資料集並建立標記工作階段

將追蹤記錄持久化至 UC 資料集，並指派給領域專家進行審閱。

**重要：標籤架構的 `name` 必須與 `evaluate()` 工作中使用的評審員 `name` 完全一致。** 這是 `align()` 將中小企業回饋與相同追蹤記錄上對應 LLM 評審員分數配對的方式。若名稱不符，對齊將失敗或產生不正確的結果。

```python
from mlflow.genai.datasets import create_dataset, get_dataset
from mlflow.genai import create_labeling_session, get_review_app
from mlflow.genai import label_schemas

# 從已標記的追蹤記錄建立持久性資料集
try:
    eval_dataset = get_dataset(name=DATASET_NAME)
except Exception:
    eval_dataset = create_dataset(name=DATASET_NAME)

tagged_traces = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",
    return_type="pandas",
)
# merge_records() 預期欄位名稱為 'inputs' 和 'outputs'
if "inputs" not in tagged_traces.columns and "request" in tagged_traces.columns:
    tagged_traces = tagged_traces.rename(columns={"request": "inputs"})
if "outputs" not in tagged_traces.columns and "response" in tagged_traces.columns:
    tagged_traces = tagged_traces.rename(columns={"response": "outputs"})

eval_dataset = eval_dataset.merge_records(tagged_traces)

# 重要：標籤架構名稱必須與 evaluate() 中使用的評審員名稱完全一致
# 這是 align() 將中小企業回饋與 LLM 評審員分數配對的方式
LABEL_SCHEMA_NAME = "domain_quality_base"  # 必須與評審員名稱完全一致

feedback_schema = label_schemas.create_label_schema(
    name=LABEL_SCHEMA_NAME,               # 必須與模式 1 中的評審員名稱一致
    type="feedback",
    title=LABEL_SCHEMA_NAME,
    input=label_schemas.InputNumeric(min_value=1.0, max_value=5.0),
    instruction=(
        "評估回應是否適當地分析了可用資料，並針對問題提供可行的建議。"
        "回應應準確、與情境相關，並為提問者提供策略優勢。"
        "\n\n 您的評分標準應為："
        "\n 1：完全無法接受。資料解讀錯誤或未提供建議。"
        "\n 2：大部分無法接受。回饋不相關或流於表面，建議的策略優勢極低。"
        "\n 3：部分可接受。提供了相關回饋，具有一定的策略優勢。"
        "\n 4：大部分可接受。提供了相關回饋，具有強烈的策略優勢。"
        "\n 5：完全可接受。提供了相關回饋，具有優異的策略優勢。"
    ),
    enable_comment=True,   # 允許中小企業留下自由文字說明（MemAlign 會使用）
    overwrite=True,
)

# 選用：將已部署的代理加入 Review App，讓中小企業可提出新問題
review_app = get_review_app(experiment_id=EXPERIMENT_ID)
review_app = review_app.add_agent(
    agent_name=MODEL_NAME,
    model_serving_endpoint=AGENT_ENDPOINT_NAME,
    overwrite=True,
)

# 建立標記工作階段並附加資料集
labeling_session = create_labeling_session(
    name=f"{LABELING_SESSION_NAME}_sme",
    assigned_users=ASSIGNED_USERS,
    label_schemas=[LABEL_SCHEMA_NAME],     # 必須與評審員名稱一致
)
labeling_session = labeling_session.add_dataset(dataset_name=DATASET_NAME)

print(f"分享給領域專家的網址：{labeling_session.url}")
# 領域專家開啟此網址，使用 1-5 量表對每個回應進行評分
```

---

## 模式 4：使用 MemAlign 對齊評審員（建議方式）

中小企業完成標記後，將其回饋模式提煉至評審員的指令中。

評審員對齊支援多種最佳化器（例如 SIMBA、自訂最佳化器），但此範例使用 **MemAlign**，這是建議的方式。MemAlign 是最快的對齊方法（需數秒，而其他替代方案需數分鐘）、最具成本效益，並支援**記憶體擴展**，即隨著回饋累積品質可持續提升，無需重新最佳化。

```python
from mlflow.genai.judges.optimizers import MemAlignOptimizer
from mlflow.genai.scorers import get_scorer

# 擷取已標記的追蹤記錄（現在已附加中小企業標籤）
traces_for_alignment = mlflow.search_traces(
    locations=[EXPERIMENT_ID],
    filter_string="tag.eval = 'complete'",
    return_type="list",   # align() 需要清單格式
)
print(f"正在對齊 {len(traces_for_alignment)} 筆追蹤記錄")

# 設定 MemAlign 最佳化器
# 其他最佳化器可用（例如 SIMBA），但 MemAlign 以其速度、成本效益
# 及隨回饋累積持續改善的能力而被建議使用
optimizer = MemAlignOptimizer(
    reflection_lm=REFLECTION_MODEL,                       # 用於指引提煉的模型
    retrieval_k=5,                                        # 每次評估擷取的範例數
    embedding_model="databricks:/databricks-gte-large-en",
    # 未設定時預設為 "openai/text-embedding-3-small" —— 詳見 GOTCHAS.md
)

# 載入已註冊的基礎評審員並執行對齊
base_judge = get_scorer(name="domain_quality_base")
aligned_judge = base_judge.align(
    traces=traces_for_alignment,
    optimizer=optimizer,
)

# 檢視提煉出的語義指引 —— 這些編碼了專家偏好
print("從中小企業回饋提煉出的指引：")
for i, guideline in enumerate(aligned_judge._semantic_memory, 1):
    print(f"  {i}. {guideline.guideline_text}")
    if guideline.source_trace_ids:
        print(f"     衍生自 {len(guideline.source_trace_ids)} 筆追蹤記錄")
```

---

## 模式 5：註冊對齊後的評審員

將對齊後的評審員持久化至實驗，以便後續在評估或最佳化執行中擷取。

```python
from mlflow.genai.scorers import ScorerSamplingConfig

# 選項 A：原地更新現有評審員記錄（建議用於迭代式對齊）
aligned_judge_registered = aligned_judge.update(
    experiment_id=EXPERIMENT_ID,
    sampling_config=ScorerSamplingConfig(sample_rate=0.0),
)
print(f"已更新評審員：{aligned_judge_registered.name}")

# 選項 B：以新名稱版本註冊（保留原始版本以供比較）
from mlflow.genai.judges import make_judge

aligned_judge_v2 = make_judge(
    name="domain_quality_aligned_v1",
    instructions=aligned_judge.instructions,  # 包含提煉後的指引
    feedback_value_type=float,                # 與原始評審員的回饋類型一致
    model=JUDGE_MODEL,
)
aligned_judge_v2 = aligned_judge_v2.register(experiment_id=EXPERIMENT_ID)

# 在後續工作階段中擷取
# 注意：情節式記憶體是延遲載入的 —— 請檢視 .instructions，而非 ._episodic_memory
from mlflow.genai.scorers import get_scorer

retrieved_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
print(retrieved_judge.instructions[:500])  # 顯示包含指引的對齊後指令
```

---

## 模式 6：使用對齊後的評審員重新評估

使用對齊後的評審員執行全新評估。這能提供更準確的品質圖像，並在您選擇進行提示最佳化時建立基準線。

**重要：對齊後的評審員分數可能低於未對齊的評審員分數。這是預期且正確的結果。** 這意味著對齊後的評審員現在是以領域專家標準進行評估，而非通用最佳實踐。來自更準確評審員的較低分數，比來自不了解您領域的評審員的較高分數更具參考價值。最佳化階段（`optimize_prompts()`）將依據這個更準確的標準來改善代理。

```python
from mlflow.genai import evaluate
from mlflow.genai.scorers import get_scorer
from mlflow.genai.datasets import get_dataset

aligned_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)

eval_dataset = get_dataset(name=DATASET_NAME)
df = eval_dataset.to_df()

eval_records = [
    {
        "inputs": {
            "input": [{"role": "user", "content": extract_user_message(row)}]
        }
    }
    for row in df["inputs"]
]

with mlflow.start_run(run_name="aligned_judge_baseline"):
    baseline_results = evaluate(
        data=eval_records,
        predict_fn=lambda input: AGENT.predict({"input": input}),
        scorers=[aligned_judge],
    )

print(f"對齊後評審員的基準指標：{baseline_results.metrics}")
# 注意：若分數低於未對齊評審員，這是預期現象。
# 對齊後的評審員更準確，而非更寬鬆。
```

---

## 超越評估的對齊評審員用途

對齊後的評審員不僅限於一次性評估，還可用於：

**生產監控：**
```python
from mlflow.genai.scorers import ScorerSamplingConfig

aligned_judge = get_scorer(name="domain_quality_base", experiment_id=EXPERIMENT_ID)
monitoring_judge = aligned_judge.start(
    sampling_config=ScorerSamplingConfig(sample_rate=0.1)  # 對 10% 的生產流量進行評分
)
```

**提示最佳化輸入（參見 `patterns-prompt-optimization.md`）：**
```python
# 在 optimize_prompts() 中將對齊後的評審員作為評分器傳入
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,
    prompt_uris=[prompt.uri],
    optimizer=GepaPromptOptimizer(reflection_model=REFLECTION_MODEL),
    scorers=[aligned_judge],   # ← 對齊後的評審員驅動 GEPA 的反思
)
```

**跨代理版本的回歸偵測：**
```python
with mlflow.start_run(run_name="agent_v2"):
    v2_results = evaluate(data=eval_records, predict_fn=agent_v2, scorers=[aligned_judge])

# 來自對齊後評審員的指標比未對齊 LLM 評審員更具意義
```
