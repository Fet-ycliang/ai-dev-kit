# Vector Search 索引類型

## 比較矩陣

| 功能 | Delta Sync（Managed） | Delta Sync（Self-Managed） | Direct Access |
|---------|---------------------|---------------------------|---------------|
| **Embeddings** | 由 Databricks 計算 | 由你提供 | 由你提供 |
| **同步** | 從 Delta 自動同步 | 從 Delta 自動同步 | 手動 CRUD |
| **設定** | 最容易 | 中等 | 控制度最高 |
| **來源** | Delta table + 文字 | Delta table + 向量 | API 呼叫 |
| **最適合** | 快速開始、RAG | 自訂模型 | 即時應用程式 |

## 使用 Managed Embeddings 的 Delta Sync

Databricks 會自動從你的文字欄位計算 embeddings。

### 需求

- 來源 Delta table 必須包含：
  - Primary key 欄位（唯一識別碼）
  - 文字欄位（要產生 embedding 的內容）
- Embedding model endpoint（或使用內建模型）

### 建立索引

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

index = w.vector_search_indexes.create_index(
    name="catalog.schema.docs_index",
    endpoint_name="my-vs-endpoint",
    primary_key="doc_id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {
                "name": "content",
                "embedding_model_endpoint_name": "databricks-gte-large-en"
            }
        ],
        "pipeline_type": "TRIGGERED",  # 或 "CONTINUOUS"
        "columns_to_sync": ["doc_id", "content", "title", "category"]
    }
)
```

### Pipeline 類型

| 類型 | 行為 | 成本 | 使用情境 |
|------|----------|------|----------|
| `TRIGGERED` | 透過 API 手動同步 | 較低 | 批次更新 |
| `CONTINUOUS` | 發生變更時自動同步 | 較高 | 即時同步 |

### 來源資料表示例

```sql
CREATE TABLE catalog.schema.documents (
    doc_id STRING,
    title STRING,
    content STRING,  -- 要產生 embedding 的文字
    category STRING,
    created_at TIMESTAMP
);
```

## 使用 Self-Managed Embeddings 的 Delta Sync

你需要先行計算 embeddings，並將其儲存在來源資料表中。

### 需求

- 來源 Delta table 必須包含：
  - Primary key 欄位
  - Embedding 向量欄位（浮點數陣列）

### 建立索引

```python
index = w.vector_search_indexes.create_index(
    name="catalog.schema.custom_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.embedded_docs",
        "embedding_vector_columns": [
            {
                "name": "embedding",
                "embedding_dimension": 768
            }
        ],
        "pipeline_type": "TRIGGERED"
    }
)
```

### 計算 Embeddings

```python
from databricks.sdk import WorkspaceClient
import pandas as pd

w = WorkspaceClient()

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """為文字呼叫 embedding endpoint。"""
    response = w.serving_endpoints.query(
        name="databricks-gte-large-en",
        input=texts
    )
    return [item.embedding for item in response.data]

# 將 embeddings 加入你的資料
df = spark.table("catalog.schema.documents").toPandas()
df["embedding"] = get_embeddings(df["content"].tolist())

# 回寫至 Delta
spark.createDataFrame(df).write.mode("overwrite").saveAsTable(
    "catalog.schema.embedded_docs"
)
```

### 來源資料表示例

```sql
CREATE TABLE catalog.schema.embedded_docs (
    id STRING,
    content STRING,
    embedding ARRAY<FLOAT>,  -- 預先計算的 embedding
    metadata STRING
);
```

## Direct Access 索引

透過 CRUD API 完整控制向量資料。不會與 Delta table 同步。

### 需求

- 事先定義 schema
- 自行管理 upsert/delete 作業

### 建立索引

```python
import json

index = w.vector_search_indexes.create_index(
    name="catalog.schema.realtime_index",
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
            "category": "string",
            "score": "float"
        })
    }
)
```

### Upsert 資料

```python
import json

# 插入或更新向量
w.vector_search_indexes.upsert_data_vector_index(
    index_name="catalog.schema.realtime_index",
    inputs_json=json.dumps([
        {
            "id": "doc-001",
            "text": "Machine learning 基礎",
            "embedding": [0.1, 0.2, 0.3, ...],  # 768 個浮點數
            "category": "ml",
            "score": 0.95
        },
        {
            "id": "doc-002",
            "text": "Deep learning 概觀",
            "embedding": [0.4, 0.5, 0.6, ...],
            "category": "dl",
            "score": 0.88
        }
    ])
)
```

### 刪除資料

```python
w.vector_search_indexes.delete_data_vector_index(
    index_name="catalog.schema.realtime_index",
    primary_keys=["doc-001", "doc-002"]
)
```

### 附加 Embedding Model（選用）

若要在 Direct Access 中使用文字查詢：

```python
# 建立含 embedding model 的索引，以便在查詢時產生 embedding
index = w.vector_search_indexes.create_index(
    name="catalog.schema.hybrid_index",
    endpoint_name="my-vs-endpoint",
    primary_key="id",
    index_type="DIRECT_ACCESS",
    direct_access_index_spec={
        "embedding_vector_columns": [
            {"name": "embedding", "embedding_dimension": 768}
        ],
        "embedding_model_endpoint_name": "databricks-gte-large-en",  # 用於 query_text
        "schema_json": json.dumps({...})
    }
)
```

## 如何選擇正確類型

```
從這裡開始：
│
├─ 你是否已經有預先計算好的 embeddings？
│   ├─ 有 → 你是否想要從 Delta 自動同步？
│   │         ├─ 是 → Delta Sync（Self-Managed）
│   │         └─ 否 → Direct Access
│   │
│   └─ 沒有 → Delta Sync（Managed Embeddings）
│
└─ 你是否需要即時更新（<1 秒）？
    ├─ 是 → Direct Access
    └─ 否 → Delta Sync（任一類型）
```

## Endpoint 選擇

選好索引類型後，再選擇 endpoint：

| 情境 | Endpoint 類型 |
|----------|---------------|
| 需要 <100ms 延遲 | Standard |
| >100M 個向量 | Storage-Optimized |
| 成本敏感 | Storage-Optimized |
| 預設選擇 | Storage-Optimized |
