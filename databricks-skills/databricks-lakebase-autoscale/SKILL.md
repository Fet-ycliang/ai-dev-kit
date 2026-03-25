---
name: databricks-lakebase-autoscale
description: "Lakebase Autoscaling（新一代受管 PostgreSQL）的模式與最佳實務。當你要建立或管理 Lakebase Autoscaling 專案、設定自動縮放運算資源或 scale-to-zero、在 dev/test 工作流程中使用資料庫分支、透過 synced tables 實作 reverse ETL，或使用 OAuth 憑證將應用程式連線至 Lakebase 時適用。"
---

# Lakebase Autoscaling

使用 Lakebase Autoscaling 的模式與最佳實務；它是在 Databricks 上具備自動縮放運算資源、分支、scale-to-zero 與即時還原功能的新一代受管 PostgreSQL。

## 何時使用

當你有以下需求時，請使用這項技能：
- 建置需要 PostgreSQL 資料庫且具備自動縮放運算資源的應用程式
- 在 dev/test/staging 工作流程中使用資料庫分支
- 為應用程式加入持久狀態，同時透過 scale-to-zero 節省成本
- 透過 synced tables，從 Delta Lake 將資料 reverse ETL 到作業型資料庫
- 管理 Lakebase Autoscaling 專案、分支、運算資源或憑證

## 概觀

Lakebase Autoscaling 是 Databricks 針對 OLTP 工作負載推出的新一代受管 PostgreSQL 服務。它提供自動縮放運算資源、類似 Git 的分支功能、scale-to-zero，以及即時時間點還原。

| 功能 | 說明 |
|---------|-------------|
| **自動縮放運算資源** | 0.5-112 CU，每個 CU 具備 2 GB RAM；會依負載動態縮放 |
| **Scale-to-Zero** | 運算資源會在可設定的不活動逾時後暫停 |
| **分支** | 建立隔離的資料庫環境（類似 Git branches），用於 dev/test |
| **即時還原** | 可在設定的視窗內，從任意時間點進行還原（最長 35 天） |
| **OAuth 驗證** | 透過 Databricks SDK 以 Token 進行驗證（1 小時到期） |
| **Reverse ETL** | 透過 synced tables，將資料從 Delta tables 同步至 PostgreSQL |

**可用區域（AWS）：** us-east-1, us-east-2, eu-central-1, eu-west-1, eu-west-2, ap-south-1, ap-southeast-1, ap-southeast-2

**可用區域（Azure Beta）：** eastus2, westeurope, westus

## 專案階層

了解此階層對於使用 Lakebase Autoscaling 至關重要：

```
專案（頂層容器）
  └── 分支（隔離的資料庫環境）
        ├── 運算資源（主要讀寫端點）
        ├── 讀取複本（選用，唯讀）
        ├── 角色（Postgres roles）
        └── 資料庫（Postgres databases）
              └── Schemas
```

| 物件 | 說明 |
|--------|-------------|
| **專案** | 頂層容器。透過 `w.postgres.create_project()` 建立。 |
| **分支** | 具備寫入時複製儲存體的隔離資料庫環境。預設分支為 `production`。 |
| **運算資源** | 為分支提供 Postgres 服務的伺服器。可設定 CU 規模與自動縮放。 |
| **資料庫** | 分支中的標準 Postgres 資料庫。預設為 `databricks_postgres`。 |

## 快速開始

建立專案並連線：

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Project, ProjectSpec

w = WorkspaceClient()

# 建立專案（長時間執行的作業）
operation = w.postgres.create_project(
    project=Project(
        spec=ProjectSpec(
            display_name="我的應用程式",
            pg_version="17"
        )
    ),
    project_id="my-app"
)
result = operation.wait()
print(f"已建立專案: {result.name}")
```

## 常見模式

### 產生 OAuth 權杖

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 產生用於連線資料庫的憑證（可選擇限定到特定端點）
cred = w.postgres.generate_database_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)
token = cred.token  # 用作連線字串中的密碼
# Token 會在 1 小時後到期
```

