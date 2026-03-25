# 使用 GEPA 的 MLflow 3 Prompt 最佳化

使用 GEPA（Genetic-Pareto）最佳化器搭配 `optimize_prompts()` 進行自動化 Prompt 改進的模式。GEPA 會透過 scorer 評估候選版本，逐步演化已註冊的 system prompt，然後提升最佳版本。

**建議使用對齊後的 judge 作為 scorer。** 對齊後的 judge 會編碼領域專家的偏好，相較於通用 LLM judge，能為 GEPA 提供更準確的最佳化訊號。完整的對齊工作流程請參閱 `patterns-judge-alignment.md`。

如需完整的端對端迴圈（evaluate、label、align、optimize、promote），請參閱 `user-journeys.md` 的 Journey 10。若要了解 GEPA 與 MemAlign 方法的細節，請參閱 [Self-Optimizing Agent 部落格文章](https://www.databricks.com/blog/self-optimizing-football-chatbot-guided-domain-experts-databricks)。

**實作前請先閱讀 `GOTCHAS.md`，尤其是 GEPA 相關章節。**

---

## 模式 1：建立最佳化資料集（必須包含 inputs + expectations）

GEPA 要求每筆記錄都同時包含 `inputs` 與 `expectations`。這與只需要 `inputs` 的 eval 資料集不同。`expectations` 欄位是 GEPA 在反思時用來推理目前 prompt 為何表現不佳的依據。

```python
# 最佳化資料集必須同時包含 inputs 與 expectations
optimization_dataset = [
    {
        "inputs": {
            "input": [{"role": "user", "content": "3 檔短碼數時有哪些傾向？"}]
        },
        "expectations": {
            "expected_response": (
                "代理程式應識別關鍵球員及其在 3 檔短碼數情境中的參與情況，"
                "提供相關統計資料，並給出戰術建議。"
                "如果存在資料品質問題，應明確說明。"
            )
        }
    },
    {
        "inputs": {
            "input": [{"role": "user", "content": "進攻方在遭遇 blitz 時的表現如何？"}]
        },
        "expectations": {
            "expected_response": (
                "代理程式應分析面對壓迫時的表現指標，"
                "比較不同 blitz 套件下的成功情況，"
                "並提供具體的防守建議。"
            )
        }
    },
    # 新增 15 到 20 個涵蓋關鍵使用案例的代表性範例
]

# 持久化到 MLflow 資料集
from mlflow.genai.datasets import create_dataset

optim_dataset = create_dataset(name=OPTIMIZATION_DATASET_NAME)
optim_dataset = optim_dataset.merge_records(optimization_dataset)
print(f"已建立最佳化資料集，共 {len(optimization_dataset)} 筆記錄")
```

---

## 模式 2：使用 GEPA 執行 optimize_prompts()

使用 scorer（理想情況下是來自 `patterns-judge-alignment.md` 的對齊後 judge）來驅動已註冊 system prompt 的 GEPA Prompt 最佳化。

```python
import mlflow
from mlflow.genai.optimize import GepaPromptOptimizer
from mlflow.genai.scorers import get_scorer

mlflow.set_experiment(experiment_id=EXPERIMENT_ID)

# 從 registry 載入 prompt（最佳化前必須先完成註冊）
system_prompt = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@production")
print(f"已載入 prompt: {system_prompt.uri}")

# 載入 scorer -- 建議使用對齊後的 judge 以進行符合領域需求的最佳化
# 如何建立 scorer，請參閱 patterns-judge-alignment.md
aligned_judge = get_scorer(name=ALIGNED_JUDGE_NAME, experiment_id=EXPERIMENT_ID)

# 定義 predict_fn -- 每次呼叫時都從 registry 載入 prompt，讓 GEPA 可以替換它
def predict_fn(input):
    prompt = mlflow.genai.load_prompt(system_prompt.uri)
    system_content = prompt.format()

    user_message = input[0]["content"]
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]
    return AGENT.predict({"input": messages})

# 定義 aggregation，將 judge feedback（Feedback.value）正規化為 0 到 1 供 GEPA 使用
def objective_function(scores: dict) -> float:
    feedback = scores.get(ALIGNED_JUDGE_NAME)
    if feedback and hasattr(feedback, "feedback") and hasattr(feedback.feedback, "value"):
        try:
            return float(feedback.feedback.value) / 5.0  # 將 1 到 5 的量表正規化為 0 到 1
        except (ValueError, TypeError):
            return 0.5
    return 0.5

# 執行最佳化
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,  # 必須包含 inputs + expectations
    prompt_uris=[system_prompt.uri],
    optimizer=GepaPromptOptimizer(
        reflection_model=REFLECTION_MODEL,
        max_metric_calls=75,            # 若要更快完成可降低；若要提升品質可增加
        display_progress_bar=True,
    ),
    scorers=[aligned_judge],
    aggregation=objective_function,
)

optimized_prompt = result.optimized_prompts[0]
print(f"初始分數: {result.initial_eval_score}")
print(f"最終分數:   {result.final_eval_score}")
print(f"\n最佳化後的範本（前 500 個字元）：\n{optimized_prompt.template[:500]}...")
```

---

## 模式 3：註冊最佳化後的 Prompt，並視情況提升

只有在最佳化後的 prompt 表現優於基準時，才提升到 `production` alias。

```python
# 以最佳化中繼資料註冊新的 prompt 版本
new_prompt_version = mlflow.genai.register_prompt(
    name=PROMPT_NAME,
    template=optimized_prompt.template,
    commit_message=f"使用 {ALIGNED_JUDGE_NAME} 進行 GEPA 最佳化",
    tags={
        "initial_score": str(result.initial_eval_score),
        "final_score": str(result.final_eval_score),
        "optimization": "GEPA",
        "judge": ALIGNED_JUDGE_NAME,
    },
)
print(f"已註冊 prompt 版本: {new_prompt_version.version}")

# 條件式提升 -- 僅在分數改善時更新 production alias
def promote_if_improved(prompt_name, result, new_prompt_version):
    if result.final_eval_score > result.initial_eval_score:
        mlflow.genai.set_prompt_alias(
            name=prompt_name,
            alias="production",
            version=new_prompt_version.version,
        )
        print(f"已將版本 {new_prompt_version.version} 提升到 production "
              f"（{result.initial_eval_score:.3f} -> {result.final_eval_score:.3f}）")
    else:
        print(f"沒有改善（{result.initial_eval_score:.3f} -> "
              f"{result.final_eval_score:.3f}）。production alias 維持不變。")

promote_if_improved(PROMPT_NAME, result, new_prompt_version)
```

---

## Prompt 最佳化建議

- 最佳化資料集應涵蓋代理程式會處理的查詢多樣性。請納入邊界案例、模稜兩可的請求，以及工具選擇很重要的情境。
- 預期回應應描述代理程式應該做什麼（要呼叫哪些工具、應包含哪些資訊），而不是精確的輸出文字。
- 建議先將 `max_metric_calls` 設定在 50 到 100 之間。較高的值會探索更多候選版本，但也會增加成本與執行時間。
- GEPA 最佳化器會從失敗模式中學習。如果對齊後的 judge 會對缺少 benchmark 或小樣本警語進行扣分，GEPA 就會把這些要求注入最佳化後的 prompt 中。
