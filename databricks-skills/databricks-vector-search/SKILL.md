---
name: databricks-vector-search
description: "Databricks 向量搜尋的模式：建立端點和索引、使用篩選查詢、管理嵌入。當建立 RAG 應用程式、語義搜尋或相似度匹配時使用。涵蓋儲存最佳化和標準端點。"
---

# Databricks 向量搜尋

為 RAG 和語義搜尋應用程式建立、管理和查詢向量搜尋索引的模式。

## 使用時機

使用此技能時：
- 建立 RAG（檢索增強生成）應用程式
- 實施語義搜尋或相似度匹配
- 從 Delta 表格建立向量索引
- 在儲存最佳化和標準端點之間進行選擇
- 使用篩選查詢向量索引

## 概覽

Databricks 向量搜尋提供具有自動嵌入生成和 Delta Lake 整合的受管向量相似度搜尋。

| 元件 | 描述 |
|------|------|
| **端點** | 託管索引的計算資源（標準或儲存最佳化） |
| **索引** | 用於相似度搜尋的向量資料結構 |
| **Delta 同步** | 自動與來源 Delta 表格同步 |
| **直接存取** | 向量上的手動 CRUD 操作 |

## 端點類型

| 類型 | 延遲 | 容量 | 成本 | 最佳用途 |
|------|------|------|------|---------|
| **標準** | 20-50ms | 3.2 億向量（768 維） | 較高 | 即時、低延遲 |
| **儲存最佳化** | 300-500ms | 10 億+ 向量（768 維） | 便宜 7 倍 | 大規模、成本敏感 |

## 索引類型

| 類型 | 嵌入 | 同步 | 使用案例 |
|------|------|------|--------|
| **Delta 同步（受管）** | Databricks 計算 | 自動來自 Delta | 最簡單的設定 |
| **Delta 同步（自管）** | 您提供 | 自動來自 Delta | 自訂嵌入 |
| **直接存取** | 您提供 | 手動 CRUD | 即時更新 |

## 快速入門

### 建立端點

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 建立標準端點
endpoint = w.vector_search_endpoints.create_endpoint(
    name="my-vs-endpoint",
    endpoint_type="STANDARD"  # 或 "STORAGE_OPTIMIZED"
)
# 注意：端點建立是非同步的；使用 get_endpoint() 檢查狀態
```

### 建立 Delta 同步索引（受管嵌入）

```python
# 來源表格必須有：主鍵欄位 + 文字欄位
index = w.vector_search_indexes.create_index(
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {
                "name": "content",  # 要嵌入的文字欄位
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED"  # 或 "CONTINUOUS"
    }
)
```

### 查詢索引

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content", "metadata"],
    query_text="什麼是機器學習？",
    num_results=5
)

for doc in results.result.data_array:
    score = doc[-1]  # 相似度分數是最後一列
    print(f"Score: {score}, Content: {doc[1][:100]}...")
```

## 常見模式

### 建立儲存最佳化端點

```python
# 用於大規模、成本有效的部署
endpoint = w.vector_search_endpoints.create_endpoint(
    name="my-storage-endpoint",
    endpoint_type="STORAGE_OPTIMIZED"
)
```

### 帶自管嵌入的 Delta 同步

```python
# 來源表格必須有：主鍵 + 嵌入向量欄位
index = w.vector_search_indexes.create_index(
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_vector_columns": [
            {
                "name": "embedding",  # 預先計算的嵌入欄位
                "embedding_dimension": 768
            }
        ],
        "pipeline_type": "TRIGGERED"
    }
)
```

### 直接存取索引

```python
import json

# 建立索引用於手動 CRUD
index = w.vector_search_indexes.create_index(
    name="catalog.schema.direct_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DIRECT_ACCESS",
    direct_access_index_spec={
        "embedding_vector_columns": [
            {"name": "embedding", "embedding_dimension": 768}
        ],
        "schema_json": json.dumps({
            "id": "string",
            "text": "string",
            "embedding": "array<float>",
            "metadata": "string"
        })
    }
)

# Upsert 資料
w.vector_search_indexes.upsert_data_vector_index(
    index_name="catalog.schema.direct_index",
    inputs_json=json.dumps([
        {"id": "1", "text": "Hello", "embedding": [0.1, 0.2, ...], "metadata": "doc1"},
        {"id": "2", "text": "World", "embedding": [0.3, 0.4, ...], "metadata": "doc2"},
    ])
)

# 刪除資料
w.vector_search_indexes.delete_data_vector_index(
    index_name="catalog.schema.direct_index",
    primary_keys=["1", "2"]
)
```

