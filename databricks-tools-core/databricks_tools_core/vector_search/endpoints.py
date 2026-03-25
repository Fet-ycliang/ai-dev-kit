"""
Vector Search 端點操作

用於建立、管理及刪除 Databricks Vector Search 端點的函式。
"""

import logging
from typing import Any, Dict, List

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_vs_endpoint(
    name: str,
    endpoint_type: str = "STANDARD",
) -> Dict[str, Any]:
    """
    建立 Vector Search 端點。

    端點建立為非同步作業。請使用 get_vs_endpoint() 檢查狀態。

    參數:
        name: 端點名稱（在 workspace 內必須唯一）
        endpoint_type: "STANDARD"（低延遲，<100ms）或
            "STORAGE_OPTIMIZED"（具成本效益，約 ~250ms，支援 1B+ vectors）

    回傳:
        包含以下內容的字典：
        - name: 端點名稱
        - endpoint_type: 已建立的端點類型
        - status: 建立狀態

    引發:
        Exception: 當建立失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.vectorsearch import EndpointType

        ep_type = EndpointType(endpoint_type)
        client.vector_search_endpoints.create_endpoint(
            name=name,
            endpoint_type=ep_type,
        )

        return {
            "name": name,
            "endpoint_type": endpoint_type,
            "status": "CREATING",
            "message": f"已啟動端點 '{name}' 的建立作業。請使用 get_vs_endpoint('{name}') 檢查狀態。",
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": name,
                "endpoint_type": endpoint_type,
                "status": "ALREADY_EXISTS",
                "error": f"端點 '{name}' 已存在",
            }
        raise Exception(f"建立 vector search 端點 '{name}' 失敗：{error_msg}")


def get_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    取得 Vector Search 端點狀態與詳細資訊。

    參數:
        name: 端點名稱

    回傳:
        包含以下內容的字典：
        - name: 端點名稱
        - endpoint_type: STANDARD 或 STORAGE_OPTIMIZED
        - state: 目前狀態（例如 ONLINE、PROVISIONING、OFFLINE）
        - creation_timestamp: 端點建立時間
        - last_updated_timestamp: 端點最後更新時間
        - num_indexes: 此端點上的索引數量
        - error: 若端點處於錯誤狀態時的錯誤訊息

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        endpoint = client.vector_search_endpoints.get_endpoint(endpoint_name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"找不到端點 '{name}'",
            }
        raise Exception(f"取得 vector search 端點 '{name}' 失敗：{error_msg}")

    result: Dict[str, Any] = {
        "name": endpoint.name,
        "state": (
            endpoint.endpoint_status.state.value
            if endpoint.endpoint_status and endpoint.endpoint_status.state
            else None
        ),
        "error": None,
    }

    if endpoint.endpoint_type:
        result["endpoint_type"] = endpoint.endpoint_type.value

    if endpoint.endpoint_status and endpoint.endpoint_status.message:
        result["message"] = endpoint.endpoint_status.message

    if endpoint.creation_timestamp:
        result["creation_timestamp"] = endpoint.creation_timestamp

    if endpoint.last_updated_timestamp:
        result["last_updated_timestamp"] = endpoint.last_updated_timestamp

    if endpoint.num_indexes is not None:
        result["num_indexes"] = endpoint.num_indexes

    return result


def list_vs_endpoints() -> List[Dict[str, Any]]:
    """
    列出 workspace 中所有 Vector Search 端點。

    回傳:
        端點字典列表，包含：
        - name: 端點名稱
        - endpoint_type: STANDARD 或 STORAGE_OPTIMIZED
        - state: 目前狀態
        - num_indexes: 端點上的索引數量

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_endpoints.list_endpoints()
    except Exception as e:
        raise Exception(f"列出 vector search 端點失敗：{str(e)}")

    result = []
    # SDK 可能回傳 generator，或是具有 .endpoints 屬性的物件
    if hasattr(response, "endpoints"):
        endpoints = response.endpoints if response.endpoints else []
    else:
        endpoints = list(response) if response else []
    for ep in endpoints:
        entry: Dict[str, Any] = {"name": ep.name}

        if ep.endpoint_type:
            entry["endpoint_type"] = ep.endpoint_type.value

        if ep.endpoint_status and ep.endpoint_status.state:
            entry["state"] = ep.endpoint_status.state.value

        if ep.num_indexes is not None:
            entry["num_indexes"] = ep.num_indexes

        if ep.creation_timestamp:
            entry["creation_timestamp"] = ep.creation_timestamp

        result.append(entry)

    return result


def delete_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    刪除 Vector Search 端點。

    必須先刪除此端點上的所有索引。

    參數:
        name: 要刪除的端點名稱

    回傳:
        包含以下內容的字典：
        - name: 端點名稱
        - status: "deleted" 或錯誤資訊

    引發:
        Exception: 當刪除失敗時
    """
    client = get_workspace_client()

    try:
        client.vector_search_endpoints.delete_endpoint(endpoint_name=name)
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
        raise Exception(f"刪除 vector search 端點 '{name}' 失敗：{error_msg}")