### 從 Notebook 連線

```python
import psycopg
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 取得端點詳細資料
endpoint = w.postgres.get_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary"
)
host = endpoint.status.hosts.host

# 產生權杖（限定到端點）
cred = w.postgres.generate_database_credential(
    endpoint="projects/my-app/branches/production/endpoints/ep-primary"
)

# 使用 psycopg3 連線
conn_string = (
    f"host={host} "
    f"dbname=databricks_postgres "
    f"user={w.current_user.me().user_name} "
    f"password={cred.token} "
    f"sslmode=require"
)
with psycopg.connect(conn_string) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone())
```

### 為開發建立分支

```python
from databricks.sdk.service.postgres import Branch, BranchSpec, Duration

# 建立 7 天後到期的開發分支
branch = w.postgres.create_branch(
    parent="projects/my-app",
    branch=Branch(
        spec=BranchSpec(
            source_branch="projects/my-app/branches/production",
            ttl=Duration(seconds=604800)  # 7 天
        )
    ),
    branch_id="development"
).wait()
print(f"已建立分支: {branch.name}")
```

### 調整運算資源大小（自動縮放）

```python
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask

# 將運算資源更新為在 2-8 CU 之間自動縮放
w.postgres.update_endpoint(
    name="projects/my-app/branches/production/endpoints/ep-primary",
    endpoint=Endpoint(
        name="projects/my-app/branches/production/endpoints/ep-primary",
        spec=EndpointSpec(
            autoscaling_limit_min_cu=2.0,
            autoscaling_limit_max_cu=8.0
        )
    ),
    update_mask=FieldMask(field_mask=[
        "spec.autoscaling_limit_min_cu",
        "spec.autoscaling_limit_max_cu"
    ])
).wait()
```

## MCP 工具

以下 MCP 工具可用於管理 Lakebase 基礎架構。對於 Lakebase Autoscaling，請使用 `type="autoscale"`。

### 資料庫（專案）管理

| 工具 | 說明 |
|------|-------------|
| `create_or_update_lakebase_database` | 建立或更新資料庫。會依名稱尋找，若不存在則建立，已存在則更新。使用 `type="autoscale"`、`display_name`、`pg_version` 參數。新專案會自動建立 production 分支、預設運算資源，以及 databricks_postgres 資料庫。 |
| `get_lakebase_database` | 取得資料庫詳細資料（包含分支與端點）或列出全部。傳入 `name` 可取得單一項目，省略則列出全部。使用 `type="autoscale"` 進行篩選。 |
| `delete_lakebase_database` | 刪除專案及其所有分支、運算資源與資料。使用 `type="autoscale"`。 |

### 分支管理

| 工具 | 說明 |
|------|-------------|
| `create_or_update_lakebase_branch` | 建立或更新分支及其運算端點。參數：`project_name`、`branch_id`、`source_branch`、`ttl_seconds`、`is_protected`，以及運算資源參數（`autoscaling_limit_min_cu`、`autoscaling_limit_max_cu`、`scale_to_zero_seconds`）。 |
| `delete_lakebase_branch` | 刪除分支及其運算端點。 |

### 憑證

| 工具 | 說明 |
|------|-------------|
| `generate_lakebase_credential` | 為 PostgreSQL 連線產生 OAuth Token（1 小時到期）。對 autoscale 請傳入 `endpoint` 資源名稱。 |

## 參考檔案

- [projects.md](projects.md) - 專案管理模式與設定
- [branches.md](branches.md) - 分支工作流程、保護與到期設定
- [computes.md](computes.md) - 運算資源規模、自動縮放與 scale-to-zero
- [connection-patterns.md](connection-patterns.md) - 各種使用情境的連線模式
- [reverse-etl.md](reverse-etl.md) - 從 Delta Lake 到 Lakebase 的 synced tables

## CLI 快速參考

