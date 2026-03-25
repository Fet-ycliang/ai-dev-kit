# 使用者旅程指南

常見評估情境的逐步工作流程。

---

## 旅程 0：策略對齊（一定要先從這裡開始）

**起點**：你需要評估一個 agent
**目標**：在撰寫任何程式碼之前，先對齊要評估的內容

**優先順序：** 在撰寫評估程式碼之前，先完成策略對齊。這可確保評估衡量真正重要的事項，並提供可採取行動的洞察。

### 步驟 1：了解 Agent

在開始評估之前，先蒐集你要評估對象的背景脈絡：

**要詢問的問題（或在程式碼庫中調查）：**
1. **這個 agent 會做什麼？**（資料分析、RAG、多輪聊天、任務自動化）
2. **它會使用哪些工具？**（UC functions、vector search、外部 APIs）
3. **輸入／輸出格式是什麼？**（messages 格式、結構化輸出）
4. **目前狀態是什麼？**（原型、正式環境、需要改善）

**要採取的動作：**
- 閱讀 agent 的主要程式碼檔案（例如 `agent.py`）
- 檢視 config 檔案中的 system prompts 與工具定義
- 檢查既有測試或評估腳本
- 查看 CLAUDE.md 或 README 以了解專案背景

### 步驟 2：對齊要評估的內容

**可考慮的評估面向：**

| 面向 | 使用時機 | 範例 Scorer |
|-----------|-------------|----------------|
| **Safety** | 一律需要（基本門檻） | `Safety()` |
| **Correctness** | 有 ground truth 時 | `Correctness()` |
| **Relevance** | 回應應能回答查詢時 | `RelevanceToQuery()` |
| **Groundedness** | 具備擷取脈絡的 RAG 系統 | `RetrievalGroundedness()` |
| **Domain Guidelines** | 領域特定需求 | `Guidelines(name="...", guidelines="...")` |
| **Format/Structure** | 結構化輸出需求 | 自訂 scorer |
| **Tool Usage** | 會呼叫工具的 agents | 檢查工具選擇的自訂 scorer |

**要詢問使用者的問題：**
1. 哪些是**必備**品質條件？（safety、accuracy、relevance）
2. 哪些是**加分但非必要**的條件？（精簡、語氣、格式）
3. 是否有你曾遇過或擔心的**特定失敗模式**？
4. 你是否有測試案例的 **ground truth** 或預期答案？

### 步驟 3：定義使用者情境（評估資料集）

**應包含的測試案例類型：**

| 類別 | 目的 | 範例 |
|----------|---------|---------|
| **正常路徑** | 核心功能可正常運作 | 一般使用者問題 |
| **邊界案例** | 邊界條件 | 空輸入、非常長的查詢 |
| **對抗性案例** | 強健性測試 | Prompt injection、離題內容 |
| **多輪互動** | 對話處理能力 | 追問、脈絡回憶 |
| **領域特定** | 商業邏輯 | 產業術語、特定格式 |

**要詢問使用者的問題：**
1. 使用者最常問的問題是什麼？
2. 哪些是 agent 應該能處理的**高難度**問題？
3. 是否有一些問題是它應該**拒絕回答**的？
4. 你是否有可作為起點的**既有測試案例**或正式環境 traces？

### 步驟 4：建立成功標準

**在執行評估之前先定義品質門檻：**

```python
QUALITY_GATES = {
    "safety": 1.0,           # 100% - 不可妥協
    "correctness": 0.9,      # 90% - 準確性高標準
    "relevance": 0.85,       # 85% - 良好的相關性
    "concise": 0.8,          # 80% - 有最好
}
```

**要詢問使用者的問題：**
1. 每個面向可接受的通過率是多少？
2. 哪些指標是**阻擋上線**，哪些只是**資訊參考**？
3. 評估結果將如何**協助決策**？（上線／不上線、迭代、調查）

### 策略對齊檢查清單

在實作評估之前，確認：
- [ ] 已了解 Agent 目的與架構
- [ ] 已就評估面向取得共識
- [ ] 已識別測試案例類別
- [ ] 已定義成功標準
- [ ] 已確認資料來源（新資料、traces、既有資料集）

---

## 旅程 3：「有東西壞掉了」- 迴歸偵測

**起點**：你修改了 agent，懷疑有地方退化了
**目標**：找出壞掉的地方並驗證修復結果

### 步驟

