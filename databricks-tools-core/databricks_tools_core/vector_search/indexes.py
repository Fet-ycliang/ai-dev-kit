"""
Vector Search 索引操作

用於建立、管理、查詢及同步 Vector Search 索引的函式。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_vs_index(
    name: str,
    endpoint_name: str,
    primary_key: str,
    index_type: str = "DELTA_SYNC",
    delta_sync_index_spec: Optional[Dict[str, Any]] = None,
    direct_access_index_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    建立 Vector Search 索引。

    對於 DELTA_SYNC 索引，請提供 delta_sync_index_spec，並包含以下其中一項：
    - embedding_source_columns（受管 embeddings）：由 Databricks 計算 embeddings
    - embedding_vector_columns（自行管理）：由您提供預先計算的 embeddings

    對於 DIRECT_ACCESS 索引，請提供 direct_access_index_spec，並包含：
    - embedding_vector_columns 與 schema_json

    參數:
        name: 完整限定索引名稱（catalog.schema.index_name）
        endpoint_name: 用於承載此索引的 Vector Search 端點
        primary_key: 主鍵的欄位名稱
        index_type: "DELTA_SYNC" 或 "DIRECT_ACCESS"
        delta_sync_index_spec: Delta Sync 索引的設定。鍵值包括：
            - source_table (str): 完整限定來源資料表名稱
            - embedding_source_columns (list): 用於受管 embeddings，
              例如 [{"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}]
            - embedding_vector_columns (list): 用於自行管理 embeddings，
              例如 [{"name": "embedding", "embedding_dimension": 768}]
            - pipeline_type (str): "TRIGGERED" 或 "CONTINUOUS"
            - columns_to_sync (list, optional): 要包含的欄位名稱
        direct_access_index_spec: Direct Access 索引的設定。鍵值包括：
            - embedding_vector_columns (list): 例如 [{"name": "embedding", "embedding_dimension": 768}]
            - schema_json (str): JSON schema 字串
            - embedding_model_endpoint_name (str, optional): 用於查詢時 embedding

    回傳:
        包含索引建立詳細資訊的字典

    引發:
        Exception: 當建立失敗時
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.vectorsearch import (
            DeltaSyncVectorIndexSpecRequest,
            DirectAccessVectorIndexSpec,
            EmbeddingSourceColumn,
            EmbeddingVectorColumn,
            VectorIndexType,
        )

        kwargs: Dict[str, Any] = {
            "name": name,
            "endpoint_name": endpoint_name,
            "primary_key": primary_key,
            "index_type": VectorIndexType(index_type),
        }

        if index_type == "DELTA_SYNC" and delta_sync_index_spec:
            spec = delta_sync_index_spec
            ds_kwargs: Dict[str, Any] = {}

            if "source_table" in spec:
                ds_kwargs["source_table"] = spec["source_table"]

            if "pipeline_type" in spec:
                from databricks.sdk.service.vectorsearch import PipelineType

                ds_kwargs["pipeline_type"] = PipelineType(spec["pipeline_type"])

            if "embedding_source_columns" in spec:
                ds_kwargs["embedding_source_columns"] = [
                    EmbeddingSourceColumn(**col) for col in spec["embedding_source_columns"]
                ]

            if "embedding_vector_columns" in spec:
                ds_kwargs["embedding_vector_columns"] = [
                    EmbeddingVectorColumn(**col) for col in spec["embedding_vector_columns"]
                ]

            if "columns_to_sync" in spec:
                ds_kwargs["columns_to_sync"] = spec["columns_to_sync"]

            kwargs["delta_sync_vector_index_spec"] = DeltaSyncVectorIndexSpecRequest(**ds_kwargs)

        elif index_type == "DIRECT_ACCESS" and direct_access_index_spec:
            spec = direct_access_index_spec
            da_kwargs: Dict[str, Any] = {}

            if "embedding_vector_columns" in spec:
                da_kwargs["embedding_vector_columns"] = [
                    EmbeddingVectorColumn(**col) for col in spec["embedding_vector_columns"]
                ]

            if "schema_json" in spec:
                da_kwargs["schema_json"] = spec["schema_json"]

            if "embedding_model_endpoint_name" in spec:
                da_kwargs["embedding_source_columns"] = [
                    EmbeddingSourceColumn(
                        name="__query__",
                        embedding_model_endpoint_name=spec["embedding_model_endpoint_name"],
                    )
                ]

            kwargs["direct_access_index_spec"] = DirectAccessVectorIndexSpec(**da_kwargs)

        client.vector_search_indexes.create_index(**kwargs)

        return {
            "name": name,
            "endpoint_name": endpoint_name,
            "index_type": index_type,
            "primary_key": primary_key,
            "status": "CREATING",
            "message": f"已啟動索引 '{name}' 的建立作業。請使用 get_vs_index('{name}') 檢查狀態。",
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": name,
                "status": "ALREADY_EXISTS",
                "error": f"索引 '{name}' 已存在",
            }
        raise Exception(f"建立 vector search 索引 '{name}' 失敗：{error_msg}")


def get_vs_index(index_name: str) -> Dict[str, Any]:
    """
    取得 Vector Search 索引狀態與詳細資訊。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）

    回傳:
        包含以下內容的字典：
        - name: 索引名稱
        - endpoint_name: 承載索引的端點
        - index_type: DELTA_SYNC 或 DIRECT_ACCESS
        - primary_key: 主鍵欄位
        - state: 索引狀態（ONLINE、PROVISIONING 等）
        - delta_sync_index_spec: 同步設定（若為 DELTA_SYNC）
        - direct_access_index_spec: 設定（若為 DIRECT_ACCESS）

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        index = client.vector_search_indexes.get_index(index_name=index_name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": index_name,
                "state": "NOT_FOUND",
                "error": f"找不到索引 '{index_name}'",
            }
        raise Exception(f"取得 vector search 索引 '{index_name}' 失敗：{error_msg}")

    result: Dict[str, Any] = {
        "name": index.name,
        "endpoint_name": index.endpoint_name,
        "primary_key": index.primary_key,
    }

    if index.index_type:
        result["index_type"] = index.index_type.value

    if index.status:
        if index.status.ready:
            result["state"] = "ONLINE" if index.status.ready else "NOT_READY"
        if index.status.message:
            result["message"] = index.status.message
        if index.status.index_url:
            result["index_url"] = index.status.index_url

    if index.delta_sync_index_spec:
        spec = index.delta_sync_index_spec
        result["delta_sync_index_spec"] = {
            "source_table": spec.source_table,
            "pipeline_type": spec.pipeline_type.value if spec.pipeline_type else None,
        }
        if spec.pipeline_id:
            result["delta_sync_index_spec"]["pipeline_id"] = spec.pipeline_id

    return result


