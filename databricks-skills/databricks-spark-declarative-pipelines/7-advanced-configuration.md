# 進階管線設定 (`extra_settings`)

預設情況下，系統會使用 **serverless compute 和 Unity Catalog** 建立管線。只有在進階使用情境下，才應使用 `extra_settings` 參數。

**重要：除非使用者明確要求，否則不要使用 `extra_settings` 將 `serverless=false`：**
- R 語言支援
- Spark RDD API
- JAR library 或 Maven coordinate

## 何時使用 `extra_settings`

- **開發模式**：以較寬鬆的驗證加快迭代速度
- **持續執行管線**：使用即時串流，而不是觸發式執行
- **事件記錄**：自訂 event log 資料表位置
- **管線中繼資料**：標籤、設定變數
- **Python 依賴**：為 serverless 管線安裝 pip 套件
- **Classic clusters**（少見）：僅在使用者明確需要 R、RDD API 或 JAR 時使用

## `extra_settings` 參數參考

### 最上層欄位

| 欄位 | 類型 | 預設值 | 說明 |
|-------|------|---------|-------------|
| `serverless` | bool | `true` | 使用 serverless compute。若要使用專用叢集，請設為 `false`。 |
| `continuous` | bool | `false` | `true` = 持續執行（即時），`false` = 觸發式執行 |
| `development` | bool | `false` | 開發模式：啟動較快、驗證較寬鬆、不會重試 |
| `photon` | bool | `false` | 啟用 Photon 向量化查詢引擎 |
| `edition` | str | `"CORE"` | `"CORE"`、`"PRO"` 或 `"ADVANCED"`。CDC 需要 Advanced。 |
| `channel` | str | `"CURRENT"` | `"CURRENT"`（穩定版）或 `"PREVIEW"`（最新功能） |
| `clusters` | list | `[]` | 叢集設定（若 `serverless=false` 則為必要） |
| `configuration` | dict | `{}` | Spark 設定 key-value 配對（所有值都必須是字串） |
| `tags` | dict | `{}` | 管線中繼資料標籤（最多 25 個） |
| `event_log` | dict | auto | 自訂 event log 資料表位置 |
| `notifications` | list | `[]` | 管線事件的 Email/webhook 通知 |
| `id` | str | - | 強制更新指定的 pipeline ID |
| `allow_duplicate_names` | bool | `false` | 允許多個管線使用相同名稱 |
| `budget_policy_id` | str | - | 用於成本追蹤的 budget policy ID |
| `storage` | str | - | 供 checkpoint/資料表使用的 DBFS 根目錄（舊版，請改用 Unity Catalog） |
| `target` | str | - | **已淘汰**：請改用 `schema` 參數 |
| `dry_run` | bool | `false` | 僅驗證管線而不建立（僅限 create） |
| `run_as` | dict | - | 以指定 user/service principal 身分執行管線 |
| `restart_window` | dict | - | 持續執行管線重新啟動的維護時段 |
| `filters` | dict | - | 在管線中納入/排除特定路徑 |
| `trigger` | dict | - | **已淘汰**：請改用 `continuous` |
| `deployment` | dict | - | 部署方式（BUNDLE 或 DEFAULT） |
| `environment` | dict | - | serverless 的 Python pip 依賴 |
| `gateway_definition` | dict | - | CDC gateway 管線設定 |
| `ingestion_definition` | dict | - | 受管理的 ingestion 設定（Salesforce、Workday 等） |
| `usage_policy_id` | str | - | usage policy ID |

### `clusters` 陣列 - 叢集設定

