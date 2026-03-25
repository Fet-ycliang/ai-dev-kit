"""
Lakebase Autoscaling 認證操作

用於產生連線至 Lakebase Autoscaling PostgreSQL 資料庫所需 OAuth Token 的函式。
"""

import logging
from typing import Any, Dict

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def generate_credential(endpoint: str) -> Dict[str, Any]:
    """
    產生用於連線 Lakebase Autoscaling 資料庫的 OAuth Token。

    注意：
        此 Token 約可使用 1 小時。請在 PostgreSQL 連線字串中搭配
        sslmode=require 作為密碼使用。

    參數:
        endpoint: 要限定認證範圍的端點資源名稱
            （例如："projects/my-app/branches/production/endpoints/ep-primary"）。

    回傳:
        包含以下欄位的字典：
        - token: OAuth Token（作為連線字串中的密碼使用）
        - expiration_time: Token 到期時間
        - message: 使用說明

    引發:
        Exception: 當認證產生失敗時
    """
    client = get_workspace_client()

    try:
        cred = client.postgres.generate_database_credential(endpoint=endpoint)

        result: Dict[str, Any] = {}

        if hasattr(cred, "token") and cred.token:
            result["token"] = cred.token

        if hasattr(cred, "expiration_time") and cred.expiration_time:
            result["expiration_time"] = str(cred.expiration_time)

        result["message"] = "已產生 Token。約可使用 1 小時。請搭配 sslmode=require 作為密碼使用。"

        return result
    except Exception as e:
        raise Exception(f"產生 Lakebase Autoscaling 認證失敗：{str(e)}")
