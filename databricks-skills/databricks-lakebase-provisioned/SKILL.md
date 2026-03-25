---
name: databricks-lakebase-provisioned
description: "Lakebase Provisioned（Databricks 代管 PostgreSQL）在 OLTP 工作負載上的模式與最佳實務。適用於建立 Lakebase 實例、讓應用程式或 Databricks Apps 連線 PostgreSQL、透過同步資料表實作 reverse ETL、儲存代理或聊天記憶、或設定 Lakebase 的 OAuth 驗證。"
---

# Lakebase Provisioned

本技能說明如何在 OLTP 工作負載中運用 Lakebase Provisioned（Databricks 代管 PostgreSQL）的模式與最佳實務。

## 適用時機

在以下情境使用此技能：
- 建置需要 PostgreSQL 資料庫處理交易工作負載的應用程式
- 為 Databricks Apps 加入持久化狀態
- 從 Delta Lake 實作 reverse ETL 至作業型資料庫
- 為 LangChain 應用程式儲存聊天/代理記憶

## 概觀

Lakebase Provisioned 是 Databricks 提供的 OLTP（Online Transaction Processing）代管 PostgreSQL 服務，整合 Unity Catalog，並支援 OAuth token 驗證。

| 功能 | 說明 |
|------|------|
| **Managed PostgreSQL** | 具自動布建的全代管實例 |
| **OAuth Authentication** | 透過 Databricks SDK 使用 token 驗證（有效 1 小時） |
| **Unity Catalog** | 可註冊資料庫以利治理 |
| **Reverse ETL** | 將 Delta 資料表同步至 PostgreSQL |
| **Apps Integration** | 與 Databricks Apps 深度整合 |

**可用 AWS 區域：** us-east-1、us-east-2、us-west-2、eu-central-1、eu-west-1、ap-south-1、ap-southeast-1、ap-southeast-2

## 快速開始

建立並連線到 Lakebase Provisioned 實例：

```python
from databricks.sdk import WorkspaceClient
import uuid

# 初始化客戶端
w = WorkspaceClient()

# 建立資料庫實例
instance = w.database.create_database_instance(
    name="my-lakebase-instance",
    capacity="CU_1",  # CU_1, CU_2, CU_4, CU_8
    stopped=False
)
print(f"Instance created: {instance.name}")
print(f"DNS endpoint: {instance.read_write_dns}")
```

## 常見模式

### 產生 OAuth Token

```python
from databricks.sdk import WorkspaceClient
import uuid

w = WorkspaceClient()

# 產生連線資料庫用的 OAuth token
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=["my-lakebase-instance"]
)
token = cred.token  # 於連線字串中當作密碼使用
```

### 從 Notebook 連線

```python
import psycopg
from databricks.sdk import WorkspaceClient
import uuid

# 取得實例詳細資訊
w = WorkspaceClient()
instance = w.database.get_database_instance(name="my-lakebase-instance")

# 產生 token
cred = w.database.generate_database_credential(
    request_id=str(uuid.uuid4()),
    instance_names=["my-lakebase-instance"]
)

# 使用 psycopg3 連線
conn_string = f"host={instance.read_write_dns} dbname=postgres user={w.current_user.me().user_name} password={cred.token} sslmode=require"
with psycopg.connect(conn_string) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone())
```

### SQLAlchemy 搭配 Token 重新整理（正式環境）

長時間執行的應用程式必須重新整理 token（1 小時過期）：

```python
import asyncio
import os
import uuid
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from databricks.sdk import WorkspaceClient

# Token 重新整理狀態
_current_token = None
_token_refresh_task = None
TOKEN_REFRESH_INTERVAL = 50 * 60  # 50 分鐘（早於 1 小時失效）

def _generate_token(instance_name: str) -> str:
    """產生最新 OAuth token。"""
    w = WorkspaceClient()
    cred = w.database.generate_database_credential(
        request_id=str(uuid.uuid4()),
        instance_names=[instance_name]
    )
    return cred.token

async def _token_refresh_loop(instance_name: str):
    """背景工作，每 50 分鐘重新整理 token。"""
    global _current_token
    while True:
        await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
        _current_token = await asyncio.to_thread(_generate_token, instance_name)

def init_database(instance_name: str, database_name: str, username: str) -> AsyncEngine:
    """初始化資料庫並注入 OAuth token。"""
    global _current_token
    
    w = WorkspaceClient()
    instance = w.database.get_database_instance(name=instance_name)
    
    # 產生初始 token
    _current_token = _generate_token(instance_name)
    
    # 建立 URL（密碼透過 do_connect 注入）
    url = f"postgresql+psycopg://{username}@{instance.read_write_dns}:5432/{database_name}"
    
    engine = create_async_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        connect_args={"sslmode": "require"}
    )
    
    # 每次連線時注入 token
    @event.listens_for(engine.sync_engine, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        cparams["password"] = _current_token
    
    return engine
```

### Databricks Apps 整合

於 Databricks Apps 中透過環境變數設定：

