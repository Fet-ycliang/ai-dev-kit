"""Warehouse 管理端點。"""

import logging

from fastapi import APIRouter, Request
from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

from ..services.warehouses import list_warehouses_async
from ..services.user import get_current_user, get_current_token, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/warehouses')
async def get_warehouses(request: Request):
  """取得可用的 Databricks SQL warehouse。

  回傳依優先順序排序的 warehouse：
  1. 執行中 + 名稱含 "shared"（最高優先）
  2. 執行中（不含 "shared"）
  3. 未執行 + 名稱含 "shared"
  4. 其他全部

  結果會快取 5 分鐘並在背景重新整理。
  """
  # 驗證使用者已認證並取得 Databricks 認證
  await get_current_user(request)
  user_token = await get_current_token(request)
  workspace_url = get_workspace_url()

  # 設定請求的認證上下文
  set_databricks_auth(workspace_url, user_token)

  try:
    # 取得 warehouse（已快取並非同步重新整理）
    warehouses = await list_warehouses_async()
    return warehouses
  finally:
    clear_databricks_auth()
