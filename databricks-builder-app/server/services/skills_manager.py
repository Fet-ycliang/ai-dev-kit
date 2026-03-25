"""複製和管理 Databricks 技能的 Skills 管理器。

處理從來源儲存庫複製技能到應用程式及專案目錄。
"""

import json
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill → MCP 工具映射
# 將技能名稱映射到其專屬的 Databricks MCP 工具函式名稱。
# 此處未列出的工具（sql、compute、file、operation tracking）無論
# 啟用哪些技能都始終可用。
# ---------------------------------------------------------------------------
SKILL_TOOL_MAPPING: dict[str, list[str]] = {
  'databricks-agent-bricks': ['manage_ka', 'manage_mas'],
  'databricks-aibi-dashboards': [
    'create_or_update_dashboard', 'get_dashboard',
    'delete_dashboard', 'publish_dashboard',
  ],
  'databricks-genie': [
    'create_or_update_genie', 'get_genie', 'delete_genie', 'ask_genie',
  ],
  'databricks-spark-declarative-pipelines': [
    'create_or_update_pipeline', 'get_pipeline',
    'delete_pipeline', 'run_pipeline',
  ],
  'databricks-model-serving': [
    'get_serving_endpoint_status', 'query_serving_endpoint', 'list_serving_endpoints',
  ],
  'databricks-jobs': [
    'list_jobs', 'get_job', 'find_job_by_name', 'create_job', 'update_job',
    'delete_job', 'run_job_now', 'get_run', 'get_run_output', 'cancel_run',
    'list_runs', 'wait_for_run',
  ],
  'databricks-unity-catalog': [
    'manage_uc_objects', 'manage_uc_grants', 'manage_uc_storage',
    'manage_uc_connections', 'manage_uc_tags', 'manage_uc_security_policies',
    'manage_uc_monitors', 'manage_uc_sharing',
    'list_volume_files', 'upload_to_volume', 'download_from_volume',
    'delete_volume_file', 'delete_volume_directory', 'create_volume_directory',
    'get_volume_file_info',
  ],
  # APX (FastAPI+React) 和 Python (Dash/Streamlit/etc.) 共享相同的
  # 應用程式生命週期工具 — 技能內容不同，非 MCP 操作。
  'databricks-app-apx': [
    'create_or_update_app', 'get_app', 'delete_app',
  ],
  'databricks-app-python': [
    'create_or_update_app', 'get_app', 'delete_app',
  ],
}


def get_allowed_mcp_tools(
  all_tool_names: list[str],
  enabled_skills: list[str] | None = None,
) -> list[str]:
  """根據啟用的技能過濾 MCP 工具名稱。

  映射到停用技能的工具會被移除。未映射到任何技能的工具
  （例如 execute_sql、compute 工具）始終保留。

  Args:
      all_tool_names: 完整的 MCP 工具名稱列表（mcp__databricks__xxx 格式）
      enabled_skills: 啟用的技能名稱列表，或 None 代表所有技能。

  Returns:
      過濾後允許的 MCP 工具名稱列表。
  """
  if enabled_skills is None:
    return all_tool_names

  # 收集屬於停用技能的工具名稱
  enabled_set = set(enabled_skills)
  blocked_tools: set[str] = set()
  for skill_name, tool_names in SKILL_TOOL_MAPPING.items():
    if skill_name not in enabled_set:
      blocked_tools.update(tool_names)

  # 若工具也被啟用的技能宣稱則不阻擋
  for skill_name in enabled_skills:
    for tool_name in SKILL_TOOL_MAPPING.get(skill_name, []):
      blocked_tools.discard(tool_name)

  # 過濾：工具名稱格式為 mcp__databricks__{name}
  prefix = 'mcp__databricks__'
  return [
    t for t in all_tool_names
    if not t.startswith(prefix) or t[len(prefix):] not in blocked_tools
  ]


# 來源技能目錄 - 檢查多個位置
# 1. 此應用程式的兄弟目錄（本地開發）：../../databricks-skills
# 2. 部署位置（Databricks Apps）：應用程式根目錄的 ./skills
_DEV_SKILLS_DIR = Path(__file__).parent.parent.parent.parent / 'databricks-skills'
_DEPLOYED_SKILLS_DIR = Path(__file__).parent.parent.parent / 'skills'

# 此應用程式內的本地技能快取（啟動時複製）
APP_SKILLS_DIR = Path(__file__).parent.parent.parent / 'skills'

