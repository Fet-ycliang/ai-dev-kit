# 使用向量搜尋的端到端 RAG

建立完整的檢索增強生成管道：準備文件、建立向量索引、查詢它，並將其接入代理。

## 使用的 MCP 工具

| 工具 | 步驟 |
|------|------|
| `execute_sql` | 建立來源表格、插入文件 |
| `create_vs_endpoint` | 建立計算端點 |
| `create_vs_index` | 建立帶受管嵌入的 Delta 同步索引 |
| `sync_vs_index` | 觸發索引同步 |
| `get_vs_index` | 檢查索引狀態 |
| `query_vs_index` | 測試相似度搜尋 |

---

## 步驟 1：準備來源表格

來源 Delta 表格需要主鍵欄位和要嵌入的文字欄位。

```sql
CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
    doc_id STRING,
    title STRING,
    content STRING,
    category STRING,
    updated_at TIMESTAMP DEFAULT current_timestamp()
);

INSERT INTO catalog.schema.knowledge_base VALUES
('doc-001', 'Getting Started', 'Databricks 是統一分析平台...', 'overview', current_timestamp()),
('doc-002', 'Unity Catalog', 'Unity Catalog 提供集中治理...', 'governance', current_timestamp()),
('doc-003', 'Delta Lake', 'Delta Lake 是開源儲存層...', 'storage', current_timestamp());
```

或透過 MCP：

```python
execute_sql(sql_query="""
    CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
        doc_id STRING,
        title STRING,
        content STRING,
        category STRING,
        updated_at TIMESTAMP DEFAULT current_timestamp()
    )
""")
```

## 步驟 2：建立向量搜尋端點

```python
create_vs_endpoint(
    name="my-rag-endpoint",
    endpoint_type="STORAGE_OPTIMIZED"
)
```

端點建立是非同步的。檢查狀態：

```python
get_vs_endpoint(name="my-rag-endpoint")
# 等待狀態：「ONLINE」
```

## 步驟 3：建立 Delta 同步索引

```python
create_vs_index(
    name="catalog.schema.knowledge_base_index",
    endpoint_name="my-rag-endpoint",
    primary_key="doc_id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.knowledge_base",
        "embedding_source_columns": [
            {
                "name": "content",
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED",
        "columns_to_sync": ["doc_id", "title", "content", "category"]
    }
)
```

關鍵決策：
- **`embedding_source_columns`**：Databricks 自動從 `content` 欄位計算嵌入
- **`pipeline_type`**：`TRIGGERED` 用於手動同步（更便宜），`CONTINUOUS` 用於表格變更時自動同步
- **`columns_to_sync`**：僅同步查詢結果中需要的欄位（減少儲存並改善效能）

## 步驟 4：同步和驗證

```python
# 觸發初始同步
sync_vs_index(index_name="catalog.schema.knowledge_base_index")

# 檢查狀態
get_vs_index(index_name="catalog.schema.knowledge_base_index")
# 等待狀態：「ONLINE」
```

## 步驟 5：查詢索引

```python
# 語義搜尋
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content", "category"],
    query_text="我如何治理我的資料？",
    num_results=3
)
```

### 帶篩選

篩選語法取決於建立索引時使用的端點類型。

```python
# 儲存最佳化端點（本演練中使用）：SQL 類似篩選語法
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    query_text="我如何治理我的資料？",
    num_results=3,
    filters="category = 'governance'"
)

# 標準端點（如果您改為建立標準端點）：JSON filters_json
query_vs_index(
    index_name="catalog.schema.my_standard_index",
    columns=["doc_id", "title", "content"],
    query_text="我如何治理我的資料？",
    num_results=3,
    filters_json='{"category": "governance"}'
)
```

### 混合搜尋（向量 + 關鍵字）

```python
query_vs_index(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    query_text="Delta Lake ACID 交易",
    num_results=5,
    query_type="HYBRID"
)
```

---

## 步驟 6：在代理中使用

### 作為 ChatAgent 中的工具

使用 `VectorSearchRetrieverTool` 將索引接入在模型服務上部署的代理：

```python
from databricks.agents import ChatAgent
from databricks.agents.tools import VectorSearchRetrieverTool
from databricks.sdk import WorkspaceClient

# 定義檢索工具
retriever_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    num_results=3,
)

class RAGAgent(ChatAgent):
    def __init__(self):
        self.w = WorkspaceClient()

    def predict(self, messages, context=None):
        query = messages[-1].content

        results = self.w.vector_search_indexes.query_index(
            index_name="catalog.schema.knowledge_base_index",
            columns=["title", "content"],
            query_text=query,
            num_results=3,
        )

        context_docs = "\n\n".join(
            f"**{row[0]}**: {row[1]}"
            for row in results.result.data_array
        )

        response = self.w.serving_endpoints.query(
            name="databricks-meta-llama-3-3-70b-instruct",
            messages=[
                {"role": "system", "content": f"使用此內容回答：\n{context_docs}"},
                {"role": "user", "content": query},
            ],
        )

        return {"content": response.choices[0].message.content}
```

---

## 更新索引

### 新增文件

```sql
INSERT INTO catalog.schema.knowledge_base VALUES
('doc-004', 'MLflow', 'MLflow 是 ML 生命週期的開源平台...', 'ml', current_timestamp());
```

然後同步：

```python
sync_vs_index(index_name="catalog.schema.knowledge_base_index")
```

### 刪除文件

```sql
DELETE FROM catalog.schema.knowledge_base WHERE doc_id = 'doc-001';
```

然後同步 — 索引自動透過 Delta 變更資料 feed 處理刪除。

---

## 常見問題

| 問題 | 解決方案 |
|------|--------|
| **索引卡在 PROVISIONING** | 端點仍可能在建立中。先檢查 `get_vs_endpoint` |
| **查詢無結果** | 索引可能尚未同步。執行 `sync_vs_index` 並等待 ONLINE 狀態 |
| **「索引中找不到欄位」** | 欄位必須在 `columns_to_sync` 中。使用包含的欄位重新建立索引 |
| **未計算嵌入** | 確保 `embedding_model_endpoint_name` 是有效的服務端點 |
| **表格更新後結果陳舊** | 對於 TRIGGERED 管道，您必須手動呼叫 `sync_vs_index` |
| **篩選不起作用** | 標準端點使用字典格式篩選（`filters_json`），儲存最佳化使用 SQL 類似字串篩選（`filters`） |
