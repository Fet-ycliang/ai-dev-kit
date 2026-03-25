---
name: databricks-unstructured-pdf-generation
description: "生成合成 PDF 文件，用於 RAG 與非結構化資料使用情境。適合建立測試用 PDF、展示文件或檢索系統的評估資料集。"
---

# 非結構化 PDF 生成

使用 LLM 生成逼真的合成 PDF 文件，適用於 RAG（檢索增強生成）與非結構化資料使用情境。

## 概覽

此 Skill 提供兩個 MCP 工具，用於建立專業的 PDF 文件：

1. **`generate_and_upload_pdfs`** — 依據描述批次生成多份 PDF（由 LLM 生成文件規格）
2. **`generate_and_upload_pdf`** — 精確控制內容，生成單份 PDF

兩個工具均：
- 使用 LLM 生成專業 HTML 內容，再轉換為 PDF
- 建立附帶的 JSON 檔案，包含問題與評估指引（供 RAG 測試使用）
- 直接上傳至 Unity Catalog Volumes

## 快速入門

### 批次生成多份 PDF

使用 `generate_and_upload_pdfs` MCP 工具：
- `catalog`: "my_catalog"
- `schema`: "my_schema"
- `description`: "雲端基礎設施平台的技術文件，包含設定指南、疑難排解程序與 API 參考資料。"
- `count`: 10

此操作將生成 10 份 PDF 文件，並儲存至 `/Volumes/my_catalog/my_schema/raw_data/pdf_documents/`（使用預設 Volume 與資料夾）。

### 精確控制生成單份 PDF

當您需要精確控制文件內容時，使用 `generate_and_upload_pdf` MCP 工具：
- `title`: "API Authentication Guide"
- `description`: "雲端平台 REST API 認證完整指南，包含 OAuth2、API 金鑰與 JWT Token。"
- `question`: "支援哪些認證方式？"
- `guideline`: "答案應涵蓋 OAuth2、API 金鑰與 JWT 及其適用情境"
- `catalog`: "my_catalog"
- `schema`: "my_schema"

---

## 工具一：generate_and_upload_pdfs（批次模式）

以兩階段 LLM 流程生成多份 PDF：
1. LLM 依據您的描述生成多樣化的文件規格
2. 依據規格平行生成 PDF

### 參數

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `catalog` | string | 是 | — | Unity Catalog 名稱 |
| `schema` | string | 是 | — | Schema 名稱 |
| `description` | string | 是 | — | PDF 內容的詳細描述 |
| `count` | int | 是 | — | 要生成的 PDF 數量 |
| `volume` | string | 否 | `raw_data` | Volume 名稱（須已存在） |
| `folder` | string | 否 | `pdf_documents` | Volume 內的輸出資料夾 |
| `doc_size` | string | 否 | `MEDIUM` | 文件大小：`SMALL`（約 1 頁）、`MEDIUM`（約 5 頁）、`LARGE`（約 10+ 頁） |
| `overwrite_folder` | bool | 否 | `false` | 若為 true，先清空現有資料夾內容 |

---

## 工具二：generate_and_upload_pdf（精確控制模式）

完整控制內容與中繼資料，生成恰好一份 PDF。

### 參數

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `title` | string | 是 | — | 文件標題（同時用於生成檔名） |
| `description` | string | 是 | — | 文件應包含的內容，含領域背景 |
| `question` | string | 是 | — | 閱讀此文件後可回答的問題 |
| `guideline` | string | 是 | — | 評估答案是否正確的標準 |
| `catalog` | string | 是 | — | Unity Catalog 名稱 |
| `schema` | string | 是 | — | Schema 名稱 |
| `volume` | string | 否 | `raw_data` | Volume 名稱（須已存在） |
| `folder` | string | 否 | `pdf_documents` | Volume 內的資料夾 |
| `doc_size` | string | 否 | `MEDIUM` | 文件大小：`SMALL`、`MEDIUM`、`LARGE` |

### 文件大小說明

- **SMALL**：約 1 頁，內容簡潔。適合快速展示或功能測試。
- **MEDIUM**：約 4–6 頁，內容完整。適合大多數使用情境。
- **LARGE**：約 10+ 頁，詳盡完整。適合 RAG 深度評估。

---

## 輸出檔案

每份文件會產生兩個檔案：

1. **PDF 檔案**（`<model_id>.pdf`）：生成的文件本體
2. **JSON 檔案**（`<model_id>.json`）：供 RAG 評估使用的中繼資料

### JSON 結構

```json
{
  "title": "API Authentication Guide",
  "category": "Technical",
  "pdf_path": "/Volumes/catalog/schema/volume/folder/doc_001.pdf",
  "question": "What authentication methods are supported by the API?",
  "guideline": "Answer should mention OAuth 2.0, API keys, and JWT tokens with their use cases."
}
```