每個叢集物件支援以下欄位：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `label` | str | **必要**。主叢集使用 `"default"`，維護工作使用 `"maintenance"` |
| `num_workers` | int | 固定 worker 數量（與 autoscale 擇一，不可同時使用） |
| `autoscale` | dict | `{"min_workers": 1, "max_workers": 4, "mode": "ENHANCED"}` |
| `node_type_id` | str | 執行個體類型，例如 `"i3.xlarge"`、`"Standard_DS3_v2"` |
| `driver_node_type_id` | str | Driver 執行個體類型（預設為 `node_type_id`） |
| `instance_pool_id` | str | 使用此 pool 中的執行個體（啟動較快） |
| `driver_instance_pool_id` | str | Driver 節點使用的 pool |
| `spark_conf` | dict | 此叢集的 Spark 設定 |
| `spark_env_vars` | dict | 環境變數 |
| `custom_tags` | dict | 套用至雲端資源的標籤 |
| `init_scripts` | list | 初始化腳本位置 |
| `aws_attributes` | dict | AWS 專屬：`{"availability": "SPOT", "zone_id": "us-west-2a"}` |
| `azure_attributes` | dict | Azure 專屬：`{"availability": "SPOT_AZURE"}` |
| `gcp_attributes` | dict | GCP 專屬設定 |

**Autoscale 模式**：`"LEGACY"` 或 `"ENHANCED"`（建議使用，可針對 DLT 工作負載最佳化）

### `event_log` 物件 - 自訂 Event Log 位置

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `catalog` | str | event log 資料表使用的 Unity Catalog 名稱 |
| `schema` | str | event log 資料表使用的 schema 名稱 |
| `name` | str | event log 的資料表名稱 |

### `notifications` 陣列 - 通知設定

每個通知物件包含：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `email_recipients` | list | Email 位址清單 |
| `alerts` | list | 要發送通知的事件：`"on-update-success"`、`"on-update-failure"`、`"on-update-fatal-failure"`、`"on-flow-failure"` |

### `configuration` Dict - Spark/管線設定

常見設定 key（所有值都必須是字串）：

| Key | 說明 |
|-----|-------------|
| `spark.sql.shuffle.partitions` | shuffle partition 數量（建議使用 `"auto"`） |
| `pipelines.numRetries` | 暫時性失敗時的重試次數 |
| `pipelines.trigger.interval` | 持續執行管線的觸發間隔，例如 `"1 hour"` |
| `spark.databricks.delta.preview.enabled` | 啟用 Delta preview 功能（`"true"`） |

### `run_as` 物件 - 管線執行身分

指定由哪位使用者或 service principal 執行管線：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `user_name` | str | workspace 使用者的 Email（只能設為自己的 Email） |
| `service_principal_name` | str | service principal 的 Application ID（需要 servicePrincipal/user 角色） |

**注意**：`user_name` 或 `service_principal_name` 只能擇一設定。

### `restart_window` 物件 - 持續執行管線的重新啟動排程

對持續執行管線，定義允許重新啟動的時間：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `start_hour` | int | **必要**。5 小時重新啟動時段開始的整點（0-23） |
| `days_of_week` | list | 允許的日期：`"MONDAY"`、`"TUESDAY"` 等（預設：每天） |
| `time_zone_id` | str | 時區，例如 `"America/Los_Angeles"`（預設：UTC） |

### `filters` 物件 - 路徑篩選

在管線中納入或排除特定路徑：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `include` | list | 要納入的路徑清單 |
| `exclude` | list | 要排除的路徑清單 |

### `environment` 物件 - Python 依賴（Serverless）

為 serverless 管線安裝 pip 依賴：

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `dependencies` | list | pip requirement 清單（例如 `["pandas==2.0.0", "requests"]`） |

### `deployment` 物件 - 部署方式

| 欄位 | 類型 | 說明 |
|-------|------|-------------|
| `kind` | str | `"BUNDLE"`（Databricks Asset Bundles）或 `"DEFAULT"` |
| `metadata_file_path` | str | 部署中繼資料檔案的路徑 |

### Edition 比較

| 功能 | CORE | PRO | ADVANCED |
|---------|------|-----|----------|
| Streaming tables | 是 | 是 | 是 |
| Materialized views | 是 | 是 | 是 |
| Expectations（資料品質） | 是 | 是 | 是 |
| Change Data Capture (CDC) | 否 | 否 | 是 |
| SCD Type 1/2 | 否 | 否 | 是 |

## 設定範例

### 開發模式管線

