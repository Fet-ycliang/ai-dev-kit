# Knowledge Assistants (KA)

Knowledge Assistants 是以文件為基礎的問答系統，使用 RAG（Retrieval-Augmented Generation）從已建立索引的文件中回答問題。

## 什麼是 Knowledge Assistant？

KA 會連接儲存在 Unity Catalog Volume 中的文件，讓使用者可以提出自然語言問題。系統會：

1. **建立索引**：為 volume 中的所有文件建立索引（PDF、文字檔等）
2. **擷取內容**：當有人提問時，擷取相關的內容片段
3. **產生答案**：使用擷取到的情境內容產生答案

## 何時使用

在以下情境可使用 Knowledge Assistant：
- 你有一批文件集合（政策、手冊、指南、報告）
- 使用者需要找出特定資訊，而不想閱讀整份文件
- 你想為文件提供對話式介面

## 先決條件

建立 KA 之前，你需要在 Unity Catalog Volume 中準備好文件：

**選項 1：使用既有文件**
- 手動或透過 SDK 將 PDF／文字檔上傳到 Volume

**選項 2：產生合成文件**
- 使用 `databricks-unstructured-pdf-generation` skill 建立擬真的 PDF 文件
- 每份 PDF 都會附帶一個 companion JSON 檔，內含 question/guideline 配對，供評估使用

## 建立 Knowledge Assistant

使用 `manage_ka` 工具並指定 `action="create_or_update"`：

- `name`: "HR 政策助理"
- `volume_path`: "/Volumes/my_catalog/my_schema/raw_data/hr_docs"
- `description`: "回答有關 HR 政策與流程的問題"
- `instructions`: "請以專業且樂於協助的方式回答，並在作答時一律引用具體的政策文件。若不確定，請明確說明。"

工具會：
1. 使用指定的 volume 作為 knowledge source 建立 KA
2. 掃描 volume 中包含範例問題的 JSON 檔案（來自 PDF 產生流程）
3. 將範例排入佇列，待 endpoint 就緒後自動新增

## 佈建時程

建立後，KA endpoint 需要時間完成佈建：

| 狀態 | 說明 | 時間 |
|------|------|------|
| `PROVISIONING` | 正在建立 endpoint | 2-5 分鐘 |
| `ONLINE` | 可開始使用 | - |
| `OFFLINE` | 目前未執行 | - |

使用 `manage_ka` 並指定 `action="get"` 可檢查狀態：

- `tile_id`: "<來自 create 的 tile_id>"

## 加入範例問題

範例問題有助於：
- **評估**：測試 KA 是否能正確回答
- **使用者上手**：讓使用者知道可以怎麼提問

### 自動加入（來自 PDF 產生流程）

如果你使用 `generate_pdf_documents`，每份 PDF 都會附帶一個 companion JSON，內容如下：
```json
{
  "question": "公司的遠端工作政策是什麼？",
  "guideline": "應提到每週至少 3 天進辦公室的要求"
}
```

當 `add_examples_from_volume=true`（預設值）時，這些範例會自動加入。

### 手動加入

如有需要，也可以在 `manage_ka` 的 create_or_update 呼叫中直接指定範例。

## 最佳實務

### 文件組織

- **每個主題使用一個 volume**：例如 `/Volumes/catalog/schema/raw_data/hr_docs`、`/Volumes/catalog/schema/raw_data/tech_docs`
- **清楚命名**：以具描述性的方式命名檔案，讓內容片段可辨識

### 撰寫 Instructions

良好的 instructions 能提升回答品質：

```
請以專業且樂於協助的方式回答。回答時請遵守以下原則：
1. 一律引用具體的文件與章節
2. 若有多份文件相關，請一併提及
3. 若文件中沒有該資訊，請明確說明
4. 多部分答案請使用項目符號
```

### 更新內容

若要更新已建立索引的文件：
1. 在 volume 中新增／移除／修改檔案
2. 使用相同的名稱與 `tile_id` 呼叫 `manage_ka`，並指定 `action="create_or_update"`
3. KA 會重新為更新後的內容建立索引

## 範例工作流程

1. 使用 `databricks-unstructured-pdf-generation` skill **產生 PDF 文件**：
   - 在 `/Volumes/catalog/schema/raw_data/pdf_documents` 建立 PDF
   - 建立 question/guideline 配對的 JSON 檔案

2. **建立 Knowledge Assistant**：
   - `name`: "我的文件助理"
   - `volume_path`: "/Volumes/catalog/schema/raw_data/pdf_documents"

3. **等待 `ONLINE` 狀態**（2-5 分鐘）

4. **自動從 JSON 檔案加入範例**

5. **在 Databricks UI 中測試 KA**

## 在 Supervisor Agents 中使用 KA

Knowledge Assistants 可作為 Supervisor Agent（前稱 Multi-Agent Supervisor, MAS）中的 agent。每個 KA 都有對應的 model serving endpoint。

### 取得 endpoint 名稱

使用 `manage_ka` 並指定 `action="get"` 來取得 KA 詳細資料。回應中會包含：
- `tile_id`：KA 的唯一識別子
- `name`：KA 名稱（已清理）
- `endpoint_status`：目前狀態（ONLINE、PROVISIONING 等）

endpoint 名稱遵循以下格式：`ka-{tile_id}-endpoint`

### 依名稱尋找 KA

如果你知道 KA 名稱但不知道 tile_id，可使用 `manage_ka` 並指定 `action="find_by_name"`：

```python
manage_ka(action="find_by_name", name="HR_Policy_Assistant")
# 回傳：{"found": True, "tile_id": "01abc...", "name": "HR_Policy_Assistant", "endpoint_name": "ka-01abc...-endpoint"}
```

### 範例：將 KA 加入 Supervisor Agent

```python
# 先找到 KA
manage_ka(action="find_by_name", name="HR_Policy_Assistant")

# 再將 tile_id 用於 Supervisor Agent
manage_mas(
    action="create_or_update",
    name="Support_MAS",
    agents=[
        {
            "name": "hr_agent",
            "ka_tile_id": "<tile_id from find_by_name>",
            "description": "回答員工手冊中的 HR 政策問題"
        }
    ]
)
```

## 疑難排解

### Endpoint 一直停留在 PROVISIONING

- 檢查 workspace 容量與配額
- 確認 volume 路徑可存取
- 最多等待 10 分鐘後再進一步檢查

### 文件未建立索引

- 確認檔案格式受支援（PDF、TXT、MD）
- 檢查 volume 中的檔案權限
- 確認 volume 路徑正確

### 回答品質不佳

- 加入更具體的 instructions
- 確保文件結構良好
- 可考慮將大型文件拆成較小的檔案
