"""
Spark Declarative Pipelines - 管線管理

用於透過 Databricks Pipelines API 管理 SDP pipeline 生命週期的函式。
所有 pipelines 預設皆使用 Unity Catalog 與 serverless compute。
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from databricks.sdk.service.pipelines import (
    CreatePipelineResponse,
    GetPipelineResponse,
    PipelineLibrary,
    FileLibrary,
    PipelineEvent,
    UpdateInfoState,
    PipelineCluster,
    EventLogSpec,
    Notifications,
    RestartWindow,
    PipelineDeployment,
    Filters,
    PipelinesEnvironment,
    IngestionGatewayPipelineDefinition,
    IngestionPipelineDefinition,
    PipelineTrigger,
    RunAs,
)

from ..auth import get_workspace_client


# 不是有效的 SDK 參數欄位，應予以過濾
_INVALID_SDK_FIELDS = {"pipeline_type"}

# 需要從 dict 轉換為 SDK objects 的欄位
_COMPLEX_FIELD_CONVERTERS = {
    "libraries": lambda items: [PipelineLibrary.from_dict(item) for item in items] if items else None,
    "clusters": lambda items: [PipelineCluster.from_dict(item) for item in items] if items else None,
    "event_log": lambda item: EventLogSpec.from_dict(item) if item else None,
    "notifications": lambda items: [Notifications.from_dict(item) for item in items] if items else None,
    "restart_window": lambda item: RestartWindow.from_dict(item) if item else None,
    "deployment": lambda item: PipelineDeployment.from_dict(item) if item else None,
    "filters": lambda item: Filters.from_dict(item) if item else None,
    "environment": lambda item: PipelinesEnvironment.from_dict(item) if item else None,
    "gateway_definition": lambda item: IngestionGatewayPipelineDefinition.from_dict(item) if item else None,
    "ingestion_definition": lambda item: IngestionPipelineDefinition.from_dict(item) if item else None,
    "trigger": lambda item: PipelineTrigger.from_dict(item) if item else None,
    "run_as": lambda item: RunAs.from_dict(item) if item else None,
}


def _convert_extra_settings(extra_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    將 extra_settings dict 轉換為與 SDK 相容的 kwargs。

    - 過濾無效欄位（例如 pipeline_type）
    - 將巢狀 dict 轉換為 SDK objects（例如 clusters、event_log）
    - 直接傳遞簡單型別

    參數:
        extra_settings: 使用者提供的原始 dict（例如來自 Databricks UI 的 JSON 匯出）

    回傳:
        帶有 SDK 相容值的 Dict
    """
    result = {}

    for key, value in extra_settings.items():
        # 略過無效欄位
        if key in _INVALID_SDK_FIELDS:
            continue

        # 略過 None 值
        if value is None:
            continue

        # 轉換複合欄位
        if key in _COMPLEX_FIELD_CONVERTERS:
            converted = _COMPLEX_FIELD_CONVERTERS[key](value)
            if converted is not None:
                result[key] = converted
        else:
            # 直接傳遞簡單型別（strings、bools，以及如 configuration/tags 的 dicts）
            result[key] = value

    return result


# 終止狀態 - pipeline update 已完成（成功或失敗）
TERMINAL_STATES = {
    UpdateInfoState.COMPLETED,
    UpdateInfoState.FAILED,
    UpdateInfoState.CANCELED,
}

# 執行中狀態 - pipeline update 進行中
RUNNING_STATES = {
    UpdateInfoState.RUNNING,
    UpdateInfoState.INITIALIZING,
    UpdateInfoState.SETTING_UP_TABLES,
    UpdateInfoState.WAITING_FOR_RESOURCES,
    UpdateInfoState.QUEUED,
    UpdateInfoState.RESETTING,
    UpdateInfoState.STOPPING,
    UpdateInfoState.CREATED,
}


def _build_libraries(workspace_file_paths: List[str]) -> List[PipelineLibrary]:
    """根據檔案路徑建立 PipelineLibrary 清單。"""
    return [PipelineLibrary(file=FileLibrary(path=path)) for path in workspace_file_paths]


