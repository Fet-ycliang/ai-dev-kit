"""取得目前已驗證使用者與 token 的使用者服務。

在正式環境（Databricks Apps）中：
- 優先檢查 X-Forwarded-Email header（M2M 呼叫者轉送真實使用者身分）
- 若無則使用 X-Forwarded-User header（透過 Databricks Apps proxy 的瀏覽器使用者）
- 可從 X-Forwarded-Access-Token header 取得 access token
- 也接受來自其他 Databricks Apps 的 Bearer token（M2M OAuth）

在開發環境中，會回退使用環境變數與 WorkspaceClient。
"""

import asyncio
import hashlib
import logging
import os
import time
from typing import Optional

from databricks.sdk import WorkspaceClient
from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION
from fastapi import Request

logger = logging.getLogger(__name__)

# 開發環境使用者快取，避免重複 API 呼叫
_dev_user_cache: Optional[str] = None
_workspace_url_cache: Optional[str] = None

# Bearer token -> 使用者身分快取（以 token 雜湊為索引，TTL 為 5 分鐘）
_bearer_user_cache: dict[str, tuple[str, float]] = {}
_BEARER_CACHE_TTL = 300  # 5 minutes
_BEARER_CACHE_MAX_SIZE = 100  # Max unique tokens to cache


def _is_local_development() -> bool:
  """檢查是否在本機開發模式下執行。"""
  return os.getenv('ENV', 'development') == 'development'


def _has_oauth_credentials() -> bool:
  """檢查環境中是否已設定 OAuth credentials（SP）。"""
  return bool(os.environ.get('DATABRICKS_CLIENT_ID') and os.environ.get('DATABRICKS_CLIENT_SECRET'))


def _get_workspace_client() -> WorkspaceClient:
  """取得已正確處理認證的 WorkspaceClient。

  在 Databricks Apps 中會明確使用 OAuth M2M，以避免與其他認證方式衝突。
  """
  product_kwargs = dict(product=PRODUCT_NAME, product_version=PRODUCT_VERSION)
  if _has_oauth_credentials():
    # 明確設定 OAuth M2M 以避免認證衝突
    return WorkspaceClient(
      host=os.environ.get('DATABRICKS_HOST', ''),
      client_id=os.environ.get('DATABRICKS_CLIENT_ID', ''),
      client_secret=os.environ.get('DATABRICKS_CLIENT_SECRET', ''),
      auth_type='oauth-m2m',
      **product_kwargs,
    )
  # 開發模式 - 使用預設 SDK 認證
  return WorkspaceClient(**product_kwargs)


async def get_current_user(request: Request) -> str:
  """從 request 取得目前使用者的 email。

  認證優先順序：
    1. X-Forwarded-Email header（M2M 呼叫者轉送真實使用者身分）
    2. X-Forwarded-User header（透過 Databricks Apps proxy 的瀏覽器使用者）
    3. Authorization: Bearer token（來自其他 Databricks Apps 的 M2M OAuth）
    4. WorkspaceClient 開發環境回退方案（僅限本機開發）

  Args:
      request: FastAPI Request 物件

  Returns:
      使用者 email 或 service principal 身分

  Raises:
      ValueError: 如果無法判定使用者
  """
  # 1. X-Forwarded-Email（M2M 呼叫者轉送真實使用者身分）
  # 先檢查此值，這樣當 M2M 呼叫者（例如 Lemma）明確設定真實使用者的
  # SCIM 身分時，就會優先於 X-Forwarded-User；後者可能被 proxy
  # 覆寫成 service principal 的身分。
  forwarded_email = request.headers.get('X-Forwarded-Email')
  if forwarded_email:
    logger.debug(f'Got user from X-Forwarded-Email header: {forwarded_email}')
    return forwarded_email

  # 2. X-Forwarded-User（Databricks Apps proxy 提供給瀏覽器使用者）
  user = request.headers.get('X-Forwarded-User')
  if user:
    logger.debug(f'Got user from X-Forwarded-User header: {user}')
    return user

  # 3. Bearer token（來自其他 Databricks Apps 的 M2M OAuth）
  auth_header = request.headers.get('Authorization', '')
  if auth_header.startswith('Bearer '):
    token = auth_header[7:]
    if token:
      try:
        identity = await _resolve_bearer_user(token)
        logger.debug(f'Got user from Bearer token: {identity}')
        return identity
      except Exception as e:
        logger.warning(f'Bearer token identity resolution failed: {e}')
        # 若在開發模式中則繼續回退到開發環境方案

  # 4. 在開發環境回退到 WorkspaceClient
  if _is_local_development():
    return await _get_dev_user()

  # 正式環境中沒有任何身分來源
  raise ValueError(
    'No X-Forwarded-User/X-Forwarded-Email header found, no valid Bearer token, '
    'and not in development mode. Ensure the app is deployed with user authentication enabled.'
  )


