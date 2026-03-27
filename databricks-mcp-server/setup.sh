#!/bin/bash
#
# databricks-mcp-server 的設定腳本
# 建立虛擬環境並安裝相依套件
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR=$(dirname ${SCRIPT_DIR})
TOOLS_CORE_DIR="${PARENT_DIR}/databricks-tools-core"
echo AI Dev Kit 目錄: $PARENT_DIR
echo MCP Server 目錄: $SCRIPT_DIR
echo Tools Core 目錄: $TOOLS_CORE_DIR


echo "======================================"
echo "正在設定 Databricks MCP Server"
echo "======================================"
echo ""

# 檢查是否已安裝 uv
if ! command -v uv &> /dev/null; then
    echo "錯誤：尚未安裝 'uv'。"
    echo "安裝方式：curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ 已安裝 uv"

# 檢查 tools-core 目錄是否存在
if [ ! -d "$TOOLS_CORE_DIR" ]; then
    echo "錯誤：在 $TOOLS_CORE_DIR 找不到 databricks-tools-core"
    exit 1
fi
echo "✓ 已找到 databricks-tools-core"


# 建立虛擬環境
echo ""
echo "正在建立虛擬環境..."
uv venv --python 3.11
echo "✓ 已建立虛擬環境"


# 安裝套件
echo ""
echo "正在安裝 databricks-tools-core（editable）..."
uv pip install --python .venv/bin/python -e "$TOOLS_CORE_DIR" --quiet
echo "✓ 已安裝 databricks-tools-core"

echo ""
echo "正在安裝 databricks-mcp-server（editable）..."

uv pip install --python .venv/bin/python -e "$SCRIPT_DIR" --quiet
echo "✓ 已安裝 databricks-mcp-server"

# 驗證
echo ""
echo "正在驗證安裝結果..."
if .venv/bin/python -c "import databricks_mcp_server; print('✓ 已成功匯入 MCP Server')" ; then
    echo ""
    echo "======================================"
    echo "設定完成！"
    echo "======================================"
    echo ""
    echo "啟動 MCP Server："
    echo "  .venv/bin/python run_server.py"
    echo ""
    echo "若要在專案中設定，請將以下內容貼到 .mcp.json（Claude）或 .cursor/mcp.json（Cursor）："
    cat <<EOF
    {
      "mcpServers": {
        "databricks": {
          "command": "${PARENT_DIR}/.venv/bin/python",
          "args": ["${SCRIPT_DIR}/run_server.py"]
        }
      }
    }
EOF
    echo ""
    echo "若要使用 Claude Code CLI 設定："
    echo "  claude mcp add-json databricks '{\"command\":\"$PARENT_DIR/.venv/bin/python\",\"args\":[\"$SCRIPT_DIR/run_server.py\"]}'"
    echo ""
else
    echo "錯誤：無法匯入 databricks_mcp_server"
    exit 1
fi
