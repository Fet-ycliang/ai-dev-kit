"""Skill 探索與管理 API 端點。"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..services import (
  get_available_skills,
  get_project_directory,
  get_project_enabled_skills,
  reload_project_skills,
  set_project_enabled_skills,
  sync_project_skills,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class UpdateEnabledSkillsRequest(BaseModel):
  """更新專案啟用 skill 的請求。"""

  enabled_skills: list[str] | None = None  # None 代表啟用所有 skill


def _get_skills_dir(project_id: str) -> Path:
  """取得專案的 skill 目錄。"""
  project_dir = get_project_directory(project_id)
  return project_dir / '.claude' / 'skills'


def _build_tree_node(path: Path, base_path: Path) -> dict:
  """建立檔案或目錄的樹狀結構節點。"""
  relative_path = str(path.relative_to(base_path))
  name = path.name

  if path.is_dir():
    children = []
    # 排序：目錄在前、檔案在後，依字母順序
    items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    for item in items:
      # 跳過隱藏檔案與 __pycache__
      if item.name.startswith('.') or item.name == '__pycache__':
        continue
      children.append(_build_tree_node(item, base_path))
    return {
      'name': name,
      'path': relative_path,
      'type': 'directory',
      'children': children,
    }
  else:
    return {
      'name': name,
      'path': relative_path,
      'type': 'file',
    }


@router.get('/projects/{project_id}/skills/tree')
async def get_skills_tree(project_id: str):
  """取得專案的 skill 目錄樹狀結構。"""
  skills_dir = _get_skills_dir(project_id)

  if not skills_dir.exists():
    return {'tree': []}

  tree = []
  items = sorted(skills_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))

  for item in items:
    if item.name.startswith('.'):
      continue
    tree.append(_build_tree_node(item, skills_dir))

  return {'tree': tree}


@router.get('/projects/{project_id}/skills/file')
async def get_skill_file(
  project_id: str,
  path: str = Query(..., description='skill 資料夾中的檔案相對路徑'),
):
  """取得 skill 檔案的內容。"""
  skills_dir = _get_skills_dir(project_id)

  try:
    requested_path = (skills_dir / path).resolve()

    if not str(requested_path).startswith(str(skills_dir.resolve())):
      raise HTTPException(status_code=403, detail='Access denied: path outside skills directory')

    if not requested_path.exists():
      raise HTTPException(status_code=404, detail='File not found')

    if not requested_path.is_file():
      raise HTTPException(status_code=400, detail='Path is not a file')

    content = requested_path.read_text(encoding='utf-8')
    return {
      'path': path,
      'content': content,
      'filename': requested_path.name,
    }

  except HTTPException:
    raise
  except Exception as e:
    logger.error(f'Failed to read skill file: {e}')
    raise HTTPException(status_code=500, detail=f'Failed to read file: {str(e)}')


@router.get('/projects/{project_id}/skills/available')
async def get_available_skills_for_project(project_id: str):
  """取得專案所有可用的 skill 及其啟用/停用狀態。"""
  project_dir = get_project_directory(project_id)
  enabled_skills = get_project_enabled_skills(project_dir)

  # 從應用程式快取中取得所有 skill（未過濾）
  all_skills = get_available_skills()

  result = []
  for skill in all_skills:
    result.append({
      'name': skill['name'],
      'description': skill['description'],
      'enabled': enabled_skills is None or skill['name'] in enabled_skills,
    })

  enabled_count = len(result) if enabled_skills is None else sum(1 for s in result if s['enabled'])

  return {
    'skills': result,
    'all_enabled': enabled_skills is None,
    'enabled_count': enabled_count,
    'total_count': len(result),
  }


@router.put('/projects/{project_id}/skills/enabled')
async def update_enabled_skills(project_id: str, body: UpdateEnabledSkillsRequest):
  """更新專案的啟用 skill 清單。

  將 enabled_skills 設為 null 會重新啟用所有 skill。
  更新後會同步專案的 .claude/skills 目錄。
  """
  project_dir = get_project_directory(project_id)

  # 寫入檔案系統
  success = set_project_enabled_skills(project_dir, body.enabled_skills)
  if not success:
    raise HTTPException(status_code=500, detail='Failed to update enabled skills')

  # 同步專案的 skill 目錄
  sync_project_skills(project_dir, body.enabled_skills)

  return {
    'success': True,
    'enabled_skills': body.enabled_skills,
    'all_enabled': body.enabled_skills is None,
  }


@router.post('/projects/{project_id}/skills/reload')
async def reload_skills(project_id: str):
  """重新載入專案的 skill（遵循已啟用的 skill 設定）。"""
  try:
    project_dir = get_project_directory(project_id)
    enabled_skills = get_project_enabled_skills(project_dir)

    success = reload_project_skills(project_dir, enabled_skills=enabled_skills)

    if success:
      return {'success': True, 'message': 'Skills reloaded successfully'}
    else:
      raise HTTPException(status_code=500, detail='Failed to reload skills')

  except HTTPException:
    raise
  except Exception as e:
    logger.error(f'Failed to reload skills: {e}')
    raise HTTPException(status_code=500, detail=f'Failed to reload skills: {str(e)}')
