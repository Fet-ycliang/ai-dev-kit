"""Clusters 服務的測試。"""

import asyncio
import time

import pytest


def test_fetch_clusters_sync_performance():
  """測試原始 API cluster 擷取速度（< 10 秒）。"""
  from server.services.clusters import _fetch_clusters_sync

  start = time.time()
  clusters = _fetch_clusters_sync(limit=50)
  elapsed = time.time() - start

  print(f'\nFetched {len(clusters)} clusters in {elapsed:.2f}s')
  if clusters:
    print(f'First cluster: {clusters[0]["cluster_name"]} ({clusters[0]["state"]})')

  # 應在 10 秒內完成
  assert elapsed < 10, f'Cluster fetch took too long: {elapsed:.2f}s'
  assert len(clusters) <= 50, f'Got more than limit: {len(clusters)}'


def test_clusters_sorted_correctly():
  """測試 clusters 排序正確：serverless 優先、然後執行中、shared、其餘。"""
  from server.services.clusters import _fetch_clusters_sync, SERVERLESS_CLUSTER_ID

  clusters = _fetch_clusters_sync(limit=50)

  # 第一個項目應該總是 Serverless Compute
  assert clusters[0]['cluster_id'] == SERVERLESS_CLUSTER_ID
  assert clusters[0]['cluster_name'] == 'Serverless Compute'

  # 跳過合成的 serverless 項目以檢查排序順序
  real_clusters = [c for c in clusters if c['cluster_id'] != SERVERLESS_CLUSTER_ID]

  if len(real_clusters) < 2:
    pytest.skip('Not enough real clusters to test sorting')

  # 檢查執行中的 clusters 在真實 clusters 中排在最前面
  found_non_running = False
  for c in real_clusters:
    if c['state'] != 'RUNNING':
      found_non_running = True
    elif found_non_running:
      # 在非執行中 cluster 之後發現執行中 cluster - 排序錯誤
      pytest.fail(f"Running cluster {c['cluster_name']} found after non-running cluster")

  print(f'\nFirst 5 clusters:')
  for c in clusters[:5]:
    print(f"  {c['cluster_name']} ({c['state']})")


@pytest.mark.asyncio
async def test_list_clusters_async_caching():
  """測試快取功能 - 第二次呼叫應該是即時的。"""
  from server.services.clusters import _cache, list_clusters_async

  # 先清除快取
  _cache['clusters'] = None
  _cache['last_updated'] = 0

  # 第一次呼叫 - 應從 API 擷取
  start = time.time()
  clusters1 = await list_clusters_async()
  first_call_time = time.time() - start
  print(f'\nFirst call: {len(clusters1)} clusters in {first_call_time:.2f}s')

  # 第二次呼叫 - 應從快取取得（即時）
  start = time.time()
  clusters2 = await list_clusters_async()
  second_call_time = time.time() - start
  print(f'Second call: {len(clusters2)} clusters in {second_call_time:.4f}s')

  assert first_call_time < 15, f'First call too slow: {first_call_time:.2f}s'
  assert second_call_time < 0.01, f'Cached call too slow: {second_call_time:.4f}s'
  assert clusters1 == clusters2, 'Cached data should match'


if __name__ == '__main__':
  # 直接執行同步測試
  print('=== Testing sync fetch performance ===')
  test_fetch_clusters_sync_performance()

  print('\n=== Testing sorting ===')
  test_clusters_sorted_correctly()

  print('\n=== Testing async caching ===')
  asyncio.run(test_list_clusters_async_caching())

  print('\n=== All tests passed! ===')
