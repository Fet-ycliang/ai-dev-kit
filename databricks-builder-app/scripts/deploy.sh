#!/bin/bash
# Databricks Builder App 部署腳本
# 將應用程式部署至 Databricks Apps 平台

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 最低需求 Databricks CLI 版本
MIN_CLI_VERSION="0.278.0"

# 腳本目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

# 預設值
APP_NAME="${APP_NAME:-}"
WORKSPACE_PATH=""
STAGING_DIR=""
SKIP_BUILD="${SKIP_BUILD:-false}"

# 使用說明
usage() {
  echo "用法：$0 <app-name> [選項]"
  echo ""
  echo "將 Databricks Builder App 部署至 Databricks Apps 平台。"
  echo ""
  echo "參數："
  echo "  app-name              Databricks App 的名稱（必填）"
  echo ""
  echo "選項："
  echo "  --skip-build          略過前端建置（使用現有建置結果）"
  echo "  --staging-dir DIR     自訂暫存目錄（預設：/tmp/<app-name>-deploy）"
  echo "  -h, --help            顯示此說明訊息"
  echo ""
  echo "前置需求："
  echo "  1. 已設定 Databricks CLI（databricks auth login）"
  echo "  2. 已在 Databricks 建立 App（databricks apps create <app-name>）"
  echo "  3. 已設定 Lakebase（自動擴充：設定 LAKEBASE_ENDPOINT；固定容量：add-resource）"
  echo "  4. 已依您的設定調整 app.yaml"
  echo ""
  echo "範例："
  echo "  $0 my-builder-app"
  echo "  APP_NAME=my-builder-app $0"
  echo "  $0 my-builder-app --skip-build"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    --staging-dir)
      STAGING_DIR="$2"
      shift 2
      ;;
    -*)
      echo -e "${RED}錯誤：未知選項 $1${NC}"
      usage
      exit 1
      ;;
    *)
      if [ -z "$APP_NAME" ]; then
        APP_NAME="$1"
      else
        echo -e "${RED}錯誤：多餘的參數 $1${NC}"
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

# 驗證 App 名稱
if [ -z "$APP_NAME" ]; then
  echo -e "${RED}錯誤：必須指定 App 名稱${NC}"
  echo ""
  usage
  exit 1
fi

# 設定衍生路徑
STAGING_DIR="${STAGING_DIR:-/tmp/${APP_NAME}-deploy}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Databricks Builder App 部署                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  App 名稱：    ${GREEN}${APP_NAME}${NC}"
echo -e "  暫存目錄：    ${STAGING_DIR}"
echo -e "  略過建置：    ${SKIP_BUILD}"
echo ""

# 檢查前置需求
echo -e "${YELLOW}[1/6] 正在檢查前置需求...${NC}"

# 檢查 Databricks CLI
if ! command -v databricks &> /dev/null; then
  echo -e "${RED}錯誤：找不到 Databricks CLI。請以下列指令安裝：curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${NC}"
  exit 1
fi

# 檢查 Databricks CLI 版本
cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$cli_version" ]; then
  if printf '%s\n%s' "$MIN_CLI_VERSION" "$cli_version" | sort -V -C; then
    echo -e "  ${GREEN}✓${NC} Databricks CLI v${cli_version}"
  else
    echo -e "  ${YELLOW}警告：Databricks CLI v${cli_version} 已過舊（最低需求：v${MIN_CLI_VERSION}）${NC}"
    echo -e "  ${BOLD}升級指令：${NC} curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
  fi
else
  echo -e "  ${YELLOW}警告：無法判斷 Databricks CLI 版本${NC}"
fi

# 檢查是否已驗證身份
if ! databricks auth describe &> /dev/null; then
  echo -e "${RED}錯誤：尚未通過 Databricks 驗證。請執行：databricks auth login${NC}"
  exit 1
fi