async def get_current_token(request: Request) -> str | None:
  """取得目前使用者用於 workspace 操作的 Databricks access token。

  在正式環境（Databricks Apps）中，回傳 None 以使用環境變數中的
  SP OAuth 憑證（由 Databricks Apps 自動設定）。
  在開發環境中，使用 DATABRICKS_TOKEN 環境變數。

  Args:
      request: FastAPI Request 物件

  Returns:
      Access token 字串，或 None 以使用預設憑證
  """
  # 在正式環境中回傳 None，讓 WorkspaceClient 使用環境變數中的 SP OAuth
  if not _is_local_development():
    logger.debug('Production mode: using SP OAuth credentials from environment')
    return None

  # 開發環境回退到環境變數
  token = os.getenv('DATABRICKS_TOKEN')
  if token:
    logger.debug('Got token from DATABRICKS_TOKEN env var')
    return token

  return None


async def get_fmapi_token(request: Request) -> str | None:
  """取得 Databricks Foundation Model API（Claude 端點）所需的 token。

  在正式環境（Databricks Apps）中，使用環境變數中的
  Service Principal 憑證產生新的 OAuth token。
  在開發環境中，使用 DATABRICKS_TOKEN 環境變數。

  Args:
      request: FastAPI Request 物件

  Returns:
      用於 FMAPI 驗證的 access token 字串
  """
  # 在正式環境中，使用 SP 憑證產生 OAuth token
  if not _is_local_development():
    try:
      # 使用會明確設定 OAuth M2M 的輔助函式，避免認證衝突
      client = _get_workspace_client()
      # 呼叫 config 的 authenticate 方法以取得新的 token
      headers = client.config.authenticate()
      if headers and 'Authorization' in headers:
        # 從 "Bearer <token>" 格式中取出 token
        auth_header = headers['Authorization']
        if auth_header.startswith('Bearer '):
          token = auth_header[7:]
          logger.info(f'Got FMAPI token from SP OAuth (length: {len(token)})')
          return token
    except Exception as e:
      logger.warning(f'Failed to get SP OAuth token: {e}')

  # 開發環境回退到環境變數
  token = os.getenv('DATABRICKS_TOKEN')
  if token:
    logger.debug('Got FMAPI token from DATABRICKS_TOKEN env var')
    return token

  return None


