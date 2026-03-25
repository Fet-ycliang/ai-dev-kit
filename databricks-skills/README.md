# Databricks Skills for Claude Code

教導 Claude Code 如何有效使用 Databricks 的 Skills 集合——提供模式、最佳實踐與程式碼範例，可搭配 Databricks MCP 工具使用。

## 安裝

在您的專案根目錄執行：

```bash
# 安裝所有 Skills（Databricks + MLflow）
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash

# 安裝特定 Skills
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- databricks-bundles agent-evaluation

# 將 MLflow Skills 固定在特定版本
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --mlflow-version v1.0.0

# 列出所有可用 Skills
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- --list
```

安裝後會建立 `.claude/skills/` 目錄並下載所有 Skills，Claude Code 會自動載入。
- **Databricks Skills** 從本儲存庫下載
- **MLflow Skills** 動態從 [github.com/mlflow/skills](https://github.com/mlflow/skills) 取得

**手動安裝：**
```bash
mkdir -p .claude/skills
cp -r ai-dev-kit/databricks-skills/databricks-agent-bricks .claude/skills/
```

---

## 可用 Skills

### 🤖 AI 與 Agent

- **databricks-ai-functions** — 內建 AI 函式（ai_classify、ai_extract、ai_summarize、ai_query、ai_forecast、ai_parse_document 等），含 SQL 與 PySpark 使用模式、函式選擇指引、文件處理管道，以及自訂 RAG 流程（解析 → 切分 → 索引 → 查詢）
- **databricks-agent-bricks** — 知識助手（Knowledge Assistant）、Genie Spaces、Supervisor Agent
- **databricks-genie** — Genie Spaces：建立、策展與透過 Conversation API 查詢
- **databricks-model-serving** — 將 MLflow 模型與 AI Agent 部署至服務端點
- **databricks-unstructured-pdf-generation** — 生成合成 PDF 供 RAG 使用
- **databricks-vector-search** — 向量相似度搜尋，用於 RAG 與語意搜尋

### 📊 MLflow（來自 [mlflow/skills](https://github.com/mlflow/skills)）

- **agent-evaluation** — 端到端 Agent 評估工作流程
- **analyze-mlflow-chat-session** — 除錯多輪對話
- **analyze-mlflow-trace** — 除錯 Trace、Span 與評估結果
- **instrumenting-with-mlflow-tracing** — 在 Python/TypeScript 中加入 MLflow Tracing
- **mlflow-onboarding** — 新用戶 MLflow 設定指南
- **querying-mlflow-metrics** — 彙總指標與時間序列分析
- **retrieving-mlflow-traces** — Trace 搜尋與篩選
- **searching-mlflow-docs** — 搜尋 MLflow 文件

### 📊 分析與儀表板

- **databricks-aibi-dashboards** — Databricks AI/BI 儀表板（含 SQL 驗證工作流程）
- **databricks-unity-catalog** — 系統資料表，用於資料血緣、稽核、計費分析

### 🔧 資料工程

- **databricks-iceberg** — Apache Iceberg 資料表（Managed/Foreign）、UniForm、Iceberg REST Catalog、跨引擎互通性
- **databricks-spark-declarative-pipelines** — SDP（前身為 DLT），支援 SQL/Python
- **databricks-jobs** — 多任務工作流程、觸發條件、排程設定
- **databricks-synthetic-data-gen** — 使用 Faker 生成逼真的測試資料

### 🚀 開發與部署

- **databricks-bundles** — DABs 多環境部署（開發/測試/生產）
- **databricks-app-apx** — 全端應用程式（FastAPI + React）
- **databricks-app-python** — Python Web 應用（Dash、Streamlit、Flask）含基礎模型整合
- **databricks-python-sdk** — Python SDK、Databricks Connect、CLI、REST API
- **databricks-config** — 設定檔認證設定
- **databricks-lakebase-provisioned** — OLTP 工作負載的受管 PostgreSQL

### 📚 參考資料

- **databricks-docs** — 透過 llms.txt 存取的文件索引

---

## 運作原理

```
┌────────────────────────────────────────────────┐
│  .claude/skills/     +    .claude/mcp.json     │
│  （知識）                   （操作）             │
│                                                │
│  Skills 教導 HOW     +    MCP 執行 DO           │
│  ↓                        ↓                    │
│  Claude Code 學習模式並實際執行                  │
└────────────────────────────────────────────────┘
```

**範例：** 使用者說「建立銷售儀表板」

1. Claude 載入 `databricks-aibi-dashboards` Skill → 學習驗證工作流程
2. 呼叫 `get_table_details()` → 取得資料表 Schema
3. 呼叫 `execute_sql()` → 測試查詢語句
4. 呼叫 `create_or_update_dashboard()` → 部署儀表板
5. 回傳可用的儀表板 URL

---

## 自訂 Skills

在 `.claude/skills/my-skill/SKILL.md` 建立您自己的 Skill：

```markdown
---
name: my-skill
description: "此 Skill 教導的內容"
---

# My Skill

## 使用時機
...

## 模式
...
```

---

## 疑難排解

**Skills 未載入？** 確認 `.claude/skills/` 存在，且每個 Skill 目錄中有 `SKILL.md`

**安裝失敗？** 執行 `bash install_skills.sh` 或確認是否具備寫入權限

---

## 相關資源

- [databricks-tools-core](../databricks-tools-core/) — Python 核心函式庫
- [databricks-mcp-server](../databricks-mcp-server/) — MCP 伺服器
- [Databricks 官方文件](https://docs.databricks.com/)
- [MLflow Skills](https://github.com/mlflow/skills) — 上游 MLflow Skills 儲存庫
