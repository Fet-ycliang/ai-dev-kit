---
name: databricks-python-sdk
description: "包含 Python SDK、Databricks Connect、CLI 與 REST API 的 Databricks 開發指南。當使用 databricks-sdk、databricks-connect 或 Databricks API 時請使用。"
---

# Databricks 開發指南

此技能提供 Databricks SDK、Databricks Connect、CLI 與 REST API 的使用指引。

**SDK 文件：** https://databricks-sdk-py.readthedocs.io/en/latest/
**GitHub 儲存庫：** https://github.com/databricks/databricks-sdk-py

---

## 環境設定

- 使用現有的 `.venv` 虛擬環境，或使用 `uv` 建立新的環境
- 進行 Spark 作業時：`uv pip install databricks-connect`
- 進行 SDK 作業時：`uv pip install databricks-sdk`
- Databricks CLI 版本應為 0.278.0 或更高

## 設定

- 預設設定檔名稱：`DEFAULT`
- 設定檔：`~/.databrickscfg`
- 環境變數：`DATABRICKS_HOST`、`DATABRICKS_TOKEN`

---

## Databricks Connect（Spark 作業）

使用 `databricks-connect` 可在本機針對 Databricks 叢集執行 Spark 程式碼。

```python
from databricks.connect import DatabricksSession

# 自動偵測 ~/.databrickscfg 中的 'DEFAULT' 設定檔
spark = DatabricksSession.builder.getOrCreate()

# 明確指定設定檔
spark = DatabricksSession.builder.profile("MY_PROFILE").getOrCreate()

# 像平常一樣使用 spark
df = spark.sql("SELECT * FROM catalog.schema.table")
df.show()
```

**重要：** 請勿設定 `.master("local[*]")`，這會導致 Databricks Connect 發生問題。

---

## 直接存取 REST API

對於 SDK 尚未支援，或透過 SDK 實作過於複雜的作業，可直接使用 REST API：

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 使用已驗證的用戶端直接呼叫 API
response = w.api_client.do(
    method="GET",
    path="/api/2.0/clusters/list"
)

# 帶請求主體的 POST
response = w.api_client.do(
    method="POST",
    path="/api/2.0/jobs/run-now",
    body={"job_id": 123}
)
```

**使用時機：** 優先使用可用的 SDK 方法。在下列情況請使用 `api_client.do`：
- SDK 尚未支援的新 API 端點
- SDK 抽象層不易處理的複雜作業
- 對原始 API 回應進行除錯／測試

---

## Databricks CLI

```bash
# 檢查版本（應 >= 0.278.0）
databricks --version

# 使用特定設定檔
databricks --profile MY_PROFILE clusters list

# 常用指令
databricks clusters list
databricks jobs list
databricks workspace ls /Users/me
```

---

## SDK 文件架構

SDK 文件遵循可預測的 URL 模式：

```
基底: https://databricks-sdk-py.readthedocs.io/en/latest/

Workspace API:  /workspace/{category}/{service}.html
Account API:    /account/{category}/{service}.html
驗證:           /authentication.html
DBUtils:        /dbutils.html
```

### Workspace API 類別
| 類別 | 服務 |
|----------|----------|
| `compute` | clusters, cluster_policies, command_execution, instance_pools, libraries |
| `catalog` | catalogs, schemas, tables, volumes, functions, storage_credentials, external_locations |
| `jobs` | jobs |
| `sql` | warehouses, statement_execution, queries, alerts, dashboards |
| `serving` | serving_endpoints |
| `vectorsearch` | vector_search_indexes, vector_search_endpoints |
| `pipelines` | pipelines |
| `workspace` | repos, secrets, workspace, git_credentials |
| `files` | files, dbfs |
| `ml` | experiments, model_registry |

---

## 驗證

**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html

### 環境變數
```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...  # 個人存取權杖
```

### 程式碼模式

```python
# 從環境自動偵測認證資訊
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# 明確指定的 token 驗證
w = WorkspaceClient(
    host="https://your-workspace.cloud.databricks.com",
    token="dapi..."
)