### 使用嵌入向量查詢

```python
# 當您有預先計算的查詢嵌入時
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "text"],
    query_vector=[0.1, 0.2, 0.3, ...],  # 您的 768 維向量
    num_results=10
)
```

### 混合搜尋（語義 + 關鍵字）

混合搜尋結合向量相似度（ANN）與 BM25 關鍵字評分。當查詢包含必須匹配的確切術語時使用 - SKU、錯誤代碼、專有名詞或技術術語 - 其中純語義搜尋可能會遺漏關鍵字特定的結果。參見 [search-modes.md](search-modes.md) 以取得選擇 ANN 和混合搜尋之間的詳細指導。

```python
# 結合向量相似度與關鍵字匹配
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="SPARK-12345 executor memory error",
    query_type="HYBRID",
    num_results=10
)
```

## 篩選

### 標準端點篩選（字典）

```python
# filters_json 使用字典格式
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="machine learning",
    num_results=10,
    filters_json='{"category": "ai", "status": ["active", "pending"]}'
)
```

### 儲存最佳化篩選（SQL 類似）

儲存最佳化端點透過 `databricks-vectorsearch` 套件的 `filters` 參數使用 SQL 類似的篩選語法（接受字串）：

```python
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()
index = vsc.get_index(endpoint_name="my-storage-endpoint", index_name="catalog.schema.my_index")

# 儲存最佳化端點的 SQL 類似篩選語法
results = index.similarity_search(
    query_text="machine learning",
    columns=["id", "content"],
    num_results=10,
    filters="category = 'ai' AND status IN ('active', 'pending')"
)

# 更多篩選範例
# filters="price > 100 AND price < 500"
# filters="department LIKE 'eng%'"
# filters="created_at >= '2024-01-01'"
```

### 觸發索引同步

```python
# 對於 TRIGGERED 管道類型，手動同步
w.vector_search_indexes.sync_index(
    index_name="catalog.schema.my_index"
)
```

### 掃描所有索引項目

```python
# 檢索所有向量（用於偵錯/匯出）
scan_result = w.vector_search_indexes.scan_index(
    index_name="catalog.schema.my_index",
    num_results=100
)
```

## 參考檔案

| 主題 | 檔案 | 描述 |
|------|------|------|
| 索引類型 | [index-types.md](index-types.md) | Delta 同步（受管/自管）與直接存取的詳細比較 |
| 端到端 RAG | [end-to-end-rag.md](end-to-end-rag.md) | 完整演練：來源表格 → 端點 → 索引 → 查詢 → 代理整合 |
| 搜尋模式 | [search-modes.md](search-modes.md) | 何時使用語義（ANN）與混合搜尋、決策指南 |
| 操作 | [troubleshooting-and-operations.md](troubleshooting-and-operations.md) | 監控、成本最佳化、容量規劃、遷移 |

## CLI 快速參考

```bash
# 列表端點
databricks vector-search endpoints list

# 建立端點
databricks vector-search endpoints create \
    --name my-endpoint \
    --endpoint-type STANDARD

# 列表端點上的索引
databricks vector-search indexes list-indexes \
    --endpoint-name my-endpoint

# 取得索引狀態
databricks vector-search indexes get-index \
    --index-name catalog.schema.my_index

# 同步索引（用於 TRIGGERED）
databricks vector-search indexes sync-index \
    --index-name catalog.schema.my_index

# 刪除索引
databricks vector-search indexes delete-index \
    --index-name catalog.schema.my_index
```

## 常見問題

| 問題 | 解決方案 |
|------|--------|
| **索引同步緩慢** | 使用儲存最佳化端點（索引速度快 20 倍） |
| **查詢延遲高** | 使用標準端點以實現 <100ms 延遲 |
| **filters_json 不起作用** | 儲存最佳化使用透過 `databricks-vectorsearch` 套件 `filters` 參數的 SQL 類似字串篩選 |
| **嵌入維度不匹配** | 確保查詢和索引維度相符 |
| **索引未更新** | 檢查 pipeline_type；對 TRIGGERED 使用 sync_index() |
| **容量不足** | 升級至儲存最佳化（10 億+ 向量） |
| **`query_vector` 被 MCP 工具截斷** | MCP 工具呼叫將陣列序列化為 JSON，可能截斷大向量（例如 1024 維）。改用 `query_text`（用於受管嵌入索引），或使用 Databricks SDK/CLI 傳遞原始向量 |

## 嵌入模型

Databricks 提供內建嵌入模型：

