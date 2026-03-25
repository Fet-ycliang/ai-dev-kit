"""Warehouses 服務，用於列出 Databricks SQL warehouses 並提供快取功能。"""

import asyncio
import logging
import time
from itertools import islice
from threading import Lock
from typing import Optional

from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)

# 快取設定
CACHE_TTL_SECONDS = 300  # 5 分鐘
_cache: dict = {
  'warehouses': None,
  'last_updated': 0,
  'is_refreshing': False,
}
_cache_lock = Lock()


def _fetch_warehouses_sync(limit: int = 50, timeout: int = 15) -> list[dict]:
  """使用 SDK 同步取得 SQL warehouses。

  回傳依優先順序排序的 warehouses：
  1. Serverless + 執行中（最高優先）
  2. Serverless + 非執行中
  3. 執行中 + 名稱包含 "shared"
  4. 執行中（不含 "shared"）
  5. 非執行中 + 名稱包含 "shared"
  6. 其餘全部

  Args:
      limit: 回傳的 warehouses 數量上限
      timeout: API 呼叫的逾時秒數
  """
  from databricks.sdk.service.sql import State

  # 使用 get_workspace_client 取得已設定的驗證上下文
  client = get_workspace_client()

  # 擷取 warehouses
  warehouses = list(islice(client.warehouses.list(), limit * 2))

  # 依優先順序排序：serverless 優先，然後執行中 + shared > 執行中 > shared > 其餘
  def sort_key(w):
    is_running = w.state == State.RUNNING if w.state else False
    is_shared = 'shared' in (w.name or '').lower()
    is_serverless = getattr(w, 'enable_serverless_compute', False) or False
    # Serverless warehouse 一律排在最前面
    if is_serverless and is_running:
      priority = 0
    elif is_serverless:
      priority = 1
    elif is_running and is_shared:
      priority = 2
    elif is_running:
      priority = 3
    elif is_shared:
      priority = 4
    else:
      priority = 5
    return priority

  warehouses.sort(key=sort_key)

  return [
    {
      'warehouse_id': w.id,
      'warehouse_name': w.name,
      'state': w.state.value if w.state else 'UNKNOWN',
      'cluster_size': w.cluster_size,
      'creator_name': w.creator_name,
      'is_serverless': getattr(w, 'enable_serverless_compute', False) or False,
    }
    for w in warehouses[:limit]
  ]


async def _refresh_cache(timeout_seconds: int = 30) -> None:
  """在背景更新 warehouse 快取。

  Args:
      timeout_seconds: 等待 API 呼叫的最長時間
  """
  global _cache

  with _cache_lock:
    if _cache['is_refreshing']:
      return  # 已有另一個更新作業在執行中
    _cache['is_refreshing'] = True

  try:
    logger.info('Refreshing warehouses cache...')
    start = time.time()

    # 使用 wait_for 為執行緒操作加上逾時限制
    warehouses = await asyncio.wait_for(
      asyncio.to_thread(_fetch_warehouses_sync),
      timeout=timeout_seconds,
    )

    with _cache_lock:
      _cache['warehouses'] = warehouses
      _cache['last_updated'] = time.time()

    logger.info(f'Warehouses cache refreshed: {len(warehouses)} warehouses in {time.time() - start:.2f}s')

  except asyncio.TimeoutError:
    logger.error(f'Warehouses cache refresh timed out after {timeout_seconds}s')

  except Exception as e:
    logger.error(f'Failed to refresh warehouses cache: {e}')

  finally:
    with _cache_lock:
      _cache['is_refreshing'] = False


def _is_cache_valid() -> bool:
  """檢查快取是否仍然有效。"""
  with _cache_lock:
    if _cache['warehouses'] is None:
      return False
    return (time.time() - _cache['last_updated']) < CACHE_TTL_SECONDS


def _get_cached_warehouses() -> Optional[list[dict]]:
  """從快取取得 warehouses（若可用）。"""
  with _cache_lock:
    return _cache['warehouses']


async def list_warehouses_async() -> list[dict]:
  """列出可用的 Databricks SQL warehouses 並提供快取功能。

  若有可用的快取資料會立即回傳，若快取過期則觸發背景更新。

  Returns:
      包含 warehouse_id、warehouse_name、state 等資訊的 warehouse 字典清單
  """
  cached = _get_cached_warehouses()

  if cached is not None:
    # 有快取資料 - 立即回傳
    if not _is_cache_valid():
      # 快取過期，觸發背景更新
      asyncio.create_task(_refresh_cache())
    return cached

  # 無快取 - 必須等待首次擷取
  await _refresh_cache()
  return _get_cached_warehouses() or []