# Azure 服務主體
w = WorkspaceClient(
    host="https://adb-xxx.azuredatabricks.net",
    azure_workspace_resource_id="/subscriptions/.../resourceGroups/.../providers/Microsoft.Databricks/workspaces/...",
    azure_tenant_id="tenant-id",
    azure_client_id="client-id",
    azure_client_secret="secret"
)

# 使用 ~/.databrickscfg 中的具名設定檔
w = WorkspaceClient(profile="MY_PROFILE")
```

---

## 核心 API 參考

### 叢集 API
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html

```python
# 列出所有叢集
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")

# 取得叢集詳細資料
cluster = w.clusters.get(cluster_id="0123-456789-abcdef")

# 建立叢集（回傳 Wait 物件）
wait = w.clusters.create(
    cluster_name="my-cluster",
    spark_version=w.clusters.select_spark_version(latest=True),
    node_type_id=w.clusters.select_node_type(local_disk=True),
    num_workers=2
)
cluster = wait.result()  # 等待叢集進入執行中狀態

# 或使用 create_and_wait 進行阻塞呼叫
cluster = w.clusters.create_and_wait(
    cluster_name="my-cluster",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# 啟動 / 停止 / 刪除
w.clusters.start(cluster_id="...").result()
w.clusters.stop(cluster_id="...")
w.clusters.delete(cluster_id="...")
```

### 作業 API
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html

```python
from databricks.sdk.service.jobs import Task, NotebookTask

# 列出作業
for job in w.jobs.list():
    print(f"{job.job_id}: {job.settings.name}")

# 建立作業
created = w.jobs.create(
    name="my-job",
    tasks=[
        Task(
            task_key="main",
            notebook_task=NotebookTask(notebook_path="/Users/me/notebook"),
            existing_cluster_id="0123-456789-abcdef"
        )
    ]
)

# 立即執行作業
run = w.jobs.run_now_and_wait(job_id=created.job_id)
print(f"執行完成: {run.state.result_state}")

# 取得執行輸出
output = w.jobs.get_run_output(run_id=run.run_id)
```

### SQL 陳述式執行
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html

```python
# 執行 SQL 查詢
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM catalog.schema.table LIMIT 10",
    wait_timeout="30s"
)

# 檢查狀態並取得結果
if response.status.state == StatementState.SUCCEEDED:
    for row in response.result.data_array:
        print(row)

# 對於大型結果，逐塊取得資料
chunk = w.statement_execution.get_statement_result_chunk_n(
    statement_id=response.statement_id,
    chunk_index=0
)
```

### SQL 倉儲
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html

```python
# 列出 SQL 倉儲
for wh in w.warehouses.list():
    print(f"{wh.name}: {wh.state}")

# 取得 SQL 倉儲
warehouse = w.warehouses.get(id="abc123")

# 建立 SQL 倉儲
created = w.warehouses.create_and_wait(
    name="my-warehouse",
    cluster_size="Small",
    max_num_clusters=1,
    auto_stop_mins=15
)

# 啟動 / 停止
w.warehouses.start(id="abc123").result()
w.warehouses.stop(id="abc123").result()
```

### Unity Catalog - 資料表
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html

```python
# 列出結構描述中的資料表
for table in w.tables.list(catalog_name="main", schema_name="default"):
    print(f"{table.full_name}: {table.table_type}")

# 取得資料表資訊
table = w.tables.get(full_name="main.default.my_table")
print(f"欄位: {[c.name for c in table.columns]}")

# 檢查資料表是否存在
exists = w.tables.exists(full_name="main.default.my_table")
```

### Unity Catalog - 目錄與結構描述
**文件（目錄）：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
**文件（結構描述）：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html

```python
# 列出目錄
for catalog in w.catalogs.list():
    print(catalog.name)

# 建立目錄
w.catalogs.create(name="my_catalog", comment="說明")

# 列出結構描述
for schema in w.schemas.list(catalog_name="main"):
    print(schema.name)

