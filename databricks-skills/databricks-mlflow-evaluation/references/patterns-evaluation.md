# MLflow 3 評估模式

執行評估、比較結果及迭代品質改善的實用程式碼模式。

---

## Pattern 0：本地 Agent 測試優先（重要）

**務必直接 import agent 在本地測試，而非透過 model serving endpoint。**

這樣可加快疊代速度、便於除錯，並無需部署。

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# ✅ 正確：直接從模組 import agent
from plan_execute_agent import AGENT  # 或您的 agent 模組

# 啟用自動 tracing
mlflow.openai.autolog()
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-evaluation-experiment")

# 建立評估資料
eval_data = [
    {"inputs": {"messages": [{"role": "user", "content": "What is MLflow?"}]}},
    {"inputs": {"messages": [{"role": "user", "content": "How do I track experiments?"}]}},
]

# 定義使用本地 agent 的 predict 函式
def predict_fn(messages):
    """直接呼叫本地 agent 的包裝函式。"""
    result = AGENT.predict({"messages": messages})
    # 從 agent 輸出格式中取出回應
    if isinstance(result, dict) and "messages" in result:
        # ResponsesAgent 格式——取最後一則 assistant 訊息
        for msg in reversed(result["messages"]):
            if msg.get("role") == "assistant":
                return {"response": msg.get("content", "")}
    return {"response": str(result)}

# 以本地 agent 執行評估
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=predict_fn,
    scorers=[
        Safety(),
        Guidelines(name="helpful", guidelines="Response must be helpful and informative"),
    ]
)

print(f"Run ID: {results.run_id}")
print(f"Metrics: {results.metrics}")
```

### 為什麼要本地測試優先？

| 面向 | 本地 Agent | Model Serving Endpoint |
|------|------------|------------------------|
| 疊代速度 | 快（無需部署） | 慢（每次修改都要部署） |
| 除錯 | 完整堆疊追蹤 | 可見性有限 |
| 費用 | 無 serving 費用 | 需支付 endpoint 運算費用 |
| 依賴 | 直接存取 | 受網路延遲影響 |
| 使用情境 | 開發、測試 | 生產監控 |

### 何時使用 Model Serving Endpoint

僅在以下情況使用已部署的 endpoint：
- 生產監控與品質追蹤
- 對已部署模型進行壓力測試
- 對已部署版本進行 A/B 測試
- 外部整合測試

---

## Pattern 1：基本評估執行

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# 啟用自動 tracing
mlflow.openai.autolog()

# 設定 experiment
mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/my-evaluation-experiment")

# 定義應用程式
@mlflow.trace
def my_app(query: str) -> dict:
    # 您的應用程式邏輯
    response = call_llm(query)
    return {"response": response}

# 建立評估資料
eval_data = [
    {"inputs": {"query": "What is MLflow?"}},
    {"inputs": {"query": "How do I track experiments?"}},
    {"inputs": {"query": "What are best practices?"}},
]

# 定義 scorer
scorers = [
    Safety(),
    Guidelines(name="helpful", guidelines="Response must be helpful and informative"),
    Guidelines(name="concise", guidelines="Response must be under 200 words"),
]

# 執行評估
results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=scorers
)

print(f"Run ID: {results.run_id}")
print(f"Metrics: {results.metrics}")
```

---

## Pattern 2：使用預先計算輸出的評估

當您已有輸出結果時使用（例如來自生產日誌）。

```python
# 包含預先計算輸出的資料——無需 predict_fn
eval_data = [
    {
        "inputs": {"query": "What is X?"},
        "outputs": {"response": "X is a platform for..."}
    },
    {
        "inputs": {"query": "How to use Y?"},
        "outputs": {"response": "To use Y, follow these steps..."}
    }
]

# 不傳入 predict_fn 執行評估
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[Guidelines(name="quality", guidelines="Response must be accurate")]
)
```

---

## Pattern 3：含基準答案的評估

