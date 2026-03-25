"""
Lakebase Autoscaling Compute（端點）操作

用於在 Lakebase Autoscaling 分支中建立、管理與刪除 compute 端點的函式。
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_endpoint(
    branch_name: str,
    endpoint_id: str,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    在分支上建立 compute 端點。

    參數:
        branch_name: 分支資源名稱
            （例如："projects/my-app/branches/production"）
        endpoint_id: 端點識別子（1-63 個字元，限小寫字母、
            數字與連字號）
        endpoint_type: 端點類型："ENDPOINT_TYPE_READ_WRITE" 或
            "ENDPOINT_TYPE_READ_ONLY"。預設："ENDPOINT_TYPE_READ_WRITE"
        autoscaling_limit_min_cu: 最小 compute units（0.5-32）
        autoscaling_limit_max_cu: 最大 compute units（0.5-112）
        scale_to_zero_seconds: 暫停前的閒置逾時秒數。
            設為 0 可停用 scale-to-zero。

    回傳:
        包含以下欄位的字典：
        - name: 端點資源名稱
        - host: 連線主機名稱
        - status: 建立狀態

    引發:
        Exception: 當建立失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

        ep_type = EndpointType(endpoint_type)

        spec_kwargs: Dict[str, Any] = {
            "endpoint_type": ep_type,
        }

        if autoscaling_limit_min_cu is not None:
            spec_kwargs["autoscaling_limit_min_cu"] = autoscaling_limit_min_cu
        if autoscaling_limit_max_cu is not None:
            spec_kwargs["autoscaling_limit_max_cu"] = autoscaling_limit_max_cu
        if scale_to_zero_seconds is not None:
            from databricks.sdk.service.postgres import Duration

            spec_kwargs["suspend_timeout_duration"] = Duration(seconds=scale_to_zero_seconds)

        operation = client.postgres.create_endpoint(
            parent=branch_name,
            endpoint=Endpoint(spec=EndpointSpec(**spec_kwargs)),
            endpoint_id=endpoint_id,
        )
        result_ep = operation.wait()

        result: Dict[str, Any] = {
            "name": result_ep.name,
            "status": "CREATED",
        }

        if result_ep.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("endpoint_type", "endpoint_type", str),
                ("autoscaling_limit_min_cu", "min_cu", None),
                ("autoscaling_limit_max_cu", "max_cu", None),
            ]:
                try:
                    val = getattr(result_ep.status, attr)
                    if val is not None:
                        result[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

            try:
                if result_ep.status.hosts and result_ep.status.hosts.host:
                    result["host"] = result_ep.status.hosts.host
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"{branch_name}/endpoints/{endpoint_id}",
                "status": "ALREADY_EXISTS",
                "error": f"分支上已存在端點 '{endpoint_id}'",
            }
        raise Exception(f"建立端點 '{endpoint_id}' 失敗：{error_msg}")


def get_endpoint(name: str) -> Dict[str, Any]:
    """
    取得 Lakebase Autoscaling 端點詳細資料。

    參數:
        name: 端點資源名稱
            （例如："projects/my-app/branches/production/endpoints/ep-primary"）

    回傳:
        包含以下欄位的字典：
        - name: 端點資源名稱
        - state: 目前狀態（ACTIVE、SUSPENDED 等）
        - endpoint_type: READ_WRITE 或 READ_ONLY
        - host: 連線主機名稱
        - min_cu: 最小 compute units
        - max_cu: 最大 compute units

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        endpoint = client.postgres.get_endpoint(name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"找不到端點 '{name}'",
            }
        raise Exception(f"取得端點 '{name}' 失敗：{error_msg}")

    result: Dict[str, Any] = {"name": endpoint.name}

    if endpoint.status:
        for attr, key, transform in [
            ("current_state", "state", str),
            ("endpoint_type", "endpoint_type", str),
            ("autoscaling_limit_min_cu", "min_cu", None),
            ("autoscaling_limit_max_cu", "max_cu", None),
        ]:
            try:
                val = getattr(endpoint.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

        try:
            if endpoint.status.hosts and endpoint.status.hosts.host:
                result["host"] = endpoint.status.hosts.host
        except (KeyError, AttributeError):
            pass

    return result


def list_endpoints(branch_name: str) -> List[Dict[str, Any]]:
    """
    列出分支上的所有端點。

    參數:
        branch_name: 分支資源名稱
            （例如："projects/my-app/branches/production"）

    回傳:
        包含 name、state、type 與 CU 設定的端點字典清單。

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        response = client.postgres.list_endpoints(parent=branch_name)
    except Exception as e:
        raise Exception(f"列出 '{branch_name}' 的端點失敗：{str(e)}")

    result = []
    endpoints = list(response) if response else []
    for ep in endpoints:
        entry: Dict[str, Any] = {"name": ep.name}

        if ep.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("endpoint_type", "endpoint_type", str),
                ("autoscaling_limit_min_cu", "min_cu", None),
                ("autoscaling_limit_max_cu", "max_cu", None),
            ]:
                try:
                    val = getattr(ep.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

            try:
                if ep.status.hosts and ep.status.hosts.host:
                    entry["host"] = ep.status.hosts.host
            except (KeyError, AttributeError):
                pass

        result.append(entry)

    return result


def update_endpoint(
    name: str,
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    更新 Lakebase Autoscaling 端點（調整大小或設定 scale-to-zero）。

    參數:
        name: 端點資源名稱
            （例如："projects/my-app/branches/production/endpoints/ep-primary"）
        autoscaling_limit_min_cu: 新的最小 compute units（0.5-32）
        autoscaling_limit_max_cu: 新的最大 compute units（0.5-112）
        scale_to_zero_seconds: 新的閒置逾時秒數。設為 0 可停用。

    回傳:
        包含更新後端點詳細資料的字典

    引發:
        Exception: 當更新失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType, FieldMask

        spec_kwargs: Dict[str, Any] = {}
        update_fields: list[str] = []

        if autoscaling_limit_min_cu is not None:
            spec_kwargs["autoscaling_limit_min_cu"] = autoscaling_limit_min_cu
            update_fields.append("spec.autoscaling_limit_min_cu")

        if autoscaling_limit_max_cu is not None:
            spec_kwargs["autoscaling_limit_max_cu"] = autoscaling_limit_max_cu
            update_fields.append("spec.autoscaling_limit_max_cu")

        if scale_to_zero_seconds is not None:
            from databricks.sdk.service.postgres import Duration

            spec_kwargs["suspend_timeout_duration"] = Duration(seconds=scale_to_zero_seconds)
            update_fields.append("spec.suspend_timeout_duration")

        if not update_fields:
            return {
                "name": name,
                "status": "NO_CHANGES",
                "error": "未指定要更新的欄位",
            }

        # EndpointSpec 需要 endpoint_type，因此先從目前的端點取得
        existing_ep = client.postgres.get_endpoint(name=name)
        ep_type = (
            existing_ep.spec.endpoint_type
            if existing_ep.spec and existing_ep.spec.endpoint_type
            else EndpointType.ENDPOINT_TYPE_READ_WRITE
        )
        spec_kwargs["endpoint_type"] = ep_type

        operation = client.postgres.update_endpoint(
            name=name,
            endpoint=Endpoint(
                name=name,
                spec=EndpointSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_ep = operation.wait()

        result: Dict[str, Any] = {
            "name": name,
            "status": "UPDATED",
        }

        if autoscaling_limit_min_cu is not None:
            result["min_cu"] = autoscaling_limit_min_cu
        if autoscaling_limit_max_cu is not None:
            result["max_cu"] = autoscaling_limit_max_cu

        if result_ep and result_ep.status:
            try:
                if result_ep.status.current_state:
                    result["state"] = str(result_ep.status.current_state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"更新端點 '{name}' 失敗：{str(e)}")


def delete_endpoint(name: str, max_retries: int = 6, retry_delay: int = 10) -> Dict[str, Any]:
    """
    刪除 Lakebase Autoscaling 端點。

    注意：
        遇到 ``Aborted`` 錯誤時會重試（代表 reconciliation 進行中）。

    參數:
        name: 端點資源名稱
            （例如："projects/my-app/branches/production/endpoints/ep-primary"）
        max_retries: 暫時性錯誤的最大重試次數。
        retry_delay: 每次重試之間等待的秒數。

    回傳:
        包含以下欄位的字典：
        - name: 端點資源名稱
        - status: "deleted" 或錯誤資訊

    引發:
        Exception: 當重試後仍刪除失敗時
    """
    import time

    client = get_workspace_client()

    for attempt in range(max_retries + 1):
        try:
            operation = client.postgres.delete_endpoint(name=name)
            operation.wait()
            return {
                "name": name,
                "status": "deleted",
            }
        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
                return {
                    "name": name,
                    "status": "NOT_FOUND",
                    "error": f"找不到端點 '{name}'",
                }
            if ("reconciliation" in error_msg.lower() or "aborted" in error_msg.lower()) and attempt < max_retries:
                logger.info(
                    f"端點 reconciliation 進行中，將在 {retry_delay} 秒後重試 "
                    f"（第 {attempt + 1}/{max_retries} 次）"
                )
                time.sleep(retry_delay)
                continue
            raise Exception(f"刪除端點 '{name}' 失敗：{error_msg}")
