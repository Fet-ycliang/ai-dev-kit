---
name: databricks-mlflow-evaluation
description: "MLflow 3 GenAI Agent 評估。適用於撰寫 mlflow.genai.evaluate() 程式碼、建立 @scorer 函式、使用內建 scorer（Guidelines、Correctness、Safety、RetrievalGroundedness）、從 trace 建立評估資料集、設定 trace 攝取與生產環境監控、使用 MemAlign 根據領域專家回饋對齊 judge，或使用 optimize_prompts() 搭配 GEPA 進行自動化 prompt 改善。"
---

# MLflow 3 GenAI 評估

## 撰寫任何程式碼前

1. **閱讀 GOTCHAS.md** — 15 種以上會導致失敗的常見錯誤
2. **閱讀 CRITICAL-interfaces.md** — 精確的 API 簽章與資料 schema

## 端到端工作流程

依照您的目標選擇對應的工作流程。每個步驟均標示需閱讀的參考文件。

### 工作流程一：首次評估設定

適用於 MLflow GenAI 評估的新使用者，或為新 Agent 建立評估。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 了解評估目標 | `user-journeys.md`（Journey 0：策略） |
| 2 | 學習 API 模式 | `GOTCHAS.md` + `CRITICAL-interfaces.md` |
| 3 | 建立初始資料集 | `patterns-datasets.md`（Patterns 1–4） |
| 4 | 選擇/建立 scorer | `patterns-scorers.md` + `CRITICAL-interfaces.md`（內建清單） |
| 5 | 執行評估 | `patterns-evaluation.md`（Patterns 1–3） |

### 工作流程二：生產 Trace → 評估資料集

適用於從生產環境 trace 建立評估資料集。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 搜尋與過濾 trace | `patterns-trace-analysis.md`（MCP 工具區段） |
| 2 | 分析 trace 品質 | `patterns-trace-analysis.md`（Patterns 1–7） |
| 3 | 標記要納入的 trace | `patterns-datasets.md`（Patterns 16–17） |
| 4 | 從 trace 建立資料集 | `patterns-datasets.md`（Patterns 6–7） |
| 5 | 新增期望值/基準答案 | `patterns-datasets.md`（Pattern 2） |

### 工作流程三：效能最佳化

適用於偵錯緩慢或成本過高的 Agent 執行。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 依 span 分析延遲 | `patterns-trace-analysis.md`（Patterns 4–6） |
| 2 | 分析 token 使用量 | `patterns-trace-analysis.md`（Pattern 9） |
| 3 | 偵測 context 問題 | `patterns-context-optimization.md`（第 5 節） |
| 4 | 套用最佳化 | `patterns-context-optimization.md`（第 1–4、6 節） |
| 5 | 重新評估以衡量成效 | `patterns-evaluation.md`（Pattern 6–7） |

### 工作流程四：回歸偵測

適用於比較不同 Agent 版本並找出回歸問題。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 建立基準線 | `patterns-evaluation.md`（Pattern 4：具名 run） |
| 2 | 執行當前版本 | `patterns-evaluation.md`（Pattern 1） |
| 3 | 比較指標 | `patterns-evaluation.md`（Patterns 6–7） |
| 4 | 分析失敗的 trace | `patterns-trace-analysis.md`（Pattern 7） |
| 5 | 針對特定失敗進行除錯 | `patterns-trace-analysis.md`（Patterns 8–9） |

### 工作流程五：自訂 Scorer 開發

適用於建立專案特定的評估指標。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 了解 scorer 介面 | `CRITICAL-interfaces.md`（Scorer 區段） |
| 2 | 選擇 scorer 模式 | `patterns-scorers.md`（Patterns 4–11） |
| 3 | 多 Agent scorer | `patterns-scorers.md`（Patterns 13–16） |
| 4 | 以評估進行測試 | `patterns-evaluation.md`（Pattern 1） |

### 工作流程六：Unity Catalog Trace 攝取與生產監控

適用於將 trace 儲存至 Unity Catalog、對應用程式進行儀器化，以及啟用持續的生產環境監控。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 將 UC schema 連結至 experiment | `patterns-trace-ingestion.md`（Patterns 1–2） |
| 2 | 設定 trace 目的地 | `patterns-trace-ingestion.md`（Patterns 3–4） |
| 3 | 對應用程式進行儀器化 | `patterns-trace-ingestion.md`（Patterns 5–8） |
| 4 | 設定 trace 來源（Apps/Serving/OTEL） | `patterns-trace-ingestion.md`（Patterns 9–11） |
| 5 | 啟用生產監控 | `patterns-trace-ingestion.md`（Patterns 12–13） |
| 6 | 查詢與分析 UC trace | `patterns-trace-ingestion.md`（Pattern 14） |

### 工作流程七：使用 MemAlign 對齊 Judge