# 可用時優先使用開發位置（兄弟 repo）以避免自我刪除：
# APP_SKILLS_DIR == _DEPLOYED_SKILLS_DIR，所以使用 deployed 作為來源會
# 在 copy_skills_to_app() 期間刪除來源。僅在開發來源 repo
# 不可用時才回退到 deployed 位置（實際部署）。
if _DEV_SKILLS_DIR.exists() and any(_DEV_SKILLS_DIR.iterdir()):
  SKILLS_SOURCE_DIR = _DEV_SKILLS_DIR
elif _DEPLOYED_SKILLS_DIR.exists() and any(_DEPLOYED_SKILLS_DIR.iterdir()):
  SKILLS_SOURCE_DIR = _DEPLOYED_SKILLS_DIR
else:
  SKILLS_SOURCE_DIR = _DEV_SKILLS_DIR


def _get_enabled_skills() -> list[str] | None:
  """從環境取得啟用技能的列表。

  Returns:
      要包含的技能名稱列表，或 None 代表包含所有技能
  """
  enabled = os.environ.get('ENABLED_SKILLS', '').strip()
  if not enabled:
    return None
  return [s.strip() for s in enabled.split(',') if s.strip()]


def get_available_skills(enabled_skills: list[str] | None = None) -> list[dict]:
  """取得可用技能及其中繼資料的列表。

  Args:
      enabled_skills: 要包含的技能名稱可選列表。
          若為 None，回傳所有技能。

  Returns:
      每個技能的名稱、描述和路徑的字典列表
  """
  skills = []

  if not APP_SKILLS_DIR.exists():
    logger.warning(f'Skills directory not found: {APP_SKILLS_DIR}')
    return skills

  for skill_dir in APP_SKILLS_DIR.iterdir():
    if not skill_dir.is_dir():
      continue

    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
      continue

    # 解析 frontmatter 以取得名稱與描述
    try:
      content = skill_md.read_text()
      if content.startswith('---'):
        # 擷取 YAML frontmatter
        end_idx = content.find('---', 3)
        if end_idx > 0:
          frontmatter = content[3:end_idx].strip()
          name = None
          description = None

          for line in frontmatter.split('\n'):
            if line.startswith('name:'):
              name = line.split(':', 1)[1].strip().strip('"\'')
            elif line.startswith('description:'):
              description = line.split(':', 1)[1].strip().strip('"\'')

          if name:
            # 若提供 enabled_skills 則過濾
            if enabled_skills is not None and name not in enabled_skills:
              continue
            skills.append({
              'name': name,
              'description': description or '',
              'path': str(skill_dir),
            })
    except Exception as e:
      logger.warning(f'Failed to parse skill {skill_dir}: {e}')

  return skills


class SkillNotFoundError(Exception):
  """當在來源目錄中找不到啟用的技能時引發。"""

  pass


def copy_skills_to_app() -> bool:
  """從來源 repo 複製技能到應用程式的 skills 目錄。

  在伺服器啟動時呼叫以確保我們有最新技能。
  僅複製 ENABLED_SKILLS 環境變數中列出的技能（若已設定）。

  Returns:
      若成功則回傳 True，否則回傳 False

  Raises:
      SkillNotFoundError: 若啟用的技能資料夾不存在或缺少 SKILL.md
  """
  if not SKILLS_SOURCE_DIR.exists():
    logger.warning(f'Skills source directory not found: {SKILLS_SOURCE_DIR}')
    return False

  # 避免自我刪除：在已部署的應用程式中，SKILLS_SOURCE_DIR 與
  # APP_SKILLS_DIR 可能解析到同一個目錄。刪除 APP_SKILLS_DIR
  # 會破壞來源內容。由於 Skills 已就緒，因此略過複製。
  if SKILLS_SOURCE_DIR.resolve() == APP_SKILLS_DIR.resolve():
    logger.info(f'Skills source and app directory are the same ({APP_SKILLS_DIR}), skipping copy')
    return True

  enabled_skills = _get_enabled_skills()
  if enabled_skills:
    logger.info(f'Filtering skills to: {enabled_skills}')

    # 複製前驗證所有啟用的技能是否存在
    for skill_name in enabled_skills:
      skill_path = SKILLS_SOURCE_DIR / skill_name
      skill_md_path = skill_path / 'SKILL.md'

      if not skill_path.exists():
        raise SkillNotFoundError(
          f"Skill '{skill_name}' not found. "
          f"Directory does not exist: {skill_path}. "
          f"Check ENABLED_SKILLS in your .env file."
        )

      if not skill_md_path.exists():
        raise SkillNotFoundError(
          f"Skill '{skill_name}' is invalid. "
          f"Missing SKILL.md file in: {skill_path}. "
          f"Each skill must have a SKILL.md file."
        )

  try:
    # 若存在則移除現有技能目錄
    if APP_SKILLS_DIR.exists():
      shutil.rmtree(APP_SKILLS_DIR)

    # 複製技能目錄（若已設定 ENABLED_SKILLS 則過濾）
    APP_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for item in SKILLS_SOURCE_DIR.iterdir():
      if item.is_dir() and (item / 'SKILL.md').exists():
        # 若不在啟用列表中則跳過（當指定列表時）
        if enabled_skills and item.name not in enabled_skills:
          logger.debug(f'Skipping skill (not enabled): {item.name}')
          continue

        dest = APP_SKILLS_DIR / item.name
        shutil.copytree(item, dest)
        copied_count += 1
        logger.debug(f'Copied skill: {item.name}')

    logger.info(f'Copied {copied_count} skills to {APP_SKILLS_DIR}')
    return True

  except SkillNotFoundError:
    raise  # 重新引發驗證錯誤
  except Exception as e:
    logger.error(f'Failed to copy skills: {e}')
    return False


