"""設定與使用者資訊端點。"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from ..db import get_lakebase_project_id, is_postgres_configured, test_database_connection
from ..services.system_prompt import get_system_prompt
from ..services.user import get_current_user, get_workspace_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/me')
async def get_user_info(request: Request):
  """取得目前使用者資訊與應用程式設定。"""
  user_email = await get_current_user(request)
  workspace_url = get_workspace_url()
  lakebase_configured = is_postgres_configured()
  lakebase_project_id = get_lakebase_project_id()

  # 測試資料庫連線（如已設定）
  lakebase_error = None
  if lakebase_configured:
    lakebase_error = await test_database_connection()

  return {
    'user': user_email,
    'workspace_url': workspace_url,
    'lakebase_configured': lakebase_configured,
    'lakebase_project_id': lakebase_project_id,
    'lakebase_error': lakebase_error,
  }


@router.get('/health')
async def health_check():
  """健康檢查端點。"""
  return {'status': 'healthy'}


@router.get('/system_prompt')
async def get_system_prompt_endpoint(
  cluster_id: Optional[str] = Query(None),
  warehouse_id: Optional[str] = Query(None),
  default_catalog: Optional[str] = Query(None),
  default_schema: Optional[str] = Query(None),
  workspace_folder: Optional[str] = Query(None),
  project_id: Optional[str] = Query(None),
):
  """取得套用當前設定的 system prompt。"""
  enabled_skills = None
  if project_id:
    from ..services.agent import get_project_directory
    from ..services.skills_manager import get_project_enabled_skills
    project_dir = get_project_directory(project_id)
    enabled_skills = get_project_enabled_skills(project_dir)

  prompt = get_system_prompt(
    cluster_id=cluster_id,
    default_catalog=default_catalog,
    default_schema=default_schema,
    warehouse_id=warehouse_id,
    workspace_folder=workspace_folder,
    enabled_skills=enabled_skills,
  )
  return {'system_prompt': prompt}


@router.get('/mlflow/status')
async def mlflow_status_endpoint():
  """取得 MLflow tracing 狀態與設定。

  回傳目前的 MLflow tracing 狀態，包括：
  - tracing 是否啟用（透過 MLFLOW_EXPERIMENT_NAME 環境變數）
  - Tracking URI
  - 目前的實驗資訊
  """
  experiment_name = os.environ.get('MLFLOW_EXPERIMENT_NAME', '')
  tracking_uri = os.environ.get('MLFLOW_TRACKING_URI', 'databricks')

  return {
    'enabled': bool(experiment_name),
    'tracking_uri': tracking_uri,
    'experiment_name': experiment_name,
    'info': 'MLflow tracing is configured via environment variables in app.yaml',
  }