| 模型 | 維度 | 上下文視窗 | 使用案例 |
|------|------|----------|--------|
| `databricks-gte-large-en` | 1024 | 8192 代幣 | 英文文字、高品質 |
| `databricks-bge-large-en` | 1024 | 512 代幣 | 英文文字、通用目的 |

```python
# 與受管嵌入一起使用
embedding_source_columns=[
    {
        "name": "content",
        "embedding_model_endpoint_name": "databricks-gte-large-en"
    }
]
```

## MCP 工具

下列 MCP 工具可用於管理向量搜尋基礎結構。如需完整端到端演練，請參閱 [end-to-end-rag.md](end-to-end-rag.md)。

### 端點管理

| 工具 | 描述 |
|------|------|
| `create_or_update_vs_endpoint` | 建立或更新端點（標準或儲存最佳化）。冪等 — 若找到則傳回現有端點 |
| `get_vs_endpoint` | 按名稱取得端點詳細資訊。省略 `name` 以列表工作區中的所有端點 |
| `delete_vs_endpoint` | 刪除端點（必須先刪除所有索引） |

```python
# 建立或更新端點
result = create_or_update_vs_endpoint(name="my-vs-endpoint", endpoint_type="STANDARD")
# 傳回 {"name": "my-vs-endpoint", "endpoint_type": "STANDARD", "created": True}

# 列表所有端點
endpoints = get_vs_endpoint()  # 省略 name 以列表所有
```

### 索引管理

| 工具 | 描述 |
|------|------|
| `create_or_update_vs_index` | 建立或更新索引。冪等 — 自動觸發 DELTA_SYNC 索引的初始同步 |
| `get_vs_index` | 按 `index_name` 取得索引詳細資訊。傳遞 `endpoint_name`（無 `index_name`）以列表端點上的所有索引 |
| `delete_vs_index` | 按完整限定名稱（catalog.schema.index_name）刪除索引 |

```python
# 建立帶有受管嵌入的 Delta 同步索引
result = create_or_update_vs_index(
    name="catalog.schema.my_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.docs",
        "embedding_source_columns": [{"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}],
        "pipeline_type": "TRIGGERED"
    }
)

# 按名稱取得特定索引 — 參數是 index_name，不是 name
index = get_vs_index(index_name="catalog.schema.my_index")

# 列表端點上的所有索引
indexes = get_vs_index(endpoint_name="my-vs-endpoint")
```

### 查詢和資料

| 工具 | 描述 |
|------|------|
| `query_vs_index` | 使用 `query_text`、`query_vector` 或混合（`query_type="HYBRID"`）查詢索引。偏好 `query_text` 而不是 `query_vector` — MCP 工具呼叫可能截斷大型嵌入陣列（1024 維） |
| `manage_vs_data` | 直接存取索引上的 CRUD 操作。`operation`：`"upsert"`、`"delete"`、`"scan"`、`"sync"` |

```python
# 查詢索引
results = query_vs_index(
    index_name="catalog.schema.my_index",
    columns=["id", "content"],
    query_text="machine learning best practices",
    num_results=5
)

# Upsert 資料到直接存取索引
manage_vs_data(
    index_name="catalog.schema.my_index",
    operation="upsert",
    inputs_json=[{"id": "doc1", "content": "...", "embedding": [0.1, 0.2, ...]}]
)

# 對 TRIGGERED 管道索引觸發手動同步
manage_vs_data(index_name="catalog.schema.my_index", operation="sync")
```

## 備註

- **儲存最佳化較新** — 對大多數使用案例更好，除非需要 <100ms 延遲
- **推薦 Delta 同步** — 比直接存取對大多數情境更簡單
- **混合搜尋** — 適用於 Delta 同步和直接存取索引
- **`columns_to_sync` 重要** — 僅同步的欄位在查詢結果中可用；包含所有需要的欄位
- **依端點篩選語法不同** — 標準使用字典格式篩選，儲存最佳化使用 SQL 類似字串篩選。使用 `databricks-vectorsearch` 套件的 `filters` 參數，接受兩種格式
- **管理與執行時** — 上述 MCP 工具處理生命週期管理；用於運行時的代理工具呼叫，使用 `VectorSearchRetrieverTool` 或 Databricks 受管向量搜尋 MCP 伺服器

## 相關技能

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - 部署使用 VectorSearchRetrieverTool 的代理
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - 知識助手在索引文件上使用 RAG
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - 生成要在向量搜尋中索引的文件
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - 管理支援 Delta 同步索引的目錄和表格
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - 建立用作向量搜尋來源的 Delta 表格