1. **建立基準指標**
   ```bash
   # 在前一個版本上執行評估（或使用已儲存的 baseline）
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   記錄關鍵指標：`classifier_accuracy`、`tool_selection_accuracy`、`follows_instructions`

2. **在目前版本上執行評估**
   ```bash
   python run_quick_eval.py
   ```

3. **比較指標**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.compare_iterations(-2, -1))  # 比較最後兩次
   ```

4. **找出迴歸來源**
   - 如果 `classifier_accuracy` 下降 → 檢查 ClassifierSignature 的變更
   - 如果 `tool_selection_accuracy` 下降 → 檢查工具描述、required_tools 欄位
   - 如果 `follows_instructions` 下降 → 檢查 ExecutorSignature 的輸出格式

5. **分析失敗的 traces**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   觀察：
   - 特定測試類別中的錯誤模式
   - 工具呼叫失敗
   - 非預期輸出

6. **修正並重新評估**
   - 還原有問題的變更，或套用針對性的修正
   - 重新執行評估
   - 確認指標已恢復

### 使用的指令
- `python run_quick_eval.py` - 執行評估
- `/eval:analyze-traces` - 深入 trace 分析
- `OptimizationHistory.compare_iterations()` - 指標比較

### 成功指標
- 指標回到 baseline 或有所改善
- 沒有新增失敗的測試案例
- Trace 分析顯示符合預期的行為

---

## 旅程 7：「我的 Multi-Agent 很慢」- 效能最佳化

**起點**：你的 agent 回應速度太慢
**目標**：找出瓶頸並降低延遲

### 步驟

1. **執行包含延遲評分的評估**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   注意以下延遲指標：
   - `classifier_latency_ms`
   - `rewriter_latency_ms`
   - `executor_latency_ms`
   - `total_latency_ms`

2. **找出瓶頸階段**
   | 延遲 | 一般範圍 | 偏高時檢查 |
   |---------|---------------|----------------|
   | classifier_latency | <5s | ClassifierSignature 是否過度冗長 |
   | rewriter_latency | <10s | QueryRewriterSignature 是否過於複雜 |
   | executor_latency | <30s | 工具呼叫次數、回應生成 |

3. **分析 traces 中的慢速階段**
   ```
   /eval:analyze-traces [experiment-id]
   ```
   聚焦於：
   - 各階段的 span 持續時間
   - 每個階段的 LLM 呼叫數量
   - 工具執行時間

4. **執行 signature 分析**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   檢查：
   - 總描述字元數過高（>2000）
   - OutputField 描述過於冗長
   - 缺少範例（會導致更多重試）

5. **套用最佳化**

   **若 classifier 延遲過高：**
   - 簡化 ClassifierSignature docstring
   - 加入具體範例以降低歧義

   **若 executor 延遲過高：**
   - 簡化 ExecutorSignature.answer 格式
   - 降低輸出格式要求
   - 考慮快取重複的工具呼叫

   **若總延遲過高：**
   - 檢查所有階段是否都有存在必要
   - 在可行處考慮平行執行

6. **重新評估並比較**
   ```bash
   python run_quick_eval.py
   ```
   使用 `OptimizationHistory.compare_iterations()` 驗證是否改善

### 使用的指令
- `python run_quick_eval.py` - 執行包含延遲評分的評估
- `/eval:analyze-traces` - 含時間拆解的 trace 分析
- `python -m evaluation.analyze_signatures` - signature 冗長度分析

### 成功指標
- 目標延遲：classifier <5s、executor <30s、total <60s
- 準確率指標沒有迴歸
- 各測試類別皆有一致改善

---

## 旅程 8：「改善我的 Prompts」- 系統化 Prompt 最佳化

**起點**：你的 agent 能運作，但準確度還能更好
**目標**：透過評估系統化改善 prompt 品質

### 步驟

1. **建立 baseline**
   ```bash
   cd agents/tool_calling_dspy
   python run_quick_eval.py
   ```
   將所有指標記錄在 `optimization_history.json`

2. **執行 signature 分析**
   ```bash
   python -m evaluation.analyze_signatures
   ```
   檢視報告中的：
   - 指標相關性（哪些 signatures 影響哪些 metrics）
   - 各 signature 被標記出的具體問題

3. **依指標影響程度排序修正優先順序**

   | 指標 | 主要 Signature | 常見問題 |
   |--------|-------------------|---------------|
   | follows_instructions | ExecutorSignature | answer 格式冗長、結構不清楚 |
   | tool_selection_accuracy | ClassifierSignature | 沒有範例、工具描述模糊 |
   | classifier_accuracy | ClassifierSignature | docstring 冗長、query_type 對應不清楚 |

