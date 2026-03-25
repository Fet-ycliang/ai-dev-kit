"""
Jobs - Run 作業

用於觸發與監控 job runs 的函式。
"""

import time
from typing import Optional, List, Dict, Any

from databricks.sdk.service.jobs import (
    RunLifeCycleState,
    RunResultState,
)

from ..auth import get_workspace_client
from .models import JobRunResult, JobError


# 終止狀態 - run 已結束（成功或失敗）
TERMINAL_STATES = {
    RunLifeCycleState.TERMINATED,
    RunLifeCycleState.SKIPPED,
    RunLifeCycleState.INTERNAL_ERROR,
}

# 成功狀態 - run 已成功完成
SUCCESS_STATES = {
    RunResultState.SUCCESS,
}


def run_job_now(
    job_id: int,
    idempotency_token: Optional[str] = None,
    jar_params: Optional[List[str]] = None,
    notebook_params: Optional[Dict[str, str]] = None,
    python_params: Optional[List[str]] = None,
    spark_submit_params: Optional[List[str]] = None,
    python_named_params: Optional[Dict[str, str]] = None,
    pipeline_params: Optional[Dict[str, Any]] = None,
    sql_params: Optional[Dict[str, str]] = None,
    dbt_commands: Optional[List[str]] = None,
    queue: Optional[Dict[str, Any]] = None,
    **extra_params,
) -> int:
    """
    立即觸發 job run，並回傳 run ID。

    參數:
        job_id: 要執行的 Job ID
        idempotency_token: 用於確保 job run 具冪等性的選用 token
        jar_params: JAR tasks 的參數
        notebook_params: notebook tasks 的參數
        python_params: Python tasks 的參數
        spark_submit_params: spark-submit tasks 的參數
        python_named_params: Python tasks 的具名參數
        pipeline_params: pipeline tasks 的參數
        sql_params: SQL tasks 的參數
        dbt_commands: dbt tasks 的命令
        queue: 此 run 的佇列設定
        **extra_params: 其他 run 參數

    回傳:
        用於追蹤 run 的 Run ID（整數）

    引發:
        JobError: 當 job run 啟動失敗時。

    範例:
        >>> run_id = run_job_now(job_id=123, notebook_params={"env": "prod"})
        >>> print(f"已啟動 run {run_id}")
    """
    w = get_workspace_client()

    try:
        # 為 SDK 呼叫建立 kwargs
        kwargs: Dict[str, Any] = {"job_id": job_id}

        # 加入選用參數
        if idempotency_token:
            kwargs["idempotency_token"] = idempotency_token
        if jar_params:
            kwargs["jar_params"] = jar_params
        if notebook_params:
            kwargs["notebook_params"] = notebook_params
        if python_params:
            kwargs["python_params"] = python_params
        if spark_submit_params:
            kwargs["spark_submit_params"] = spark_submit_params
        if python_named_params:
            kwargs["python_named_params"] = python_named_params
        if pipeline_params:
            kwargs["pipeline_params"] = pipeline_params
        if sql_params:
            kwargs["sql_params"] = sql_params
        if dbt_commands:
            kwargs["dbt_commands"] = dbt_commands
        if queue:
            kwargs["queue"] = queue

        # 加入額外參數
        kwargs.update(extra_params)

        # 觸發 run - SDK 會回傳 Wait[Run] 物件
        response = w.jobs.run_now(**kwargs)

        # 從回應中擷取 run_id
        # Wait 物件具有 response 屬性，其中包含 Run
        if hasattr(response, "response") and hasattr(response.response, "run_id"):
            return response.response.run_id
        elif hasattr(response, "run_id"):
            return response.run_id
        else:
            # 備援：嘗試從 as_dict() 取得
            response_dict = response.as_dict() if hasattr(response, "as_dict") else {}
            if "run_id" in response_dict:
                return response_dict["run_id"]
            raise JobError(f"無法從 job {job_id} 的回應中擷取 run_id", job_id=job_id)

    except Exception as e:
        raise JobError(f"啟動 job {job_id} 的 run 失敗：{str(e)}", job_id=job_id)