def _extract_error_summary(events: List[PipelineEvent]) -> List[str]:
    """
    Extract concise error messages from pipeline events.

    Returns a deduplicated list of error messages, trying multiple fallbacks:
    1. First exception message from error.exceptions (most detailed)
    2. Event message (always present, e.g., "Update X is FAILED")

    This is the default for MCP tools since full stack traces are too verbose.
    """
    summaries = []
    for event in events:
        message = None

        # Try to get detailed exception message first
        if event.error and event.error.exceptions:
            for exc in event.error.exceptions:
                if exc.message:
                    short_class = (exc.class_name or "Error").split(".")[-1]
                    message = f"{short_class}: {exc.message}"
                    break  # Take the first exception with a message

        # Fall back to event message if no exception message found
        if not message and event.message:
            message = str(event.message)

        if message:
            summaries.append(message)

    # Deduplicate while preserving order
    seen = set()
    return [s for s in summaries if not (s in seen or seen.add(s))]


def _extract_error_details(events: List[PipelineEvent]) -> List[Dict[str, Any]]:
    """從 pipeline events 擷取錯誤詳細資訊，供 LLM 使用。"""
    errors = []
    for event in events:
        if event.error:
            error_info = {
                "message": str(event.message) if event.message else None,
                "level": event.level.value if event.level else None,
                "timestamp": event.timestamp if event.timestamp else None,
            }
            # 擷取 exception 詳細資訊
            if event.error.exceptions:
                exceptions = []
                for exc in event.error.exceptions:
                    exc_detail = {
                        "class_name": exc.class_name if hasattr(exc, "class_name") else None,
                        "message": exc.message if hasattr(exc, "message") else str(exc),
                    }
                    exceptions.append(exc_detail)
                error_info["exceptions"] = exceptions
            errors.append(error_info)
    return errors


