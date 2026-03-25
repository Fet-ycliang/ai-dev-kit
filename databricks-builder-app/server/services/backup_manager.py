"""專案檔案的備份管理服務。

處理專案資料夾的壓縮並從 PostgreSQL 儲存/還原。
執行背景迴圈每 10 分鐘處理待備份項目。
"""

import asyncio
import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..db.database import session_scope
from ..db.models import ProjectBackup

logger = logging.getLogger(__name__)

# 設定
BACKUP_INTERVAL = 600  # 10 分鐘
PROJECTS_BASE_DIR = os.getenv('PROJECTS_BASE_DIR', './projects')

# 需要備份的 project ID 記憶體佇列
_backup_queue: set[str] = set()
_backup_task: Optional[asyncio.Task] = None


def mark_for_backup(project_id: str) -> None:
  """標記專案進行備份。

  在 agent query 完成後呼叫。專案將在下一個備份迴圈中備份。

  Args:
      project_id: 要備份的 project UUID
  """
  _backup_queue.add(project_id)
  logger.debug(f'Project {project_id} marked for backup')


async def create_backup(project_id: str) -> bool:
  """建立專案資料夾的備份。

  壓縮專案目錄中的所有檔案並儲存到資料庫。

  Args:
      project_id: 要備份的 project UUID

  Returns:
      若備份已建立則回傳 True，若專案資料夾不存在則回傳 False
  """
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id

  if not project_dir.exists():
    logger.warning(f'Project directory does not exist: {project_dir}')
    return False

  # 在記憶體中建立 zip
  buffer = BytesIO()
  file_count = 0

  with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
    for file_path in project_dir.rglob('*'):
      if file_path.is_file():
        arcname = str(file_path.relative_to(project_dir))
        zf.write(file_path, arcname)
        file_count += 1

  if file_count == 0:
    logger.debug(f'Project {project_id} has no files to backup')
    return False

  backup_data = buffer.getvalue()

  # Upsert 到資料庫（INSERT ON CONFLICT UPDATE）
  async with session_scope() as session:
    stmt = insert(ProjectBackup).values(
      project_id=project_id,
      backup_data=backup_data,
    )
    stmt = stmt.on_conflict_do_update(
      index_elements=['project_id'],
      set_={'backup_data': backup_data, 'updated_at': ProjectBackup.updated_at.default.arg()},
    )
    await session.execute(stmt)

  logger.info(f'Backed up project {project_id} ({file_count} files, {len(backup_data)} bytes)')
  return True


async def restore_backup(project_id: str) -> bool:
  """從備份還原專案。

  從資料庫下載 zip 並解壓縮到專案目錄。

  Args:
      project_id: 要還原的 project UUID

  Returns:
      若已還原則回傳 True，若無備份存在則回傳 False
  """
  async with session_scope() as session:
    result = await session.execute(
      select(ProjectBackup.backup_data).where(ProjectBackup.project_id == project_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
      logger.debug(f'No backup found for project {project_id}')
      return False

    backup_data = row

  # 建立專案目錄
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id
  project_dir.mkdir(parents=True, exist_ok=True)

  # 解壓縮 zip
  buffer = BytesIO(backup_data)
  with zipfile.ZipFile(buffer, 'r') as zf:
    zf.extractall(project_dir)

  logger.info(f'Restored project {project_id} from backup')
  return True


def _create_default_claude_md(project_dir: Path) -> None:
  """為新專案建立預設的 CLAUDE.md 檔案。

  Args:
      project_dir: 專案目錄的路徑
  """
  claude_md_path = project_dir / 'CLAUDE.md'
  if claude_md_path.exists():
    return

  default_content = """# Project Context

This file tracks the Databricks resources created in this project.
The AI assistant will update this file as resources are created.

## Configuration

- **Catalog:** (not yet configured)
- **Schema:** (not yet configured)

## Resources Created

### Tables
(none yet)

### Volumes
(none yet)

### Pipelines
(none yet)

### Jobs
(none yet)

## Notes

Add any project-specific notes or context here.
"""

  try:
    claude_md_path.write_text(default_content)
    logger.info(f'Created default CLAUDE.md in {project_dir}')
  except Exception as e:
    logger.warning(f'Failed to create CLAUDE.md: {e}')


def ensure_project_directory(project_id: str) -> Path:
  """確保專案目錄存在，必要時從備份還原。

  這是取得專案目錄的主要入口點。
  若目錄不存在，嘗試從備份還原。
  若無備份存在，建立空目錄。
  同時確保技能已複製到專案且 CLAUDE.md 存在。

  Args:
      project_id: Project UUID

  Returns:
      專案目錄的路徑
  """
  from .skills_manager import copy_skills_to_project

  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id
  needs_skills = not project_dir.exists() or not (project_dir / '.claude' / 'skills').exists()
  is_new_project = not project_dir.exists()

  if not project_dir.exists():
    # 嘗試從備份還原
    try:
      loop = asyncio.get_event_loop()
      if loop.is_running():
        # 我們在非同步上下文中，建立新任務
        future = asyncio.ensure_future(restore_backup(project_id))
        # 這是從非同步程式碼呼叫的同步函式，我們需要處理這個
        # 目前只建立目錄 - 還原將非同步進行
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f'Created empty project directory: {project_dir}')
      else:
        restored = loop.run_until_complete(restore_backup(project_id))
        if not restored:
          project_dir.mkdir(parents=True, exist_ok=True)
          logger.debug(f'Created empty project directory: {project_dir}')
    except RuntimeError:
      # 無 event loop，使用 asyncio.run
      restored = asyncio.run(restore_backup(project_id))
      if not restored:
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f'Created empty project directory: {project_dir}')

  # 必要時複製技能到專案
  if needs_skills:
    copy_skills_to_project(project_dir)

  # 為新專案建立預設 CLAUDE.md（或若不存在）
  if is_new_project or not (project_dir / 'CLAUDE.md').exists():
    _create_default_claude_md(project_dir)

  return project_dir


async def ensure_project_directory_async(project_id: str) -> Path:
  """ensure_project_directory 的非同步版本。

  Args:
      project_id: Project UUID

  Returns:
      專案目錄的路徑
  """
  project_dir = Path(PROJECTS_BASE_DIR).resolve() / project_id

  if not project_dir.exists():
    restored = await restore_backup(project_id)
    if not restored:
      project_dir.mkdir(parents=True, exist_ok=True)
      logger.debug(f'Created empty project directory: {project_dir}')

  return project_dir


async def _backup_loop() -> None:
  """背景迴圈每 10 分鐘處理待備份項目。"""
  logger.info(f'Backup worker started (interval: {BACKUP_INTERVAL}s)')

  while True:
    await asyncio.sleep(BACKUP_INTERVAL)

    if not _backup_queue:
      continue

    # 取得並清除待備份項目
    pending = _backup_queue.copy()
    _backup_queue.clear()

    logger.info(f'Processing {len(pending)} pending backups')

    for project_id in pending:
      try:
        await create_backup(project_id)
      except Exception as e:
        logger.error(f'Backup failed for project {project_id}: {e}')


def start_backup_worker() -> None:
  """啟動背景備份迴圈。

  應在應用程式啟動時呼叫。
  """
  global _backup_task
  _backup_task = asyncio.create_task(_backup_loop())
  logger.info('Backup worker task created')


def stop_backup_worker() -> None:
  """停止背景備份迴圈。

  應在應用程式關閉時呼叫。
  """
  global _backup_task
  if _backup_task:
    _backup_task.cancel()
    logger.info('Backup worker stopped')
