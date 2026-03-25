#!/bin/bash
#
# databricks-mcp-server 的設定腳本
# 建立虛擬環境並安裝相依套件
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR=$(dirname ${SCRIPT_DIR})
TOOLS_CORE_DIR="${PARENT_DIR}/databricks-tools-core"
echo AI Dev Kit directory: $PARENT_DIR
echo MCP Server directory: $SCRIPT_DIR
echo Tools Core directory: $TOOLS_CORE_DIR


echo "======================================"
echo "Setting up Databricks MCP Server"
echo "======================================"
echo ""

# 檢查是否已安裝 uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ uv is installed"

# 檢查 tools-core 目錄是否存在
if [ ! -d "$TOOLS_CORE_DIR" ]; then
    echo "Error: databricks-tools-core not found at $TOOLS_CORE_DIR"
    exit 1
fi
echo "✓ databricks-tools-core found"


# 建立虛擬環境
echo ""
echo "Creating virtual environment..."
uv venv --python 3.11
echo "✓ Virtual environment created"


# 安裝套件
echo ""
echo "Installing databricks-tools-core (editable)..."
uv pip install --python .venv/bin/python -e "$TOOLS_CORE_DIR" --quiet
echo "✓ databricks-tools-core installed"

echo ""
echo "Installing databricks-mcp-server (editable)..."

uv pip install --python .venv/bin/python -e "$SCRIPT_DIR" --quiet
echo "✓ databricks-mcp-server installed"

# 驗證
echo ""
echo "Verifying installation..."
if .venv/bin/python -c "import databricks_mcp_server; print('✓ MCP server can be imported')"; then
    echo ""
    echo "======================================"
    echo "Setup complete!"
    echo "======================================"
    echo ""
    echo "To run the MCP server:"
    echo "  .venv/bin/python run_server.py"
    echo ""
    echo "To setup in the project, paste this into .mcp.json (Claude) or .cursor/mcp.json (Cursor):"
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
    echo "To setup with Claude Code CLI:"
    echo "  claude mcp add-json databricks '{\"command\":\"$PARENT_DIR/.venv/bin/python\",\"args\":[\"$SCRIPT_DIR/run_server.py\"]}'"
    echo ""
else
    echo "Error: Failed to import databricks_mcp_server"
    exit 1
fi
