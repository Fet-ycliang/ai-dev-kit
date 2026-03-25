"""
Jobs - 核心 Job CRUD 作業

使用 Jobs API 管理 Databricks jobs 的函式。
預設使用無伺服器運算，以獲得最佳效能與成本效益。
"""

from typing import Optional, List, Dict, Any

from databricks.sdk.service.jobs import (
    Task,
    JobCluster,
    JobEnvironment,
    JobSettings,
)

from ..auth import get_workspace_client
from .models import JobError


def list_jobs(
    name: Optional[str] = None,
    limit: int = 25,
    expand_tasks: bool = False,
) -> List[Dict[str, Any]]:
    """
    列出 workspace 中的 jobs。

    參數:
        name: 選用的名稱篩選條件（部分比對，不區分大小寫）
        limit: 要回傳的 jobs 最大數量（預設：25）
        expand_tasks: 若為 True，在結果中包含完整 task 定義

    回傳:
        包含 job_id、name、creator、created_time 等資訊的 job info dict 清單。
    """
    w = get_workspace_client()
    jobs = []

    # SDK list() 會回傳 iterator，需要逐一取用
    for job in w.jobs.list(name=name, expand_tasks=expand_tasks, limit=limit):
        job_dict = {
            "job_id": job.job_id,
            "name": job.settings.name if job.settings else None,
            "creator_user_name": job.creator_user_name,
            "created_time": job.created_time,
        }

        # 若有可用資料，加入額外資訊
        if job.settings:
            job_dict["tags"] = job.settings.tags if hasattr(job.settings, "tags") else None
            job_dict["timeout_seconds"] = (
                job.settings.timeout_seconds if hasattr(job.settings, "timeout_seconds") else None
            )
            job_dict["max_concurrent_runs"] = (
                job.settings.max_concurrent_runs if hasattr(job.settings, "max_concurrent_runs") else None
            )

            # 若已展開，包含 tasks
            if expand_tasks and job.settings.tasks:
                job_dict["tasks"] = [task.as_dict() for task in job.settings.tasks]

        jobs.append(job_dict)

        if len(jobs) >= limit:
            break

    return jobs


def get_job(job_id: int) -> Dict[str, Any]:
    """
    取得詳細的 job 設定。

    參數:
        job_id: Job ID

    回傳:
        包含 tasks、clusters、schedule 等完整 job 設定的字典。

    引發:
        JobError: 當找不到 job 或 API 請求失敗時。
    """
    w = get_workspace_client()

    try:
        job = w.jobs.get(job_id=job_id)

        # 將 SDK 物件轉為可供 JSON 序列化的 dict
        return job.as_dict()

    except Exception as e:
        raise JobError(f"取得 job {job_id} 失敗：{str(e)}", job_id=job_id)


def find_job_by_name(name: str) -> Optional[int]:
    """
    依精確名稱尋找 job，並回傳其 ID。

    參數:
        name: 要搜尋的 Job 名稱（精確比對）

    回傳:
        若找到則回傳 Job ID，否則回傳 None。
    """
    w = get_workspace_client()

    # 使用名稱篩選列出 jobs，並找出精確比對項目
    for job in w.jobs.list(name=name, limit=100):
        if job.settings and job.settings.name == name:
            return job.job_id

    return None