使用 `create_or_update_pipeline` 工具並搭配：
- `name`: "my_dev_pipeline"
- `root_path`: "/Workspace/Users/user@example.com/my_pipeline"
- `catalog`: "dev_catalog"
- `schema`: "dev_schema"
- `workspace_file_paths`: [...]
- `start_run`: true
- `extra_settings`:
```json
{
    "development": true,
    "tags": {"environment": "development", "owner": "data-team"}
}
```

### 使用專用叢集的非 Serverless 管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "serverless": false,
    "clusters": [{
        "label": "default",
        "num_workers": 4,
        "node_type_id": "i3.xlarge",
        "custom_tags": {"cost_center": "analytics"}
    }],
    "photon": true,
    "edition": "ADVANCED"
}
```

### 持續執行的 Streaming 管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "continuous": true,
    "configuration": {
        "spark.sql.shuffle.partitions": "auto"
    }
}
```

### 使用 Instance Pool

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "serverless": false,
    "clusters": [{
        "label": "default",
        "instance_pool_id": "0727-104344-hauls13-pool-xyz",
        "num_workers": 2,
        "custom_tags": {"project": "analytics"}
    }]
}
```

### 自訂 Event Log 位置

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "event_log": {
        "catalog": "audit_catalog",
        "schema": "pipeline_logs",
        "name": "my_pipeline_events"
    }
}
```

### 具有 Email 通知的管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "notifications": [{
        "email_recipients": ["team@example.com", "oncall@example.com"],
        "alerts": ["on-update-failure", "on-update-fatal-failure", "on-flow-failure"]
    }]
}
```

### 使用自動縮放的正式環境管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "serverless": false,
    "development": false,
    "photon": true,
    "edition": "ADVANCED",
    "clusters": [{
        "label": "default",
        "autoscale": {
            "min_workers": 2,
            "max_workers": 8,
            "mode": "ENHANCED"
        },
        "node_type_id": "i3.xlarge",
        "spark_conf": {
            "spark.sql.adaptive.enabled": "true"
        },
        "custom_tags": {"environment": "production"}
    }],
    "notifications": [{
        "email_recipients": ["data-team@example.com"],
        "alerts": ["on-update-failure"]
    }]
}
```

### 以 Service Principal 身分執行

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "run_as": {
        "service_principal_name": "00000000-0000-0000-0000-000000000000"
    }
}
```

### 具備 Restart Window 的持續執行管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "continuous": true,
    "restart_window": {
        "start_hour": 2,
        "days_of_week": ["SATURDAY", "SUNDAY"],
        "time_zone_id": "America/Los_Angeles"
    }
}
```

### 具有 Python 依賴的 Serverless 管線

使用 `create_or_update_pipeline` 工具並搭配 `extra_settings`：
```json
{
    "serverless": true,
    "environment": {
        "dependencies": [
            "scikit-learn==1.3.0",
            "pandas>=2.0.0",
            "requests"
        ]
    }
}
```

### 依 ID 更新既有管線

如果你已從 Databricks UI 取得 pipeline ID，可在 `extra_settings` 中加入 `id` 以強制更新：
```json
{
    "id": "554f4497-4807-4182-bff0-ffac4bb4f0ce"
}
```

### Databricks UI 的完整 JSON 匯出

你可以從 Databricks UI 複製管線設定（Pipeline Settings > JSON），並直接作為 `extra_settings` 傳入。像 `pipeline_type` 這類無效欄位會自動被過濾：

```json
{
    "id": "554f4497-4807-4182-bff0-ffac4bb4f0ce",
    "pipeline_type": "WORKSPACE",
    "continuous": false,
    "development": true,
    "photon": false,
    "edition": "ADVANCED",
    "channel": "CURRENT",
    "clusters": [{
        "label": "default",
        "num_workers": 1,
        "instance_pool_id": "0727-104344-pool-xyz"
    }],
    "configuration": {
        "catalog": "main",
        "schema": "my_schema"
    }
}
```

**注意**：明確指定的工具參數（`name`、`root_path`、`catalog`、`schema`、`workspace_file_paths`）永遠優先於 `extra_settings` 內的值。
