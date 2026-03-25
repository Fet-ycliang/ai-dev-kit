#!/bin/bash
#
# Databricks Builder App 安裝腳本
# 安裝相依套件並為本機開發環境做好準備
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "  Databricks Builder App 安裝"
echo "=========================================="
echo ""

# ── 檢查前置需求 ──────────────────────────────────────────────────────

# 檢查 uv
if ! command -v uv &> /dev/null; then
    echo "錯誤：未安裝 'uv'。"
    echo "請以下列指令安裝：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ uv 已安裝"

# 檢查 node
if ! command -v node &> /dev/null; then
    echo "錯誤：未安裝 'node'。"
    echo "請從以下位址安裝 Node.js 18+：https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "錯誤：需要 Node.js 18+（目前版本為 $(node -v)）"
    exit 1
fi
echo "✓ Node.js $(node -v) 已安裝"

# 檢查 npm
if ! command -v npm &> /dev/null; then
    echo "錯誤：未安裝 'npm'。"
    exit 1
fi
echo "✓ npm 已安裝"

# ── 環境設定檔 ─────────────────────────────────────────────────────────

echo ""
if [ ! -f "$PROJECT_DIR/.env.local" ]; then
    echo "從 .env.example 建立 .env.local..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env.local"
    echo "✓ 已建立 .env.local"
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  必要動作：請設定您的 .env.local 檔案                          ║"
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║                                                                ║"
    echo "║  開啟 databricks-builder-app/.env.local 並填入下列設定值：     ║"
    echo "║                                                                ║"
    echo "║  1. DATABRICKS_HOST  - 您的工作區 URL                          ║"
    echo "║  2. DATABRICKS_TOKEN - 您的個人存取 Token                      ║"
    echo "║  3. LAKEBASE_PG_URL  - PostgreSQL 連線字串                     ║"
    echo "║     (或 LAKEBASE_ENDPOINT / LAKEBASE_INSTANCE_NAME)            ║"
    echo "║                                                                ║"
    echo "║  所有可用選項請參閱 .env.example。                             ║"
    echo "║                                                                ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    ENV_CREATED=true
else
    echo "✓ .env.local 檔案已存在"
    ENV_CREATED=false
fi

# ── 安裝後端相依套件 ─────────────────────────────────────────────────

echo ""
echo "正在安裝後端相依套件..."
uv sync --quiet
echo "✓ 後端相依套件已安裝"

# ── 安裝同層套件 ─────────────────────────────────────────────────────

echo ""
echo "正在安裝同層套件（databricks-tools-core、databricks-mcp-server）..."
if [ -d "$REPO_ROOT/databricks-tools-core" ] && [ -d "$REPO_ROOT/databricks-mcp-server" ]; then
    uv pip install -e "$REPO_ROOT/databricks-tools-core" -e "$REPO_ROOT/databricks-mcp-server" --quiet
    echo "✓ 同層套件已安裝"
else
    echo "⚠ 找不到同層套件。若您只複製了此目錄，請手動安裝："
    echo "    pip install databricks-tools-core databricks-mcp-server"
fi

# ── 安裝前端相依套件 ────────────────────────────────────────────────

echo ""
echo "正在安裝前端相依套件..."
cd "$PROJECT_DIR/client"
npm install --silent 2>/dev/null || npm install
cd "$SCRIPT_DIR"
echo "✓ 前端相依套件已安裝"

# ── 完成 ─────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  安裝完成！"
echo "=========================================="
echo ""

if [ "$ENV_CREATED" = true ]; then
    echo "後續步驟："
    echo "  1. 編輯 .env.local，填入您的 Databricks 憑證與資料庫設定"
    echo "  2. 執行：./scripts/start_dev.sh"
    echo ""
else
    echo "後續步驟："
    echo "  執行：./scripts/start_dev.sh"
    echo ""
fi

echo "以上指令將啟動："
echo "  後端：  http://localhost:8000"
echo "  前端：  http://localhost:3000"
echo ""