# 取得工作區資訊（相容新舊 Databricks CLI JSON 格式）
WORKSPACE_HOST=$(databricks auth describe --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
# 新版 CLI 格式：details.host；舊版格式：root
host = data.get('host', '') or data.get('details', {}).get('host', '')
print(host)
" 2>/dev/null || echo "")
if [ -z "$WORKSPACE_HOST" ]; then
  echo -e "${RED}錯誤：無法判斷 Databricks 工作區。請確認驗證狀態。${NC}"
  echo -e "${YELLOW}提示：執行前可設定 DATABRICKS_CONFIG_PROFILE=<profile-name>${NC}"
  echo -e "${YELLOW}     執行 'databricks auth profiles' 查看可用的設定檔${NC}"
  exit 1
fi

# 取得目前使用者，用於工作區路徑
CURRENT_USER=$(databricks current-user me --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
# 相容兩種格式
print(data.get('userName', data.get('user_name', '')))
" 2>/dev/null || echo "")
if [ -z "$CURRENT_USER" ]; then
  echo -e "${RED}錯誤：無法判斷目前使用者。${NC}"
  exit 1
fi

WORKSPACE_PATH="/Workspace/Users/${CURRENT_USER}/apps/${APP_NAME}"
echo -e "  工作區：      ${WORKSPACE_HOST}"
echo -e "  使用者：      ${CURRENT_USER}"
echo -e "  部署路徑：    ${WORKSPACE_PATH}"
echo ""

# 確認 App 存在
echo -e "${YELLOW}[2/6] 確認 App 是否存在...${NC}"
if ! databricks apps get "$APP_NAME" &> /dev/null; then
  echo -e "${RED}錯誤：App '${APP_NAME}' 不存在。${NC}"
  echo -e "請先執行以下指令建立：${GREEN}databricks apps create ${APP_NAME}${NC}"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} App '${APP_NAME}' 已存在"
echo ""

# 建置前端
echo -e "${YELLOW}[3/6] 正在建置前端...${NC}"
cd "$PROJECT_DIR/client"

if [ "$SKIP_BUILD" = true ]; then
  if [ ! -d "out" ]; then
    echo -e "${RED}錯誤：找不到現有建置結果（client/out）。無法略過建置。${NC}"
    exit 1
  fi
  echo -e "  ${GREEN}✓${NC} 使用現有建置結果（--skip-build）"
else
  # 若尚未安裝相依套件則先安裝
  if [ ! -d "node_modules" ]; then
    echo "  正在安裝 npm 相依套件..."
    npm install --silent
  fi
  
  echo "  正在建置正式版套件..."
  npm run build
  echo -e "  ${GREEN}✓${NC} 前端建置完成"
fi
cd "$PROJECT_DIR"
echo ""

# 準備暫存目錄
echo -e "${YELLOW}[4/6] 正在準備部署套件...${NC}"

# 清理並重建暫存目錄
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# 複製伺服器程式碼
echo "  正在複製伺服器程式碼..."
cp -r server "$STAGING_DIR/"
cp app.yaml "$STAGING_DIR/"
cp requirements.txt "$STAGING_DIR/"

# 複製 Alembic 資料庫遷移
echo "  正在複製 Alembic 遷移檔案..."
cp alembic.ini "$STAGING_DIR/"
cp -r alembic "$STAGING_DIR/"

# 複製前端建置結果（伺服器預期路徑為 client/out/）
echo "  正在複製前端建置結果..."
mkdir -p "$STAGING_DIR/client"
cp -r client/out "$STAGING_DIR/client/"

# 複製套件（databricks-tools-core 與 databricks-mcp-server）
echo "  正在複製 Databricks 套件..."
mkdir -p "$STAGING_DIR/packages"

# 複製 databricks-tools-core（僅複製 Python 原始碼，不含測試）
mkdir -p "$STAGING_DIR/packages/databricks_tools_core"
cp -r "$REPO_ROOT/databricks-tools-core/databricks_tools_core/"* "$STAGING_DIR/packages/databricks_tools_core/"

# 複製 databricks-mcp-server（僅複製 Python 原始碼）
mkdir -p "$STAGING_DIR/packages/databricks_mcp_server"
cp -r "$REPO_ROOT/databricks-mcp-server/databricks_mcp_server/"* "$STAGING_DIR/packages/databricks_mcp_server/"

# 透過 install_skills.sh 安裝所有 skills（databricks + MLflow + APX）
echo "  正在透過 install_skills.sh 安裝所有 skills..."
INSTALL_SKILLS_SCRIPT="$REPO_ROOT/databricks-skills/install_skills.sh"
if [ ! -f "$INSTALL_SKILLS_SCRIPT" ]; then
  echo -e "${RED}錯誤：找不到 install_skills.sh（路徑：${INSTALL_SKILLS_SCRIPT}）${NC}"
  exit 1
fi

SKILLS_TEMP_DIR=$(mktemp -d)
trap "rm -rf '$SKILLS_TEMP_DIR'" EXIT

# 建立標記檔，使 install_skills.sh 跳過「非專案根目錄」的提示
touch "$SKILLS_TEMP_DIR/databricks.yml"

# 執行 install_skills.sh 下載所有 skills（databricks、MLflow、APX）
(cd "$SKILLS_TEMP_DIR" && bash "$INSTALL_SKILLS_SCRIPT")

# 將已安裝的 skills 複製至暫存目錄
mkdir -p "$STAGING_DIR/skills"
INSTALLED_SKILLS_DIR="$SKILLS_TEMP_DIR/.claude/skills"
if [ -d "$INSTALLED_SKILLS_DIR" ]; then
  for skill_dir in "$INSTALLED_SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    if [ -f "$skill_dir/SKILL.md" ]; then
      mkdir -p "$STAGING_DIR/skills/$skill_name"
      cp -r "$skill_dir"* "$STAGING_DIR/skills/$skill_name/"
    fi
  done
fi

# 根據已安裝的 skills 動態設定 app.yaml 中的 ENABLED_SKILLS
SKILL_NAMES=""
for skill_dir in "$STAGING_DIR/skills"/*/; do
  [ -d "$skill_dir" ] || continue
  if [ -f "$skill_dir/SKILL.md" ]; then
    name=$(basename "$skill_dir")
    if [ -n "$SKILL_NAMES" ]; then
      SKILL_NAMES="${SKILL_NAMES},${name}"
    else
      SKILL_NAMES="${name}"
    fi
  fi
done
if [ -n "$SKILL_NAMES" ]; then
  echo "  正在更新 ENABLED_SKILLS，共 $(echo "$SKILL_NAMES" | tr ',' '\n' | wc -l | tr -d ' ') 個 skills..."
  python3 -c "
import re, sys
path = sys.argv[1]
skills = sys.argv[2]
with open(path) as f:
    text = f.read()
text = re.sub(
    r'(- name: ENABLED_SKILLS\n\s+value: )\"[^\"]*\"',
    r'\1\"' + skills + '\"',
    text,
)
with open(path, 'w') as f:
    f.write(text)
" "$STAGING_DIR/app.yaml" "$SKILL_NAMES"
  echo -e "  ${GREEN}✓${NC} ENABLED_SKILLS 已更新"
else
  echo -e "  ${YELLOW}警告：未找到可設定至 ENABLED_SKILLS 的 skills${NC}"
fi

# 移除 __pycache__ 目錄
find "$STAGING_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

echo -e "  ${GREEN}✓${NC} 部署套件已準備完成"
echo ""

# 上傳至工作區
echo -e "${YELLOW}[5/6] 正在上傳至 Databricks 工作區...${NC}"
echo "  目標路徑：${WORKSPACE_PATH}"
databricks workspace import-dir "$STAGING_DIR" "$WORKSPACE_PATH" --overwrite 2>&1 | tail -5
echo -e "  ${GREEN}✓${NC} 上傳完成"
echo ""

# 部署 App
echo -e "${YELLOW}[6/6] 正在部署 App...${NC}"
DEPLOY_OUTPUT=$(databricks apps deploy "$APP_NAME" --source-code-path "$WORKSPACE_PATH" 2>&1)
echo "$DEPLOY_OUTPUT"

# 確認部署狀態
if echo "$DEPLOY_OUTPUT" | grep -q '"state":"SUCCEEDED"'; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                 部署成功！                                 ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  
  # 取得 App URL
  APP_INFO=$(databricks apps get "$APP_NAME" --output json 2>/dev/null)
  APP_URL=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', 'N/A'))" 2>/dev/null || echo "N/A")
  
  echo -e "  App URL：${GREEN}${APP_URL}${NC}"
  echo ""
  echo "  後續步驟："
  echo "    1. 在瀏覽器中開啟上方的 App URL"
  echo "    2. 若為首次部署，請設定 Lakebase："
  echo ""
  echo "       自動擴充 Lakebase（建議）："
  echo "         在 app.yaml 中設定 LAKEBASE_ENDPOINT — 無需 add-resource。"
  echo ""
  echo "       固定容量 Lakebase："
  echo "         databricks apps add-resource $APP_NAME --resource-type database \\"
  echo "           --resource-name lakebase --database-instance <instance-name>"
  echo ""

  # 清理舊版部署的來源目錄
  echo -e "${YELLOW}正在清理舊版部署...${NC}"
  SP_CLIENT_ID=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('service_principal_client_id', ''))" 2>/dev/null || echo "")
  CURRENT_DEPLOYMENT_ID=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('active_deployment', {}).get('deployment_id', ''))" 2>/dev/null || echo "")

  if [ -n "$SP_CLIENT_ID" ] && [ -n "$CURRENT_DEPLOYMENT_ID" ]; then
    SP_SRC_PATH="/Workspace/Users/${SP_CLIENT_ID}/src"
    OLD_DIRS=$(databricks workspace list "$SP_SRC_PATH" --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
objects = data if isinstance(data, list) else data.get('objects', [])
current = '$CURRENT_DEPLOYMENT_ID'
for obj in objects:
    path = obj.get('path', '')
    name = path.rsplit('/', 1)[-1] if '/' in path else path
    if name != current and obj.get('object_type', '') == 'DIRECTORY':
        print(path)
" 2>/dev/null || echo "")

    if [ -n "$OLD_DIRS" ]; then
      CLEANED=0
      while IFS= read -r dir_path; do
        if databricks workspace delete "$dir_path" --recursive 2>/dev/null; then
          CLEANED=$((CLEANED + 1))
        fi
      done <<< "$OLD_DIRS"
      echo -e "  ${GREEN}✓${NC} 已移除 $CLEANED 個舊版部署"
    else
      echo -e "  ${GREEN}✓${NC} 無需清理舊版部署"
    fi
  else
    echo -e "  ${YELLOW}⚠${NC} 無法取得部署資訊，略過清理"
  fi
  echo ""
else
  echo ""
  echo -e "${RED}部署可能發生問題，請確認上方輸出訊息。${NC}"
  exit 1
fi
