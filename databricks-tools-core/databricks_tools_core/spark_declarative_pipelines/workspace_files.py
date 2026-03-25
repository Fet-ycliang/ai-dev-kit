"""
Spark Declarative Pipelines - Workspace 檔案作業

用於管理 SDP pipelines 的 workspace 檔案與目錄的函式。
"""

import base64
from typing import List
from databricks.sdk.service.workspace import ObjectInfo, Language, ImportFormat, ExportFormat

from ..auth import get_workspace_client


def list_files(path: str) -> List[ObjectInfo]:
    """
    列出 workspace 路徑中的檔案與目錄。

    參數:
        path: 要列出的 Workspace 路徑

    回傳:
        包含檔案/目錄中繼資料的 ObjectInfo objects 清單：
        - path: 完整 workspace 路徑
        - object_type: DIRECTORY、NOTEBOOK、FILE、LIBRARY 或 REPO
        - language: 適用於 notebooks (PYTHON、SQL、SCALA、R)
        - object_id: 唯一識別碼

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()
    return list(w.workspace.list(path=path))


def get_file_status(path: str) -> ObjectInfo:
    """
    取得檔案或目錄的中繼資料。

    參數:
        path: Workspace 路徑

    回傳:
        包含中繼資料的 ObjectInfo object：
        - path: 完整 workspace 路徑
        - object_type: DIRECTORY、NOTEBOOK、FILE、LIBRARY 或 REPO
        - language: 適用於 notebooks (PYTHON、SQL、SCALA、R)
        - object_id: 唯一識別碼
        - size: 檔案大小（位元組，僅適用於檔案）
        - created_at: 建立時間戳記
        - modified_at: 上次修改時間戳記

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()
    return w.workspace.get_status(path=path)


def read_file(path: str) -> str:
    """
    讀取 workspace 檔案內容。

    參數:
        path: Workspace 檔案路徑

    回傳:
        解碼後的字串檔案內容

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()
    response = w.workspace.export(path=path, format=ExportFormat.SOURCE)

    # SDK 會回傳帶有 .content 欄位的 ExportResponse（base64 編碼）
    return base64.b64decode(response.content).decode("utf-8")


def write_file(path: str, content: str, language: str = "PYTHON", overwrite: bool = True) -> None:
    """
    寫入或更新 workspace 檔案。

    參數:
        path: Workspace 檔案路徑
        content: 字串形式的檔案內容
        language: PYTHON、SQL、SCALA 或 R
        overwrite: 若為 True，會取代現有檔案

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()

    # 將 language 字串轉為 enum
    lang_map = {
        "PYTHON": Language.PYTHON,
        "SQL": Language.SQL,
        "SCALA": Language.SCALA,
        "R": Language.R,
    }
    lang_enum = lang_map.get(language.upper(), Language.PYTHON)

    # 將內容做 Base64 編碼
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    w.workspace.import_(
        path=path,
        content=content_b64,
        language=lang_enum,
        format=ImportFormat.SOURCE,
        overwrite=overwrite,
    )


def create_directory(path: str) -> None:
    """
    建立 workspace 目錄。

    參數:
        path: Workspace 目錄路徑

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()
    w.workspace.mkdirs(path=path)


def delete_path(path: str, recursive: bool = False) -> None:
    """
    刪除 workspace 檔案或目錄。

    參數:
        path: 要刪除的 Workspace 路徑
        recursive: 若為 True，會遞迴刪除目錄

    引發:
        DatabricksError: 若 API 請求失敗
    """
    w = get_workspace_client()
    w.workspace.delete(path=path, recursive=recursive)