def list_vs_indexes(endpoint_name: str) -> List[Dict[str, Any]]:
    """
    列出端點上的所有 Vector Search 索引。

    參數:
        endpoint_name: 要列出索引的端點名稱

    回傳:
        索引字典列表，包含：
        - name: 索引名稱
        - index_type: DELTA_SYNC 或 DIRECT_ACCESS
        - primary_key: 主鍵欄位
        - state: 索引狀態

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.list_indexes(
            endpoint_name=endpoint_name,
        )
    except Exception as e:
        raise Exception(f"列出端點 '{endpoint_name}' 上的索引失敗：{str(e)}")

    result = []
    # SDK 可能回傳具有 .vector_indexes 的物件，或直接回傳 generator
    if hasattr(response, "vector_indexes") and response.vector_indexes:
        indexes = response.vector_indexes
    elif response:
        indexes = list(response)
    else:
        indexes = []
    for idx in indexes:
        entry: Dict[str, Any] = {
            "name": idx.name,
        }

        # MiniVectorIndex 可能不存在 primary_key
        try:
            if idx.primary_key:
                entry["primary_key"] = idx.primary_key
        except (AttributeError, KeyError):
            pass

        try:
            if idx.index_type:
                entry["index_type"] = idx.index_type.value
        except (AttributeError, KeyError):
            pass

        # MiniVectorIndex（來自 generator 回應）可能不存在 status
        try:
            if idx.status and idx.status.ready is not None:
                entry["state"] = "ONLINE" if idx.status.ready else "NOT_READY"
        except (AttributeError, KeyError):
            pass

        result.append(entry)

    return result


def delete_vs_index(index_name: str) -> Dict[str, Any]:
    """
    刪除 Vector Search 索引。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）

    回傳:
        包含以下內容的字典：
        - name: 索引名稱
        - status: "deleted" 或錯誤資訊

    引發:
        Exception: 當刪除失敗時
    """
    client = get_workspace_client()

    try:
        client.vector_search_indexes.delete_index(index_name=index_name)
        return {
            "name": index_name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": index_name,
                "status": "NOT_FOUND",
                "error": f"找不到索引 '{index_name}'",
            }
        raise Exception(f"刪除 vector search 索引 '{index_name}' 失敗：{error_msg}")


def sync_vs_index(index_name: str) -> Dict[str, Any]:
    """
    觸發 TRIGGERED Delta Sync 索引的同步。

    僅適用於 pipeline_type=TRIGGERED 的 Delta Sync 索引。
    Continuous 索引會自動同步。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）

    回傳:
        包含同步狀態的字典

    引發:
        Exception: 當同步觸發失敗時
    """
    client = get_workspace_client()

    try:
        client.vector_search_indexes.sync_index(index_name=index_name)
        return {
            "name": index_name,
            "status": "SYNC_TRIGGERED",
            "message": f"已觸發索引 '{index_name}' 的同步。請使用 get_vs_index() 檢查進度。",
        }
    except Exception as e:
        raise Exception(f"同步索引 '{index_name}' 失敗：{str(e)}")


def query_vs_index(
    index_name: str,
    columns: List[str],
    query_text: Optional[str] = None,
    query_vector: Optional[List[float]] = None,
    num_results: int = 5,
    filters_json: Optional[str] = None,
    filter_string: Optional[str] = None,
    query_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    查詢 Vector Search 索引中的相似文件。

    請提供 query_text（適用於具有受管或附加 embeddings 的索引）
    或 query_vector（適用於預先計算的查詢 embeddings）其中之一。

    對於篩選條件：
    - Standard 端點使用 filters_json（dict 格式）：'{"category": "ai"}'
    - Storage-Optimized 端點使用 filter_string（SQL 語法）："category = 'ai'"

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）
        columns: 要在結果中回傳的欄位名稱列表
        query_text: 文字查詢（適用於受管／附加 embedding models）
        query_vector: 預先計算的查詢 embedding vector
        num_results: 要回傳的結果數量（預設：5）
        filters_json: Standard 端點使用的篩選條件 JSON 字串
        filter_string: Storage-Optimized 端點使用的類 SQL 篩選條件
        query_type: 搜尋演算法："ANN"（預設）或 "HYBRID"（vector + keyword）

    回傳:
        包含以下內容的字典：
        - columns: 結果中的欄位名稱
        - data: 結果資料列列表（相似度分數會附加在最後一欄）
        - num_results: 回傳的結果數量

    引發:
        Exception: 當查詢失敗時
    """
    client = get_workspace_client()

    kwargs: Dict[str, Any] = {
        "index_name": index_name,
        "columns": columns,
        "num_results": num_results,
    }

    if query_text is not None:
        kwargs["query_text"] = query_text
    elif query_vector is not None:
        kwargs["query_vector"] = query_vector
    else:
        raise ValueError("必須提供 query_text 或 query_vector 其中之一")

    if filters_json is not None:
        # 確保 filters_json 為字串——呼叫端可能會傳入 dict
        if isinstance(filters_json, dict):
            filters_json = json.dumps(filters_json)
        kwargs["filters_json"] = filters_json

    if filter_string is not None:
        kwargs["filter_string"] = filter_string

    if query_type is not None:
        kwargs["query_type"] = query_type

    try:
        response = client.vector_search_indexes.query_index(**kwargs)
    except Exception as e:
        raise Exception(f"查詢索引 '{index_name}' 失敗：{str(e)}")

    result: Dict[str, Any] = {}

    # 從 manifest 取得欄位名稱（SDK 不會直接放在 result 上）
    try:
        if response.manifest and response.manifest.columns:
            result["columns"] = [c.name for c in response.manifest.columns]
    except (AttributeError, KeyError):
        pass

    if response.result:
        if response.result.data_array:
            result["data"] = response.result.data_array
            result["num_results"] = len(response.result.data_array)
        else:
            result["data"] = []
            result["num_results"] = 0

    if response.manifest:
        result["manifest"] = {
            "column_count": response.manifest.column_count,
        }

    return result