def get_run(run_id: int) -> Dict[str, Any]:
    """
    取得詳細的 run 狀態與資訊。

    參數:
        run_id: Run ID

    回傳:
        包含 state、start_time、end_time、tasks 等 run 詳細資訊的字典。

    引發:
        JobError: 當找不到 run 或 API 請求失敗時。
    """
    w = get_workspace_client()

    try:
        run = w.jobs.get_run(run_id=run_id)

        # 將 SDK 物件轉為可供 JSON 序列化的 dict
        return run.as_dict()

    except Exception as e:
        raise JobError(f"取得 run {run_id} 失敗：{str(e)}", run_id=run_id)


def get_run_output(run_id: int) -> Dict[str, Any]:
    """
    取得包含 logs 與結果的 run 輸出。

    參數:
        run_id: Run ID

    回傳:
        包含 logs、錯誤訊息與 task 輸出的 run 輸出字典。

    引發:
        JobError: 當找不到 run 或 API 請求失敗時。
    """
    w = get_workspace_client()

    try:
        output = w.jobs.get_run_output(run_id=run_id)

        # 將 SDK 物件轉為可供 JSON 序列化的 dict
        return output.as_dict()

    except Exception as e:
        raise JobError(f"取得 run {run_id} 的輸出失敗：{str(e)}", run_id=run_id)


def cancel_run(run_id: int) -> None:
    """
    取消執行中的 job。

    參數:
        run_id: 要取消的 Run ID

    引發:
        JobError: 當取消請求失敗時。
    """
    w = get_workspace_client()

    try:
        w.jobs.cancel_run(run_id=run_id)
    except Exception as e:
        raise JobError(f"取消 run {run_id} 失敗：{str(e)}", run_id=run_id)