適用於對齊 LLM judge 以符合領域專家的偏好。對齊良好的 judge 可改善所有下游使用效果：評估準確度、生產監控訊號，以及 prompt 最佳化品質。此工作流程本身即具有價值，無需與 prompt 最佳化結合使用。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 使用 `make_judge` 設計基礎 judge（任何回饋類型） | `patterns-judge-alignment.md`（Pattern 1） |
| 2 | 執行 evaluate()，標記成功的 trace | `patterns-judge-alignment.md`（Pattern 2） |
| 3 | 建立 UC 資料集 + 建立 SME 標記工作階段 | `patterns-judge-alignment.md`（Pattern 3） |
| 4 | 標記完成後以 MemAlign 對齊 judge | `patterns-judge-alignment.md`（Pattern 4） |
| 5 | 將已對齊的 judge 註冊至 experiment | `patterns-judge-alignment.md`（Pattern 5） |
| 6 | 使用已對齊的 judge 重新評估（建立基準線） | `patterns-judge-alignment.md`（Pattern 6） |

### 工作流程八：使用 GEPA 進行自動化 Prompt 最佳化

適用於使用 `optimize_prompts()` 自動改善已註冊的 system prompt。可與任何 scorer 搭配使用，但與已對齊的 judge（工作流程七）配合時可獲得最精準的領域專屬訊號。完整的對齊加最佳化端到端循環，請參閱 `user-journeys.md` Journey 10。

| 步驟 | 動作 | 參考文件 |
|------|------|---------|
| 1 | 建立最佳化資料集（inputs + expectations） | `patterns-prompt-optimization.md`（Pattern 1） |
| 2 | 以 GEPA + scorer 執行 optimize_prompts() | `patterns-prompt-optimization.md`（Pattern 2） |
| 3 | 註冊新版本，條件式晉升 | `patterns-prompt-optimization.md`（Pattern 3） |

## 參考文件快速索引

| 參考文件 | 用途 | 何時閱讀 |
|---------|------|---------|
| `GOTCHAS.md` | 常見錯誤 | **撰寫程式碼前務必先閱讀** |
| `CRITICAL-interfaces.md` | API 簽章、schema | 撰寫任何評估程式碼時 |
| `patterns-evaluation.md` | 執行評估、比較結果 | 執行評估時 |
| `patterns-scorers.md` | 自訂 scorer 建立 | 內建 scorer 不足時 |
| `patterns-datasets.md` | 資料集建立 | 準備評估資料時 |
| `patterns-trace-analysis.md` | Trace 除錯 | 分析 Agent 行為時 |
| `patterns-context-optimization.md` | Token/延遲修正 | Agent 緩慢或成本過高時 |
| `patterns-trace-ingestion.md` | UC trace 設定、監控 | 設定 trace 儲存或生產監控時 |
| `patterns-judge-alignment.md` | MemAlign judge 對齊、標記工作階段、SME 回饋 | 將 judge 對齊至領域專家偏好時 |
| `patterns-prompt-optimization.md` | GEPA 最佳化：建立資料集、optimize_prompts()、晉升 | 執行自動化 prompt 改善時 |
| `user-journeys.md` | 高層次工作流程、完整的領域專家最佳化循環 | 開始新評估專案或執行完整對齊＋最佳化循環時 |

## 關鍵 API 事項

- **使用：** `mlflow.genai.evaluate()`（**非** `mlflow.evaluate()`）
- **資料格式：** `{"inputs": {"query": "..."}}` （需要巢狀結構）
- **predict_fn：** 接收 `**unpacked kwargs`（非 dict）
- **MemAlign：** 與 scorer 無關（可與任何 `feedback_value_type` 搭配使用——float、bool、categorical）；embedding model 的 token 消耗量大，請明確設定 `embedding_model`
- **Label schema 名稱對應：** 標記工作階段中的 label schema `name` 必須與 `evaluate()` 中使用的 judge `name` 相符，`align()` 才能正確配對分數
- **已對齊 judge 的分數：** 可能低於未對齊的 judge 分數——這是預期行為，表示 judge 現在更精確，而非 Agent 退步
- **GEPA 最佳化資料集：** 每筆記錄必須同時包含 `inputs` 與 `expectations`（與評估資料集格式不同）
- **Episodic memory：** 延遲載入——`get_scorer()` 的結果在 judge 首次被使用前，列印時不會顯示 episodic memory
- **optimize_prompts：** 需要 MLflow >= 3.5.0

完整清單請參閱 `GOTCHAS.md`。

## 相關 Skills

- **[databricks-docs](../databricks-docs/SKILL.md)** — Databricks 通用文件參考
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — 將模型與 Agent 部署至服務端點
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — 建立可用本 skill 評估的 Agent
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — 與 MLflow API 搭配使用的 SDK 模式
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — 用於受管評估資料集的 Unity Catalog 資料表
