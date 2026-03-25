"""
Unity Catalog - Catalog 作業

用於管理 Unity Catalog 中 Catalog 的函式。
"""

from typing import Dict, List, Optional
from databricks.sdk.service.catalog import CatalogInfo, IsolationMode

from ..auth import get_workspace_client


def list_catalogs() -> List[CatalogInfo]:
    """
    列出 Unity Catalog 中的所有 Catalog。

    回傳:
        包含 Catalog 中繼資料的 CatalogInfo 物件清單

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return list(w.catalogs.list())


def get_catalog(catalog_name: str) -> CatalogInfo:
    """
    取得特定 Catalog 的詳細資訊。

    參數:
        catalog_name: Catalog 名稱

    回傳:
        包含以下 Catalog 中繼資料的 CatalogInfo 物件：
        - name, full_name, owner, comment
        - created_at, updated_at
        - storage_location

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    return w.catalogs.get(name=catalog_name)


def create_catalog(
    name: str,
    comment: Optional[str] = None,
    storage_root: Optional[str] = None,
    properties: Optional[Dict[str, str]] = None,
) -> CatalogInfo:
    """
    在 Unity Catalog 中建立新的 Catalog。

    參數:
        name: 要建立的 Catalog 名稱
        comment: 可選的說明
        storage_root: 可選的受控儲存位置（雲端 URL）
        properties: 可選的鍵值屬性

    回傳:
        包含已建立 Catalog 中繼資料的 CatalogInfo 物件

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    kwargs: Dict = {"name": name}
    if comment is not None:
        kwargs["comment"] = comment
    if storage_root is not None:
        kwargs["storage_root"] = storage_root
    if properties is not None:
        kwargs["properties"] = properties
    return w.catalogs.create(**kwargs)


def update_catalog(
    catalog_name: str,
    new_name: Optional[str] = None,
    comment: Optional[str] = None,
    owner: Optional[str] = None,
    isolation_mode: Optional[str] = None,
) -> CatalogInfo:
    """
    更新 Unity Catalog 中既有的 Catalog。

    參數:
        catalog_name: Catalog 目前的名稱
        new_name: Catalog 的新名稱
        comment: 新的 comment／說明
        owner: 新的擁有者（user 或 group）
        isolation_mode: 隔離模式（"OPEN" 或 "ISOLATED"）

    回傳:
        包含更新後 Catalog 中繼資料的 CatalogInfo 物件

    引發:
        ValueError: 如果未提供任何要更新的欄位
        DatabricksError: 如果 API 請求失敗
    """
    if not any([new_name, comment, owner, isolation_mode]):
        raise ValueError("至少必須提供一個欄位以進行更新")

    w = get_workspace_client()
    kwargs: Dict = {"name": catalog_name}
    if new_name is not None:
        kwargs["new_name"] = new_name
    if comment is not None:
        kwargs["comment"] = comment
    if owner is not None:
        kwargs["owner"] = owner
    if isolation_mode is not None:
        kwargs["isolation_mode"] = IsolationMode(isolation_mode)
    return w.catalogs.update(**kwargs)


def delete_catalog(catalog_name: str, force: bool = False) -> None:
    """
    從 Unity Catalog 刪除 Catalog。

    參數:
        catalog_name: 要刪除的 Catalog 名稱
        force: 若為 True，即使 Catalog 包含 Schema 也會強制刪除

    引發:
        DatabricksError: 如果 API 請求失敗
    """
    w = get_workspace_client()
    w.catalogs.delete(name=catalog_name, force=force)