```python
from mlflow.genai.scorers import Correctness, Guidelines

# 包含 expectations 的資料，用於正確性驗證
eval_data = [
    {
        "inputs": {"query": "What is the capital of France?"},
        "expectations": {
            "expected_facts": ["Paris is the capital of France"]
        }
    },
    {
        "inputs": {"query": "What are MLflow's components?"},
        "expectations": {
            "expected_facts": [
                "Tracking",
                "Projects",
                "Models",
                "Registry"
            ]
        }
    }
]

results = mlflow.genai.evaluate(
    data=eval_data,
    predict_fn=my_app,
    scorers=[
        Correctness(),  # 使用 expected_facts
        Guidelines(name="format", guidelines="Must list items clearly")
    ]
)
```

---

## Pattern 4：具名評估 Run（供比較用）

```python
import mlflow

# 版本一評估
with mlflow.start_run(run_name="prompt_v1"):
    results_v1 = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=app_v1,
        scorers=scorers
    )

# 版本二評估
with mlflow.start_run(run_name="prompt_v2"):
    results_v2 = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=app_v2,
        scorers=scorers
    )

# 比較指標
print("V1 Metrics:", results_v1.metrics)
print("V2 Metrics:", results_v2.metrics)
```

---

## Pattern 5：分析評估結果

```python
import mlflow
import pandas as pd

# 評估執行後
results = mlflow.genai.evaluate(data=eval_data, predict_fn=my_app, scorers=scorers)

# 取得詳細 trace
traces_df = mlflow.search_traces(run_id=results.run_id)

# 存取每列結果
for idx, row in traces_df.iterrows():
    print(f"\n--- 第 {idx} 列 ---")
    print(f"輸入：{row['request']}")
    print(f"輸出：{row['response']}")

    # 存取評估結果（scorer 的結果）
    for assessment in row['assessments']:
        name = assessment['assessment_name']
        value = assessment['feedback']['value']
        rationale = assessment.get('rationale', 'N/A')
        print(f"  {name}: {value}")

# 篩選失敗的案例
def has_failures(assessments):
    return any(
        a['feedback']['value'] in ['no', False, 0]
        for a in assessments
    )

failures = traces_df[traces_df['assessments'].apply(has_failures)]
print(f"\n共找到 {len(failures)} 列有失敗")
```

---

## Pattern 6：比較兩次評估 Run

```python
import mlflow
import pandas as pd

# 取得 run
run_v1 = mlflow.search_runs(filter_string=f"run_id = '{results_v1.run_id}'")
run_v2 = mlflow.search_runs(filter_string=f"run_id = '{results_v2.run_id}'")

# 提取指標（以 /mean 結尾）
metric_cols = [col for col in run_v1.columns
               if col.startswith('metrics.') and col.endswith('/mean')]

# 建立比較表
comparison = []
for metric in metric_cols:
    metric_name = metric.replace('metrics.', '').replace('/mean', '')
    v1_val = run_v1[metric].iloc[0]
    v2_val = run_v2[metric].iloc[0]
    improvement = v2_val - v1_val

    comparison.append({
        'Metric': metric_name,
        'V1': f"{v1_val:.3f}",
        'V2': f"{v2_val:.3f}",
        'Change': f"{improvement:+.3f}",
        'Improved': '✓' if improvement >= 0 else '✗'
    })

comparison_df = pd.DataFrame(comparison)
print(comparison_df.to_string(index=False))
```

---

## Pattern 7：找出版本間的回歸問題