4. **一次只套用一個修正**
   - 只做單一、精準的修改
   - 在 commit message 記錄這項修改
   - 在 optimization_history.json 中追蹤

5. **立即重新評估**
   ```bash
   python run_quick_eval.py
   ```
   - 如果改善 → 保留變更，進行下一個修正
   - 如果退化 → 還原並嘗試不同做法
   - 如果沒有變化 → 評估該修正是否有必要

6. **持續迭代直到達成目標**

   | 指標 | 目標 |
   |--------|--------|
   | classifier_accuracy | 95%+ |
   | tool_selection_accuracy | 90%+ |
   | follows_instructions | 80%+ |

7. **記錄成功的最佳化結果**
   ```python
   from evaluation.optimization_history import OptimizationHistory

   history = OptimizationHistory()
   print(history.summary())
   ```

### 使用的指令
- `python run_quick_eval.py` - 執行評估
- `python -m evaluation.analyze_signatures` - 找出 prompt 問題
- `/optimize:context --quick` - 完整最佳化迴圈（當 endpoint 可用時）

### 成功指標
- 所有目標指標皆達標
- 相較 baseline 沒有任何迴歸
- 清楚記錄變更內容與原因
- 最佳化歷史顯示正向趨勢

---

## 旅程 9：「將 Traces 儲存在 Unity Catalog」- Trace 擷取與正式環境監控

**起點**：你想將 traces 持久化到 Unity Catalog，以便進行長期分析、合規或正式環境監控
**目標**：設定 trace 擷取、為應用程式加入 instrumentation，並啟用持續監控

### 先決條件

- 已啟用 Unity Catalog 的 workspace
- 已啟用「OpenTelemetry on Databricks」預覽版
- 具備 `CAN USE` 權限的 SQL warehouse
- MLflow 3.9.0+（`pip install mlflow[databricks]>=3.9.0`）
- workspace 位於 `us-east-1` 或 `us-west-2`（Beta 限制）

### 步驟

1. **將 UC schema 連結到 experiment**
   ```python
   import os
   import mlflow
   from mlflow.entities import UCSchemaLocation
   from mlflow.tracing.enablement import set_experiment_trace_location

   mlflow.set_tracking_uri("databricks")
   os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = "<SQL_WAREHOUSE_ID>"

   experiment_id = mlflow.create_experiment(name="/Shared/my-traces")
   set_experiment_trace_location(
       location=UCSchemaLocation(catalog_name="my_catalog", schema_name="my_schema"),
       experiment_id=experiment_id,
   )
   ```
   這會建立三張資料表：`mlflow_experiment_trace_otel_logs`、`_metrics`、`_spans`

2. **授與權限**
   ```sql
   GRANT USE_CATALOG ON CATALOG my_catalog TO `user@company.com`;
   GRANT USE_SCHEMA ON SCHEMA my_catalog.my_schema TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_logs TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_spans TO `user@company.com`;
   GRANT MODIFY, SELECT ON TABLE my_catalog.my_schema.mlflow_experiment_trace_otel_metrics TO `user@company.com`;
   ```
   **關鍵：** `ALL_PRIVILEGES` 並不足夠 —— 必須明確授與 MODIFY + SELECT。

3. **在應用程式中設定 trace 目的地**
   ```python
   mlflow.tracing.set_destination(
       destination=UCSchemaLocation(catalog_name="my_catalog", schema_name="my_schema")
   )
   # 或
   os.environ["MLFLOW_TRACING_DESTINATION"] = "my_catalog.my_schema"
   ```

4. **為你的應用程式加入 instrumentation**

   選擇適合的方法：
   - **Auto-tracing**：`mlflow.openai.autolog()`（或 langchain、anthropic 等）
   - **Manual tracing**：在函式上使用 `@mlflow.trace` decorator
   - **Context manager**：`mlflow.start_span()`，提供更細緻的控制
   - **Combined**：Auto-tracing + manual decorators，以取得完整覆蓋

   詳細範例請參閱 `patterns-trace-ingestion.md` 的模式 5-8。

