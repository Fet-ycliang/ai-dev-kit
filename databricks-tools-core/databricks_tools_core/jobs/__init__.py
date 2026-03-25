"""
Jobs 模組 - Databricks Jobs API

此模組提供用於管理 Databricks jobs 與 job runs 的函式。
預設使用無伺服器運算，以獲得最佳效能與成本效益。

核心作業：
- Job CRUD：create_job、update_job、delete_job、get_job、list_jobs、find_job_by_name
- Run 管理：run_job_now、get_run、get_run_output、cancel_run、list_runs
- Run 監控：wait_for_run（會阻塞直到完成）

資料模型：
- JobRunResult：包含狀態、時間資訊與錯誤資訊的詳細 run 結果
- JobStatus、RunLifecycleState、RunResultState：狀態列舉
- JobError：job 相關錯誤的例外類別

範例：
    >>> from databricks_tools_core.jobs import (
    ...     create_job, run_job_now, wait_for_run
    ... )
    >>>
    >>> # 建立 job
    >>> tasks = [{
    ...     "task_key": "main",
    ...     "notebook_task": {
    ...         "notebook_path": "/Workspace/ETL/process",
    ...         "source": "WORKSPACE"
    ...     }
    ... }]
    >>> job = create_job(name="my_etl_job", tasks=tasks)
    >>>
    >>> # 執行 job 並等待完成
    >>> run_id = run_job_now(job_id=job["job_id"])
    >>> result = wait_for_run(run_id=run_id)
    >>> if result.success:
    ...     print(f"Job 已在 {result.duration_seconds}s 內完成")
"""

# 匯入所有公開函式與類別
from .models import (
    JobStatus,
    RunLifecycleState,
    RunResultState,
    JobRunResult,
    JobError,
)

from .jobs import (
    list_jobs,
    get_job,
    find_job_by_name,
    create_job,
    update_job,
    delete_job,
)

from .runs import (
    run_job_now,
    get_run,
    get_run_output,
    cancel_run,
    list_runs,
    wait_for_run,
)

__all__ = [
    # 模型與列舉
    "JobStatus",
    "RunLifecycleState",
    "RunResultState",
    "JobRunResult",
    "JobError",
    # Job CRUD 作業
    "list_jobs",
    "get_job",
    "find_job_by_name",
    "create_job",
    "update_job",
    "delete_job",
    # Run 作業
    "run_job_now",
    "get_run",
    "get_run_output",
    "cancel_run",
    "list_runs",
    "wait_for_run",
]