def upsert_vs_data(
    index_name: str,
    inputs_json: str,
) -> Dict[str, Any]:
    """
    將資料 upsert 到 Direct Access Vector Search 索引。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）
        inputs_json: 要 upsert 的記錄 JSON 字串。每筆記錄都必須包含
            主鍵與 embedding vector 欄位。
            範例：'[{"id": "1", "text": "hello", "embedding": [0.1, 0.2, ...]}]'

    回傳:
        包含以下內容的字典：
        - name: 索引名稱
        - status: Upsert 結果狀態
        - num_records: 已 upsert 的記錄數

    引發:
        Exception: 當 upsert 失敗時
    """
    client = get_workspace_client()

    try:
        # 確保 inputs_json 為字串——呼叫端可能會傳入 list/dict
        if isinstance(inputs_json, (dict, list)):
            records = inputs_json
            inputs_json = json.dumps(inputs_json)
        else:
            records = json.loads(inputs_json)
        num_records = len(records) if isinstance(records, list) else 1

        response = client.vector_search_indexes.upsert_data_vector_index(
            index_name=index_name,
            inputs_json=inputs_json,
        )

        result: Dict[str, Any] = {
            "name": index_name,
            "status": "SUCCESS",
            "num_records": num_records,
        }

        if response and response.status:
            result["status"] = response.status.value if hasattr(response.status, "value") else str(response.status)

        return result
    except Exception as e:
        raise Exception(f"將資料 upsert 到索引 '{index_name}' 失敗：{str(e)}")