def copy_skills_to_project(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """複製技能到專案的 .claude/skills 目錄。

  Args:
      project_dir: 專案目錄的路徑
      enabled_skills: 要複製的技能名稱可選列表。
          若為 None，複製所有技能（向後相容）。

  Returns:
      若成功則回傳 True，否則回傳 False
  """
  if not APP_SKILLS_DIR.exists():
    logger.warning('App skills directory not found, trying to copy from source')
    copy_skills_to_app()

  if not APP_SKILLS_DIR.exists():
    logger.warning('No skills available to copy')
    return False

  # 透過將 SKILL.md name 與目錄匹配來建立啟用技能目錄名稱的集合
  enabled_dir_names = None
  if enabled_skills is not None:
    enabled_dir_names = set()
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if not skill_dir.is_dir() or not (skill_dir / 'SKILL.md').exists():
        continue
      skill_name = _parse_skill_name(skill_dir)
      if skill_name and skill_name in enabled_skills:
        enabled_dir_names.add(skill_dir.name)

  try:
    # 在專案中建立 .claude/skills 目錄
    project_skills_dir = project_dir / '.claude' / 'skills'
    project_skills_dir.mkdir(parents=True, exist_ok=True)

    # 複製技能（若設定 enabled_dir_names 則過濾）
    copied_count = 0
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
        if enabled_dir_names is not None and skill_dir.name not in enabled_dir_names:
          continue
        dest = project_skills_dir / skill_dir.name
        if dest.exists():
          shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        copied_count += 1

    logger.info(f'Copied {copied_count} skills to project: {project_dir}')
    return True

  except Exception as e:
    logger.error(f'Failed to copy skills to project: {e}')
    return False


def sync_project_skills(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """同步專案的 skills 目錄以匹配啟用技能列表。

  移除不在啟用列表中的技能並新增缺失的技能。
  對於增量變更比完全清除並重新複製更有效率。

  Args:
      project_dir: 專案目錄的路徑
      enabled_skills: 啟用技能名稱的列表，或 None 代表所有技能

  Returns:
      若成功則回傳 True，否則回傳 False
  """
  if not APP_SKILLS_DIR.exists():
    logger.warning('App skills directory not found')
    return False

  try:
    project_skills_dir = project_dir / '.claude' / 'skills'
    project_skills_dir.mkdir(parents=True, exist_ok=True)

    # 建構映射：skill_name -> app_skills_dir_name
    name_to_dir = {}
    for skill_dir in APP_SKILLS_DIR.iterdir():
      if not skill_dir.is_dir() or not (skill_dir / 'SKILL.md').exists():
        continue
      skill_name = _parse_skill_name(skill_dir)
      if skill_name:
        name_to_dir[skill_name] = skill_dir.name

    # 確定應該存在哪些目錄名稱
    if enabled_skills is not None:
      desired_dirs = {name_to_dir[name] for name in enabled_skills if name in name_to_dir}
    else:
      desired_dirs = set(name_to_dir.values())

    # 移除不應存在的技能
    for existing in project_skills_dir.iterdir():
      if existing.is_dir() and existing.name not in desired_dirs:
        logger.debug(f'Removing disabled skill from project: {existing.name}')
        shutil.rmtree(existing)

    # 新增缺失的技能
    for dir_name in desired_dirs:
      dest = project_skills_dir / dir_name
      if not dest.exists():
        src = APP_SKILLS_DIR / dir_name
        if src.exists():
          logger.debug(f'Adding enabled skill to project: {dir_name}')
          shutil.copytree(src, dest)

    logger.info(f'Synced project skills: {len(desired_dirs)} enabled')
    return True

  except Exception as e:
    logger.error(f'Failed to sync project skills: {e}')
    return False


def _parse_skill_name(skill_dir: Path) -> str | None:
  """從技能目錄的 SKILL.md frontmatter 解析技能名稱。

  Args:
      skill_dir: 技能目錄的路徑

  Returns:
      技能名稱字串，或若無法解析則回傳 None
  """
  skill_md = skill_dir / 'SKILL.md'
  if not skill_md.exists():
    return None
  try:
    content = skill_md.read_text()
    if content.startswith('---'):
      end_idx = content.find('---', 3)
      if end_idx > 0:
        frontmatter = content[3:end_idx].strip()
        for line in frontmatter.split('\n'):
          if line.startswith('name:'):
            return line.split(':', 1)[1].strip().strip('"\'')
  except Exception:
    pass
  return None


def reload_project_skills(project_dir: Path, enabled_skills: list[str] | None = None) -> bool:
  """透過從來源更新為專案重新載入技能。

  此函式：
  1. 從來源 repo 更新應用程式的技能快取
  2. 移除專案現有的技能
  3. 將更新的技能複製到專案（依 enabled_skills 過濾）

  Args:
      project_dir: 專案目錄的路徑
      enabled_skills: 要包含的技能名稱可選列表。
          若為 None，複製所有技能。

  Returns:
      若成功則回傳 True，否則回傳 False
  """
  try:
    # 首先，從來源更新應用程式技能
    logger.info('Refreshing app skills from source...')
    copy_skills_to_app()

    # 移除現有專案技能
    project_skills_dir = project_dir / '.claude' / 'skills'
    if project_skills_dir.exists():
      logger.info(f'Removing existing project skills: {project_skills_dir}')
      shutil.rmtree(project_skills_dir)

    # 複製新技能到專案（依 enabled_skills 過濾）
    logger.info('Copying fresh skills to project...')
    return copy_skills_to_project(project_dir, enabled_skills=enabled_skills)

  except Exception as e:
    logger.error(f'Failed to reload project skills: {e}')
    return False


def get_skills_summary() -> str:
  """取得 system prompt 的可用技能摘要。

  Returns:
      Markdown 格式的技能摘要
  """
  skills = get_available_skills()

  if not skills:
    return ''

  lines = ['## Available Skills', '']
  lines.append('使用 `Skill` 工具來呼叫這些技能以取得專業指導：')
  lines.append('')

  for skill in skills:
    lines.append(f"- **{skill['name']}**: {skill['description']}")

  lines.append('')
  lines.append('要使用技能，請依名稱呼叫（例如 `skill: "sdp"`）。')

  return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 以檔案為基礎的啟用技能儲存（無需 DB migration）
# 儲存位置：project_dir/.claude/enabled_skills.json
# ---------------------------------------------------------------------------

_ENABLED_SKILLS_FILENAME = 'enabled_skills.json'


def get_project_enabled_skills(project_dir: Path) -> list[str] | None:
  """從檔案系統讀取專案的啟用技能列表。

  Returns:
      啟用技能名稱的列表，或 None 若所有技能都已啟用。
  """
  config_path = project_dir / '.claude' / _ENABLED_SKILLS_FILENAME
  if not config_path.exists():
    return None
  try:
    data = json.loads(config_path.read_text())
    if isinstance(data, list):
      return data
    return None
  except (json.JSONDecodeError, OSError) as e:
    logger.warning(f'Failed to read enabled skills config: {e}')
    return None


def set_project_enabled_skills(project_dir: Path, enabled_skills: list[str] | None) -> bool:
  """將專案的啟用技能列表寫入檔案系統。

  Args:
      project_dir: 專案目錄的路徑
      enabled_skills: 要啟用的技能名稱列表，或 None 代表所有技能。

  Returns:
      若成功則回傳 True，否則回傳 False
  """
  claude_dir = project_dir / '.claude'
  config_path = claude_dir / _ENABLED_SKILLS_FILENAME
  try:
    if enabled_skills is None:
      # 所有技能已啟用 — 若設定檔存在則移除
      if config_path.exists():
        config_path.unlink()
    else:
      claude_dir.mkdir(parents=True, exist_ok=True)
      config_path.write_text(json.dumps(enabled_skills, indent=2))
    return True
  except OSError as e:
    logger.error(f'Failed to write enabled skills config: {e}')
    return False
