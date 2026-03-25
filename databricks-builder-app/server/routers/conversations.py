"""對話管理端點。

所有端點都限定在目前已認證的使用者與專案範圍內。
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.storage import ConversationStorage
from ..services.user import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateConversationRequest(BaseModel):
  """建立新對話的請求。"""

  title: str = 'New Conversation'


class UpdateConversationRequest(BaseModel):
  """更新對話的請求。"""

  title: str


@router.get('/projects/{project_id}/conversations')
async def get_all_conversations(request: Request, project_id: str):
  """取得專案的所有對話，依 created_at 排序（最新在前）。"""
  user_email = await get_current_user(request)
  storage = ConversationStorage(user_email, project_id)

  logger.info(f'Fetching all conversations for project {project_id}, user: {user_email}')
  conversations = await storage.get_all()
  logger.info(f'Retrieved {len(conversations)} conversations for project {project_id}')

  return [conv.to_dict_summary() for conv in conversations]


@router.get('/projects/{project_id}/conversations/{conversation_id}')
async def get_conversation(request: Request, project_id: str, conversation_id: str):
  """依 ID 取得特定對話及其所有訊息。"""
  user_email = await get_current_user(request)
  storage = ConversationStorage(user_email, project_id)

  logger.info(f'Fetching conversation {conversation_id} for project {project_id}')

  conversation = await storage.get(conversation_id)
  if not conversation:
    logger.warning(f'Conversation not found: {conversation_id}')
    raise HTTPException(status_code=404, detail=f'Conversation {conversation_id} not found')

  logger.info(
    f'Retrieved conversation {conversation_id} with {len(conversation.messages)} messages'
  )
  return conversation.to_dict()


@router.post('/projects/{project_id}/conversations')
async def create_conversation(request: Request, project_id: str, body: CreateConversationRequest):
  """在專案中建立新對話。"""
  user_email = await get_current_user(request)
  storage = ConversationStorage(user_email, project_id)

  logger.info(f'Creating conversation in project {project_id} for user: {user_email}')

  try:
    conversation = await storage.create(title=body.title)
    logger.info(f'Created conversation {conversation.id} in project {project_id}')
    return conversation.to_dict()
  except ValueError as e:
    logger.warning(f'Failed to create conversation: {e}')
    raise HTTPException(status_code=404, detail=str(e))


@router.patch('/projects/{project_id}/conversations/{conversation_id}')
async def update_conversation(
  request: Request,
  project_id: str,
  conversation_id: str,
  body: UpdateConversationRequest,
):
  """更新對話的標題。"""
  user_email = await get_current_user(request)
  storage = ConversationStorage(user_email, project_id)

  logger.info(f'Updating conversation {conversation_id} in project {project_id}')

  success = await storage.update_title(conversation_id, body.title)
  if not success:
    logger.warning(f'Conversation not found for update: {conversation_id}')
    raise HTTPException(status_code=404, detail=f'Conversation {conversation_id} not found')

  logger.info(f'Updated conversation {conversation_id}')
  return {'success': True, 'conversation_id': conversation_id}


@router.delete('/projects/{project_id}/conversations/{conversation_id}')
async def delete_conversation(request: Request, project_id: str, conversation_id: str):
  """刪除對話及其所有訊息。"""
  user_email = await get_current_user(request)
  storage = ConversationStorage(user_email, project_id)

  logger.info(f'Deleting conversation {conversation_id} from project {project_id}')

  success = await storage.delete(conversation_id)
  if not success:
    logger.warning(f'Conversation not found for deletion: {conversation_id}')
    raise HTTPException(status_code=404, detail=f'Conversation {conversation_id} not found')

  logger.info(f'Deleted conversation {conversation_id}')
  return {'success': True, 'deleted_conversation_id': conversation_id}