```bash
# 建立專案
databricks postgres create-project \
    --project-id my-app \
    --json '{"spec": {"display_name": "我的應用程式", "pg_version": "17"}}'

# 列出專案
databricks postgres list-projects

# 取得專案詳細資料
databricks postgres get-project projects/my-app

# 建立分支
databricks postgres create-branch projects/my-app development \
    --json '{"spec": {"source_branch": "projects/my-app/branches/production", "no_expiry": true}}'

# 列出分支
databricks postgres list-branches projects/my-app

# 取得端點詳細資料
databricks postgres get-endpoint projects/my-app/branches/production/endpoints/ep-primary

# 刪除專案
databricks postgres delete-project projects/my-app
```

## 與 Lakebase Provisioned 的主要差異

| 面向 | Provisioned | Autoscaling |
|--------|-------------|-------------|
| SDK 模組 | `w.database` | `w.postgres` |
| 頂層資源 | 執行個體 | 專案 |
| 容量 | CU_1, CU_2, CU_4, CU_8（16 GB/CU） | 0.5-112 CU（2 GB/CU） |
| 分支 | 不支援 | 完整支援分支 |
| Scale-to-zero | 不支援 | 可設定逾時 |
| 作業 | 同步 | 長時間執行作業（LRO） |
| 讀取複本 | 可讀取的次要節點 | 專用唯讀端點 |

## 常見問題

| 問題 | 解決方式 |
|-------|----------|
| **長時間查詢期間 Token 過期** | 實作 Token 重新整理迴圈；Token 會在 1 小時後到期 |
| **scale-to-zero 後連線被拒** | 運算資源會在連線時自動喚醒；重新啟用約需數百毫秒；請實作重試邏輯 |
| **macOS 上 DNS 解析失敗** | 使用 `dig` 指令解析主機名稱，並將 `hostaddr` 傳給 psycopg |
| **分支刪除受阻** | 先刪除子分支；無法刪除仍有子分支的分支 |
| **自動縮放範圍過大** | Max - min 不可超過 8 CU（例如 8-16 CU 有效，0.5-32 CU 無效） |
| **出現 SSL required 錯誤** | 連線字串中務必使用 `sslmode=require` |
| **必須提供 update_mask** | 所有更新作業都需要 `update_mask` 來指定要修改的欄位 |
| **連線在閒置 24 小時後關閉** | 所有連線皆有 24 小時閒置逾時與 3 天最長存活時間；請實作重試邏輯 |

## 目前限制

Lakebase Autoscaling 目前尚不支援以下功能：
- 具備可讀取次要節點的高可用性（請改用讀取複本）
- Databricks Apps UI 整合（Apps 可透過憑證手動連線）
- Feature Store 整合
- 有狀態的 AI agents（LangChain memory）
- Postgres-to-Delta 同步（僅支援 Delta-to-Postgres reverse ETL）
- 自訂計費標籤與 serverless 預算政策
- 直接從 Lakebase Provisioned 遷移（請使用 pg_dump/pg_restore 或 reverse ETL）

## SDK 版本需求

- **Databricks SDK for Python**：>= 0.81.0（適用於 `w.postgres` 模組）
- **psycopg**：3.x（支援 `hostaddr` 參數作為 DNS 解法）
- **SQLAlchemy**：2.x，搭配 `postgresql+psycopg` driver

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```

## 注意事項

- **運算單位（Compute Units）** 在 Autoscaling 中每單位約提供 2 GB RAM（Provisioned 為 16 GB）。
- **資源命名** 採用階層式路徑：`projects/{id}/branches/{id}/endpoints/{id}`。
- 所有 create/update/delete 作業皆為 **長時間執行** -- 請在 SDK 中使用 `.wait()`。
- Token 存續時間很短（1 小時） -- 正式環境應用程式**必須**實作 Token 重新整理。
- 支援 **Postgres versions** 16 與 17。

## 相關技能

- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - 固定容量的受管 PostgreSQL（前一代）
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - 可使用 Lakebase 作為持久層的全端應用程式
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - 使用 Lakebase 作為後端的 Python 應用程式
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - 用於專案管理與 Token 產生的 SDK
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - 部署包含 Lakebase 資源的應用程式
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - 排程 reverse ETL 同步工作
