# 應用程式資源與通訊策略

Databricks Apps 透過受管理的連線整合平台資源。使用資源引用而非硬編碼 ID，以確保可移植性與安全性。

**官方文件**：https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources

---

## 支援的資源類型

| 資源 | 預設鍵值 | 權限 | 使用情境 |
|------|---------|------|---------|
| SQL Warehouse | `sql-warehouse` | Can use、Can manage | 查詢 Delta table |
| Lakebase 資料庫 | `database` | Can connect and create | 低延遲交易資料 |
| 模型服務 endpoint | `serving-endpoint` | Can view、Can query、Can manage | AI/ML 推論 |
| Secret | `secret` | Can read、Can write、Can manage | API key、token |
| Unity Catalog Volume | `volume` | Can read、Can read and write | 檔案儲存 |
| 向量搜尋索引 | `vector-search-index` | Can select | 語意搜尋 |
| Genie space | `genie-space` | Can view、Can run、Can edit | 自然語言分析 |
| UC connection | `connection` | Use Connection | 外部資料來源 |
| UC function | `function` | Can execute | SQL/Python 函式 |
| MLflow experiment | `experiment` | Can read、Can edit | ML experiment 追蹤 |
| Lakeflow job | `job` | Can view、Can manage run | 資料管道 |

---

## 在 app.yaml 中設定資源

使用 `valueFrom` 引用資源——絕不硬編碼 ID：

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse

  - name: SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint

  - name: DB_CONNECTION_STRING
    valueFrom: database
```

透過 Databricks Apps UI 在建立或編輯應用程式時新增資源：
1. 前往「Configure」步驟
2. 點擊 **+ Add resource**
3. 選擇資源類型並設定權限
4. 指定鍵值（在 `valueFrom` 中引用）

---

## 通訊策略

依存取模式選擇資料後端：

| 策略 | 適用時機 | 函式庫 | 連線模式 |
|------|---------|--------|---------|
| **SQL Warehouse** | 分析查詢 Delta table | `databricks-sql-connector` | `sql.connect()` 搭配 `Config()` |
| **Lakebase（PostgreSQL）** | 低延遲交易 CRUD | `psycopg2` / `asyncpg` | 標準 PostgreSQL，透過自動注入的環境變數 |
| **Databricks SDK** | 平台 API 呼叫（jobs、clusters、UC） | `databricks-sdk` | `WorkspaceClient()` |
| **Model Serving** | AI/ML 推論請求 | `requests` 或 SDK | REST 呼叫至 serving endpoint |
| **Unity Catalog Functions** | 伺服器端運算（SQL/Python UDF） | `databricks-sql-connector` | 透過 SQL Warehouse 執行 |

### SQL Warehouse 模式

```python
import os
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)

with conn.cursor() as cursor:
    cursor.execute("SELECT * FROM catalog.schema.table LIMIT 100")
    rows = cursor.fetchall()
```

### Model Serving 模式

```python
import os, requests
from databricks.sdk.core import Config

cfg = Config()
headers = cfg.authenticate()
headers["Content-Type"] = "application/json"

endpoint = os.getenv("SERVING_ENDPOINT_NAME")
response = requests.post(
    f"https://{cfg.host}/serving-endpoints/{endpoint}/invocations",
    headers=headers,
    json={"inputs": [{"prompt": "Hello"}]},
)
result = response.json()
```

### SDK 模式

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # 自動偵測認證資訊
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")
```

Lakebase 模式請見 [5-lakebase.md](5-lakebase.md)。

---

## 最佳實踐

- 務必使用 `valueFrom`——確保應用程式可在不同環境間移植
- 授予 service principal 最少必要的權限（例如 SQL Warehouse 使用 `CAN USE` 而非 `CAN MANAGE`）
- 交易性工作負載使用 Lakebase；分析性工作負載使用 SQL Warehouse
- 外部服務請使用 UC connection 或 secret（絕不硬編碼 API key）
