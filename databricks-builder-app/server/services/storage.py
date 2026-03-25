"""Projects、Conversations 及 Messages 的儲存服務。

使用非同步 SQLAlchemy 提供以使用者為範圍的 CRUD 操作。
"""

import json
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from server.db import Conversation, Execution, Message, Project, session_scope


class ProjectStorage:
  """以使用者為範圍的專案儲存操作。"""

  def __init__(self, user_email: str):
    self.user_email = user_email

  async def get_all(self) -> list[Project]:
    """取得使用者的所有專案，最新的優先。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Project)
        .options(selectinload(Project.conversations))
        .where(Project.user_email == self.user_email)
        .order_by(Project.created_at.desc())
      )
      return list(result.scalars().all())

  async def get(self, project_id: str) -> Optional[Project]:
    """取得特定專案及其 conversations。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Project)
        .options(selectinload(Project.conversations))
        .where(
          Project.id == project_id,
          Project.user_email == self.user_email,
        )
      )
      return result.scalar_one_or_none()

  async def create(self, name: str) -> Project:
    """建立新專案。"""
    async with session_scope() as session:
      project = Project(
        name=name,
        user_email=self.user_email,
      )
      session.add(project)
      await session.flush()
      await session.refresh(project, ['id', 'name', 'user_email', 'created_at'])
      # 將 conversations 初始化為空列表供 to_dict() 使用
      # （不使用 ORM 屬性賦值，它會觸發 lazy load）
      project.__dict__['conversations'] = []
      return project

  async def update_name(self, project_id: str, name: str) -> bool:
    """更新專案名稱。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Project).where(
          Project.id == project_id,
          Project.user_email == self.user_email,
        )
      )
      project = result.scalar_one_or_none()
      if project:
        project.name = name
        return True
      return False

  async def delete(self, project_id: str) -> bool:
    """刪除專案及其所有 conversations。"""
    async with session_scope() as session:
      result = await session.execute(
        delete(Project).where(
          Project.id == project_id,
          Project.user_email == self.user_email,
        )
      )
      return result.rowcount > 0


class ConversationStorage:
  """以專案為範圍的 conversation 儲存操作。"""

  def __init__(self, user_email: str, project_id: str):
    self.user_email = user_email
    self.project_id = project_id

  async def get_all(self) -> list[Conversation]:
    """取得專案的所有 conversations，最新的優先。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .options(selectinload(Conversation.messages))
        .where(
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
        .order_by(Conversation.created_at.desc())
      )
      return list(result.scalars().all())

  async def get(self, conversation_id: str) -> Optional[Conversation]:
    """取得特定 conversation 及其訊息。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .options(selectinload(Conversation.messages))
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      return result.scalar_one_or_none()

  async def create(self, title: str = 'New Conversation') -> Conversation:
    """建立新 conversation。"""
    async with session_scope() as session:
      # 在單一查詢中驗證專案所有權
      project = await session.execute(
        select(Project).where(
          Project.id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      if not project.scalar_one_or_none():
        raise ValueError('Project not found or access denied')

      conversation = Conversation(
        project_id=self.project_id,
        title=title,
      )
      session.add(conversation)
      await session.flush()
      await session.refresh(conversation, ['id', 'project_id', 'title', 'created_at', 'session_id'])
      # 將 messages 初始化為空列表供 to_dict() 使用
      # （不使用 ORM 屬性賦值，它會觸發 lazy load）
      conversation.__dict__['messages'] = []
      return conversation

  async def update_title(self, conversation_id: str, title: str) -> bool:
    """更新 conversation 標題。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.title = title
        return True
      return False

  async def update_session_id(self, conversation_id: str, session_id: str) -> bool:
    """更新 Claude agent session ID 用於恢復 conversations。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.session_id = session_id
        return True
      return False

  async def update_cluster_id(self, conversation_id: str, cluster_id: str | None) -> bool:
    """更新 Databricks cluster ID 用於程式碼執行。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.cluster_id = cluster_id
        return True
      return False

  async def update_catalog_schema(
    self,
    conversation_id: str,
    default_catalog: str | None,
    default_schema: str | None,
  ) -> bool:
    """更新 conversation 的預設 Unity Catalog 上下文。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.default_catalog = default_catalog
        conversation.default_schema = default_schema
        return True
      return False

  async def update_warehouse_id(self, conversation_id: str, warehouse_id: str | None) -> bool:
    """更新 Databricks SQL warehouse ID 用於 SQL 查詢。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.warehouse_id = warehouse_id
        return True
      return False

  async def update_workspace_folder(self, conversation_id: str, workspace_folder: str | None) -> bool:
    """更新 workspace 資料夾用於上傳檔案。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if conversation:
        conversation.workspace_folder = workspace_folder
        return True
      return False

  async def delete(self, conversation_id: str) -> bool:
    """刪除 conversation 及其所有訊息。"""
    async with session_scope() as session:
      # 首先透過 join 驗證所有權，然後刪除
      result = await session.execute(
        select(Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      if not result.scalar_one_or_none():
        return False

      await session.execute(
        delete(Conversation).where(Conversation.id == conversation_id)
      )
      return True

  async def add_message(
    self,
    conversation_id: str,
    role: str,
    content: str,
    is_error: bool = False,
  ) -> Optional[Message]:
    """新增訊息到 conversation。

    同時從第一則使用者訊息自動產生 conversation 標題。
    """
    async with session_scope() as session:
      # 驗證 conversation 存在且使用者擁有專案
      result = await session.execute(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .options(selectinload(Conversation.messages))
        .where(
          Conversation.id == conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      conversation = result.scalar_one_or_none()
      if not conversation:
        return None

      # 建立訊息
      message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        is_error=is_error,
      )
      session.add(message)

      # 從第一則使用者訊息自動產生標題
      if (
        role == 'user'
        and conversation.title == 'New Conversation'
        and len(conversation.messages) == 0
      ):
        # 使用訊息的前 50 字元作為標題
        new_title = content[:50].strip()
        if len(content) > 50:
          new_title += '...'
        conversation.title = new_title

      await session.flush()
      await session.refresh(message)
      return message


class ExecutionStorage:
  """執行狀態儲存以實現 session 獨立性。"""

  def __init__(self, user_email: str, project_id: str, conversation_id: str):
    self.user_email = user_email
    self.project_id = project_id
    self.conversation_id = conversation_id

  async def create(self, execution_id: str) -> Execution:
    """建立新的執行記錄。"""
    async with session_scope() as session:
      # 透過 join 驗證 conversation 所有權
      result = await session.execute(
        select(Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Conversation.id == self.conversation_id,
          Conversation.project_id == self.project_id,
          Project.user_email == self.user_email,
        )
      )
      if not result.scalar_one_or_none():
        raise ValueError('Conversation not found or access denied')

      execution = Execution(
        id=execution_id,
        conversation_id=self.conversation_id,
        project_id=self.project_id,
        status='running',
        events_json='[]',
      )
      session.add(execution)
      await session.flush()
      await session.refresh(execution)
      return execution

  async def get(self, execution_id: str) -> Optional[Execution]:
    """透過 ID 取得執行。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Execution)
        .join(Conversation, Execution.conversation_id == Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Execution.id == execution_id,
          Execution.conversation_id == self.conversation_id,
          Project.user_email == self.user_email,
        )
      )
      return result.scalar_one_or_none()

  async def get_active(self) -> Optional[Execution]:
    """取得此 conversation 的活動（執行中）執行（若有）。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Execution)
        .join(Conversation, Execution.conversation_id == Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Execution.conversation_id == self.conversation_id,
          Execution.status == 'running',
          Project.user_email == self.user_email,
        )
        .order_by(Execution.created_at.desc())
        .limit(1)
      )
      return result.scalar_one_or_none()

  async def get_recent(self, limit: int = 10) -> list[Execution]:
    """取得此 conversation 最近的執行。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Execution)
        .join(Conversation, Execution.conversation_id == Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Execution.conversation_id == self.conversation_id,
          Project.user_email == self.user_email,
        )
        .order_by(Execution.created_at.desc())
        .limit(limit)
      )
      return list(result.scalars().all())

  async def add_events(self, execution_id: str, events: list[dict]) -> bool:
    """將事件附加到執行的事件列表。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Execution)
        .join(Conversation, Execution.conversation_id == Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Execution.id == execution_id,
          Project.user_email == self.user_email,
        )
      )
      execution = result.scalar_one_or_none()
      if not execution:
        return False

      # 載入現有事件並附加新事件
      existing_events = json.loads(execution.events_json) if execution.events_json else []
      existing_events.extend(events)
      execution.events_json = json.dumps(existing_events)
      return True

  async def update_status(
    self,
    execution_id: str,
    status: str,
    error: Optional[str] = None,
  ) -> bool:
    """更新執行狀態。"""
    async with session_scope() as session:
      result = await session.execute(
        select(Execution)
        .join(Conversation, Execution.conversation_id == Conversation.id)
        .join(Project, Conversation.project_id == Project.id)
        .where(
          Execution.id == execution_id,
          Project.user_email == self.user_email,
        )
      )
      execution = result.scalar_one_or_none()
      if not execution:
        return False

      execution.status = status
      if error:
        execution.error = error
      return True


def get_project_storage(user_email: str) -> ProjectStorage:
  """取得使用者的專案儲存。"""
  return ProjectStorage(user_email)


def get_conversation_storage(user_email: str, project_id: str) -> ConversationStorage:
  """取得專案的 conversation 儲存。"""
  return ConversationStorage(user_email, project_id)


def get_execution_storage(user_email: str, project_id: str, conversation_id: str) -> ExecutionStorage:
  """取得 conversation 的執行儲存。"""
  return ExecutionStorage(user_email, project_id, conversation_id)
