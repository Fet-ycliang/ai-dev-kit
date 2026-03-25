# 任務類型參考

## 目錄
- [Notebook 任務](#notebook-任務)
- [Spark Python 任務](#spark-python-任務)
- [Python Wheel 任務](#python-wheel-任務)
- [SQL 任務](#sql-任務)
- [dbt 任務](#dbt-任務)
- [Pipeline 任務](#pipeline-任務)
- [Spark JAR 任務](#spark-jar-任務)
- [Run Job 任務](#run-job-任務)
- [For Each 任務](#for-each-任務)

---

## Notebook 任務

執行 Databricks notebook。這是最常見的任務類型。

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask, Source

Task(
    task_key="run_notebook",
    notebook_task=NotebookTask(
        notebook_path="/Workspace/Users/user@example.com/etl_notebook",
        source=Source.WORKSPACE,
        base_parameters={
            "env": "prod",
            "date": "2024-01-15"
        }
    )
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_notebook
    notebook_task:
      notebook_path: ../src/notebooks/etl_notebook.py
      source: WORKSPACE
      base_parameters:
        env: "{{job.parameters.env}}"
        date: "{{job.parameters.date}}"
```

### CLI JSON

```json
{
  "task_key": "run_notebook",
  "notebook_task": {
    "notebook_path": "/Workspace/Users/user@example.com/etl_notebook",
    "source": "WORKSPACE",
    "base_parameters": {
      "env": "prod",
      "date": "2024-01-15"
    }
  }
}
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `notebook_path` | 是 | Notebook 的絕對路徑 |
| `source` | 否 | `WORKSPACE`（預設）或 `GIT` |
| `base_parameters` | 否 | 傳遞給 notebook 的鍵值參數 |
| `warehouse_id` | 否 | SQL cell 使用的 SQL warehouse（選用） |

### 在 Notebook 中存取參數

```python
# 取得參數（使用預設值）
env = dbutils.widgets.get("env")

# 或先定義 widget
dbutils.widgets.text("env", "dev")
env = dbutils.widgets.get("env")
```

---

## Spark Python 任務

直接在 Spark 叢集上執行 Python 檔案。

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SparkPythonTask

Task(
    task_key="run_python",
    spark_python_task=SparkPythonTask(
        python_file="/Workspace/Users/user@example.com/scripts/process.py",
        parameters=["--env", "prod", "--date", "2024-01-15"]
    )
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_python
    spark_python_task:
      python_file: ../src/scripts/process.py
      parameters:
        - "--env"
        - "prod"
        - "--date"
        - "2024-01-15"
```

### CLI JSON

```json
{
  "task_key": "run_python",
  "spark_python_task": {
    "python_file": "/Workspace/Users/user@example.com/scripts/process.py",
    "parameters": ["--env", "prod", "--date", "2024-01-15"]
  }
}
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `python_file` | 是 | Python 檔案路徑（workspace、DBFS 或 Unity Catalog volume） |
| `parameters` | 否 | 傳遞給 script 的命令列引數 |
| `source` | 否 | `WORKSPACE`（預設）或 `GIT` |

---

## Python Wheel 任務

執行以 wheel 發佈的 Python 套件。

### Python SDK

```python
from databricks.sdk.service.jobs import Task, PythonWheelTask

Task(
    task_key="run_wheel",
    python_wheel_task=PythonWheelTask(
        package_name="my_package",
        entry_point="main",
        parameters=["--env", "prod"]
    ),
    libraries=[
        {"whl": "/Volumes/catalog/schema/libs/my_package-1.0.0-py3-none-any.whl"}
    ]
)
```

### DABs YAML

```yaml
tasks:
  - task_key: run_wheel
    python_wheel_task:
      package_name: my_package
      entry_point: main
      parameters:
        - "--env"
        - "prod"
    libraries:
      - whl: /Volumes/catalog/schema/libs/my_package-1.0.0-py3-none-any.whl
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `package_name` | 是 | Python 套件名稱 |
| `entry_point` | 是 | 進入點函式或模組 |
| `parameters` | 否 | 命令列引數 |
| `named_parameters` | 否 | 以鍵值組表示的具名參數 |

### 進入點設定

在套件的 `setup.py` 或 `pyproject.toml` 中：

```python
# setup.py
entry_points={
    'console_scripts': [
        'main=my_package.main:run',
    ],
}
```

---

## SQL 任務

執行 SQL 查詢、檔案，或重新整理儀表板／警示。

### 執行 SQL 查詢

```yaml
tasks:
  - task_key: run_query
    sql_task:
      query:
        query_id: "abc123-def456"  # 現有查詢 ID
      warehouse_id: "1234567890abcdef"
```

### 執行 SQL 檔案

```yaml
tasks:
  - task_key: run_sql_file
    sql_task:
      file:
        path: ../src/sql/transform.sql
        source: WORKSPACE
      warehouse_id: "1234567890abcdef"
```

### 重新整理儀表板

```yaml
tasks:
  - task_key: refresh_dashboard
    sql_task:
      dashboard:
        dashboard_id: "dashboard-uuid"
      warehouse_id: "1234567890abcdef"
```

### 重新整理警示

```yaml
tasks:
  - task_key: refresh_alert
    sql_task:
      alert:
        alert_id: "alert-uuid"
      warehouse_id: "1234567890abcdef"
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SqlTask, SqlTaskFile

Task(
    task_key="run_sql",
    sql_task=SqlTask(
        warehouse_id="1234567890abcdef",
        file=SqlTaskFile(
            path="/Workspace/Users/user@example.com/queries/transform.sql",
            source=Source.WORKSPACE
        )
    )
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `warehouse_id` | 是 | SQL warehouse ID |
| `query` | 擇一 | 依 ID 執行現有查詢 |
| `file` | 擇一 | 執行 SQL 檔案 |
| `dashboard` | 擇一 | 重新整理儀表板 |
| `alert` | 擇一 | 重新整理警示 |
| `parameters` | 否 | 查詢參數 |

---

## dbt 任務

搭配 Databricks 執行 dbt 專案。

### DABs YAML

```yaml
tasks:
  - task_key: run_dbt
    dbt_task:
      project_directory: ../src/dbt_project
      commands:
        - "dbt deps"
        - "dbt seed"
        - "dbt run --select tag:daily"
        - "dbt test"
      warehouse_id: "1234567890abcdef"
      catalog: "main"
      schema: "analytics"
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, DbtTask

Task(
    task_key="run_dbt",
    dbt_task=DbtTask(
        project_directory="/Workspace/Users/user@example.com/dbt_project",
        commands=["dbt deps", "dbt run", "dbt test"],
        warehouse_id="1234567890abcdef",
        catalog="main",
        schema="analytics"
    )
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `project_directory` | 是 | dbt 專案路徑 |
| `commands` | 是 | 要執行的 dbt 命令清單 |
| `warehouse_id` | 否 | SQL warehouse（未使用 cluster 時必填） |
| `catalog` | 否 | Unity Catalog catalog |
| `schema` | 否 | 目標 schema |
| `profiles_directory` | 否 | profiles.yml 目錄路徑 |
| `source` | 否 | `WORKSPACE`（預設）或 `GIT` |

---

## Pipeline 任務

觸發 DLT 或 Spark Declarative Pipelines。

### DABs YAML

```yaml
tasks:
  - task_key: run_pipeline
    pipeline_task:
      pipeline_id: "pipeline-uuid-here"
      full_refresh: false
```

### 搭配 Pipeline 資源參照（DABs）

```yaml
resources:
  pipelines:
    my_pipeline:
      name: "我的資料管線"
      # ... pipeline 設定

  jobs:
    my_job:
      name: "協調管線"
      tasks:
        - task_key: run_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.my_pipeline.id}
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, PipelineTask

Task(
    task_key="run_pipeline",
    pipeline_task=PipelineTask(
        pipeline_id="pipeline-uuid-here",
        full_refresh=False
    )
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `pipeline_id` | 是 | 要觸發的 pipeline ID |
| `full_refresh` | 否 | 強制完整重新整理（預設：false） |

---

## Spark JAR 任務

在 Spark 上執行 Scala/Java JAR 檔案。

### DABs YAML

```yaml
tasks:
  - task_key: run_jar
    spark_jar_task:
      main_class_name: "com.example.Main"
      parameters:
        - "--env"
        - "prod"
    libraries:
      - jar: /Volumes/catalog/schema/libs/my-app.jar
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, SparkJarTask

Task(
    task_key="run_jar",
    spark_jar_task=SparkJarTask(
        main_class_name="com.example.Main",
        parameters=["--env", "prod"]
    ),
    libraries=[
        {"jar": "/Volumes/catalog/schema/libs/my-app.jar"}
    ]
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `main_class_name` | 是 | 要執行的主類別 |
| `parameters` | 否 | 命令列引數 |

---

## Run Job 任務

以任務形式觸發另一個 job（job chaining）。

### DABs YAML

```yaml
tasks:
  - task_key: trigger_downstream
    run_job_task:
      job_id: 12345
      job_parameters:
        source_table: "catalog.schema.table"
```

### 搭配 Job 資源參照（DABs）

```yaml
resources:
  jobs:
    upstream_job:
      name: "上游作業"
      tasks:
        - task_key: process
          notebook_task:
            notebook_path: ../src/process.py

    downstream_job:
      name: "下游作業"
      tasks:
        - task_key: trigger_upstream
          run_job_task:
            job_id: ${resources.jobs.upstream_job.id}
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, RunJobTask

Task(
    task_key="trigger_downstream",
    run_job_task=RunJobTask(
        job_id=12345,
        job_parameters={"source_table": "catalog.schema.table"}
    )
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `job_id` | 是 | 要觸發的 job ID |
| `job_parameters` | 否 | 傳遞給被觸發 job 的參數 |

---

## For Each 任務

逐一遍歷集合，並為每個項目執行巢狀任務。

### DABs YAML - 靜態輸入

```yaml
tasks:
  - task_key: process_regions
    for_each_task:
      inputs: '["us-east", "us-west", "eu-west"]'
      task:
        task_key: process_region
        notebook_task:
          notebook_path: ../src/process_region.py
          base_parameters:
            region: "{{input}}"
```

### DABs YAML - 來自前一個任務的動態輸入

```yaml
tasks:
  - task_key: generate_list
    notebook_task:
      notebook_path: ../src/generate_countries.py

  - task_key: process_countries
    depends_on:
      - task_key: generate_list
    for_each_task:
      inputs: "{{tasks.generate_list.values.countries}}"
      task:
        task_key: process_country
        notebook_task:
          notebook_path: ../src/process_country.py
          base_parameters:
            country: "{{input}}"
```

### 產生動態輸入

在產生資料的 notebook 中，使用 task values 回傳值：

```python
# generate_countries.py notebook
countries = ["USA", "UK", "Germany", "France"]

# 為下游 for_each_task 設定 task value
dbutils.jobs.taskValues.set(key="countries", value=countries)
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, ForEachTask, NotebookTask

Task(
    task_key="process_regions",
    for_each_task=ForEachTask(
        inputs='["us-east", "us-west", "eu-west"]',
        task=Task(
            task_key="process_region",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/process_region",
                base_parameters={"region": "{{input}}"}
            )
        )
    )
)
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `inputs` | 是 | JSON 陣列字串或 task value 參照 |
| `task` | 是 | 每個輸入都要執行的巢狀任務 |
| `concurrency` | 否 | 最大平行迭代數（預設：20） |

### 存取目前項目

在巢狀任務內，可存取目前項目：
- 在參數中：`{{input}}`
- 在 notebook 中：使用透過 `base_parameters` 傳入的參數

---

## 任務程式庫

為任務新增程式庫以提供依賴。

### DABs YAML

```yaml
tasks:
  - task_key: with_libraries
    notebook_task:
      notebook_path: ../src/notebook.py
    libraries:
      - pypi:
          package: pandas==2.0.0
      - pypi:
          package: scikit-learn
      - whl: /Volumes/catalog/schema/libs/custom-1.0.0-py3-none-any.whl
      - jar: /Volumes/catalog/schema/libs/custom.jar
      - maven:
          coordinates: "org.apache.spark:spark-avro_2.12:3.5.0"
```

### 程式庫類型

| 類型 | 格式 | 範例 |
|------|--------|---------|
| PyPI | `pypi.package` | `pandas==2.0.0` |
| Wheel | `whl` | `.whl` 檔案路徑 |
| JAR | `jar` | `.jar` 檔案路徑 |
| Maven | `maven.coordinates` | `group:artifact:version` |
| Egg | `egg` | `.egg` 檔案路徑 |

---

## 環境

為 serverless 任務定義可重複使用的 Python 環境，並可加入自訂 pip 依賴套件。

> **重要：** environment `spec` 中的 `client` 欄位為 **必填**。它用來指定基底 serverless 環境版本。請使用 `"4"` 作為值。若缺少此欄位，API 會回傳：
> `"必須為 environment 提供 base environment 或 version"`。
> MCP `manage_jobs` 工具（action="create"）在省略時會自動注入 `client: "4"`，但 CLI/SDK 呼叫必須明確提供。

### DABs YAML

```yaml
environments:
  - environment_key: ml_env
    spec:
      client: "4"
      dependencies:
        - pandas==2.0.0
        - scikit-learn==1.3.0
        - mlflow

tasks:
  - task_key: ml_task
    environment_key: ml_env
    notebook_task:
      notebook_path: ../src/train_model.py
```

### CLI JSON

```json
{
  "environments": [
    {
      "environment_key": "ml_env",
      "spec": {
        "client": "4",
        "dependencies": ["pandas==2.0.0", "scikit-learn==1.3.0"]
      }
    }
  ]
}
```

### Python SDK

```python
from databricks.sdk.service.jobs import JobEnvironment
from databricks.sdk.service.compute import Environment

environments = [
    JobEnvironment(
        environment_key="ml_env",
        spec=Environment(
            client="4",
            dependencies=["pandas==2.0.0", "scikit-learn==1.3.0"]
        )
    )
]
```

### 參數

| 參數 | 必填 | 說明 |
|-----------|----------|-------------|
| `environment_key` | 是 | 任務透過 `environment_key` 參照的唯一識別碼 |
| `spec.client` | 是 | 基底 serverless 環境版本（使用 `"4"`） |
| `spec.dependencies` | 否 | pip 套件清單（例如 `["pandas==2.0.0", "dbldatagen"]`） |