---

## 常用模式

### 模式一：人資政策文件

使用 `generate_and_upload_pdfs` MCP 工具：
- `catalog`: "ai_dev_kit"
- `schema`: "hr_demo"
- `description`: "科技公司人資政策文件，包含員工手冊、請假政策、績效考核程序、福利說明與職場行為準則。"
- `count`: 15
- `folder`: "hr_policies"
- `overwrite_folder`: true

### 模式二：技術文件

使用 `generate_and_upload_pdfs` MCP 工具：
- `catalog`: "ai_dev_kit"
- `schema`: "tech_docs"
- `description`: "SaaS 分析平台技術文件，包含安裝指南、API 參考、疑難排解程序、資安最佳實踐與整合教學。"
- `count`: 20
- `folder`: "product_docs"
- `overwrite_folder`: true

### 模式三：財務報告

使用 `generate_and_upload_pdfs` MCP 工具：
- `catalog`: "ai_dev_kit"
- `schema`: "finance_demo"
- `description`: "零售公司財務文件，包含季度報告、費用政策、預算指南與稽核程序。"
- `count`: 12
- `folder`: "reports"
- `overwrite_folder`: true

### 模式四：教育訓練素材

使用 `generate_and_upload_pdfs` MCP 工具：
- `catalog`: "ai_dev_kit"
- `schema`: "training"
- `description`: "新進軟體開發人員訓練素材，包含入職指南、程式碼規範、Code Review 程序與部署工作流程。"
- `count`: 8
- `folder`: "courses"
- `overwrite_folder`: true

---

## 建議工作流程

1. **確認目標位置**：預設使用 `ai_dev_kit` Catalog，詢問使用者 Schema 名稱
2. **取得描述**：詢問需要哪類型文件
3. **生成 PDF**：以適當參數呼叫 `generate_and_upload_pdfs` MCP 工具
4. **驗證輸出**：確認 Volume 路徑中已有生成的檔案

---

## 最佳實踐

1. **詳細描述**：描述越具體，生成內容品質越高
   - ❌ 不好：「生成一些人資文件」
   - ✅ 好：「科技公司人資政策文件，包含涵蓋遠端工作政策的員工手冊、含特休與病假細節的請假政策、季度與年度績效考核程序，以及職場行為準則」

2. **適當的數量**：
   - 展示用途：5–10 份
   - RAG 測試：15–30 份
   - 完整評估：50+ 份

3. **資料夾命名**：使用可描述內容類型的名稱
   - `hr_policies/`
   - `technical_docs/`
   - `training_materials/`

4. **善用 overwrite_folder**：重新生成時設為 `true`，確保目錄乾淨

---

## 與 RAG 管道整合

生成的 JSON 檔案專為 RAG 評估設計：

1. **擷取 PDF**：將 PDF 檔案作為向量資料庫的來源文件
2. **測試檢索**：使用 `question` 欄位查詢 RAG 系統
3. **評估答案**：使用 `guideline` 欄位評估 RAG 回應是否正確

評估工作流程範例：
```python
# 從 JSON 檔案載入問題
questions = load_json_files(f"/Volumes/{catalog}/{schema}/{volume}/{folder}/*.json")

for q in questions:
    # 查詢 RAG 系統
    response = rag_system.query(q["question"])

    # 依據指引評估
    is_correct = evaluate_response(response, q["guideline"])
```

---

## LLM 設定

工具會自動探索工作區中的 `databricks-gpt-*` 端點。如有需要，可透過環境變數覆蓋：

```bash
# 可選：覆蓋自動探索結果
DATABRICKS_MODEL=databricks-gpt-5-4           # 用於內容生成的主要模型
DATABRICKS_MODEL_NANO=databricks-gpt-5-4-nano # 較小的模型（預設使用，速度較快）
```

**自動探索**：若未設定環境變數，工具會列出所有服務端點並尋找最新的 `databricks-gpt-*` 端點（版本號最高且狀態為 READY）。

---

## 常見問題

| 問題 | 解決方式 |
|------|---------|
| **「No LLM endpoint configured」** | 找不到 `databricks-gpt-*` 端點。請部署端點或設定 `DATABRICKS_MODEL` 環境變數 |
| **「Volume does not exist」** | 請先建立 Volume；工具不會自動建立 |
| **「PDF generation timeout」** | 減少 `count` 或改用 `doc_size: "SMALL"` |
| **內容品質偏低** | 提供更詳細的 `description`，說明具體主題與文件類型 |

---

## 相關 Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — 建立可擷取生成 PDF 的知識助手
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — 對生成文件建立索引，用於語意搜尋與 RAG
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — 生成結構化表格資料（與非結構化 PDF 互補）
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** — 使用生成的問題/指引配對評估 RAG 系統