def list_runs(
    job_id: Optional[int] = None,
    active_only: bool = False,
    completed_only: bool = False,
    limit: int = 25,
    offset: int = 0,
    start_time_from: Optional[int] = None,
    start_time_to: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    列出 job runs，並可選擇套用篩選條件。

    參數:
        job_id: 依特定 Job ID 篩選的選用條件
        active_only: 若為 True，僅回傳進行中的 runs（RUNNING、PENDING 等）
        completed_only: 若為 True，僅回傳已完成的 runs
        limit: 要回傳的 runs 最大數量（預設：25，最大：1000）
        offset: 分頁位移量
        start_time_from: 依開始時間篩選（epoch 毫秒）
        start_time_to: 依開始時間篩選（epoch 毫秒）

    回傳:
        包含 run_id、state、start_time、job_id 等資訊的 run info dict 清單。

    範例:
        >>> # 取得特定 job 最近 10 次 runs
        >>> runs = list_runs(job_id=123, limit=10)
        >>>
        >>> # 取得所有進行中的 runs
        >>> active_runs = list_runs(active_only=True)
    """
    w = get_workspace_client()
    runs = []

    try:
        # SDK list_runs 會回傳 iterator
        for run in w.jobs.list_runs(
            job_id=job_id,
            active_only=active_only,
            completed_only=completed_only,
            limit=limit,
            offset=offset,
            start_time_from=start_time_from,
            start_time_to=start_time_to,
        ):
            run_dict = run.as_dict()
            runs.append(run_dict)

            if len(runs) >= limit:
                break

        return runs

    except Exception as e:
        raise JobError(f"列出 runs 失敗：{str(e)}", job_id=job_id)


def wait_for_run(
    run_id: int,
    timeout: int = 3600,
    poll_interval: int = 10,
) -> JobRunResult:
    """
    等待 job run 完成，並回傳詳細結果。

    參數:
        run_id: 要等待的 Run ID
        timeout: 最長等待時間（秒）（預設：3600 = 1 小時）
        poll_interval: 狀態檢查之間的時間間隔（秒）（預設：10）

    回傳:
        包含詳細 run 狀態的 JobRunResult，其中包含：
        - success: 若 run 成功完成則為 True
        - lifecycle_state: 最終生命週期狀態（TERMINATED、SKIPPED 等）
        - result_state: 最終結果狀態（SUCCESS、FAILED 等）
        - duration_seconds: 總耗時
        - error_message: 若失敗時的錯誤訊息
        - run_page_url: Databricks UI 中該 run 的連結

    引發:
        TimeoutError: 當 run 未在 timeout 內完成時。
        JobError: 當 API 請求失敗時。

    範例:
        >>> run_id = run_job_now(job_id=123)
        >>> result = wait_for_run(run_id=run_id, timeout=1800)
        >>> if result.success:
        ...     print(f"Job 已在 {result.duration_seconds}s 內完成")
        ... else:
        ...     print(f"Job 失敗：{result.error_message}")
    """
    w = get_workspace_client()
    start_time = time.time()

    job_id = None
    job_name = None

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            raise TimeoutError(
                f"Job run {run_id} 未在 {timeout} 秒內完成。"
                f"請在 Databricks UI 檢查 run 狀態，或呼叫 get_run(run_id={run_id})。"
            )

        try:
            run = w.jobs.get_run(run_id=run_id)

            # 在第一次迭代時擷取 job 資訊
            if job_id is None:
                job_id = run.job_id
                # 若可用則取得 job 名稱
                if run.job_id:
                    try:
                        job = w.jobs.get(job_id=run.job_id)
                        job_name = job.settings.name if job.settings else None
                    except Exception:
                        pass  # 忽略取得 job 名稱時發生的錯誤

            # 檢查 run 是否處於終止狀態
            lifecycle_state = run.state.life_cycle_state if run.state else None
            result_state = run.state.result_state if run.state else None
            state_message = run.state.state_message if run.state else None

            if lifecycle_state in TERMINAL_STATES:
                # 計算持續時間
                duration = round(elapsed, 2)
                if run.start_time and run.end_time:
                    # 若可用則使用實際 run 時間（較準確）
                    duration = round((run.end_time - run.start_time) / 1000.0, 2)

                # 判斷是否成功
                success = result_state in SUCCESS_STATES

                # 建立結果
                result = JobRunResult(
                    job_id=job_id or 0,
                    run_id=run_id,
                    job_name=job_name,
                    lifecycle_state=lifecycle_state.value if lifecycle_state else None,
                    result_state=result_state.value if result_state else None,
                    success=success,
                    duration_seconds=duration,
                    start_time=run.start_time,
                    end_time=run.end_time,
                    run_page_url=run.run_page_url,
                    state_message=state_message,
                )

                # 建立訊息
                if success:
                    result.message = f"Job run {run_id} 已於 {duration}s 內成功完成。檢視：{run.run_page_url}"
                else:
                    # 擷取錯誤詳細資訊
                    error_message = (
                        state_message or f"Run 失敗，狀態為：{result_state.value if result_state else 'UNKNOWN'}"
                    )
                    result.error_message = error_message

                    # 嘗試取得輸出以獲得更多詳細資訊
                    try:
                        output = w.jobs.get_run_output(run_id=run_id)
                        if output.error:
                            result.error_message = output.error
                        if output.error_trace:
                            result.errors = [{"trace": output.error_trace}]
                    except Exception:
                        pass  # 忽略取得輸出時發生的錯誤

                    result.message = (
                        f"Job run {run_id} 失敗。"
                        f"State：{lifecycle_state.value if lifecycle_state else 'UNKNOWN'}，"
                        f"Result：{result_state.value if result_state else 'UNKNOWN'}。"
                        f"錯誤：{error_message}。"
                        f"檢視：{run.run_page_url}"
                    )

                return result

        except Exception as e:
            # 若無法取得 run 狀態則引發錯誤
            raise JobError(f"取得 run {run_id} 狀態失敗：{str(e)}", run_id=run_id)

        time.sleep(poll_interval)