```python
# Databricks Apps 會設定以下環境變數：
# - LAKEBASE_INSTANCE_NAME: 實例名稱
# - LAKEBASE_DATABASE_NAME: 資料庫名稱
# - LAKEBASE_USERNAME: 使用者名稱（選用，預設為 service principal）

import os

def is_lakebase_configured() -> bool:
    """檢查此 App 是否已設定 Lakebase。"""
    return bool(
        os.environ.get("LAKEBASE_PG_URL") or
        (os.environ.get("LAKEBASE_INSTANCE_NAME") and 
         os.environ.get("LAKEBASE_DATABASE_NAME"))
    )
```

透過 CLI 將 Lakebase 加入 App 資源：

```bash
databricks apps add-resource $APP_NAME \
    --resource-type database \
    --resource-name lakebase \
    --database-instance my-lakebase-instance
```

### 向 Unity Catalog 註冊

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 在 Unity Catalog 註冊資料庫
w.database.register_database_instance(
    name="my-lakebase-instance",
    catalog="my_catalog",
    schema="my_schema"
)
```

### MLflow Model Resources

將 Lakebase 宣告為模型資源，便於自動配置憑證：

```python
from mlflow.models.resources import DatabricksLakebase

resources = [
    DatabricksLakebase(database_instance_name="my-lakebase-instance"),
]

# 註冊模型時
mlflow.langchain.log_model(
    model,
    artifact_path="model",
    resources=resources,
    pip_requirements=["databricks-langchain[memory]"]
)
```

## MCP Tools

以下 MCP 工具可管理 Lakebase 基礎設施。針對 Lakebase Provisioned，請使用 `type="provisioned"`。

### Database Management

| 工具 | 說明 |
|------|------|
| `create_or_update_lakebase_database` | 建立或更新資料庫；若存在即更新，否則新建。需設定 `type="provisioned"`、`capacity`（CU_1-CU_8）、`stopped` 等參數。 |
| `get_lakebase_database` | 取得資料庫詳細資訊或列出全部。提供 `name` 取得特定實例，若省略則列出全部並可用 `type="provisioned"` 篩選。 |
| `delete_lakebase_database` | 刪除資料庫及其資源；使用 `type="provisioned"`，可搭配 `force=True` 連同相依資源移除。 |
| `generate_lakebase_credential` | 產生 PostgreSQL 連線用 OAuth token（有效 1 小時）；於 provisioned 模式傳入 `instance_names`。 |

### Reverse ETL（Catalog + Synced Tables）

| 工具 | 說明 |
|------|------|
| `create_or_update_lakebase_sync` | 設定 reverse ETL：確保 UC catalog 註冊存在後，從 Delta 建立同步表至 Lakebase。參數含 `instance_name`、`source_table_name`、`target_table_name`、`scheduling_policy`（"TRIGGERED"/"SNAPSHOT"/"CONTINUOUS"）。 |
| `delete_lakebase_sync` | 移除同步表並可選擇刪除 UC catalog 註冊。 |

## 參考文件

- [connection-patterns.md](connection-patterns.md) - 各使用情境的詳細連線模式
- [reverse-etl.md](reverse-etl.md) - 從 Delta Lake 同步資料到 Lakebase

## CLI 快速查詢

```bash
# 建立實例
databricks database create-database-instance \
    --name my-lakebase-instance \
    --capacity CU_1

# 取得實例詳細資訊
databricks database get-database-instance --name my-lakebase-instance

# 產生憑證
databricks database generate-database-credential \
    --request-id $(uuidgen) \
    --json '{"instance_names": ["my-lakebase-instance"]}'

# 列出實例
databricks database list-database-instances

# 停止實例（節省成本）
databricks database stop-database-instance --name my-lakebase-instance

# 啟動實例
databricks database start-database-instance --name my-lakebase-instance
```

## 常見問題

| 問題 | 解法 |
|------|------|
| **長時間查詢時 token 過期** | 實作 token 重新整理迴圈（參考 SQLAlchemy 節）；token 1 小時後過期 |
| **macOS DNS 解析失敗** | 改用 `dig` 解析主機名稱並將 `hostaddr` 傳給 psycopg |
| **Connection refused** | 確認實例未被停止，檢查 `instance.state` |
| **Permission denied** | 確保使用者已獲得 Lakebase 實例的存取權 |
| **需使用 SSL 的錯誤** | 連線字串中務必設定 `sslmode=require` |

## SDK 版本需求

- **Databricks SDK for Python**：>= 0.61.0（建議 0.81.0+ 以完整支援 API）
- **psycopg**：3.x（支援 DNS 替代方案的 `hostaddr` 參數）
- **SQLAlchemy**：2.x，搭配 `postgresql+psycopg` 驅動

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```

## 備註

- **Capacity 值** 以 compute unit 表示：`CU_1`、`CU_2`、`CU_4`、`CU_8`
- **Lakebase Autoscaling** 為新服務，具自動擴縮但區域有限；本技能聚焦較廣泛可用的 **Lakebase Provisioned**
- LangChain 代理的記憶/狀態建議使用 `databricks-langchain[memory]`，內含 Lakebase 支援
- Token 壽命短（1 小時），正式環境應用務必實作 token 重新整理

## 相關技能

- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - 可使用 Lakebase 儲存的全端 App
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - 以 Lakebase 作為後端的 Python App
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - 用於管理實例與產生 token 的 SDK
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - 部署含 Lakebase 資源的應用
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - 排程 reverse ETL 同步作業
