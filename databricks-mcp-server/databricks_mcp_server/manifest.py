"""用於跨 session 延續性的資源追蹤 manifest。

追蹤透過 MCP 伺服器建立的 Databricks 資源，並記錄於本機
`.databricks-resources.json` 檔案中。這讓代理可以看到
先前 session 建立的資源，並避免重複建立。
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 資源刪除器登錄表
# ---------------------------------------------------------------------------
# 各工具模組都會註冊一個 callable，根據資源 ID 刪除資源。
# 這可避免在 manifest 工具層中硬編碼每一種資源類型。
_RESOURCE_DELETERS: Dict[str, Callable[[str], None]] = {}


def register_deleter(resource_type: str, fn: Callable[[str], None]) -> None:
    """註冊某個資源類型的刪除函式。

    工具模組會在匯入時呼叫此函式，讓 manifest 工具層可以
    在不知道實作細節的情況下刪除任何已追蹤的資源。

    參數:
        resource_type: manifest 的資源類型鍵值（例如 ``"job"``）。
        fn: 一個接受 ``resource_id`` 字串並刪除對應
            Databricks 資源的 callable。失敗時應拋出例外。

    回傳:
        None
    """
    _RESOURCE_DELETERS[resource_type] = fn


MANIFEST_FILENAME = ".databricks-resources.json"
MANIFEST_VERSION = 1


def _get_manifest_path() -> Path:
    """取得 manifest 檔案的路徑。

    尋找相對於 CWD 的 ``MANIFEST_FILENAME``（MCP 伺服器
    會從專案根目錄啟動）。
    """
    return Path(os.getcwd()) / MANIFEST_FILENAME


def _read_manifest() -> Dict[str, Any]:
    """讀取 manifest 檔案；若不存在則回傳空結構。"""
    path = _get_manifest_path()
    if not path.exists():
        return {"version": MANIFEST_VERSION, "resources": []}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "resources" not in data:
            return {"version": MANIFEST_VERSION, "resources": []}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read manifest %s: %s", path, exc)
        return {"version": MANIFEST_VERSION, "resources": []}


def _write_manifest(data: Dict[str, Any]) -> None:
    """以原子方式寫入 manifest 檔案。"""
    path = _get_manifest_path()
    try:
        # 先在相同目錄寫入暫存檔，再重新命名
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".manifest-tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            # 發生失敗時清理暫存檔
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("Failed to write manifest %s: %s", path, exc)


def _now_iso() -> str:
    """以 ISO 8601 字串回傳目前的 UTC 時間。"""
    return datetime.now(timezone.utc).isoformat()


def track_resource(
    resource_type: str,
    name: str,
    resource_id: str,
    url: Optional[str] = None,
) -> None:
    """在 manifest 中追蹤已建立/已更新的資源。

    Upsert 邏輯：
    - 若存在相同 type+id 的資源，更新 name/url/updated_at。
    - 若存在相同 type+name 但 id 不同的資源，更新其 id。
    - 否則，附加一筆新項目。

    這是 best-effort 作法：失敗只會記錄日誌，不會拋出例外。
    """
    try:
        data = _read_manifest()
        resources: List[Dict[str, Any]] = data.get("resources", [])
        now = _now_iso()

        # 嘗試以 type+id 尋找
        for r in resources:
            if r.get("type") == resource_type and r.get("id") == resource_id:
                r["name"] = name
                if url:
                    r["url"] = url
                r["updated_at"] = now
                _write_manifest(data)
                return

        # 嘗試以 type+name 尋找（可處理跨 session 的 ID 變更）
        for r in resources:
            if r.get("type") == resource_type and r.get("name") == name:
                r["id"] = resource_id
                if url:
                    r["url"] = url
                r["updated_at"] = now
                _write_manifest(data)
                return

        # 新資源
        entry: Dict[str, Any] = {
            "type": resource_type,
            "name": name,
            "id": resource_id,
            "created_at": now,
            "updated_at": now,
        }
        if url:
            entry["url"] = url
        resources.append(entry)
        data["resources"] = resources
        _write_manifest(data)
    except Exception as exc:
        logger.warning("Failed to track resource %s/%s: %s", resource_type, name, exc)


def remove_resource(resource_type: str, resource_id: str) -> bool:
    """依 type+id 從 manifest 中移除資源。

    回傳 True 表示已找到並移除該資源。
    """
    try:
        data = _read_manifest()
        resources = data.get("resources", [])
        original_count = len(resources)
        data["resources"] = [
            r for r in resources if not (r.get("type") == resource_type and r.get("id") == resource_id)
        ]
        if len(data["resources"]) < original_count:
            _write_manifest(data)
            return True
        return False
    except Exception as exc:
        logger.warning("Failed to remove resource %s/%s: %s", resource_type, resource_id, exc)
        return False


def list_resources(resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """回傳已追蹤的資源，可選擇依類型篩選。"""
    data = _read_manifest()
    resources = data.get("resources", [])
    if resource_type:
        resources = [r for r in resources if r.get("type") == resource_type]
    return resources