# 建立結構描述
w.schemas.create(name="my_schema", catalog_name="main")
```

### 磁碟區
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html

```python
from databricks.sdk.service.catalog import VolumeType

# 列出磁碟區
for vol in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"{vol.full_name}: {vol.volume_type}")

# 建立受控磁碟區
w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_volume",
    volume_type=VolumeType.MANAGED
)

# 讀取磁碟區資訊
vol = w.volumes.read(name="main.default.my_volume")
```

### 檔案 API
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html

```python
# 上傳檔案到磁碟區
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=open("local_file.csv", "rb")
)

# 下載檔案
with w.files.download(file_path="/Volumes/main/default/my_volume/data.csv") as f:
    content = f.read()

# 列出目錄內容
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    print(f"{entry.name}: {entry.is_directory}")

# 以上傳 / 下載並顯示進度（平行）
w.files.upload_from(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    source_path="/local/path/large.parquet",
    use_parallel=True
)

w.files.download_to(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    destination="/local/output/",
    use_parallel=True
)
```

### Serving Endpoints（Model Serving）
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html

```python
# 列出端點
for ep in w.serving_endpoints.list():
    print(f"{ep.name}: {ep.state}")

# 取得端點
endpoint = w.serving_endpoints.get(name="my-endpoint")

# 查詢端點
response = w.serving_endpoints.query(
    name="my-endpoint",
    inputs={"prompt": "哈囉，世界！"}
)

# 適用於 chat/completions 端點
response = w.serving_endpoints.query(
    name="my-chat-endpoint",
    messages=[{"role": "user", "content": "你好！"}]
)

# 取得與 OpenAI 相容的用戶端
openai_client = w.serving_endpoints.get_open_ai_client()
```

### Vector Search
**文件（索引）：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
**文件（端點）：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_endpoints.html

```python
# 列出 Vector Search 索引
for idx in w.vector_search_indexes.list_indexes(endpoint_name="my-vs-endpoint"):
    print(idx.name)

# 查詢索引
results = w.vector_search_indexes.query_index(
    index_name="main.default.my_index",
    columns=["id", "text", "embedding"],
    query_text="搜尋查詢",
    num_results=10
)
for doc in results.result.data_array:
    print(doc)
```

### Pipelines（Delta Live Tables）
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html

```python
# 列出管線
for pipeline in w.pipelines.list_pipelines():
    print(f"{pipeline.name}: {pipeline.state}")

# 取得管線
pipeline = w.pipelines.get(pipeline_id="abc123")

# 啟動管線更新
w.pipelines.start_update(pipeline_id="abc123")

# 停止管線
w.pipelines.stop_and_wait(pipeline_id="abc123")
```

### Secrets
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html

```python
# 列出 Secret scope
for scope in w.secrets.list_scopes():
    print(scope.name)

# 建立 Secret scope
w.secrets.create_scope(scope="my-scope")

# 寫入 Secret
w.secrets.put_secret(scope="my-scope", key="api-key", string_value="secret123")

# 取得 Secret（回傳含有 value 的 GetSecretResponse）
secret = w.secrets.get_secret(scope="my-scope", key="api-key")

# 列出 scope 中的 Secrets（僅中繼資料，不含值）
for s in w.secrets.list_secrets(scope="my-scope"):
    print(s.key)
```

### DBUtils
**文件：** https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html

```python
# 透過 WorkspaceClient 存取 dbutils
dbutils = w.dbutils

# 檔案系統作業
files = dbutils.fs.ls("/")
dbutils.fs.cp("dbfs:/source", "dbfs:/dest")
dbutils.fs.rm("dbfs:/path", recurse=True)

# Secrets（與 w.secrets 相同，但使用 dbutils 介面）
value = dbutils.secrets.get(scope="my-scope", key="my-key")
```

---

## 常見模式

### 關鍵：非同步應用程式（FastAPI 等）

**Databricks SDK 完全是同步的。** 所有呼叫都會阻塞執行緒。在非同步應用程式（FastAPI、asyncio）中，你必須使用 `asyncio.to_thread()` 包裝 SDK 呼叫，以避免阻塞事件迴圈。

```python
import asyncio
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 錯誤 - 會阻塞事件迴圈
async def get_clusters_bad():
    return list(w.clusters.list())  # 會阻塞！

