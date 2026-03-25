# 向量搜尋模式

Databricks 向量搜尋支援三種搜尋模式：**ANN**（語義、預設）、**HYBRID**（語義 + 關鍵字）和 **FULL_TEXT**（僅關鍵字、測試版）。ANN 和 HYBRID 適用於 Delta 同步和直接存取索引。

## 語義搜尋（ANN）

ANN（近似最近鄰）是預設搜尋模式。它按向量相似度找到文件 — 將查詢的*意義*與儲存的嵌入相符。

### 使用時機

- 概念或基於意義的查詢（「我如何在管道中處理錯誤？」）
- 改述輸入，其中確切術語可能不會出現在文件中
- 多語言情境，其中查詢和文件語言可能不同
- 通用目的 RAG 檢索

### 範例

```python
# ANN 是預設值 — 不需要 query_type 參數
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="我如何在管道中處理錯誤？",
    num_results=5
)
```

## 混合搜尋

混合搜尋結合向量相似度（ANN）與 BM25 關鍵字評分。它檢索在語義上相似*且*包含匹配關鍵字的文件，然後合併結果。

### 使用時機

- 包含必須出現的確切術語的查詢：SKU、產品代碼、錯誤代碼、首字母縮寫
- 專有名詞 — 公司名稱、人名、特定技術
- 技術文件，其中術語精度很重要
- 結合概念和特定術語的混合意圖查詢

### 範例

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10
)
```

## 決策指南

| 模式 | 最佳用途 | 權衡 | 選擇時機 |
|------|--------|------|--------|
| **ANN**（預設） | 概念查詢、改述、基於意義的搜尋 | 最快；可能遺漏確切關鍵字匹配 | 您想要*關於*主題的文件，無論確切措辭如何 |
| **HYBRID** | 確切術語、代碼、專有名詞、混合意圖查詢 | ~2 倍資源使用相比 ANN；最多 200 結果 | 您的查詢包含必須出現在結果中的特定識別碼或技術術語 |
| **FULL_TEXT**（測試版） | 純關鍵字搜尋，無向量嵌入 | 無語義理解；最多 200 結果 | 您需要僅限關鍵字匹配，無向量相似度 |

**從 ANN 開始。** 如果您注意到因為相關文件不與查詢共用詞彙而被遺漏，切換至 HYBRID。

## 結合搜尋模式與篩選

兩種搜尋模式都支援篩選。篩選語法取決於您的端點類型：

- **標準端點** → `filters` 作為字典（或透過 `databricks-sdk` 的 `filters_json` 作為 JSON 字串）
- **儲存最佳化端點** → `filters` 作為 SQL 類似字串（透過 `databricks-vectorsearch` 套件）

### 帶混合搜尋的標準端點

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content", "category"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10,
    filters_json='{"category": "troubleshooting", "status": ["open", "in_progress"]}'
)
```

### 帶混合搜尋的儲存最佳化端點

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()
index = vsc.get_index(endpoint_name="my-storage-endpoint", index_name="catalog.schema.my_index")

results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    columns=["id", "content", "category"],
    query_type="hybrid",
    num_results=10,
    filters="category = 'troubleshooting' AND status IN ('open', 'in_progress')"
)
```

## 使用預先計算的嵌入

如果您自己計算嵌入，對 ANN 搜尋使用 `query_vector` 而不是 `query_text`：

```python
# ANN 與預先計算嵌入（預設）
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_vector=[0.1, 0.2, 0.3, ...],  # 您的嵌入向量
    num_results=10
)
```

對於**帶自管嵌入的混合搜尋**（無關聯模型端點的索引），您必須同時提供 **`query_vector` 和 `query_text`**。向量用於 ANN 元件，文字用於 BM25 關鍵字元件：

```python
# HYBRID 與自管嵌入 — 需要向量和文字
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_vector=[0.1, 0.2, 0.3, ...],  # 用於 ANN 相似度
    query_text="executor memory error",   # 用於 BM25 關鍵字匹配
    query_type="HYBRID",
    num_results=10
)
```

**備註：**
- 對於 **ANN** 查詢：提供 `query_text` 或 `query_vector`，不可同時提供。
- 對於 **HYBRID** 查詢在**受管嵌入索引上**：僅提供 `query_text`（系統處理兩個元件）。
- 對於 **HYBRID** 查詢在**無模型端點的自管索引上**：同時提供 `query_vector` 和 `query_text`。
- 單獨使用 `query_text` 時，索引必須有關聯的嵌入模型（受管嵌入或直接存取索引上的 `embedding_model_endpoint_name`）。

## 參數參考

| 參數 | 類型 | 套件 | 描述 |
|------|------|------|------|
| `query_text` | `str` | 兩者 | 文字查詢 — 需要索引上的嵌入模型 |
| `query_vector` | `list[float]` | 兩者 | 預先計算的嵌入向量 |
| `query_type` | `str` | 兩者 | `"ANN"`（預設）或 `"HYBRID"` 或 `"FULL_TEXT"`（測試版） |
| `columns` | `list[str]` | 兩者 | 在結果中傳回的欄位名稱 |
| `num_results` | `int` | 兩者 | 結果數量（`databricks-sdk` 預設：10，`databricks-vectorsearch` 預設：5） |
| `filters_json` | `str` | `databricks-sdk` | JSON 字典篩選字串（標準端點） |
| `filters` | `str` 或 `dict` | `databricks-vectorsearch` | 標準字典、儲存最佳化 SQL 類似字串 |
