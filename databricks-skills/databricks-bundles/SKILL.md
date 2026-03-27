---
name: databricks-bundles
description: "建立及設定宣告式自動化 Bundle（先前稱為 Asset Bundles），並採用多目標環境部署（CICD）的最佳實務。適用情境：(1) 建立新的 DAB 專案，(2) 新增資源（dashboards、pipelines、jobs、alerts），(3) 設定多目標環境部署，(4) 設定權限，(5) 部署或執行 bundle 資源"
---

# DABs 編寫器

## 概覽
建立用於多目標環境部署（dev/staging/prod）的 DABs。

## 參考檔案

- **[SDP_guidance.md](SDP_guidance.md)** - Spark Declarative Pipeline 設定
- **[alerts_guidance.md](alerts_guidance.md)** - SQL Alert 結構描述（重要 - API 與其他資源不同）

## Bundle 結構

```
project/
├── databricks.yml           # 主要設定 + 目標環境
├── resources/*.yml          # 資源定義
└── src/                     # 程式碼/dashboard 檔案
```

### 主要設定（databricks.yml）

```yaml
bundle:
  name: project-name

include:
  - resources/*.yml

variables:
  catalog:
    default: "default_catalog"
  schema:
    default: "default_schema"
  warehouse_id:
    lookup:
      warehouse: "Shared SQL Warehouse"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      catalog: "dev_catalog"
      schema: "dev_schema"

  prod:
    mode: production
    workspace:
      profile: prod-profile
    variables:
      catalog: "prod_catalog"
      schema: "prod_schema"
```

### Dashboard 資源

**Databricks CLI 0.281.0（2026 年 1 月）起新增對 dataset_catalog 和 dataset_schema 參數的支援**

```yaml
resources:
  dashboards:
    dashboard_name:
      display_name: "[${bundle.target}] Dashboard Title"
      file_path: ../src/dashboards/dashboard.lvdash.json  # 相對於 resources/
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog} # 若 query 未另行指定，dashboard 中所有 datasets 會使用的預設 catalog
      dataset_schema: ${var.schema} # 若 query 未另行指定，dashboard 中所有 datasets 會使用的預設 schema
      permissions:
        - level: CAN_RUN
          group_name: "users"
```

**權限層級**：`CAN_READ`, `CAN_RUN`, `CAN_EDIT`, `CAN_MANAGE`

### Pipelines

**請參閱 [SDP_guidance.md](SDP_guidance.md)** 取得 pipeline 設定

### SQL Alerts

**請參閱 [alerts_guidance.md](alerts_guidance.md)** - Alert 結構描述與其他資源差異很大

### Jobs 資源

```yaml
resources:
  jobs:
    job_name:
      name: "[${bundle.target}] Job Name"
      tasks:
        - task_key: "main_task"
          notebook_task:
            notebook_path: ../src/notebooks/main.py  # 相對於 resources/
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2
      schedule:
        quartz_cron_expression: "0 0 9 * * ?"
        timezone_id: "America/Los_Angeles"
      permissions:
        - level: CAN_VIEW
          group_name: "users"
```

**權限層級**：`CAN_VIEW`, `CAN_MANAGE_RUN`, `CAN_MANAGE`

⚠️ **無法在 jobs 上修改 "admins" 群組權限** - 使用前請先確認自訂群組存在

### 路徑解析

⚠️ **重要**：路徑會依檔案位置而定：

| 檔案位置 | 路徑格式 | 範例 |
|--------------|-------------|---------|
| `resources/*.yml` | `../src/...` | `../src/dashboards/file.json` |
| `databricks.yml` `targets` 區塊 | `./src/...` | `./src/dashboards/file.json` |

**原因**：`resources/` 檔案位於下一層，因此需使用 `../` 回到 bundle root。`databricks.yml` 位於 root，因此使用 `./`

### Volume 資源

```yaml
resources:
  volumes:
    my_volume:
      catalog_name: ${var.catalog}
      schema_name: ${var.schema}
      name: "volume_name"
      volume_type: "MANAGED"
```

⚠️ **Volumes 使用的是 `grants`，不是 `permissions`** - 格式與其他資源不同

### Apps 資源

**Databricks CLI 0.239.0（2025 年 1 月）起新增 Apps 資源支援**

DABs 中的 Apps 設定非常精簡——環境變數定義在來源目錄中的 `app.yaml`，而不是 `databricks.yml`。

#### 從現有應用程式產生 Bundle（建議）

```bash
# 從現有以 CLI 部署的 app 產生 bundle 設定
databricks bundle generate app --existing-app-name my-app --key my_app --profile DEFAULT

# 這會建立：
# - resources/my_app.app.yml（最精簡的資源定義）
# - src/app/（下載的原始碼檔案，包含 app.yaml）
```

#### 手動設定

**resources/my_app.app.yml：**
```yaml
resources:
  apps:
    my_app:
      name: my-app-${bundle.target}        # 依目標環境命名
      description: "My application"
      source_code_path: ../src/app         # 相對於 resources/ 目錄
```

**src/app/app.yaml：**（環境變數寫在這裡）
```yaml
command:
  - "python"
  - "dash_app.py"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "my_schema"
```

**databricks.yml：**
```yaml
bundle:
  name: my-bundle

include:
  - resources/*.yml

variables:
  warehouse_id:
    default: "default-warehouse-id"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      warehouse_id: "dev-warehouse-id"
```

#### 與其他資源的主要差異