# 正確 - 在執行緒集區中執行
async def get_clusters_good():
    return await asyncio.to_thread(lambda: list(w.clusters.list()))

# 正確 - 適用於簡單呼叫
async def get_cluster(cluster_id: str):
    return await asyncio.to_thread(w.clusters.get, cluster_id)

# 正確 - FastAPI 端點
from fastapi import FastAPI
app = FastAPI()

@app.get("/clusters")
async def list_clusters():
    clusters = await asyncio.to_thread(lambda: list(w.clusters.list()))
    return [{"id": c.cluster_id, "name": c.cluster_name} for c in clusters]

@app.post("/query")
async def run_query(sql: str, warehouse_id: str):
    # 包裝會阻塞的 SDK 呼叫
    response = await asyncio.to_thread(
        w.statement_execution.execute_statement,
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s"
    )
    return response.result.data_array
```

**注意：** `WorkspaceClient().config.host` 並不是網路呼叫，它只是讀取設定，無需包裝屬性存取。

---

### 等待長時間執行的作業
```python
from datetime import timedelta

# 模式 1：使用 *_and_wait 方法
cluster = w.clusters.create_and_wait(
    cluster_name="test",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# 模式 2：使用 Wait 物件
wait = w.clusters.create(...)
cluster = wait.result()  # 阻塞直到準備完成

# 模式 3：使用回呼手動輪詢
def progress(cluster):
    print(f"狀態: {cluster.state}")

cluster = w.clusters.wait_get_cluster_running(
    cluster_id="...",
    timeout=timedelta(minutes=30),
    callback=progress
)
```

### 分頁
```python
# 所有 list 方法都會回傳可自動處理分頁的迭代器
for job in w.jobs.list():  # 會取得所有頁面
    print(job.settings.name)

# 手動控制
from databricks.sdk.service.jobs import ListJobsRequest
response = w.jobs.list(limit=10)
for job in response:
    print(job)
```

### 錯誤處理
```python
from databricks.sdk.errors import NotFound, PermissionDenied, ResourceAlreadyExists

try:
    cluster = w.clusters.get(cluster_id="invalid-id")
except NotFound:
    print("找不到叢集")
except PermissionDenied:
    print("存取遭拒")
```

---

## 不確定時

如果我不確定某個方法，我應該：

1. **檢查文件 URL 模式：**
   - `https://databricks-sdk-py.readthedocs.io/en/latest/workspace/{category}/{service}.html`

2. **常見類別：**
   - 叢集：`/workspace/compute/clusters.html`
   - 作業：`/workspace/jobs/jobs.html`
   - 資料表：`/workspace/catalog/tables.html`
   - SQL 倉儲：`/workspace/sql/warehouses.html`
   - Serving Endpoints：`/workspace/serving/serving_endpoints.html`

3. **先抓取並驗證**，再提供關於參數或回傳型別的指引。

---

## 快速參考連結

| API | 文件 URL |
|-----|-------------------|
| 驗證 | https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html |
| 叢集 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html |
| 作業 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html |
| SQL 倉儲 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html |
| 陳述式執行 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html |
| 資料表 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html |
| 目錄 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html |
| 結構描述 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html |
| 磁碟區 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html |
| 檔案 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html |
| Serving Endpoints | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html |
| Vector Search | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html |
| 管線 | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html |
| Secrets | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html |
| DBUtils | https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html |

## 相關技能

- **[databricks-config](../databricks-config/SKILL.md)** - 設定檔與驗證設定
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - 透過 DABs 部署資源
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - 作業協調模式
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - 目錄治理
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Serving endpoint 管理
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** - 向量索引作業
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - 透過 SDK 使用受控 PostgreSQL
