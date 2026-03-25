---
name: databricks-jobs
description: "針對任何 Databricks Jobs 工作主動使用此技能 - 建立、列表、運行、更新或刪除 Jobs。觸發情況包括：(1) 「建立 Job」或「新增 Job」，(2) 「列表 Jobs」或「顯示 Jobs」，(3) 「運行 Job」或「觸發 Job」，(4) 「Job 狀態」或「檢查 Job」，(5) 以 cron 或觸發器排程，(6) 設定通知/監控，(7) 任何透過 CLI、Python SDK 或 Asset Bundles 涉及 Databricks Jobs 的任務。對於 Job 相關工作，始終優先使用此技能而不是一般 Databricks 知識。"
---

# Databricks Lakeflow Jobs

## 概覽

Databricks Jobs 使用多工作 DAG、彈性觸發器和全面監控來協調資料工作流程。Jobs 支援多樣的工作類型，可透過 Python SDK、CLI 或 Asset Bundles 管理。

## 參考檔案

| 使用案例 | 參考檔案 |
|----------|--------|
| 設定工作類型（Notebook、Python、SQL、dbt 等） | [task-types.md](task-types.md) |
| 設定觸發器和排程 | [triggers-schedules.md](triggers-schedules.md) |
| 設定通知和健康監控 | [notifications-monitoring.md](notifications-monitoring.md) |
| 完整工作範例 | [examples.md](examples.md) |

## 快速入門

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Task, NotebookTask, Source

w = WorkspaceClient()

job = w.jobs.create(
    name="my-etl-job",
    tasks=[
        Task(
            task_key="extract",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/Users/user@example.com/extract",
                source=Source.WORKSPACE
            )
        )
    ]
)
print(f"Created job: {job.job_id}")
```

### CLI

```bash
databricks jobs create --json '{
  "name": "my-etl-job",
  "tasks": [{
    "task_key": "extract",
    "notebook_task": {
      "notebook_path": "/Workspace/Users/user@example.com/extract",
      "source": "WORKSPACE"
    }
  }]
}'
```

### Asset Bundles (DABs)

```yaml
# resources/jobs.yml
resources:
  jobs:
    my_etl_job:
      name: "[${bundle.target}] My ETL Job"
      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/notebooks/extract.py
```

## 核心概念

### 多工作流程

Jobs 支援基於 DAG 的工作依賴關係：

```yaml
tasks:
  - task_key: extract
    notebook_task:
      notebook_path: ../src/extract.py

  - task_key: transform
    depends_on:
      - task_key: extract
    notebook_task:
      notebook_path: ../src/transform.py

  - task_key: load
    depends_on:
      - task_key: transform
    run_if: ALL_SUCCESS  # 僅當所有依賴項成功時才執行
    notebook_task:
      notebook_path: ../src/load.py
```

**run_if 條件：**
- `ALL_SUCCESS`（預設）- 當所有依賴項成功時執行
- `ALL_DONE` - 當所有依賴項完成時執行（成功或失敗）
- `AT_LEAST_ONE_SUCCESS` - 當至少一個依賴項成功時執行
- `NONE_FAILED` - 當沒有依賴項失敗時執行
- `ALL_FAILED` - 當所有依賴項失敗時執行
- `AT_LEAST_ONE_FAILED` - 當至少一個依賴項失敗時執行

### 工作類型摘要

| 工作類型 | 使用案例 | 參考 |
|---------|--------|------|
| `notebook_task` | 執行 Notebook | [task-types.md#notebook-task](task-types.md#notebook-task) |
| `spark_python_task` | 執行 Python 指令碼 | [task-types.md#spark-python-task](task-types.md#spark-python-task) |
| `python_wheel_task` | 執行 Python wheels | [task-types.md#python-wheel-task](task-types.md#python-wheel-task) |
| `sql_task` | 執行 SQL 查詢/檔案 | [task-types.md#sql-task](task-types.md#sql-task) |
| `dbt_task` | 執行 dbt 專案 | [task-types.md#dbt-task](task-types.md#dbt-task) |
| `pipeline_task` | 觸發 DLT/SDP 管道 | [task-types.md#pipeline-task](task-types.md#pipeline-task) |
| `spark_jar_task` | 執行 Spark JAR | [task-types.md#spark-jar-task](task-types.md#spark-jar-task) |
| `run_job_task` | 觸發其他 Jobs | [task-types.md#run-job-task](task-types.md#run-job-task) |
| `for_each_task` | 迴圈遍歷輸入 | [task-types.md#for-each-task](task-types.md#for-each-task) |

### 觸發器類型摘要

| 觸發器類型 | 使用案例 | 參考 |
|----------|--------|------|
| `schedule` | Cron 排程 | [triggers-schedules.md#cron-schedule](triggers-schedules.md#cron-schedule) |
| `trigger.periodic` | 間隔型 | [triggers-schedules.md#periodic-trigger](triggers-schedules.md#periodic-trigger) |
| `trigger.file_arrival` | 檔案到達事件 | [triggers-schedules.md#file-arrival-trigger](triggers-schedules.md#file-arrival-trigger) |
| `trigger.table_update` | 表格變更事件 | [triggers-schedules.md#table-update-trigger](triggers-schedules.md#table-update-trigger) |
| `continuous` | 持續運行的 Jobs | [triggers-schedules.md#continuous-jobs](triggers-schedules.md#continuous-jobs) |

## 計算配置

### Job 叢集（推薦）

定義可重用的叢集配置：

```yaml
job_clusters:
  - job_cluster_key: shared_cluster
    new_cluster:
      spark_version: "15.4.x-scala2.12"
      node_type_id: "i3.xlarge"
      num_workers: 2
      spark_conf:
        spark.speculation: "true"

