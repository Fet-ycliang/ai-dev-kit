"""
模型服務端點作業

用於檢查狀態及查詢 Databricks Model Serving endpoints 的函式。
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.service.serving import ChatMessage

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def get_serving_endpoint_status(name: str) -> Dict[str, Any]:
    """
    取得 Model Serving endpoint 的狀態。

    參數:
        name: serving endpoint 的名稱

    回傳:
        包含 endpoint 狀態的字典：
        - name: endpoint 名稱
        - state: 目前狀態 (READY、NOT_READY 等)
        - config_update: 若正在更新時的設定更新狀態
        - creation_timestamp: endpoint 建立時間
        - last_updated_timestamp: endpoint 上次更新時間
        - pending_config: 若有待處理設定更新，其詳細資訊
        - served_entities: 已提供服務的 model/entity 清單及其狀態
        - error: 若 endpoint 處於錯誤狀態時的錯誤訊息

    引發:
        Exception: 若找不到 endpoint 或 API 請求失敗
    """
    client = get_workspace_client()

    try:
        endpoint = client.serving_endpoints.get(name=name)
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"找不到 Endpoint '{name}'",
            }
        raise Exception(f"取得 serving endpoint '{name}' 失敗：{error_msg}")

    # 擷取狀態資訊
    state_info = {}
    if endpoint.state:
        state_info["state"] = endpoint.state.ready.value if endpoint.state.ready else None
        state_info["config_update"] = endpoint.state.config_update.value if endpoint.state.config_update else None

    # 擷取 served entity 狀態
    served_entities = []
    if endpoint.config and endpoint.config.served_entities:
        for entity in endpoint.config.served_entities:
            entity_info = {
                "name": entity.name,
                "entity_name": entity.entity_name,
                "entity_version": entity.entity_version,
            }
            if entity.state:
                entity_info["deployment_state"] = entity.state.deployment.value if entity.state.deployment else None
                entity_info["deployment_state_message"] = entity.state.deployment_state_message
            served_entities.append(entity_info)

    # 檢查是否有待處理的設定
    pending_config = None
    if endpoint.pending_config:
        pending_config = {
            "served_entities": [
                {
                    "name": e.name,
                    "entity_name": e.entity_name,
                    "entity_version": e.entity_version,
                }
                for e in (endpoint.pending_config.served_entities or [])
            ]
        }

    return {
        "name": endpoint.name,
        "state": state_info.get("state"),
        "config_update": state_info.get("config_update"),
        "creation_timestamp": endpoint.creation_timestamp,
        "last_updated_timestamp": endpoint.last_updated_timestamp,
        "served_entities": served_entities,
        "pending_config": pending_config,
        "error": None,
    }


def query_serving_endpoint(
    name: str,
    messages: Optional[List[Dict[str, str]]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    dataframe_records: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    查詢 Model Serving endpoint。

    支援多種輸入格式：
    - messages: 適用於 chat/agent endpoints（OpenAI 相容格式）
    - inputs: 適用於自訂 pyfunc models
    - dataframe_records: 適用於傳統 ML models（pandas DataFrame 格式）

    參數:
        name: serving endpoint 的名稱
        messages: chat 訊息清單 [{"role": "user", "content": "..."}]
        inputs: 自訂 models 的輸入字典
        dataframe_records: DataFrame 輸入的記錄清單
        max_tokens: chat/completion endpoints 的最大 tokens 數
        temperature: chat/completion endpoints 的 temperature

    回傳:
        包含查詢回應的字典：
        - 對 chat endpoints：包含帶有 assistant 回應的 'choices'
        - 對 ML endpoints：包含 'predictions'
        - 若可用則一律包含 'usage'

    引發:
        Exception: 若查詢失敗或 endpoint 尚未就緒
    """
    client = get_workspace_client()

    # 建立查詢 kwargs
    query_kwargs: Dict[str, Any] = {"name": name}

    if messages is not None:
        # Chat/Agent endpoint：將 dict 轉為 ChatMessage objects
        query_kwargs["messages"] = [ChatMessage.from_dict(m) for m in messages]
        if max_tokens is not None:
            query_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            query_kwargs["temperature"] = temperature
    elif inputs is not None:
        # 自訂 pyfunc model：使用 instances 格式
        query_kwargs["instances"] = [inputs]
    elif dataframe_records is not None:
        # 傳統 ML model：DataFrame 格式
        query_kwargs["dataframe_records"] = dataframe_records
    else:
        raise ValueError(
            "必須提供下列其中之一：messages（用於 chat/agents）、"
            "inputs（用於自訂 models），或 dataframe_records（用於 ML models）"
        )

    try:
        response = client.serving_endpoints.query(**query_kwargs)
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg:
            raise Exception(f"找不到 Endpoint '{name}'")
        if "NOT_READY" in error_msg or "PENDING" in error_msg:
            raise Exception(f"Endpoint '{name}' 尚未就緒。請使用 get_serving_endpoint_status('{name}') 檢查狀態")
        raise Exception(f"查詢 endpoint '{name}' 失敗：{error_msg}")

    # 將回應轉為 dict
    result: Dict[str, Any] = {}

    # 處理 chat 回應格式
    if hasattr(response, "choices") and response.choices:
        result["choices"] = [
            {
                "index": c.index,
                "message": {
                    "role": c.message.role if c.message else None,
                    "content": c.message.content if c.message else None,
                },
                "finish_reason": c.finish_reason,
            }
            for c in response.choices
        ]

    # 處理 predictions 格式（ML models）
    if hasattr(response, "predictions") and response.predictions:
        result["predictions"] = response.predictions

    # 處理一般輸出
    if hasattr(response, "output") and response.output:
        result["output"] = response.output

    # 若可用則加入 usage
    if hasattr(response, "usage") and response.usage:
        result["usage"] = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    # 若為空，則以 dict 形式回傳原始回應
    if not result:
        result = response.as_dict() if hasattr(response, "as_dict") else {"raw": str(response)}

    return result


def list_serving_endpoints(limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    """
    列出 workspace 中的 Model Serving endpoints。

    參數:
        limit: 要回傳的最大 endpoint 數量（預設：50）。傳入 None 表示全部。

    回傳:
        endpoint 字典清單，包含下列鍵值：
        - name: endpoint 名稱
        - state: 目前狀態 (READY、NOT_READY 等)
        - creation_timestamp: endpoint 建立時間
        - creator: endpoint 建立者
        - served_entities_count: 已提供服務的 models 數量

    引發:
        Exception: 若 API 請求失敗
    """
    client = get_workspace_client()

    try:
        endpoints = list(client.serving_endpoints.list())
    except Exception as e:
        raise Exception(f"列出 serving endpoints 失敗：{str(e)}")

    result = []
    for ep in endpoints[:limit]:
        state = None
        if ep.state:
            state = ep.state.ready.value if ep.state.ready else None

        served_count = 0
        if ep.config and ep.config.served_entities:
            served_count = len(ep.config.served_entities)

        result.append(
            {
                "name": ep.name,
                "state": state,
                "creation_timestamp": ep.creation_timestamp,
                "creator": ep.creator,
                "served_entities_count": served_count,
            }
        )

    return result