| 面向 | Apps | 其他資源 |
|--------|------|-----------------|
| **環境變數** | 位於 `app.yaml`（source dir） | 位於 `databricks.yml` 或資源檔案 |
| **設定** | 精簡（name、description、path） | 完整（tasks、clusters 等） |
| **來源路徑** | 指向 app 目錄 | 指向特定檔案 |

⚠️ **重要**：當原始碼位於 project root（不是 src/app）時，請在資源檔案中使用 `source_code_path: ..`

### 其他資源

DABs 支援 schemas、models、experiments、clusters、warehouses 等資源。使用 `databricks bundle schema` 來檢查結構描述。

**參考**：[DABs 資源類型](https://docs.databricks.com/dev-tools/bundles/resources)

## 常用指令

### 驗證
```bash
databricks bundle validate                    # 驗證預設目標環境
databricks bundle validate -t prod           # 驗證指定目標環境
```

### 部署
```bash
databricks bundle deploy                      # 部署到預設目標環境
databricks bundle deploy -t prod             # 部署到指定目標環境
databricks bundle deploy --auto-approve      # 跳過確認提示
databricks bundle deploy --force             # 強制覆寫遠端變更
```

### 執行資源
```bash
databricks bundle run resource_name          # 執行 pipeline 或 job
databricks bundle run pipeline_name -t prod  # 在指定目標環境中執行

# Apps 部署後需要執行 bundle run 才會啟動
databricks bundle run app_resource_key -t dev    # 啟動/部署該 app
```

### 監控與日誌

**檢視應用程式日誌（適用於 Apps 資源）：**
```bash
# 檢視已部署 app 的日誌
databricks apps logs <app-name> --profile <profile-name>

# 範例：
databricks apps logs my-dash-app-dev -p DEFAULT
databricks apps logs my-streamlit-app-prod -p DEFAULT
```

**日誌會顯示：**
- `[SYSTEM]` - 部署進度、檔案更新、依賴安裝
- `[APP]` - 應用程式輸出（print statements、errors）
- Backend 連線狀態
- 部署 IDs 與時間戳記
- 錯誤的 stack traces

**需要留意的重要日誌模式：**
- ✅ `Deployment successful` - 確認部署已完成
- ✅ `App started successfully` - App 正在執行
- ✅ `Initialized real backend` - Backend 已連線至 Unity Catalog
- ❌ `Error:` - 查看錯誤訊息與 stack traces
- 📝 `Requirements installed` - 依賴已正確載入

### 清理
```bash
databricks bundle destroy -t dev
databricks bundle destroy -t prod --auto-approve
```

---

## 常見問題

| 問題 | 解決方式 |
|-------|----------|
| **App 部署失敗** | 檢查日誌：`databricks apps logs <app-name>` 取得錯誤詳情 |
| **App 無法連線至 Unity Catalog** | 檢查日誌中的 backend 連線錯誤；確認 warehouse ID 與權限 |
| **權限層級錯誤** | Dashboards：CAN_READ/RUN/EDIT/MANAGE；Jobs：CAN_VIEW/MANAGE_RUN/MANAGE |
| **路徑解析失敗** | 在 `resources/*.yml` 使用 `../src/`，在 `databricks.yml` 使用 `./src/` |
| **Catalog 不存在** | 先建立 catalog 或更新變數 |
| **Jobs 上的 "admins" 群組錯誤** | 無法在 jobs 上修改 admins 權限 |
| **Volume 權限** | Volumes 請使用 `grants`，不要用 `permissions` |
| **dashboard 中硬編碼的 catalog** | 使用 dataset_catalog 參數（CLI v0.281.0+）、建立環境專屬檔案，或將 JSON 參數化 |
| **deploy 後 app 未啟動** | Apps 需要 `databricks bundle run <resource_key>` 才會啟動 |
| **App 環境變數未生效** | 環境變數要放在 `app.yaml`（source dir），不是 `databricks.yml` |
| **App 來源路徑錯誤** | 若原始碼位於 project root，請從 resources/ 目錄使用 `../` |
| **除錯任何 app 問題** | 第一步：`databricks apps logs <app-name>`，先查看發生了什麼問題 |

## 核心原則

1. **路徑解析**：在 `resources/*.yml` 使用 `../src/`，在 `databricks.yml` 使用 `./src/`
2. **變數**：將 catalog、schema、warehouse 參數化
3. **模式**：dev/staging 用 `development`，prod 用 `production`
4. **群組**：對所有 workspace 使用者使用 `"users"`
5. **Job 權限**：確認自訂群組存在；無法修改 "admins"

## 相關技能

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - DABs 參照的 pipeline 定義
- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - 透過 DABs 進行 app 部署
- **[databricks-app-python](../databricks-app-python/SKILL.md)** - 透過 DABs 進行 Python app 部署
- **[databricks-config](../databricks-config/SKILL.md)** - CLI/SDK 的 profile 與 authentication 設定
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - 透過 bundles 管理的 job orchestration

## 資源

- [DABs 文件](https://docs.databricks.com/dev-tools/bundles/)
- [Bundle 資源參考](https://docs.databricks.com/dev-tools/bundles/resources)
- [Bundle 設定參考](https://docs.databricks.com/dev-tools/bundles/settings)
- [支援的資源類型](https://docs.databricks.com/aws/en/dev-tools/bundles/resources#resource-types)
- [範例儲存庫 1](https://github.com/Fet-ycliang/databricks-dab-examples)
- [範例儲存庫 2](https://github.com/databricks/bundle-examples)
