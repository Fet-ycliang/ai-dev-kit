"""AI 驅動的對話標題產生器。

使用 Claude 根據使用者的第一則訊息產生簡潔、描述性的對話標題。

支援直接使用 Anthropic API 和 Databricks FMAPI（Foundation Model API）。
在 Databricks Apps 中執行時，使用使用者的 OAuth token 進行驗證。
"""

import asyncio
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


def _get_model() -> str:
  """取得用於標題產生的模型。

  為求效率使用 ANTHROPIC_MODEL_MINI（標題產生是簡單任務）。
  若未設定 mini 則回退至 ANTHROPIC_MODEL。
  """
  return os.environ.get(
    'ANTHROPIC_MODEL_MINI',
    os.environ.get('ANTHROPIC_MODEL', 'databricks-claude-sonnet-4-5')
  )


def _create_client(
  databricks_host: Optional[str] = None,
  databricks_token: Optional[str] = None,
) -> anthropic.AsyncAnthropic:
  """建立針對目前環境設定的 Anthropic client。

  當提供 databricks_host 和 databricks_token 時，設定 client 使用 Databricks FMAPI。
  否則回退至直接使用 Anthropic API。

  Args:
      databricks_host: Databricks workspace URL（例如：https://xxx.cloud.databricks.com）
      databricks_token: 使用者的 Databricks OAuth 或 PAT token

  Returns:
      已設定的 AsyncAnthropic client
  """
  # 檢查是否應使用 Databricks FMAPI
  if databricks_host and databricks_token:
    # 建立 Databricks model serving endpoint URL
    # 格式：https://<workspace>/serving-endpoints/anthropic
    host = databricks_host.replace('https://', '').replace('http://', '').rstrip('/')
    base_url = f'https://{host}/serving-endpoints/anthropic'

    return anthropic.AsyncAnthropic(
      api_key=databricks_token,
      base_url=base_url,
    )

  # 回退至基於環境變數的設定
  api_key = os.environ.get('ANTHROPIC_API_KEY')
  base_url = os.environ.get('ANTHROPIC_BASE_URL')
  auth_token = os.environ.get('ANTHROPIC_AUTH_TOKEN')

  if base_url:
    # 透過環境變數使用 Databricks FMAPI 模式
    return anthropic.AsyncAnthropic(
      api_key=auth_token or api_key or 'unused',
      base_url=base_url,
    )

  # 直接使用 Anthropic API
  return anthropic.AsyncAnthropic(api_key=api_key)


async def generate_title(
  message: str,
  max_length: int = 40,
  databricks_host: Optional[str] = None,
  databricks_token: Optional[str] = None,
) -> str:
  """根據第一則訊息為對話產生簡潔標題。

  Args:
      message: 使用者在對話中的第一則訊息
      max_length: 產生標題的最大長度
      databricks_host: FMAPI 驗證用的選擇性 Databricks workspace URL
      databricks_token: FMAPI 驗證用的選擇性使用者 Databricks token

  Returns:
      簡短、描述性的標題（或截斷訊息作為備用）
  """
  # 備用方案：截斷訊息
  fallback = message[:max_length].strip()
  if len(message) > max_length:
    fallback = fallback.rsplit(' ', 1)[0] + '...'

  try:
    client = _create_client(databricks_host, databricks_token)
    model = _get_model()

    response = await asyncio.wait_for(
      client.messages.create(
        model=model,
        max_tokens=50,
        messages=[
          {
            'role': 'user',
            'content': f'''Generate a very short title (3-6 words max) for this chat message.
The title should capture the main intent/topic. No quotes, no punctuation at the end.

Message: {message[:500]}

Title:''',
          }
        ],
      ),
      timeout=5.0,  # 5 秒逾時
    )

    # 從回應中提取標題
    title = response.content[0].text.strip()

    # 清理：移除引號、限制長度
    title = title.strip('"\'')
    if len(title) > max_length:
      title = title[:max_length].rsplit(' ', 1)[0] + '...'

    return title if title else fallback

  except asyncio.TimeoutError:
    logger.warning('Title generation timed out, using fallback')
    return fallback
  except Exception as e:
    logger.warning(f'Title generation failed: {e}, using fallback')
    return fallback


async def generate_title_async(
  message: str,
  conversation_id: str,
  user_email: str,
  project_id: str,
  databricks_host: Optional[str] = None,
  databricks_token: Optional[str] = None,
) -> None:
  """在背景產生標題並更新對話。

  以 fire-and-forget 模式執行，不會阻塞主回應。

  Args:
      message: 使用者的第一則訊息
      conversation_id: 要更新的對話 ID
      user_email: 用於 storage 存取的使用者電子郵件
      project_id: 用於 storage 存取的專案 ID
      databricks_host: FMAPI 驗證用的選擇性 Databricks workspace URL
      databricks_token: FMAPI 驗證用的選擇性使用者 Databricks token
  """
  try:
    title = await generate_title(
      message,
      databricks_host=databricks_host,
      databricks_token=databricks_token,
    )

    # 更新對話標題
    from .storage import ConversationStorage

    storage = ConversationStorage(user_email, project_id)
    await storage.update_title(conversation_id, title)
    logger.info(f'Updated conversation {conversation_id} title to: {title}')

  except Exception as e:
    logger.warning(f'Failed to update conversation title: {e}')