```python
import mlflow

# 取得兩個 run 的 trace
traces_v1 = mlflow.search_traces(run_id=results_v1.run_id)
traces_v2 = mlflow.search_traces(run_id=results_v2.run_id)

# 以 inputs 建立 merge key
traces_v1['merge_key'] = traces_v1['request'].apply(lambda x: str(x))
traces_v2['merge_key'] = traces_v2['request'].apply(lambda x: str(x))

# 以 inputs 合併
merged = traces_v1.merge(traces_v2, on='merge_key', suffixes=('_v1', '_v2'))

# 找出回歸（v1 通過，v2 失敗）
regressions = []
for idx, row in merged.iterrows():
    v1_assessments = {a['assessment_name']: a for a in row['assessments_v1']}
    v2_assessments = {a['assessment_name']: a for a in row['assessments_v2']}

    for scorer_name in v1_assessments:
        v1_val = v1_assessments[scorer_name]['feedback']['value']
        v2_val = v2_assessments.get(scorer_name, {}).get('feedback', {}).get('value')

        # 檢查回歸（yes→no 或 True→False）
        if v1_val in ['yes', True] and v2_val in ['no', False]:
            regressions.append({
                'input': row['request_v1'],
                'metric': scorer_name,
                'v1_output': row['response_v1'],
                'v2_output': row['response_v2'],
                'v1_rationale': v1_assessments[scorer_name].get('rationale'),
                'v2_rationale': v2_assessments[scorer_name].get('rationale')
            })

print(f"找到 {len(regressions)} 個回歸問題")
for r in regressions[:5]:  # 顯示前 5 個
    print(f"\n'{r['metric']}' 的回歸：")
    print(f"  輸入：{r['input']}")
    print(f"  V2 說明：{r['v2_rationale']}")
```

---

## Pattern 8：迭代改善循環

```python
import mlflow
from mlflow.genai.scorers import Guidelines

# 定義品質門檻
QUALITY_THRESHOLD = 0.9  # 90% 通過率

def evaluate_and_improve(app_fn, eval_data, scorers, max_iterations=5):
    """迭代改善直到達到品質門檻。"""

    for iteration in range(max_iterations):
        print(f"\n=== 第 {iteration + 1} 輪 ===")

        with mlflow.start_run(run_name=f"iteration_{iteration + 1}"):
            results = mlflow.genai.evaluate(
                data=eval_data,
                predict_fn=app_fn,
                scorers=scorers
            )

        # 計算整體通過率
        pass_rates = {}
        for metric, value in results.metrics.items():
            if metric.endswith('/mean'):
                metric_name = metric.replace('/mean', '')
                pass_rates[metric_name] = value

        avg_pass_rate = sum(pass_rates.values()) / len(pass_rates)
        print(f"平均通過率：{avg_pass_rate:.2%}")

        if avg_pass_rate >= QUALITY_THRESHOLD:
            print(f"✓ 已達到品質門檻 {QUALITY_THRESHOLD:.0%}！")
            return results

        # 找出表現最差的指標
        worst_metric = min(pass_rates, key=pass_rates.get)
        print(f"最差指標：{worst_metric}（{pass_rates[worst_metric]:.2%}）")

        # 分析該指標的失敗案例
        traces = mlflow.search_traces(run_id=results.run_id)
        failures = analyze_failures(traces, worst_metric)

        print(f"{worst_metric} 的失敗範例：")
        for f in failures[:3]:
            print(f"  - 輸入：{f['input'][:50]}...")
            print(f"    說明：{f['rationale']}")

        # 根據失敗案例更新 app_fn
        # 可以是手動或自動化 prompt 改善
        print("\n[根據失敗案例更新應用程式後再進行下一輪]")

    print(f"✗ 在 {max_iterations} 輪後仍未達到門檻")
    return results

def analyze_failures(traces, metric_name):
    """提取特定指標的失敗案例。"""
    failures = []
    for _, row in traces.iterrows():
        for assessment in row['assessments']:
            if (assessment['assessment_name'] == metric_name and
                assessment['feedback']['value'] in ['no', False]):
                failures.append({
                    'input': row['request'],
                    'output': row['response'],
                    'rationale': assessment.get('rationale', 'N/A')
                })
    return failures
```

---

## Pattern 9：從生產 Trace 建立評估

```python
import mlflow
import time

# 搜尋近期生產 trace
one_day_ago = int((time.time() - 86400) * 1000)  # 24 小時前（毫秒）

prod_traces = mlflow.search_traces(
    filter_string=f"""
        attributes.status = 'OK' AND
        attributes.timestamp_ms > {one_day_ago} AND
        tags.environment = 'production'
    """,
    order_by=["attributes.timestamp_ms DESC"],
    max_results=100
)

print(f"找到 {len(prod_traces)} 筆生產 trace")

# 轉換為評估格式
eval_data = []
for _, trace in prod_traces.iterrows():
    eval_data.append({
        "inputs": trace['request'],
        "outputs": trace['response']
    })

# 對生產資料執行評估
results = mlflow.genai.evaluate(
    data=eval_data,
    scorers=[
        Safety(),
        Guidelines(name="quality", guidelines="Response must be helpful")
    ]
)
```

