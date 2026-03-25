"""Clusters 服務，用於列出 Databricks clusters 並提供快取功能。"""

import asyncio
import logging
import time
from itertools import islice
from threading import Lock
from typing import Optional

from databricks.sdk.config import Config
from databricks.sdk.service.compute import State
from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)

# 快取設定
CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: dict = {
  'clusters': None,
  'last_updated': 0,
  'is_refreshing': False,
}
_cache_lock = Lock()


SERVERLESS_CLUSTER_ID = '__serverless__'


def _fetch_clusters_sync(limit: int = 50, timeout: int = 15) -> list[dict]:
  """使用 SDK 同步取得 Databricks clusters。

  總是先回傳 "Serverless Compute" 項目，接著回傳真實的 clusters，
  排序規則：執行中的優先、名稱包含 "shared" 次之、然後按字母順序排列。

  Args:
      limit: 回傳的 clusters 數量上限
      timeout: API 呼叫的逾時秒數
  """
  from databricks.sdk.service.compute import ClusterSource, ListClustersFilterBy

  # 使用 get_workspace_client 取得已設定的驗證上下文
  client = get_workspace_client()

  # 在 API 層級過濾掉 serverless 和 job clusters
  filter_by = ListClustersFilterBy(
    cluster_sources=[ClusterSource.UI, ClusterSource.API],
  )

  # 使用 page_size 提高效率，用 islice 提早停止
  clusters = list(islice(client.clusters.list(filter_by=filter_by, page_size=limit * 2), limit * 2))

  # 不需再過濾 serverless - 已在 API 層級完成
  filtered_clusters = clusters

  # 排序：執行中優先，然後是名稱包含 "shared" 的
  def sort_key(c):
    is_running = c.state == State.RUNNING if c.state else False
    is_shared = 'shared' in (c.cluster_name or '').lower()
    return (not is_running, not is_shared)

  filtered_clusters.sort(key=sort_key)

  # 建立結果，Serverless Compute 作為第一個（預設）項目
  result = [
    {
      'cluster_id': SERVERLESS_CLUSTER_ID,
      'cluster_name': 'Serverless Compute',
      'state': 'RUNNING',
      'creator_user_name': None,
    },
  ]

  result.extend(
    {
      'cluster_id': c.cluster_id,
      'cluster_name': c.cluster_name,
      'state': c.state.value if c.state else 'UNKNOWN',
      'creator_user_name': c.creator_user_name,
    }
    for c in filtered_clusters[:limit]
  )

  return result


async def _refresh_cache(timeout_seconds: int = 30) -> None:
  """在背景更新 cluster 快取。

  Args:
      timeout_seconds: 等待 API 呼叫的最長時間
  """
  global _cache

  with _cache_lock:
    if _cache['is_refreshing']:
      return  # 已有另一個更新作業在執行中
    _cache['is_refreshing'] = True

  try:
    logger.info('Refreshing clusters cache...')
    start = time.time()

    # 使用 wait_for 為執行緒操作加上逾時限制
    clusters = await asyncio.wait_for(
      asyncio.to_thread(_fetch_clusters_sync),
      timeout=timeout_seconds,
    )

    with _cache_lock:
      _cache['clusters'] = clusters
      _cache['last_updated'] = time.time()

    logger.info(f'Clusters cache refreshed: {len(clusters)} clusters in {time.time() - start:.2f}s')

  except asyncio.TimeoutError:
    logger.error(f'Clusters cache refresh timed out after {timeout_seconds}s')

  except Exception as e:
    logger.error(f'Failed to refresh clusters cache: {e}')

  finally:
    with _cache_lock:
      _cache['is_refreshing'] = False


def _is_cache_valid() -> bool:
  """檢查快取是否仍然有效。"""
  with _cache_lock:
    if _cache['clusters'] is None:
      return False
    return (time.time() - _cache['last_updated']) < CACHE_TTL_SECONDS


def _get_cached_clusters() -> Optional[list[dict]]:
  """從快取取得 clusters（若可用）。"""
  with _cache_lock:
    return _cache['clusters']


async def list_clusters_async() -> list[dict]:
  """列出可用的 Databricks clusters 並提供快取功能。

  若有可用的快取資料會立即回傳，若快取過期則觸發背景更新。

  Returns:
      包含 cluster_id、cluster_name、state、creator 的 cluster 字典清單
  """
  cached = _get_cached_clusters()

  if cached is not None:
    # 有快取資料 - 立即回傳
    if not _is_cache_valid():
      # 快取過期，觸發背景更新
      asyncio.create_task(_refresh_cache())
    return cached

  # 無快取 - 必須等待首次擷取
  await _refresh_cache()
  result = _get_cached_clusters()
  if result:
    return result

  # 即使 API 呼叫失敗，仍回傳 serverless 選項
  return [
    {
      'cluster_id': SERVERLESS_CLUSTER_ID,
      'cluster_name': 'Serverless Compute',
      'state': 'RUNNING',
      'creator_user_name': None,
    },
  ]
