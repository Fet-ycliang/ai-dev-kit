# Vector Search 疑難排解與操作

提供 Databricks Vector Search 資源在監控、成本最佳化、容量規劃與移轉方面的操作指引。

## 監控 Endpoint 狀態

使用 `get_vs_endpoint`（MCP tool）或 `w.vector_search_endpoints.get_endpoint()`（SDK）檢查 endpoint 健康狀態。

### Endpoint 欄位

| 欄位 | 說明 |
|-------|-------------|
| `state` | `ONLINE`, `PROVISIONING`, `OFFLINE`, `YELLOW_STATE`, `RED_STATE`, `DELETED` |
| `message` | 人類可讀的狀態或錯誤訊息 |
| `endpoint_type` | `STANDARD` 或 `STORAGE_OPTIMIZED` |
| `num_indexes` | 此 endpoint 上承載的索引數量 |
| `creation_timestamp` | endpoint 建立時間 |
| `last_updated_timestamp` | endpoint 最後修改時間 |

### 範例

```python
endpoint = w.vector_search_endpoints.get_endpoint(endpoint_name="my-endpoint")
print(f"狀態: {endpoint.endpoint_status.state.value}")
print(f"索引數量: {endpoint.num_indexes}")
```

**各狀態對應建議：**
- `PROVISIONING` → 請等待。Endpoint 建立為非同步流程，可能需要數分鐘。
- `ONLINE` → 已可提供查詢服務並承載索引。
- `OFFLINE` → 檢查 `message` 欄位中的錯誤細節，可能需要重新建立。
- `YELLOW_STATE` → Endpoint 效能或狀態降級，但仍可提供服務。請調查 `message` 欄位。
- `RED_STATE` → Endpoint 處於不健康狀態。請檢查 `message` 細節；可能需要支援介入。

## 監控索引狀態

使用 `get_vs_index`（MCP tool）或 `w.vector_search_indexes.get_index()`（SDK）檢查索引健康狀態。

### 索引欄位

| 欄位 | 說明 |
|-------|-------------|
| `status.ready` | 布林值 — 可查詢時為 `True`，建置或同步中為 `False` |
| `status.message` | 狀態細節或錯誤資訊 |
| `status.index_url` | 在 Databricks UI 中存取該索引的 URL |
| `status.indexed_row_count` | 目前已編入索引的資料列數量 |
| `delta_sync_index_spec.pipeline_id` | DLT pipeline ID（僅限 Delta Sync 索引）— 有助於除錯同步問題 |
| `index_type` | `DELTA_SYNC` 或 `DIRECT_ACCESS` |

### 範例

```python
index = w.vector_search_indexes.get_index(index_name="catalog.schema.my_index")
if index.status.ready:
    print("索引已 ONLINE")
else:
    print(f"索引為 NOT_READY: {index.status.message}")
```

## Pipeline 類型取捨

Delta Sync 索引會使用 DLT pipeline 從來源 Delta table 同步資料。Pipeline 類型會決定同步行為：

| Pipeline 類型 | 行為 | 成本 | 最適合 |
|---------------|----------|------|----------|
| **TRIGGERED** | 透過 `sync_vs_index()` 手動同步 | 較低 — 僅在觸發時執行 | 批次更新、定期重新整理、對成本敏感的工作負載 |
| **CONTINUOUS** | 來源資料表變更時自動同步 | 較高 — 持續執行 | 需要即時新鮮度、結果必須維持最新的應用程式 |

### 觸發同步

```python
# 僅適用於 TRIGGERED pipelines
w.vector_search_indexes.sync_index(index_name="catalog.schema.my_index")
# 使用 get_index() 檢查同步進度
```

**提示：** CONTINUOUS pipelines 無法手動同步，它們會自動同步。對 CONTINUOUS 索引呼叫 `sync_index()` 會引發錯誤。

## 成本最佳化

### Endpoint 類型選擇

| 因素 | Standard | Storage-Optimized |
|--------|----------|-------------------|
| 查詢延遲 | 20-50ms | 300-500ms |
| 成本 | 較高 | 約低 7 倍 |
| 最大容量 | 320M 個向量（768 dim） | 1B+ 個向量（768 dim） |
| 索引速度 | 較慢 | 快 20 倍 |

**建議：** 除非你需要低於 100ms 的延遲，否則建議從 Storage-Optimized 開始。它足以應付大多數 RAG 工作負載。

### 降低儲存成本

- 使用 `columns_to_sync` 限制要同步到索引的欄位。只有同步的欄位會出現在查詢結果中，因此只保留你真正需要的欄位。
- 針對批次工作負載選擇 TRIGGERED pipelines，以避免持續運算成本。