def delete_vs_data(
    index_name: str,
    primary_keys: List[str],
) -> Dict[str, Any]:
    """
    從 Direct Access Vector Search 索引刪除資料。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）
        primary_keys: 要刪除的主鍵值列表

    回傳:
        包含以下內容的字典：
        - name: 索引名稱
        - status: 刪除結果狀態
        - num_deleted: 要求刪除的記錄數

    引發:
        Exception: 當刪除失敗時
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.delete_data_vector_index(
            index_name=index_name,
            primary_keys=primary_keys,
        )

        result: Dict[str, Any] = {
            "name": index_name,
            "status": "SUCCESS",
            "num_deleted": len(primary_keys),
        }

        if response and response.status:
            result["status"] = response.status.value if hasattr(response.status, "value") else str(response.status)

        return result
    except Exception as e:
        raise Exception(f"從索引 '{index_name}' 刪除資料失敗：{str(e)}")


def scan_vs_index(
    index_name: str,
    num_results: int = 100,
) -> Dict[str, Any]:
    """
    掃描 Vector Search 索引以取得所有項目。

    適用於除錯、匯出或驗證索引內容。

    參數:
        index_name: 完整限定索引名稱（catalog.schema.index_name）
        num_results: 要回傳的項目上限（預設：100）

    回傳:
        包含以下內容的字典：
        - columns: 欄位名稱
        - data: 索引項目列表
        - num_results: 回傳的項目數量

    引發:
        Exception: 當掃描失敗時
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.scan_index(
            index_name=index_name,
            num_results=num_results,
        )
    except Exception as e:
        raise Exception(f"掃描索引 '{index_name}' 失敗：{str(e)}")

    result: Dict[str, Any] = {}

    # ScanVectorIndexResponse 具有 .data（項目列表）與 .last_primary_key
    # 而不是像 QueryVectorIndexResponse 那樣使用 .result
    try:
        data = response.data
        if data:
            # data 是由 Struct/dict 物件組成的列表
            if isinstance(data, list) and len(data) > 0:
                # 從第一筆項目擷取欄位名稱
                first = data[0]
                if hasattr(first, "as_dict"):
                    rows = [d.as_dict() for d in data]
                elif isinstance(first, dict):
                    rows = data
                else:
                    rows = data

                if rows and isinstance(rows[0], dict):
                    result["columns"] = list(rows[0].keys())
                result["data"] = rows
                result["num_results"] = len(rows)
            else:
                result["data"] = []
                result["num_results"] = 0
        else:
            result["data"] = []
            result["num_results"] = 0
    except (AttributeError, KeyError):
        # 備援：若 SDK 有變更，嘗試舊版的 .result 模式
        try:
            if response.result:
                if hasattr(response.result, "column_names") and response.result.column_names:
                    result["columns"] = response.result.column_names
                if response.result.data_array:
                    result["data"] = response.result.data_array
                    result["num_results"] = len(response.result.data_array)
                else:
                    result["data"] = []
                    result["num_results"] = 0
        except (AttributeError, KeyError):
            result["data"] = []
            result["num_results"] = 0

    return result
