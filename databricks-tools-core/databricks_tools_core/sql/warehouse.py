"""
SQL Warehouse 作業

用於列出與選擇 SQL warehouses 的函式。
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.service.sql import State

from ..auth import get_workspace_client, get_current_username

logger = logging.getLogger(__name__)


def list_warehouses(limit: int = 20) -> List[Dict[str, Any]]:
    """
    列出 SQL warehouses，並優先顯示線上（RUNNING）的 warehouses。

    參數:
        limit: 要回傳的 warehouse 最大數量（預設：20）

    回傳:
        由 warehouse 字典組成的清單，包含以下鍵值：
        - id: Warehouse ID
        - name: Warehouse 名稱
        - state: 目前狀態（RUNNING、STOPPED、STARTING 等）
        - cluster_size: Warehouse 大小
        - auto_stop_mins: 自動停止逾時時間（分鐘）
        - creator_name: 建立此 warehouse 的人
        - warehouse_type: Warehouse 類型（PRO、CLASSIC）
        - enable_serverless_compute: 是否啟用 serverless compute

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()

    try:
        warehouses = list(client.warehouses.list())
    except Exception as e:
        raise Exception(f"列出 SQL warehouses 失敗：{str(e)}。請確認您具有檢視 warehouses 的權限。")

    # 排序：先顯示 RUNNING，再依名稱排序
    def sort_key(w):
        # RUNNING = 0（優先），其他 = 1
        state_priority = 0 if w.state == State.RUNNING else 1
        return (state_priority, w.name.lower() if w.name else "")

    warehouses.sort(key=sort_key)

    # 轉換為 dict 並套用數量限制
    result = []
    for w in warehouses[:limit]:
        result.append(
            {
                "id": w.id,
                "name": w.name,
                "state": w.state.value if w.state else None,
                "cluster_size": w.cluster_size,
                "auto_stop_mins": w.auto_stop_mins,
                "creator_name": w.creator_name,
                "warehouse_type": getattr(w, "warehouse_type", None),
                "enable_serverless_compute": getattr(w, "enable_serverless_compute", None),
            }
        )

    return result


def _sort_within_tier(warehouses: list, current_user: Optional[str]) -> list:
    """在同一層級內排序 warehouses：先 serverless，再目前使用者擁有的。

    這是*軟性*偏好，不會移除任何 warehouse。在相同優先級群組中，
    會先嘗試 serverless warehouses，再嘗試目前使用者建立的 warehouses。

    參數:
        warehouses: SDK warehouse 物件清單。
        current_user: 目前使用者的使用者名稱／電子郵件，或 None。

    回傳:
        重新排序後的清單（先 serverless，再目前使用者擁有，其餘最後）。
    """
    if not warehouses:
        return warehouses

    def sort_key(w):
        is_serverless = 0 if getattr(w, "enable_serverless_compute", False) else 1
        user_lower = (current_user or "").lower()
        is_owned = 0 if user_lower and (w.creator_name or "").lower() == user_lower else 1
        return (is_serverless, is_owned)

    return sorted(warehouses, key=sort_key)


def get_best_warehouse() -> Optional[str]:
    """
    依據優先順序規則選擇最佳可用的 SQL warehouse。

    在每個優先層級中，會優先選擇 serverless warehouses
    （可即時啟動、自動調整規模、沒有閒置成本），其次是由目前使用者建立的
    warehouses。不會排除任何 warehouse。

    注意:
        優先順序：
        1. 名稱為 "Shared endpoint" 或 "dbdemos-shared-endpoint" 的執行中 warehouse
        2. 名稱中包含 'shared' 的任一執行中 warehouse
        3. 任一執行中 warehouse
        4. 名稱中包含 'shared' 的已停止 warehouse
        5. 任一已停止 warehouse

    回傳:
        Warehouse ID 字串；若沒有可用 warehouse 則為 None

    引發:
        Exception: 當 API 請求失敗時
    """
    client = get_workspace_client()
    current_user = get_current_username()

    try:
        warehouses = list(client.warehouses.list())
    except Exception as e:
        raise Exception(f"列出 SQL warehouses 失敗：{str(e)}。請確認您具有檢視 warehouses 的權限。")

    if not warehouses:
        logger.warning("在 workspace 中找不到任何 SQL warehouses")
        return None

    # 將 warehouses 分類
    standard_shared = []  # 特定 shared endpoint 名稱
    online_shared = []  # 執行中且名稱包含 'shared'
    online_other = []  # 執行中，但名稱不含 'shared'
    offline_shared = []  # 已停止且名稱包含 'shared'
    offline_other = []  # 已停止，但名稱不含 'shared'

    for warehouse in warehouses:
        is_running = warehouse.state == State.RUNNING
        name_lower = warehouse.name.lower() if warehouse.name else ""
        is_shared = "shared" in name_lower

        # 檢查是否為標準 shared endpoint 名稱
        if is_running and warehouse.name in ("Shared endpoint", "dbdemos-shared-endpoint"):
            standard_shared.append(warehouse)
        elif is_running and is_shared:
            online_shared.append(warehouse)
        elif is_running:
            online_other.append(warehouse)
        elif is_shared:
            offline_shared.append(warehouse)
        else:
            offline_other.append(warehouse)

    # 在每個層級內，優先選擇由目前使用者建立的 warehouses
    standard_shared = _sort_within_tier(standard_shared, current_user)
    online_shared = _sort_within_tier(online_shared, current_user)
    online_other = _sort_within_tier(online_other, current_user)
    offline_shared = _sort_within_tier(offline_shared, current_user)
    offline_other = _sort_within_tier(offline_other, current_user)

    # 依優先順序選擇
    if standard_shared:
        selected = standard_shared[0]
    elif online_shared:
        selected = online_shared[0]
    elif online_other:
        selected = online_other[0]
    elif offline_shared:
        selected = offline_shared[0]
    elif offline_other:
        selected = offline_other[0]
    else:
        return None

    logger.debug(f"已選擇 warehouse：{selected.name}（狀態：{selected.state}）")
    return selected.id