def create_job(
    name: str,
    tasks: List[Dict[str, Any]],
    job_clusters: Optional[List[Dict[str, Any]]] = None,
    environments: Optional[List[Dict[str, Any]]] = None,
    tags: Optional[Dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_concurrent_runs: int = 1,
    email_notifications: Optional[Dict[str, Any]] = None,
    webhook_notifications: Optional[Dict[str, Any]] = None,
    notification_settings: Optional[Dict[str, Any]] = None,
    schedule: Optional[Dict[str, Any]] = None,
    queue: Optional[Dict[str, Any]] = None,
    run_as: Optional[Dict[str, Any]] = None,
    git_source: Optional[Dict[str, Any]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    health: Optional[Dict[str, Any]] = None,
    deployment: Optional[Dict[str, Any]] = None,
    **extra_settings,
) -> Dict[str, Any]:
    """
    建立新的 Databricks job，預設使用無伺服器運算。

    參數:
        name: Job 名稱
        tasks: task 定義清單（dict）。每個 task 應包含：
            - task_key: 唯一識別碼
            - description: 選用的 task 說明
            - depends_on: 選用的 task 相依清單
            - [task_type]: 下列其中之一：spark_python_task、notebook_task、python_wheel_task、
                           spark_jar_task, spark_submit_task, pipeline_task, sql_task, dbt_task, run_job_task
            - [compute]: 下列其中之一：new_cluster、existing_cluster_id、job_cluster_key、compute_key
        job_clusters: 選用的 job cluster 定義清單（供非無伺服器 tasks 使用）
        environments: 選用的無伺服器 tasks 環境定義清單。
            每個 dict 應包含：
            - environment_key: 由 tasks 透過 environment_key 參照的唯一識別碼
            - spec: 包含 dependencies（pip 套件清單）且可選擇包含 client（"4"）的 Dict
        tags: 選用的組織用 tags dict
        timeout_seconds: job 層級逾時時間（0 表示不設逾時）
        max_concurrent_runs: 最大並行 runs 數量（預設：1）
        email_notifications: Email 通知設定
        webhook_notifications: Webhook 通知設定
        notification_settings: run 生命週期事件的通知設定
        schedule: 選用的排程設定
        queue: 選用的 job 佇列設定
        run_as: 選用的 run-as 使用者／service principal
        git_source: 選用的 Git 來源設定
        parameters: 選用的 job 參數
        health: 選用的健康狀態監控規則
        deployment: 選用的部署設定
        **extra_settings: 直接傳給 SDK 的其他 job 設定

    回傳:
        包含 job_id 與其他建立中繼資料的字典。

    引發:
        JobError: 當 job 建立失敗時。

    範例:
        >>> tasks = [
        ...     {
        ...         "task_key": "data_ingestion",
        ...         "notebook_task": {
        ...             "notebook_path": "/Workspace/ETL/ingest",
        ...             "source": "WORKSPACE"
        ...         }
        ...     }
        ... ]
        >>> job = create_job(name="my_etl_job", tasks=tasks)
        >>> print(job["job_id"])
    """
    w = get_workspace_client()

    try:
        # 為 SDK 呼叫建立 kwargs
        kwargs: Dict[str, Any] = {
            "name": name,
            "max_concurrent_runs": max_concurrent_runs,
        }

        # 將 tasks 從 dict 轉為 SDK Task 物件
        if tasks:
            kwargs["tasks"] = [Task.from_dict(task) for task in tasks]

        # 若有提供，轉換 job_clusters
        if job_clusters:
            kwargs["job_clusters"] = [JobCluster.from_dict(jc) for jc in job_clusters]

        # 若有提供，轉換 environments（供有相依性的無伺服器 tasks 使用）
        # 若 spec 缺少 "client": "4"，自動注入以避免 API 錯誤：
        # "Either base environment or version must be provided for environment"
        if environments:
            for env in environments:
                if "spec" in env and "client" not in env["spec"]:
                    env["spec"]["client"] = "4"
            kwargs["environments"] = [JobEnvironment.from_dict(env) for env in environments]

        # 加入選用參數
        if tags:
            kwargs["tags"] = tags
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        if email_notifications:
            kwargs["email_notifications"] = email_notifications
        if webhook_notifications:
            kwargs["webhook_notifications"] = webhook_notifications
        if notification_settings:
            kwargs["notification_settings"] = notification_settings
        if schedule:
            kwargs["schedule"] = schedule
        if queue:
            kwargs["queue"] = queue
        if run_as:
            kwargs["run_as"] = run_as
        if git_source:
            kwargs["git_source"] = git_source
        if parameters:
            kwargs["parameters"] = parameters
        if health:
            kwargs["health"] = health
        if deployment:
            kwargs["deployment"] = deployment

        # 加入其他額外設定
        kwargs.update(extra_settings)

        # 建立 job
        response = w.jobs.create(**kwargs)

        # 將回應轉為 dict
        return response.as_dict()

    except Exception as e:
        raise JobError(f"建立 job '{name}' 失敗：{str(e)}")


def update_job(
    job_id: int,
    name: Optional[str] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    job_clusters: Optional[List[Dict[str, Any]]] = None,
    environments: Optional[List[Dict[str, Any]]] = None,
    tags: Optional[Dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_concurrent_runs: Optional[int] = None,
    email_notifications: Optional[Dict[str, Any]] = None,
    webhook_notifications: Optional[Dict[str, Any]] = None,
    notification_settings: Optional[Dict[str, Any]] = None,
    schedule: Optional[Dict[str, Any]] = None,
    queue: Optional[Dict[str, Any]] = None,
    run_as: Optional[Dict[str, Any]] = None,
    git_source: Optional[Dict[str, Any]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    health: Optional[Dict[str, Any]] = None,
    deployment: Optional[Dict[str, Any]] = None,
    **extra_settings,
) -> None:
    """
    更新現有 job 的設定。

    只會更新有提供的參數。若要移除欄位，請明確將其設為 None
    或空值。

    參數:
        job_id: 要更新的 Job ID
        name: 新的 Job 名稱
        tasks: 新的 task 定義
        job_clusters: 新的 job cluster 定義
        environments: 供有相依性的無伺服器 tasks 使用的新環境定義
        tags: 新的 tags（會取代既有值）
        timeout_seconds: 新的逾時時間
        max_concurrent_runs: 新的最大並行 runs 數量
        email_notifications: 新的 Email 通知
        webhook_notifications: 新的 Webhook 通知
        notification_settings: 新的通知設定
        schedule: 新的排程設定
        queue: 新的佇列設定
        run_as: 新的 run-as 設定
        git_source: 新的 Git 來源設定
        parameters: 新的 job 參數
        health: 新的健康狀態監控規則
        deployment: 新的部署設定
        **extra_settings: 其他 job 設定

    引發:
        JobError: 當 job 更新失敗時。
    """
    w = get_workspace_client()

    try:
        # 為 SDK 呼叫建立 kwargs - 必須包含完整的 new_settings
        # 先取得目前的 job 設定
        current_job = w.jobs.get(job_id=job_id)

        # 以目前設定的 dict 作為起點
        new_settings_dict = current_job.settings.as_dict() if current_job.settings else {}

        # 以提供的參數更新
        if name is not None:
            new_settings_dict["name"] = name
        if tasks is not None:
            new_settings_dict["tasks"] = tasks
        if job_clusters is not None:
            new_settings_dict["job_clusters"] = job_clusters
        if environments is not None:
            new_settings_dict["environments"] = environments
        if tags is not None:
            new_settings_dict["tags"] = tags
        if timeout_seconds is not None:
            new_settings_dict["timeout_seconds"] = timeout_seconds
        if max_concurrent_runs is not None:
            new_settings_dict["max_concurrent_runs"] = max_concurrent_runs
        if email_notifications is not None:
            new_settings_dict["email_notifications"] = email_notifications
        if webhook_notifications is not None:
            new_settings_dict["webhook_notifications"] = webhook_notifications
        if notification_settings is not None:
            new_settings_dict["notification_settings"] = notification_settings
        if schedule is not None:
            new_settings_dict["schedule"] = schedule
        if queue is not None:
            new_settings_dict["queue"] = queue
        if run_as is not None:
            new_settings_dict["run_as"] = run_as
        if git_source is not None:
            new_settings_dict["git_source"] = git_source
        if parameters is not None:
            new_settings_dict["parameters"] = parameters
        if health is not None:
            new_settings_dict["health"] = health
        if deployment is not None:
            new_settings_dict["deployment"] = deployment

        # 套用額外設定
        new_settings_dict.update(extra_settings)

        # 轉為 JobSettings 物件
        new_settings = JobSettings.from_dict(new_settings_dict)

        # 更新 job
        w.jobs.update(job_id=job_id, new_settings=new_settings)

    except Exception as e:
        raise JobError(f"更新 job {job_id} 失敗：{str(e)}", job_id=job_id)


def delete_job(job_id: int) -> None:
    """
    刪除 job。

    參數:
        job_id: 要刪除的 Job ID

    引發:
        JobError: 當 job 刪除失敗時。
    """
    w = get_workspace_client()

    try:
        w.jobs.delete(job_id=job_id)
    except Exception as e:
        raise JobError(f"刪除 job {job_id} 失敗：{str(e)}", job_id=job_id)
