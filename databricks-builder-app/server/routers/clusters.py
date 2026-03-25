"""Cluster 管理端點。"""

import logging

from fastapi import APIRouter, Request
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

from ..services.clusters import list_clusters_async
from ..services.user import get_current_user, get_current_token, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/clusters')
async def get_clusters(request: Request):
  """取得可用的 Databricks cluster。

  回傳排序後的 cluster：執行中的優先、名稱含 "shared" 次之、最後依字母排序。
  結果會快取 5 分鐘並在背景重新整理。
  """
  # 驗證使用者已認證並取得 Databricks 認證
  await get_current_user(request)
  user_token = await get_current_token(request)
  workspace_url = get_workspace_url()

  # 設定請求的認證上下文
  set_databricks_auth(workspace_url, user_token)

  try:
    # 取得 cluster（已快取並非同步重新整理）
    clusters = await list_clusters_async()
    return clusters
  finally:
    clear_databricks_auth()
