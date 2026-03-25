# 通知與監控參考

## 目錄
- [電子郵件通知](#電子郵件通知)
- [Webhook 通知](#webhook-通知)
- [健康狀態規則](#健康狀態規則)
- [逾時設定](#逾時設定)
- [重試設定](#重試設定)
- [執行佇列設定](#執行佇列設定)

---

## 電子郵件通知

針對作業生命週期事件傳送電子郵件警示。

### DABs YAML

```yaml
resources:
  jobs:
    monitored_job:
      name: "受監控作業"
      email_notifications:
        on_start:
          - "team@example.com"
        on_success:
          - "team@example.com"
        on_failure:
          - "oncall@example.com"
          - "team@example.com"
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        no_alert_for_skipped_runs: true
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobEmailNotifications

w = WorkspaceClient()

job = w.jobs.create(
    name="受監控作業",
    email_notifications=JobEmailNotifications(
        on_start=["team@example.com"],
        on_success=["team@example.com"],
        on_failure=["oncall@example.com", "team@example.com"],
        on_duration_warning_threshold_exceeded=["oncall@example.com"],
        no_alert_for_skipped_runs=True
    ),
    tasks=[...]
)
```

### 電子郵件通知事件

| 事件 | 說明 |
|-------|-------------|
| `on_start` | 當作業執行開始時 |
| `on_success` | 當作業執行成功完成時 |
| `on_failure` | 當作業執行失敗時 |
| `on_duration_warning_threshold_exceeded` | 當執行時間超過警告門檻時 |
| `on_streaming_backlog_exceeded` | 當串流積壓超過門檻時 |

### 任務層級電子郵件通知

```yaml
tasks:
  - task_key: critical_task
    email_notifications:
      on_start:
        - "task-owner@example.com"
      on_success:
        - "task-owner@example.com"
      on_failure:
        - "oncall@example.com"
    notebook_task:
      notebook_path: ../src/critical.py
```

---

## Webhook 通知

針對作業事件傳送 HTTP webhook（Slack、PagerDuty、自訂端點）。

### 先建立通知目的地

使用 webhook 之前，請先在 workspace 中建立通知目的地：

**Python SDK：**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.settings import (
    CreateNotificationDestinationRequest,
    DestinationType,
    SlackConfig
)

w = WorkspaceClient()

# 建立 Slack 目的地
destination = w.notification_destinations.create(
    display_name="Slack 警示",
    config=SlackConfig(
        url="https://hooks.slack.com/services/XXX/YYY/ZZZ"
    )
)

print(f"目的地 ID: {destination.id}")
```

### DABs YAML

```yaml
resources:
  jobs:
    webhook_job:
      name: "含 Webhook 的作業"
      webhook_notifications:
        on_start:
          - id: "notification-destination-uuid"
        on_success:
          - id: "notification-destination-uuid"
        on_failure:
          - id: "pagerduty-destination-uuid"
        on_duration_warning_threshold_exceeded:
          - id: "slack-destination-uuid"
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import WebhookNotifications, Webhook

w = WorkspaceClient()

job = w.jobs.create(
    name="含 Webhook 的作業",
    webhook_notifications=WebhookNotifications(
        on_start=[Webhook(id="notification-destination-uuid")],
        on_success=[Webhook(id="notification-destination-uuid")],
        on_failure=[Webhook(id="pagerduty-destination-uuid")],
        on_duration_warning_threshold_exceeded=[Webhook(id="slack-destination-uuid")]
    ),
    tasks=[...]
)
```

### 支援的目的地

| 類型 | 設定 |
|------|---------------|
| Slack | Slack webhook URL |
| Microsoft Teams | Teams webhook URL |
| PagerDuty | PagerDuty 整合金鑰 |
| 一般 Webhook | 自訂 HTTP 端點 |
| 電子郵件 | 電子郵件地址 |

### 任務層級 Webhook

```yaml
tasks:
  - task_key: critical_task
    webhook_notifications:
      on_failure:
        - id: "pagerduty-destination-uuid"
    notebook_task:
      notebook_path: ../src/critical.py
```

---

## 健康狀態規則

監控作業健康狀態指標並觸發警示。

### DABs YAML

```yaml
resources:
  jobs:
    health_monitored:
      name: "健康監控作業"
      health:
        rules:
          - metric: RUN_DURATION_SECONDS
            op: GREATER_THAN
            value: 3600  # 若執行超過 1 小時則警示
          - metric: STREAMING_BACKLOG_BYTES
            op: GREATER_THAN
            value: 1073741824  # 若積壓超過 1GB 則警示
          - metric: STREAMING_BACKLOG_SECONDS
            op: GREATER_THAN
            value: 300  # 若積壓超過 5 分鐘則警示
          - metric: STREAMING_BACKLOG_FILES
            op: GREATER_THAN
            value: 1000  # 若積壓超過 1000 個檔案則警示
          - metric: STREAMING_BACKLOG_RECORDS
            op: GREATER_THAN
            value: 100000  # 若積壓超過 10 萬筆記錄則警示
      email_notifications:
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        on_streaming_backlog_exceeded:
          - "oncall@example.com"
      tasks:
        - task_key: streaming
          notebook_task:
            notebook_path: ../src/streaming.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobsHealthRules, JobsHealthRule, JobsHealthMetric, JobsHealthOperator

w = WorkspaceClient()

job = w.jobs.create(
    name="健康監控作業",
    health=JobsHealthRules(
        rules=[
            JobsHealthRule(
                metric=JobsHealthMetric.RUN_DURATION_SECONDS,
                op=JobsHealthOperator.GREATER_THAN,
                value=3600
            ),
            JobsHealthRule(
                metric=JobsHealthMetric.STREAMING_BACKLOG_BYTES,
                op=JobsHealthOperator.GREATER_THAN,
                value=1073741824
            )
        ]
    ),
    tasks=[...]
)
```

### 健康狀態指標

| 指標 | 說明 | 使用情境 |
|--------|-------------|----------|
| `RUN_DURATION_SECONDS` | 總執行時間 | 偵測卡住／緩慢的作業 |
| `STREAMING_BACKLOG_BYTES` | 未處理資料大小 | 串流延遲 |
| `STREAMING_BACKLOG_SECONDS` | 處理延遲時間 | 串流延遲 |
| `STREAMING_BACKLOG_FILES` | 未處理檔案數量 | 檔案處理延遲 |
| `STREAMING_BACKLOG_RECORDS` | 未處理記錄數量 | 記錄處理延遲 |

### 運算子

| 運算子 | 說明 |
|----------|-------------|
| `GREATER_THAN` | 值超過門檻 |

---

## 逾時設定

### 作業層級逾時

```yaml
resources:
  jobs:
    timeout_job:
      name: "含逾時設定的作業"
      timeout_seconds: 7200  # 最長執行時間 2 小時
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### 任務層級逾時

```yaml
tasks:
  - task_key: long_running
    timeout_seconds: 3600  # 此任務最長 1 小時
    notebook_task:
      notebook_path: ../src/long_running.py
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask

Task(
    task_key="long_running",
    timeout_seconds=3600,
    notebook_task=NotebookTask(
        notebook_path="/Workspace/long_running"
    )
)
```

### 逾時行為

- 值為 `0` = 不設逾時（預設）
- 超過逾時時間時，task/job 會被取消
- 部分結果可能遺失
- 會觸發 `on_failure` 通知

---

## 重試設定

### 任務重試設定

```yaml
tasks:
  - task_key: flaky_task
    max_retries: 3
    min_retry_interval_millis: 30000  # 每次重試間隔 30 秒
    retry_on_timeout: true
    notebook_task:
      notebook_path: ../src/flaky_task.py
```

### Python SDK

```python
from databricks.sdk.service.jobs import Task, NotebookTask

Task(
    task_key="flaky_task",
    max_retries=3,
    min_retry_interval_millis=30000,
    retry_on_timeout=True,
    notebook_task=NotebookTask(
        notebook_path="/Workspace/flaky_task"
    )
)
```

### 重試參數

| 參數 | 預設值 | 說明 |
|-----------|---------|-------------|
| `max_retries` | 0 | 重試次數 |
| `min_retry_interval_millis` | 0 | 兩次重試之間的最短等待時間 |
| `retry_on_timeout` | false | 任務逾時時重試 |

### 重試行為

- 重試僅適用於任務失敗
- 每次重試都是新的任務嘗試
- 每次作業執行都會重新計算重試次數
- 相依任務會等待重試完成

---

## 執行佇列設定

控制並行執行行為。

### 最大並行執行數

```yaml
resources:
  jobs:
    concurrent_job:
      name: "並行作業"
      max_concurrent_runs: 5  # 最多允許 5 個同時執行
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### 佇列設定

```yaml
resources:
  jobs:
    queued_job:
      name: "佇列作業"
      max_concurrent_runs: 1
      queue:
        enabled: true  # 將額外執行排入佇列，而不是略過
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import QueueSettings

w = WorkspaceClient()

job = w.jobs.create(
    name="佇列作業",
    max_concurrent_runs=1,
    queue=QueueSettings(enabled=True),
    tasks=[...]
)
```

### 行為選項

| 設定 | 行為 |
|---------|----------|
| `max_concurrent_runs=1`, `queue.enabled=false` | 若已在執行中則略過 |
| `max_concurrent_runs=1`, `queue.enabled=true` | 將執行排入佇列並依序執行 |
| `max_concurrent_runs=N` | 允許 N 個同時執行 |

---

## 通知設定

微調通知行為。

### 作業層級設定

```yaml
resources:
  jobs:
    notification_settings_job:
      name: "含通知設定的作業"
      notification_settings:
        no_alert_for_skipped_runs: true
        no_alert_for_canceled_runs: true
      email_notifications:
        on_failure:
          - "team@example.com"
      tasks:
        - task_key: main
          notebook_task:
            notebook_path: ../src/main.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import JobNotificationSettings

w = WorkspaceClient()

job = w.jobs.create(
    name="含通知設定的作業",
    notification_settings=JobNotificationSettings(
        no_alert_for_skipped_runs=True,
        no_alert_for_canceled_runs=True
    ),
    tasks=[...]
)
```

### 設定

| 設定 | 預設值 | 說明 |
|---------|---------|-------------|
| `no_alert_for_skipped_runs` | false | 當執行被略過時不發送警示 |
| `no_alert_for_canceled_runs` | false | 當執行被取消時不發送警示 |

---

## 完整監控範例

```yaml
resources:
  jobs:
    fully_monitored:
      name: "[${bundle.target}] 完整監控 ETL"

      # 逾時與重試
      timeout_seconds: 14400  # 最多 4 小時
      max_concurrent_runs: 1
      queue:
        enabled: true

      # 健康狀態監控
      health:
        rules:
          - metric: RUN_DURATION_SECONDS
            op: GREATER_THAN
            value: 7200  # 若超過 2 小時則警告

      # 電子郵件通知
      email_notifications:
        on_start:
          - "team@example.com"
        on_success:
          - "team@example.com"
        on_failure:
          - "oncall@example.com"
          - "team@example.com"
        on_duration_warning_threshold_exceeded:
          - "oncall@example.com"
        no_alert_for_skipped_runs: true

      # Webhook 通知
      webhook_notifications:
        on_failure:
          - id: "pagerduty-destination-uuid"
        on_duration_warning_threshold_exceeded:
          - id: "slack-alerts-uuid"

      # 通知設定
      notification_settings:
        no_alert_for_canceled_runs: true

      tasks:
        - task_key: extract
          max_retries: 2
          min_retry_interval_millis: 60000
          timeout_seconds: 3600
          notebook_task:
            notebook_path: ../src/extract.py

        - task_key: transform
          depends_on:
            - task_key: extract
          max_retries: 1
          timeout_seconds: 3600
          notebook_task:
            notebook_path: ../src/transform.py

        - task_key: load
          depends_on:
            - task_key: transform
          timeout_seconds: 1800
          # 關鍵任務 - 特定通知
          email_notifications:
            on_failure:
              - "data-team-lead@example.com"
          notebook_task:
            notebook_path: ../src/load.py
```