@dataclass
class PipelineRunResult:
    """
    pipeline 作業結果，包含供 LLM 使用的詳細狀態。

    此 dataclass 提供 pipeline 作業的完整資訊，
    以協助 LLM 了解發生了什麼事並採取適當行動。
    """

    # Pipeline 識別資訊
    pipeline_id: str
    pipeline_name: str

    # 作業詳細資訊
    update_id: Optional[str] = None
    state: Optional[str] = None
    success: bool = False
    created: bool = False  # 若 pipeline 為新建則為 True，若為更新則為 False

    # 設定內容（供背景脈絡使用）
    catalog: Optional[str] = None
    schema: Optional[str] = None
    root_path: Optional[str] = None

    # 時間資訊
    duration_seconds: Optional[float] = None

    # 錯誤詳細資訊（若失敗）
    error_message: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # 人類可讀狀態
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可供 JSON 序列化的 dictionary。"""
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "update_id": self.update_id,
            "state": self.state,
            "success": self.success,
            "created": self.created,
            "catalog": self.catalog,
            "schema": self.schema,
            "root_path": self.root_path,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "errors": self.errors,
            "message": self.message,
        }


def find_pipeline_by_name(name: str) -> Optional[str]:
    """
    依名稱尋找 pipeline 並回傳其 ID。

    參數:
        name: 要搜尋的 Pipeline 名稱（完全符合）

    回傳:
        若找到則回傳 Pipeline ID，否則回傳 None
    """
    w = get_workspace_client()

    # 列出 pipelines 並使用名稱篩選，再找出完全符合的項目
    for pipeline in w.pipelines.list_pipelines(filter=f"name LIKE '{name}'"):
        if pipeline.name == name:
            return pipeline.pipeline_id

    return None


def create_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: List[str],
    extra_settings: Optional[Dict[str, Any]] = None,
) -> CreatePipelineResponse:
    """
    建立新的 Spark Declarative Pipeline（預設使用 Unity Catalog 與 serverless）。

    參數:
        name: Pipeline 名稱
        root_path: 原始碼根目錄（會加入 Python sys.path 供 imports 使用）
        catalog: Unity Catalog 名稱
        schema: 輸出資料表的 Schema 名稱
        workspace_file_paths: workspace 檔案路徑清單（原始 .sql 或 .py 檔案）
        extra_settings: 額外 pipeline 設定的選用 dict。這些設定會直接傳遞到
            Databricks SDK pipelines.create() 呼叫。明確傳入的參數
            （name、root_path、catalog、schema、workspace_file_paths）優先。
            支援所有 SDK 選項：clusters、continuous、development、photon、edition、
            channel、event_log、configuration、notifications、tags 等。
            注意：若 extra_settings 中提供 'id'，請改用 update_pipeline。

    回傳:
        含有 pipeline_id 的 CreatePipelineResponse

    引發:
        DatabricksError: 若 pipeline 已存在或 API 請求失敗
    """
    w = get_workspace_client()
    libraries = _build_libraries(workspace_file_paths)

    # 先以轉換後的 extra_settings 作為基礎
    kwargs: Dict[str, Any] = {}
    if extra_settings:
        kwargs = _convert_extra_settings(extra_settings)

    # 明確傳入的參數一律優先
    kwargs["name"] = name
    kwargs["root_path"] = root_path
    kwargs["catalog"] = catalog
    kwargs["schema"] = schema
    kwargs["libraries"] = libraries

    # 僅在 extra_settings 未提供時才設定預設值
    if "continuous" not in kwargs:
        kwargs["continuous"] = False
    if "serverless" not in kwargs:
        kwargs["serverless"] = True

    # 若存在 'id' 則移除 - create 不應帶有 id
    kwargs.pop("id", None)

    return w.pipelines.create(**kwargs)


def get_pipeline(pipeline_id: str) -> GetPipelineResponse:
    """
    取得 pipeline 詳細資料與設定。

    參數:
        pipeline_id: Pipeline ID

    回傳:
        包含完整 pipeline 設定與狀態的 GetPipelineResponse
    """
    w = get_workspace_client()
    return w.pipelines.get(pipeline_id=pipeline_id)


def update_pipeline(
    pipeline_id: str,
    name: Optional[str] = None,
    root_path: Optional[str] = None,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    workspace_file_paths: Optional[List[str]] = None,
    extra_settings: Optional[Dict[str, Any]] = None,
) -> None:
    """
    更新 pipeline 設定。

    參數:
        pipeline_id: Pipeline ID
        name: 新的 Pipeline 名稱
        root_path: 新的原始碼根目錄
        catalog: 新的 catalog 名稱
        schema: 新的 schema 名稱
        workspace_file_paths: 新的檔案路徑清單（原始 .sql 或 .py 檔案）
        extra_settings: 額外 pipeline 設定的選用 dict。這些設定會直接傳遞到
            Databricks SDK pipelines.update() 呼叫。明確傳入的參數
            會優先於 extra_settings 中的值。
            支援所有 SDK 選項：clusters、continuous、development、photon、edition、
            channel、event_log、configuration、notifications、tags 等。
    """
    w = get_workspace_client()

    # 先以轉換後的 extra_settings 作為基礎
    kwargs: Dict[str, Any] = {}
    if extra_settings:
        kwargs = _convert_extra_settings(extra_settings)

    # pipeline_id 為必要欄位，且一定會設定
    kwargs["pipeline_id"] = pipeline_id

    # 明確傳入的參數優先（僅在有提供時）
    if name:
        kwargs["name"] = name
    if root_path:
        kwargs["root_path"] = root_path
    if catalog:
        kwargs["catalog"] = catalog
    if schema:
        kwargs["schema"] = schema
    if workspace_file_paths:
        kwargs["libraries"] = _build_libraries(workspace_file_paths)

    # 確保 kwargs 中的 id 與 pipeline_id 一致（SDK 兩者都會使用）
    if "id" in kwargs and kwargs["id"] != pipeline_id:
        kwargs["id"] = pipeline_id

    w.pipelines.update(**kwargs)


def delete_pipeline(pipeline_id: str) -> None:
    """
    刪除 pipeline。

    參數:
        pipeline_id: Pipeline ID
    """
    w = get_workspace_client()
    w.pipelines.delete(pipeline_id=pipeline_id)


def start_update(
    pipeline_id: str,
    refresh_selection: Optional[List[str]] = None,
    full_refresh: bool = False,
    full_refresh_selection: Optional[List[str]] = None,
    validate_only: bool = False,
    wait: bool = True,
    timeout: int = 300,
    poll_interval: int = 5,
    full_error_details: bool = False,
) -> Dict[str, Any]:
    """
    啟動 pipeline update 或 dry-run 驗證。

    參數:
        pipeline_id: Pipeline ID
        refresh_selection: 要刷新的資料表名稱清單
        full_refresh: 若為 True，會對所有資料表執行完整刷新
        full_refresh_selection: 要執行完整刷新的資料表名稱清單
        validate_only: 若為 True，僅執行 dry-run 驗證，不更新資料
        wait: 若為 True（預設），等待 update 完成並回傳結果；
            若為 False，則只立即回傳 update_id
        timeout: 最長等待時間（秒，預設：300，也就是 5 分鐘）
        poll_interval: 每次狀態檢查之間的間隔秒數（預設：5）
        full_error_details: 若為 True，回傳含 stack trace 的完整錯誤事件；
            若為 False（預設），只回傳精簡錯誤摘要

    回傳:
        字典，包含：
        - update_id: Update ID
        - 若 wait=True，另外還會包含：
            - state: 最終狀態（COMPLETED、FAILED、CANCELED）
            - success: 是否成功完成
            - duration_seconds: 總耗時
            - error_summary: 精簡錯誤訊息清單（預設）
            - errors: 完整錯誤事件（僅當 full_error_details=True 時）
    """
    w = get_workspace_client()

    response = w.pipelines.start_update(
        pipeline_id=pipeline_id,
        refresh_selection=refresh_selection,
        full_refresh=full_refresh,
        full_refresh_selection=full_refresh_selection,
        validate_only=validate_only,
    )

    update_id = response.update_id

    if not wait:
        return {"update_id": update_id}

    # Wait for completion
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            return {
                "update_id": update_id,
                "state": "TIMEOUT",
                "success": False,
                "duration_seconds": round(elapsed, 2),
                "error_summary": [
                    f"Pipeline update did not complete within {timeout} seconds. "
                    f"Check status with get_update(pipeline_id='{pipeline_id}', update_id='{update_id}')."
                ],
            }

        update_response = w.pipelines.get_update(pipeline_id=pipeline_id, update_id=update_id)
        update_info = update_response.update

        if not update_info:
            time.sleep(poll_interval)
            continue

        state = update_info.state

        if state in TERMINAL_STATES:
            result = {
                "update_id": update_id,
                "state": state.value if state else None,
                "success": state == UpdateInfoState.COMPLETED,
                "duration_seconds": round(elapsed, 2),
            }

            # If failed, get error/warning events for this specific update
            if state == UpdateInfoState.FAILED:
                events = get_pipeline_events(
                    pipeline_id=pipeline_id,
                    max_results=10,
                    filter="level in ('ERROR', 'WARN')",
                    update_id=update_id,
                )
                result["error_summary"] = _extract_error_summary(events)
                if full_error_details:
                    result["errors"] = [e.as_dict() if hasattr(e, "as_dict") else vars(e) for e in events]

            return result

        time.sleep(poll_interval)


def get_update(
    pipeline_id: str,
    update_id: str,
    include_config: bool = False,
    full_error_details: bool = False,
) -> Dict[str, Any]:
    """
    取得 pipeline update 的狀態與結果。

    參數:
        pipeline_id: Pipeline ID
        update_id: 來自 start_update 的 Update ID
        include_config: 若為 True，回傳完整 pipeline 設定。
            預設為 False，因為設定內容通常很大且冗長
        full_error_details: 若為 True，回傳含 stack trace 的完整錯誤事件；
            若為 False（預設），只回傳精簡錯誤摘要

    回傳:
        字典，包含：
        - update_id: Update ID
        - state: 目前狀態（QUEUED、RUNNING、COMPLETED、FAILED、CANCELED）
        - success: 成功時為 True、失敗時為 False、執行中為 None
        - cause: 觸發 update 的原因（例如 USER_ACTION、RETRY_ON_FAILURE）
        - creation_time: Update 建立時間
        - error_summary: 精簡錯誤訊息清單（預設）
        - errors: 完整錯誤事件（僅當 full_error_details=True 時）
        - config: Pipeline 設定（僅當 include_config=True 時）
    """
    w = get_workspace_client()
    response = w.pipelines.get_update(pipeline_id=pipeline_id, update_id=update_id)

    update_info = response.update
    if not update_info:
        return {"update_id": update_id, "state": None, "success": None}

    state = update_info.state

    # Determine success status
    success = None
    if state == UpdateInfoState.COMPLETED:
        success = True
    elif state in (UpdateInfoState.FAILED, UpdateInfoState.CANCELED):
        success = False

    result = {
        "update_id": update_id,
        "state": state.value if state else None,
        "success": success,
        "cause": update_info.cause.value if update_info.cause else None,
        "creation_time": update_info.creation_time,
    }

    # If failed, get error/warning events for this specific update
    if state == UpdateInfoState.FAILED:
        events = get_pipeline_events(
            pipeline_id=pipeline_id,
            max_results=10,
            filter="level in ('ERROR', 'WARN')",
            update_id=update_id,
        )
        result["error_summary"] = _extract_error_summary(events)
        if full_error_details:
            result["errors"] = [e.as_dict() if hasattr(e, "as_dict") else vars(e) for e in events]

    # Optionally include config
    if include_config and update_info.config:
        config = update_info.config
        result["config"] = config.as_dict() if hasattr(config, "as_dict") else vars(config)

    return result


def stop_pipeline(pipeline_id: str) -> None:
    """
    停止執行中的 pipeline。

    參數:
        pipeline_id: Pipeline ID
    """
    w = get_workspace_client()
    w.pipelines.stop(pipeline_id=pipeline_id)


def get_pipeline_events(
    pipeline_id: str,
    max_results: int = 5,
    filter: str = "level in ('ERROR', 'WARN')",
    update_id: str = None,
) -> List[PipelineEvent]:
    """
    取得 pipeline events、issues 與錯誤訊息。

    可用於除錯 pipeline 失敗問題。

    參數:
        pipeline_id: Pipeline ID
        max_results: 要回傳的最大 event 數量（預設：5）
        filter: 類 SQL 的篩選條件（預設：`level in ('ERROR', 'WARN')`）。
            例如：
            - `level in ('ERROR', 'WARN')`：錯誤與警告（預設）
            - `level='ERROR'`：僅錯誤
            - `level='INFO'`：資訊事件（例如狀態轉換）
            - None 或空字串：不套用篩選，回傳所有事件
        update_id: 可選的 Update ID 篩選條件。若有提供，
            只回傳該次 update 的事件。可從 get_pipeline().latest_updates
            或 start_update() 取得 update ID

    回傳:
        含有錯誤詳細資訊的 PipelineEvent objects 清單
    """
    w = get_workspace_client()

    effective_filter = filter if filter else None

    # If filtering by update_id, we need to fetch more events and filter client-side
    # since the API doesn't support origin.update_id in filter expressions
    api_max_results = max_results * 10 if update_id else max_results

    events = w.pipelines.list_pipeline_events(
        pipeline_id=pipeline_id,
        max_results=api_max_results,
        filter=effective_filter,
    )

    result = []
    for event in events:
        # Filter by update_id client-side if specified
        if update_id:
            event_update_id = event.origin.update_id if event.origin else None
            if event_update_id != update_id:
                continue

        result.append(event)
        if len(result) >= max_results:
            break

    return result


def wait_for_pipeline_update(
    pipeline_id: str, update_id: str, timeout: int = 1800, poll_interval: int = 5
) -> Dict[str, Any]:
    """
    等待 pipeline update 完成並回傳詳細結果。

    參數:
        pipeline_id: Pipeline ID
        update_id: 來自 start_update 的 Update ID
        timeout: 最長等待時間（秒，預設：30 分鐘）
        poll_interval: 每次檢查狀態的間隔秒數

    回傳:
        包含 update 詳細結果的字典：
        - state: 最終狀態（COMPLETED、FAILED、CANCELED）
        - success: 若成功完成則為 True
        - duration_seconds: 總耗時
        - errors: 若失敗則包含錯誤詳細資訊清單

    引發:
        TimeoutError: 若 pipeline 未在 timeout 內完成
    """
    w = get_workspace_client()
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            raise TimeoutError(
                f"Pipeline update {update_id} 未在 {timeout} 秒內完成。"
                f"請在 UI 中檢查狀態，或呼叫 get_update(pipeline_id='{pipeline_id}', update_id='{update_id}')。"
            )

        response = w.pipelines.get_update(pipeline_id=pipeline_id, update_id=update_id)

        update_info = response.update
        if not update_info:
            time.sleep(poll_interval)
            continue

        state = update_info.state

        if state in TERMINAL_STATES:
            result = {
                "state": state.value if state else None,
                "success": state == UpdateInfoState.COMPLETED,
                "duration_seconds": round(elapsed, 2),
                "update_id": update_id,
                "errors": [],
            }

            # 若失敗，取得詳細錯誤資訊
            if state == UpdateInfoState.FAILED:
                events = get_pipeline_events(pipeline_id, max_results=50)
                result["errors"] = _extract_error_details(events)

            return result

        time.sleep(poll_interval)


def create_or_update_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: List[str],
    start_run: bool = False,
    wait_for_completion: bool = False,
    full_refresh: bool = True,
    timeout: int = 1800,
    extra_settings: Optional[Dict[str, Any]] = None,
) -> PipelineRunResult:
    """
    建立新的 pipeline，或更新同名的既有 pipeline。

    這是管理 pipeline 的主要進入點。它會：
    1. 搜尋是否已有同名 pipeline（或使用 extra_settings 中的 'id'）
    2. 建立新 pipeline，或更新既有 pipeline
    3. 視需要啟動 pipeline run
    4. 視需要等待 run 完成

    預設使用 Unity Catalog 與 serverless compute。

    參數:
        name: Pipeline 名稱（用於查找與建立）
        root_path: 原始碼根目錄（會加入 Python sys.path 供 imports 使用）
        catalog: 輸出資料表使用的 Unity Catalog 名稱
        schema: 輸出資料表使用的 Schema 名稱
        workspace_file_paths: workspace 檔案路徑清單（原始 .sql 或 .py 檔案）
        start_run: 若為 True，會在 create/update 後啟動 pipeline run
        wait_for_completion: 若為 True，會等待 run 完成（需搭配 start_run=True）
        full_refresh: 若為 True，啟動時執行完整刷新
        timeout: 最長等待時間（秒，預設：30 分鐘）
        extra_settings: 額外 pipeline 設定的選用 dict。支援所有 SDK
            選項：clusters、continuous、development、photon、edition、channel、event_log、
            configuration、notifications、tags、serverless 等。
            若提供 'id'，則會改為更新 pipeline 而非建立。
            明確傳入的參數（name、root_path、catalog、schema）優先。

    回傳:
        含有詳細狀態的 PipelineRunResult，包括：
        - pipeline_id、pipeline_name、catalog、schema、root_path
        - created: 若為新建則為 True，若為更新則為 False
        - success: 若所有作業都成功則為 True
        - state: 若有啟動 run，則為最終狀態（COMPLETED、FAILED 等）
        - duration_seconds: 若有等待則為耗時
        - error_message: 若失敗則為摘要錯誤訊息
        - errors: 若失敗則為詳細錯誤清單
        - message: 人類可讀狀態訊息
    """
    # 步驟 1：檢查 pipeline 是否存在（依名稱，或依 extra_settings 中的 id）
    existing_pipeline_id = None

    # 若 extra_settings 包含 'id'，則用於更新
    if extra_settings and extra_settings.get("id"):
        existing_pipeline_id = extra_settings["id"]
    else:
        existing_pipeline_id = find_pipeline_by_name(name)

    created = existing_pipeline_id is None

    # 步驟 2：建立或更新
    try:
        if created:
            response = create_pipeline(
                name=name,
                root_path=root_path,
                catalog=catalog,
                schema=schema,
                workspace_file_paths=workspace_file_paths,
                extra_settings=extra_settings,
            )
            pipeline_id = response.pipeline_id
        else:
            pipeline_id = existing_pipeline_id
            update_pipeline(
                pipeline_id=pipeline_id,
                name=name,
                root_path=root_path,
                catalog=catalog,
                schema=schema,
                workspace_file_paths=workspace_file_paths,
                extra_settings=extra_settings,
            )
    except Exception as e:
        # 回傳供 LLM 使用的詳細錯誤
        return PipelineRunResult(
            pipeline_id=existing_pipeline_id or "unknown",
            pipeline_name=name,
            catalog=catalog,
            schema=schema,
            root_path=root_path,
            success=False,
            created=False,
            error_message=str(e),
            message=f"{'建立' if created else '更新'} pipeline 失敗：{e}",
        )

    # 建立包含背景脈絡的結果
    result = PipelineRunResult(
        pipeline_id=pipeline_id,
        pipeline_name=name,
        catalog=catalog,
        schema=schema,
        root_path=root_path,
        created=created,
        success=True,
        message=f"Pipeline {'建立' if created else '更新'}成功。目標：{catalog}.{schema}",
    )

    # 步驟 3：若有要求則啟動 run
    if start_run:
        try:
            update_id = start_update(
                pipeline_id=pipeline_id,
                full_refresh=full_refresh,
            )
            result.update_id = update_id
            result.message = f"Pipeline {'建立' if created else '更新'}完成並已啟動 run。Update ID: {update_id}"
        except Exception as e:
            result.success = False
            result.error_message = f"Pipeline 已建立，但啟動 run 失敗：{e}"
            result.message = result.error_message
            return result

        # 步驟 4：若有要求則等待完成
        if wait_for_completion:
            try:
                wait_result = wait_for_pipeline_update(
                    pipeline_id=pipeline_id,
                    update_id=update_id,
                    timeout=timeout,
                )
                result.state = wait_result["state"]
                result.success = wait_result["success"]
                result.duration_seconds = wait_result["duration_seconds"]

                if result.success:
                    result.message = (
                        f"Pipeline {'建立' if created else '更新'}完成，並於 {result.duration_seconds}s 內成功執行完畢。"
                        f"資料表已寫入 {catalog}.{schema}"
                    )
                else:
                    result.errors = wait_result.get("errors", [])
                    # 為 LLM 建立具資訊量的錯誤訊息
                    if result.errors:
                        first_error = result.errors[0]
                        error_msg = first_error.get("message", "")
                        if first_error.get("exceptions"):
                            exc = first_error["exceptions"][0]
                            error_msg = exc.get("message", error_msg)
                        result.error_message = error_msg
                    else:
                        result.error_message = f"Pipeline 失敗，狀態為：{result.state}"

                    result.message = (
                        f"Pipeline {'建立' if created else '更新'}完成，但 run 失敗。"
                        f"狀態：{result.state}。"
                        f"錯誤：{result.error_message}。"
                        f"請使用 get_pipeline_events(pipeline_id='{pipeline_id}') 取得完整詳細資料。"
                    )

            except TimeoutError as e:
                result.success = False
                result.state = "TIMEOUT"
                result.error_message = str(e)
                result.message = (
                    f"Pipeline run 在 {timeout}s 後逾時。"
                    f"該 pipeline 可能仍在執行中。"
                    f"請使用 get_update(pipeline_id='{pipeline_id}', update_id='{update_id}') 檢查狀態"
                )

    return result