tasks:
  - task_key: my_task
    job_cluster_key: shared_cluster
    notebook_task:
      notebook_path: ../src/notebook.py
```

### 自動縮放叢集

```yaml
new_cluster:
  spark_version: "15.4.x-scala2.12"
  node_type_id: "i3.xlarge"
  autoscale:
    min_workers: 2
    max_workers: 8
```

### 現有叢集

```yaml
tasks:
  - task_key: my_task
    existing_cluster_id: "0123-456789-abcdef12"
    notebook_task:
      notebook_path: ../src/notebook.py
```

### 無伺服器計算

對於 Notebook 和 Python 工作，省略叢集配置以使用無伺服器：

```yaml
tasks:
  - task_key: serverless_task
    notebook_task:
      notebook_path: ../src/notebook.py
    # 無叢集配置 = 無伺服器
```

## Job 參數

### 定義參數

```yaml
parameters:
  - name: env
    default: "dev"
  - name: date
    default: "{{start_date}}"  # 動態值參考
```

### 在 Notebook 中存取

```python
# 在 Notebook 中
dbutils.widgets.get("env")
dbutils.widgets.get("date")
```

### 傳遞至工作

```yaml
tasks:
  - task_key: my_task
    notebook_task:
      notebook_path: ../src/notebook.py
      base_parameters:
        env: "{{job.parameters.env}}"
        custom_param: "value"
```

## 常見操作

### Python SDK 操作

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# 列表 Jobs
jobs = w.jobs.list()

# 取得 Job 詳細資訊
job = w.jobs.get(job_id=12345)

# 立即運行 Job
run = w.jobs.run_now(job_id=12345)

# 帶參數運行
run = w.jobs.run_now(
    job_id=12345,
    job_parameters={"env": "prod", "date": "2024-01-15"}
)

# 取消執行
w.jobs.cancel_run(run_id=run.run_id)

# 刪除 Job
w.jobs.delete(job_id=12345)
```

### CLI 操作

```bash
# 列表 Jobs
databricks jobs list

# 取得 Job 詳細資訊
databricks jobs get 12345

# 運行 Job
databricks jobs run-now 12345

# 帶參數運行
databricks jobs run-now 12345 --job-params '{"env": "prod"}'

# 取消執行
databricks jobs cancel-run 67890

# 刪除 Job
databricks jobs delete 12345
```

### Asset Bundle 操作

```bash
# 驗證配置
databricks bundle validate

# 部署 Job
databricks bundle deploy

# 運行 Job
databricks bundle run my_job_resource_key

# 部署至特定目標
databricks bundle deploy -t prod

# 銷毀資源
databricks bundle destroy
```

## 權限（DABs）

```yaml
resources:
  jobs:
    my_job:
      name: "My Job"
      permissions:
        - level: CAN_VIEW
          group_name: "data-analysts"
        - level: CAN_MANAGE_RUN
          group_name: "data-engineers"
        - level: CAN_MANAGE
          user_name: "admin@example.com"
```

**權限級別：**
- `CAN_VIEW` - 檢視 Job 和執行歷史
- `CAN_MANAGE_RUN` - 檢視、觸發和取消執行
- `CAN_MANAGE` - 完全控制，包括編輯和刪除

## 常見問題

| 問題 | 解決方案 |
|------|--------|
| Job 叢集啟動緩慢 | 使用 `job_cluster_key` 在工作間重用 Job 叢集 |
| 工作依賴關係不起作用 | 驗證 `task_key` 參考在 `depends_on` 中完全相符 |
| 排程未觸發 | 檢查 `pause_status: UNPAUSED` 和有效的時區 |
| 檔案到達未檢測 | 確保路徑具有適當權限且使用雲端存儲 URL |
| 表格更新觸發器遺漏事件 | 驗證 Unity Catalog 表格和適當的授予權限 |
| 參數不可存取 | 在 Notebook 中使用 `dbutils.widgets.get()` |
| 「admins」群組錯誤 | 無法修改 Jobs 上的 admins 權限 |
| 無伺服器工作失敗 | 確保工作類型支援無伺服器（Notebook、Python） |

## 相關技能

- **[databricks-bundles](../databricks-bundles/SKILL.md)** - 透過 Databricks Asset Bundles 部署 Jobs
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - 設定由 Jobs 觸發的管道

## 資源

- [Jobs API 參考](https://docs.databricks.com/api/workspace/jobs)
- [Jobs 文件](https://docs.databricks.com/en/jobs/index.html)
- [DABs Job 工作類型](https://docs.databricks.com/en/dev-tools/bundles/job-task-types.html)
- [Bundle 範例儲存庫](https://github.com/databricks/bundle-examples)