async def _resolve_bearer_user(token: str) -> str:
  """透過 Databricks SCIM API 將 Bearer token 解析為使用者身分。

  用於 app-to-app 認證情境：其他 Databricks App 使用
  M2M OAuth Bearer token 呼叫本應用程式 API。透過呼叫
  current_user.me() 來驗證 token，並解析出 service principal 身分。

  結果會快取 5 分鐘（以 token 雜湊為索引），避免對同一個 token
  重複發送 API 呼叫。

  Args:
      token: 來自 Authorization header 的 Bearer token

  Returns:
      token 對應身分的使用者名稱或顯示名稱

  Raises:
      ValueError: 如果無法將 token 解析為身分
  """
  # 使用 token 的 SHA-256 雜湊作為快取鍵（不要儲存原始 token）
  token_hash = hashlib.sha256(token.encode()).hexdigest()

  # 檢查快取
  if token_hash in _bearer_user_cache:
    cached_user, cached_at = _bearer_user_cache[token_hash]
    if time.time() - cached_at < _BEARER_CACHE_TTL:
      logger.debug(f'Using cached Bearer identity: {cached_user}')
      return cached_user
    else:
      # 已過期 - 從快取移除
      del _bearer_user_cache[token_hash]

  # 透過 Databricks API 解析身分（在執行緒池中執行同步 SDK 呼叫）
  identity = await asyncio.to_thread(_fetch_bearer_identity, token)

  # 若快取已滿則移除最舊項目
  if len(_bearer_user_cache) >= _BEARER_CACHE_MAX_SIZE:
    oldest_key = min(_bearer_user_cache, key=lambda k: _bearer_user_cache[k][1])
    del _bearer_user_cache[oldest_key]

  # 快取結果
  _bearer_user_cache[token_hash] = (identity, time.time())
  logger.info(f'Cached Bearer identity: {identity}')

  return identity


def _fetch_bearer_identity(token: str) -> str:
  """同步輔助函式：將 Bearer token 解析為身分。

  Args:
      token: 要解析的 Bearer token

  Returns:
      token 對應身分的使用者名稱或顯示名稱

  Raises:
      ValueError: 如果無法解析 token
  """
  try:
    host = os.environ.get('DATABRICKS_HOST', '')
    client = WorkspaceClient(host=host, token=token)
    me = client.current_user.me()
    identity = me.user_name or me.display_name
    if not identity:
      raise ValueError('Bearer token resolved to user without user_name or display_name')
    return identity
  except Exception as e:
    logger.error(f'Failed to resolve Bearer token identity: {e}')
    raise ValueError(f'Could not resolve Bearer token identity: {e}') from e


async def _get_dev_user() -> str:
  """在開發模式中從 WorkspaceClient 取得使用者 email。"""
  global _dev_user_cache

  if _dev_user_cache is not None:
    logger.debug(f'Using cached dev user: {_dev_user_cache}')
    return _dev_user_cache

  logger.info('Fetching current user from WorkspaceClient')

  # 在執行緒池中執行同步 SDK 呼叫以避免阻塞
  user_email = await asyncio.to_thread(_fetch_user_from_workspace)

  _dev_user_cache = user_email
  logger.info(f'Cached dev user: {user_email}')

  return user_email


def _fetch_user_from_workspace() -> str:
  """同步輔助函式：從 WorkspaceClient 取得使用者。"""
  try:
    # 使用可正確處理 OAuth 與 PAT 認證的輔助函式
    client = _get_workspace_client()
    me = client.current_user.me()

    if not me.user_name:
      raise ValueError('WorkspaceClient returned user without email/user_name')

    return me.user_name

  except Exception as e:
    logger.error(f'Failed to get current user from WorkspaceClient: {e}')
    raise ValueError(f'Could not determine current user: {e}') from e


def get_workspace_url() -> str:
  """取得 Databricks workspace URL。

  會優先使用 DATABRICKS_HOST 環境變數，否則改從 WorkspaceClient 設定讀取。
  結果會快取供後續呼叫重複使用。

  Returns:
      Workspace URL（例如 https://company-dev.cloud.databricks.com）
  """
  global _workspace_url_cache

  if _workspace_url_cache is not None:
    return _workspace_url_cache

  # 優先嘗試環境變數
  host = os.getenv('DATABRICKS_HOST')
  if host:
    _workspace_url_cache = host.rstrip('/')
    logger.debug(f'Got workspace URL from env: {_workspace_url_cache}')
    return _workspace_url_cache

  # 回退到 WorkspaceClient 設定（僅讀取設定，不會發出網路呼叫）
  try:
    client = _get_workspace_client()
    _workspace_url_cache = client.config.host.rstrip('/')
    logger.debug(f'Got workspace URL from WorkspaceClient: {_workspace_url_cache}')
    return _workspace_url_cache
  except Exception as e:
    logger.error(f'Failed to get workspace URL: {e}')
    return ''
