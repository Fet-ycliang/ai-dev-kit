#!/bin/bash
# 開發環境啟動腳本
# 同時以開發模式執行後端與前端

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

cd "$PROJECT_DIR"

echo "正在啟動開發伺服器..."

# 終止佔用指定埠號的現有程序
echo "正在檢查現有程序..."
# lsof -ti:8000 | xargs kill -9 2>/dev/null || true
# lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

# 先同步主要相依套件以確保 .venv 存在
echo "正在同步相依套件..."
uv sync --quiet

# 安裝同層套件（databricks-tools-core 與 databricks-mcp-server）
echo "正在安裝 Databricks MCP 套件..."
uv pip install -e "$REPO_ROOT/databricks-tools-core" -e "$REPO_ROOT/databricks-mcp-server" --quiet 2>/dev/null || {
  echo "改用 pip 安裝..."
  pip install -e "$REPO_ROOT/databricks-tools-core" -e "$REPO_ROOT/databricks-mcp-server" --quiet
}

# 程序退出時終止背景程序的清理函式
cleanup() {
    echo ""
    echo "正在關閉伺服器..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# 啟動後端
echo "正在啟動後端（http://localhost:8000）..."
uv run uvicorn server.app:app --reload --port 8000 --reload-dir server &
BACKEND_PID=$!

# 等待後端啟動
sleep 2

# 啟動前端
echo "正在啟動前端（http://localhost:3000）..."
cd client

# 若 node_modules 不存在則先安裝
if [ ! -d "node_modules" ]; then
  echo "正在安裝前端相依套件..."
  npm install
fi

npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "開發伺服器執行中："
echo "  後端：  http://localhost:8000"
echo "  前端：  http://localhost:3000"
echo ""
echo "按下 Ctrl+C 可同時停止兩個伺服器"
echo ""

# 等待程序結束
wait