---

## Pattern 10：A/B 測試兩個 Prompt

```python
import mlflow
from mlflow.genai.scorers import Guidelines, Safety

# 兩個不同的 system prompt
PROMPT_A = "You are a helpful assistant. Be concise."
PROMPT_B = "You are an expert assistant. Provide detailed, comprehensive answers."

def create_app(system_prompt):
    @mlflow.trace
    def app(query):
        response = client.chat.completions.create(
            model="databricks-claude-sonnet-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
        )
        return {"response": response.choices[0].message.content}
    return app

app_a = create_app(PROMPT_A)
app_b = create_app(PROMPT_B)

scorers = [
    Safety(),
    Guidelines(name="helpful", guidelines="Must be helpful"),
    Guidelines(name="accurate", guidelines="Must be accurate"),
    Guidelines(name="concise", guidelines="Must be under 100 words"),
]

# 執行 A/B 測試
with mlflow.start_run(run_name="prompt_a_concise"):
    results_a = mlflow.genai.evaluate(
        data=eval_data, predict_fn=app_a, scorers=scorers
    )

with mlflow.start_run(run_name="prompt_b_detailed"):
    results_b = mlflow.genai.evaluate(
        data=eval_data, predict_fn=app_b, scorers=scorers
    )

# 比較結果
print("Prompt A（簡潔）：", results_a.metrics)
print("Prompt B（詳細）：", results_b.metrics)
```

---

## Pattern 11：平行化評估

適用於大型資料集或複雜的應用程式。

```python
import mlflow

# 透過環境變數或 run 設定啟用平行化
# 預設為循序執行；增加平行度可加快評估速度

results = mlflow.genai.evaluate(
    data=large_eval_data,  # 1000 筆以上記錄
    predict_fn=my_app,
    scorers=scorers,
    # 平行化由內部處理
    # 若 agent 較複雜，考慮分批處理資料
)
```

---

## Pattern 12：CI/CD 持續評估

```python
import mlflow
import sys

def run_ci_evaluation():
    """作為 CI/CD 管道的一部分執行評估。"""

    # 載入測試資料
    eval_data = load_test_data()  # 從檔案或測試夾具載入

    # 定義品質門檻
    QUALITY_GATES = {
        "safety": 1.0,           # 100% 必須通過
        "helpful": 0.9,          # 90% 必須通過
        "concise": 0.8,          # 80% 必須通過
    }

    # 執行評估
    results = mlflow.genai.evaluate(
        data=eval_data,
        predict_fn=my_app,
        scorers=[
            Safety(),
            Guidelines(name="helpful", guidelines="Must be helpful"),
            Guidelines(name="concise", guidelines="Must be concise"),
        ]
    )

    # 檢查品質門檻
    failures = []
    for metric, threshold in QUALITY_GATES.items():
        actual = results.metrics.get(f"{metric}/mean", 0)
        if actual < threshold:
            failures.append(f"{metric}: {actual:.2%} < {threshold:.2%}")

    if failures:
        print("❌ 品質門檻未通過：")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("✅ 所有品質門檻均已通過")
        sys.exit(0)

if __name__ == "__main__":
    run_ci_evaluation()
```

---

## 評估最佳實踐

1. **從小規模開始**：先準備 20–50 個多元測試案例
2. **涵蓋邊界情況**：納入對抗性、模糊、超出範圍的輸入
3. **使用多個 Scorer**：結合安全性、品質及領域特定的檢查
4. **隨時間追蹤**：為 run 命名以便後續比較
5. **分析失敗案例**：不要只看彙總指標
6. **持續迭代**：根據失敗案例改善 prompt 或邏輯，再重新評估
7. **對資料版本化**：使用 MLflow 管理的 dataset 確保可重現性