5. **設定其他 trace 來源**（如適用）

   | 來源 | 主要設定 |
   |--------|-------------------|
   | Databricks Apps | 授與 SP 權限、設定 `MLFLOW_TRACING_DESTINATION` |
   | Model Serving | 新增 `DATABRICKS_TOKEN` + `MLFLOW_TRACING_DESTINATION` 環境變數 |
   | OTEL Clients | 使用帶有 `X-Databricks-UC-Table-Name` header 的 OTLP exporter |

   各來源的詳細設定請參閱 `patterns-trace-ingestion.md` 的模式 9-11。

6. **啟用正式環境監控**
   ```python
   from mlflow.tracing import set_databricks_monitoring_sql_warehouse_id
   from mlflow.genai.scorers import Safety, ScorerSamplingConfig

   set_databricks_monitoring_sql_warehouse_id(warehouse_id="<SQL_WAREHOUSE_ID>")

   safety = Safety().register(name="safety_monitor")
   safety = safety.start(sampling_config=ScorerSamplingConfig(sample_rate=1.0))
   ```

7. **在 UI 中驗證**
   - 前往 **Experiments** → 你的 experiment → **Traces** 分頁
   - 從下拉選單選擇 SQL warehouse 以載入 UC traces
   - 確認 traces 以正確的 span 階層顯示

### 參考檔案
- `patterns-trace-ingestion.md` — 所有設定與 instrumentation 模式
- `CRITICAL-interfaces.md` — Trace 擷取 API signatures
- `GOTCHAS.md` — 常見 trace 擷取錯誤

### 成功指標
- 在 Experiments UI 的 Traces 分頁中可看見 traces
- 三張 UC 資料表已有資料
- 正式環境監控 scorers 正在執行並產生評估結果
- Trace 擷取時沒有權限錯誤

---

## 旅程 10：領域專家最佳化迴圈

**起點**：你已有一個 agent，並想納入領域專家的回饋來持續提升品質。
**目標**：執行完整的 evaluate、label、align judge、optimize prompt、promote 週期。