```python
# 只同步查詢結果中實際需要的欄位
delta_sync_index_spec={
    "source_table": "catalog.schema.documents",
    "embedding_source_columns": [
        {"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}
    ],
    "pipeline_type": "TRIGGERED",
    "columns_to_sync": ["id", "content", "title"]  # 排除未使用的大型欄位
}
```

## 容量規劃

| Endpoint 類型 | 最大向量數（768 dim） | 建議 |
|---------------|----------------------|----------|
| Standard | ~320M | 適合大多數低於 300M 文件的正式環境工作負載 |
| Storage-Optimized | 1B+ | 大規模語料庫、企業知識庫 |

**需求估算：**
- 一份文件通常對應一個向量（若做 chunking，則可能對應多個）
- 若以約 512 tokens 進行 chunking，平均每頁文字可能會產生 2 到 5 個向量
- 監控 endpoint 上的 `num_indexes` 以了解使用率

## 移轉模式

### 變更 endpoint 類型

Endpoint 在**建立後即不可變更**，你無法修改既有 endpoint 的類型（Standard ↔ Storage-Optimized）。若要移轉：

1. **建立新的 endpoint**，使用目標類型
2. **重新建立索引** 到新 endpoint，並指向相同的來源資料表
3. **等待同步完成**（檢查索引狀態）
4. **更新應用程式**，改查詢新的索引名稱
5. **刪除舊索引**，再刪除舊 endpoint

```python
# 步驟 1：建立新的 endpoint
w.vector_search_endpoints.create_endpoint(
    name="my-endpoint-storage-optimized",
    endpoint_type="STORAGE_OPTIMIZED"
)

# 步驟 2：在新 endpoint 上重建索引（使用相同來源資料表）
w.vector_search_indexes.create_index(
    name="catalog.schema.my_index_v2",
    endpoint_name="my-endpoint-storage-optimized",
    primary_key="id",
    index_type="DELTA_SYNC",
    delta_sync_index_spec={
        "source_table": "catalog.schema.documents",
        "embedding_source_columns": [
            {"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}
        ],
        "pipeline_type": "TRIGGERED"
    }
)

# 步驟 3：觸發同步並等待進入 ONLINE 狀態
w.vector_search_indexes.sync_index(index_name="catalog.schema.my_index_v2")

# 步驟 4：更新你的應用程式，改用 "catalog.schema.my_index_v2"
# 步驟 5：清理舊資源
w.vector_search_indexes.delete_index(index_name="catalog.schema.my_index")
w.vector_search_endpoints.delete_endpoint(endpoint_name="my-endpoint")
```

## 延伸疑難排解

| 問題 | 可能原因 | 解法 |
|-------|-------------|----------|
| **索引卡在 NOT_READY** | Sync pipeline 失敗或來源資料表有問題 | 透過 `get_vs_index()` 檢查 `message` 欄位，並使用 `pipeline_id` 檢視 DLT pipeline。 |
| **Embedding 維度不符** | 查詢向量維度 ≠ 索引維度 | 確認你的 embedding model 輸出與索引規格中的 `embedding_dimension` 一致。 |
| **建立時發生權限錯誤** | 缺少 Unity Catalog 權限 | 使用者需要對 schema 擁有 `CREATE TABLE` 與 `USE CATALOG`/`USE SCHEMA` 權限。 |
| **索引回傳 NOT_FOUND** | 名稱格式錯誤或索引已刪除 | 索引名稱必須為完整格式：`catalog.schema.index_name`。 |
| **Sync 未執行（TRIGGERED）** | 更新來源資料後未觸發同步 | 更新來源資料後，請呼叫 `sync_vs_index()` 或 `w.vector_search_indexes.sync_index()`。 |
| **Endpoint NOT_FOUND** | Endpoint 名稱打錯或已刪除 | 使用 `get_vs_endpoint()`（不帶名稱）列出所有 endpoints，確認可用項目。 |
| **查詢回傳空結果** | 索引尚未同步完成，或篩選條件過於嚴格 | 檢查索引狀態是否為 ONLINE，並確認 `columns_to_sync` 包含查詢使用的欄位。先在不加 filters 的情況下測試。 |
| **filters_json 沒有效果** | 使用了不符合 endpoint 類型的 filter 語法 | Standard endpoints 使用 dict 格式 filters（SDK 中為 `filters_json`，`databricks-vectorsearch` 中 `filters` 為 dict）。Storage-Optimized endpoints 使用類 SQL 字串 filters（`databricks-vectorsearch` 中 `filters` 為 str）。 |
| **Quota 或容量錯誤** | 索引或向量數量過多 | 檢查 endpoint 的 `num_indexes`。若需要更高容量，可考慮 Storage-Optimized。 |
| **Delta Sync 的 upsert 失敗** | 無法對 Delta Sync 索引進行 upsert | Upsert/delete 僅適用於 Direct Access 索引。Delta Sync 索引必須透過其來源資料表更新。 |
