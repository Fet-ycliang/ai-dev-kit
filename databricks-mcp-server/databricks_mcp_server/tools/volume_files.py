"""Volume 檔案工具 - 管理 Unity Catalog Volumes 中的檔案。"""

from typing import Dict, Any

from databricks_tools_core.unity_catalog import (
    list_volume_files as _list_volume_files,
    upload_to_volume as _upload_to_volume,
    download_from_volume as _download_from_volume,
    delete_volume_file as _delete_volume_file,
    delete_volume_directory as _delete_volume_directory,
    create_volume_directory as _create_volume_directory,
    get_volume_file_metadata as _get_volume_file_metadata,
)

from ..server import mcp


@mcp.tool
def list_volume_files(volume_path: str, max_results: int = 500) -> Dict[str, Any]:
    """
    列出 Unity Catalog volume 路徑中的檔案與目錄。

    參數:
        volume_path: Volume 中的路徑（例如 "/Volumes/catalog/schema/volume/folder"）
        max_results: 要回傳的最大結果數（預設：500，上限：1000）

    回傳:
        包含 'files' 清單與 'truncated' 布林值的字典，用來表示結果是否被限制
    """
    # 限制 max_results 以避免緩衝區溢位（1MB JSON 限制）
    max_results = min(max_results, 1000)

    # 多抓一筆以判斷是否還有更多結果
    results = _list_volume_files(volume_path, max_results=max_results + 1)
    truncated = len(results) > max_results

    # 僅回傳最多 max_results 筆
    results = results[:max_results]

    files = [
        {
            "name": r.name,
            "path": r.path,
            "is_directory": r.is_directory,
            "file_size": r.file_size,
            "last_modified": r.last_modified,
        }
        for r in results
    ]

    return {
        "files": files,
        "returned_count": len(files),
        "truncated": truncated,
        "message": f"Results limited to {len(files)} items. Use a more specific path or subdirectory to see more files."
        if truncated
        else None,
    }


@mcp.tool
def upload_to_volume(
    local_path: str,
    volume_path: str,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    將本機檔案上傳到 Unity Catalog volume。

    參數:
        local_path: 要上傳的本機檔案路徑
        volume_path: Volume 中的目標路徑（例如 "/Volumes/catalog/schema/volume/data.csv"）
        overwrite: 是否覆寫既有檔案（預設：True）

    回傳:
        包含 local_path、volume_path、success 與 error（若失敗）的字典
    """
    result = _upload_to_volume(
        local_path=local_path,
        volume_path=volume_path,
        overwrite=overwrite,
    )
    return {
        "local_path": result.local_path,
        "volume_path": result.volume_path,
        "success": result.success,
        "error": result.error,
    }


@mcp.tool
def download_from_volume(
    volume_path: str,
    local_path: str,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    將檔案從 Unity Catalog volume 下載到本機路徑。

    參數:
        volume_path: Volume 中的路徑（例如 "/Volumes/catalog/schema/volume/data.csv"）
        local_path: 目標本機檔案路徑
        overwrite: 是否覆寫既有本機檔案（預設：True）

    回傳:
        包含 volume_path、local_path、success 與 error（若失敗）的字典
    """
    result = _download_from_volume(
        volume_path=volume_path,
        local_path=local_path,
        overwrite=overwrite,
    )
    return {
        "volume_path": result.volume_path,
        "local_path": result.local_path,
        "success": result.success,
        "error": result.error,
    }


@mcp.tool
def delete_volume_file(volume_path: str) -> Dict[str, Any]:
    """
    從 Unity Catalog volume 刪除檔案。

    參數:
        volume_path: Volume 中檔案的路徑（例如 "/Volumes/catalog/schema/volume/file.csv"）

    回傳:
        包含 volume_path 與 success 狀態的字典
    """
    try:
        _delete_volume_file(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool
def delete_volume_directory(volume_path: str) -> Dict[str, Any]:
    """
    從 Unity Catalog volume 刪除空目錄。

    注意：目錄必須為空。請先刪除所有內容。

    參數:
        volume_path: Volume 中目錄的路徑

    回傳:
        包含 volume_path 與 success 狀態的字典
    """
    try:
        _delete_volume_directory(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool
def create_volume_directory(volume_path: str) -> Dict[str, Any]:
    """
    在 Unity Catalog volume 中建立目錄。

    會視需要建立父目錄（如同 mkdir -p）。
    具冪等性 - 若目錄已存在仍視為成功。

    參數:
        volume_path: 新目錄的路徑（例如 "/Volumes/catalog/schema/volume/new_folder"）

    回傳:
        包含 volume_path 與 success 狀態的字典
    """
    try:
        _create_volume_directory(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool
def get_volume_file_info(volume_path: str) -> Dict[str, Any]:
    """
    取得 Unity Catalog volume 中檔案的中繼資料。

    參數:
        volume_path: Volume 中檔案的路徑

    回傳:
        包含 name、path、is_directory、file_size、last_modified 的字典
    """
    try:
        info = _get_volume_file_metadata(volume_path)
        return {
            "name": info.name,
            "path": info.path,
            "is_directory": info.is_directory,
            "file_size": info.file_size,
            "last_modified": info.last_modified,
            "success": True,
        }
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}