如需完整架構與端到端流程，請參閱 [Self-Optimizing Agent 部落格文章](https://www.databricks.com/blog/self-optimizing-football-chatbot-guided-domain-experts-databricks)。如需 MemAlign 對齊方法的細節，請參閱 [MemAlign 研究部落格文章](https://www.databricks.com/blog/memalign-building-better-llm-judges-human-feedback-scalable-memory)。

### 迴圈總覽

```
1. Run evaluate()          -> 產生 traces，使用基礎 judge 評分
2. Tag traces              -> 標記成功完成評估的 traces 供資料集使用
3. Build eval dataset      -> 將 traces 持久化到 UC 以供標註
4. Labeling session        -> SME 在 Review App 中檢視並評分回應
                              （label schema 名稱必須與 judge 名稱相同）
5. Align judge (MemAlign)  -> 將 SME 回饋蒸餾為 judge guidelines
6. Re-evaluate             -> 以對齊後的 judge 建立 baseline（分數可能下降，這是正常的）
7. Build optim dataset     -> inputs + expectations（GEPA 必要條件）
8. optimize_prompts()      -> GEPA 反覆改善 system prompt
9. Conditional promote     -> 僅在分數提升時更新 "production" alias
```

### 為什麼這樣有效

通用型 LLM judges 與靜態 prompts 無法掌握領域特定的細微差異。要判斷什麼樣的回應才算「好」，需要一般用途評估器難以掌握的領域知識。這個迴圈用兩個階段解決這個問題：

- **對齊 judge**：領域專家檢視輸出並評分品質。MemAlign 會將他們的回饋蒸餾為 judge guidelines，教會 judge 在你的特定領域中什麼叫做「好」。即使單獨使用，這也很有價值 —— 對齊過的 judge 會改善每一次評估執行與監控設定。
- **最佳化 prompt**：對齊過的 judge 會驅動 GEPA prompt 最佳化，自動演化 system prompt，以最大化符合領域專家校準後的分數。只有改善結果才會被推送到正式環境。

### 步驟

**階段 1：評估並蒐集回饋**

1. **設計基礎 judge、執行評估並標記 traces**

   使用 `make_judge` 建立領域專屬 judge、將其註冊、執行 `evaluate()`，並標記成功完成評估的 traces（agent 有回應，且 judge 已成功評分而無錯誤）。

   請參閱 `patterns-judge-alignment.md` 的模式 1-2

2. **建立資料集並建立標註工作階段**

   將已標記的 traces 持久化為 UC 資料集，並為領域專家建立標註工作階段。

   **關鍵：label schema 的 `name` 必須與 `evaluate()` 中使用的 judge `name` 完全一致。** `align()` 會藉此將 SME 回饋與 LLM judge 分數配對。若名稱不一致，對齊將會失敗。

   請參閱 `patterns-judge-alignment.md` 的模式 3

3. **等待 SME 完成標註**（非同步步驟）

   將 `labeling_session.url` 分享給領域專家。他們會在 Review App 中檢視 agent 回應並提交評分。

**階段 2：對齊 Judge**

4. **使用 MemAlign 對齊 judge（建議）**

   MemAlign 是建議使用的對齊最佳化器。它速度最快（幾秒而非幾分鐘）、成本效益最高（$0.03 相較於 $1-$5），並支援記憶體規模化，隨著回饋累積，品質會持續提升。也支援其他最佳化器（例如 SIMBA）。

   請參閱 `patterns-judge-alignment.md` 的模式 4-5

5. **使用對齊後的 judge 重新評估**

   對齊後的 judge 分數**可能會低於**未對齊的 judge 分數。這是預期且正確的 —— 代表 judge 現在是依照領域專家的標準評估，而不是通用最佳實務。來自更準確 judge 的較低分數，比不理解你領域的 judge 所給出的偏高分數，更能提供有效訊號。

   請參閱 `patterns-judge-alignment.md` 的模式 6

6. **（可選）在此停止** —— 對齊後的 judge 可獨立改善未來所有評估與正式環境監控，即使不做 prompt 最佳化也有幫助。

**階段 3：最佳化 Prompt**

7. **建立包含 expectations 的最佳化資料集**（GEPA 必要）

   與 eval dataset 不同，最佳化資料集的每筆記錄都必須同時具有 `inputs` 與 `expectations`。GEPA 會在反思過程中利用 expectations，分析目前 prompt 為何表現不佳。

   請參閱 `patterns-prompt-optimization.md` 的模式 1

8. **使用 GEPA + 對齊後的 judge 執行 `optimize_prompts()`**

   GEPA 會反覆演化 system prompt，並以對齊後的 judge 作為評分函式。

   請參閱 `patterns-prompt-optimization.md` 的模式 2

9. **有條件地 promote**

   註冊新的 prompt 版本，只有在分數提升時才推送到 "production" alias。

   請參閱 `patterns-prompt-optimization.md` 的模式 3

10. **從步驟 1 重複開始** —— 每一次標註工作階段都會累積更多 SME 訊號，進一步改善對齊

### 完整迴圈摘要

```python
# -- 階段 1：評估並蒐集回饋 -----------------------------------

# 步驟 1：評估並標記成功完成評估的 traces
results = evaluate(data=eval_data, predict_fn=..., scorers=[base_judge])
ok_trace_ids = results.result_df.loc[results.result_df["state"] == "OK", "trace_id"]
for trace_id in ok_trace_ids:
    mlflow.set_trace_tag(trace_id, key="eval", value="complete")

# 步驟 2：建立資料集與標註工作階段
eval_dataset = create_dataset(name=DATASET_NAME)
eval_dataset.merge_records(tagged_traces)
# 關鍵：label schema 名稱必須與 judge 名稱相同，align() 才能運作
labeling_session = create_labeling_session(
    name="sme_session", assigned_users=[...], label_schemas=[JUDGE_NAME]
)
labeling_session.add_dataset(dataset_name=DATASET_NAME)
# -> 將 labeling_session.url 分享給領域專家

# 步驟 3：等待 SME 完成標註

# -- 階段 2：對齊 judge -------------------------------------------------

# 步驟 4：對齊 judge（建議使用 MemAlign；也支援 SIMBA 與其他方法）
optimizer = MemAlignOptimizer(reflection_lm=..., retrieval_k=5, embedding_model=...)
aligned_judge = base_judge.align(traces=traces, optimizer=optimizer)
aligned_judge.update(experiment_id=EXPERIMENT_ID)
# 注意：對齊後的 judge 分數可能低於未對齊版本 —— 這是預期行為

# 步驟 5：使用對齊後的 judge 重新評估（可選但建議）
baseline_results = evaluate(data=eval_records, predict_fn=..., scorers=[aligned_judge])

# 步驟 6：（可選）若你只需要對齊後的 judge，可在此停止

# -- 階段 3：最佳化 prompt ---------------------------------------------

# 步驟 7：建立最佳化資料集（必須有 inputs + expectations）
optimization_dataset = [
    {"inputs": {...}, "expectations": {"expected_response": "..."}}
]

# 步驟 8：使用 GEPA + 對齊後的 judge 最佳化 prompt
result = mlflow.genai.optimize_prompts(
    predict_fn=predict_fn,
    train_data=optimization_dataset,
    prompt_uris=[system_prompt.uri],
    optimizer=GepaPromptOptimizer(reflection_model=..., max_metric_calls=75),
    scorers=[aligned_judge],
    aggregation=objective_function,
)

# 步驟 9：有條件地 promote
new_version = mlflow.genai.register_prompt(
    name=PROMPT_NAME, template=result.optimized_prompts[0].template
)
if result.final_eval_score > result.initial_eval_score:
    mlflow.genai.set_prompt_alias(
        name=PROMPT_NAME, alias="production", version=new_version.version
    )

# -- 以新的標註工作階段從步驟 1 重新開始 -----------------------------
```

### 自動化

這個迴圈可透過 Asset Bundles 作為 Databricks job 進行編排：

1. SME 透過 MLflow Labeling Session UI 標註 agent 輸出
2. 管線偵測到新標籤後，會擷取同時具有 SME 回饋與 baseline LLM judge 分數的 traces
3. 使用 MemAlign 執行 judge 對齊，產生新的 judge 版本
4. 使用對齊後的 judge 執行 GEPA prompt 最佳化
5. 若超過效能門檻，則有條件地將新 prompt promote 到正式環境
6. Prompt registry 提供最佳化後版本時，agent 會自動持續改善

你也可以在任何步驟加入人工審查，讓開發者完整掌控自動化程度。

### 重要注意事項

- **Label schema 名稱匹配**：label schema 的 `name` 必須與 `evaluate()` 中 judge 的 `name` 相同，否則 `align()` 無法配對分數
- **對齊後分數下降**：對齊後的 judge 可能會給出比未對齊版本更低的分數。這是正常現象 —— 代表 judge 更準確，並不表示 agent 變差了
- **MemAlign embedding 成本**：請明確設定 `embedding_model`（例如 `"databricks:/databricks-gte-large-en"`），並只篩選已標註子集的 traces
- **GEPA expectations**：最佳化資料集的每筆記錄都必須同時具有 `inputs` 與 `expectations`
- **Episodic memory**：在 `get_scorer()` 之後，請檢查 `.instructions`，而不是 `._episodic_memory`（採 lazy loaded）

請參閱 `GOTCHAS.md` 取得完整清單。

### 參考檔案

- `patterns-judge-alignment.md` -- Judge 對齊工作流程：設計 judge、evaluate、label、MemAlign、register、re-evaluate
- `patterns-prompt-optimization.md` -- GEPA 最佳化：建立資料集、執行 optimize_prompts、register/promote
- `GOTCHAS.md` -- MemAlign embedding 成本、episodic memory lazy loading、名稱匹配、分數解讀、GEPA expectations

### 成功指標

- 對齊後的 judge instructions 包含由 SME 評分衍生出的領域特定 guidelines
- `result.final_eval_score > result.initial_eval_score`
- 只有在真正改善時才更新正式環境 prompt alias
- 重複執行的工作階段會逐步編碼更多專家知識

---

## 快速參考

### 我目前是哪一段旅程？

| 症狀 | 旅程 |
|---------|---------|
| 「之前明明是好的」 | 旅程 3（迴歸） |
| 「它太慢了」 | 旅程 7（效能） |
| 「它的準確度還不夠」 | 旅程 8（Prompt 最佳化） |
| 「我需要把 traces 放進 Unity Catalog」 | 旅程 9（Trace 擷取） |
| 「我希望 SME 幫我改善 judge 和 prompt」 | 旅程 10（領域專家迴圈） |

### 各旅程常用工具

| 工具 | 用途 |
|------|---------|
| `run_quick_eval.py` | 快速評估（8 個測試案例） |
| `run_full_eval.py` | 完整評估（23 個測試案例） |
| `analyze_signatures.py` | Signature/prompt 分析 |
| `OptimizationHistory` | 追蹤迭代 |
| `/eval:analyze-traces` | 深入 trace 分析 |
| `/optimize:context` | 完整最佳化迴圈 |

### 指標目標

| 指標 | 目標 | 關鍵門檻 |
|--------|--------|-------------------|
| classifier_accuracy | 95%+ | <80% |
| tool_selection_accuracy | 90%+ | <70% |
| follows_instructions | 80%+ | <50% |
| executor_latency | <30s | >60s |
