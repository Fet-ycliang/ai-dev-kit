#!/bin/bash
#
# Databricks AI Dev Kit - 統一安裝程式
#
# 安裝 skills、MCP 伺服器及設定，支援 Claude Code、Cursor、OpenAI Codex、GitHub Copilot、Gemini CLI 及 Antigravity。
#
# 用法：bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) [OPTIONS]
#
# 範例：
#   # 基本安裝（專案範圍，互動提示，使用最新版本）
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh)
#
#   # 全域安裝並強制重新安裝
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --global --force
#
#   # 指定 profile 並強制重新安裝
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --profile DEFAULT --force
#
#   # 僅安裝指定工具
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --tools cursor,codex,copilot,gemini
#
#   # 僅安裝 Skills（略過 MCP 伺服器）
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --skills-only
#
#   # 安裝指定 profile 的 skills
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --skills-profile data-engineer
#
#   # 安裝多個 profiles
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --skills-profile data-engineer,ai-ml-engineer
#
#   # 僅安裝指定 skills
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --skills databricks-jobs,databricks-dbsql
#
#   # 列出可用的 skills 及設定檔
#   bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --list-skills
#
# 替代方式：使用環境變數
#   DEVKIT_TOOLS=cursor curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh | bash
#   DEVKIT_FORCE=true DEVKIT_PROFILE=DEFAULT curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh | bash
#

set -e

# 預設值（可由環境變數或命令列參數覆蓋）
PROFILE="${DEVKIT_PROFILE:-DEFAULT}"
SCOPE="${DEVKIT_SCOPE:-project}"
SCOPE_EXPLICIT=false  # 追蹤是否明確傳入 --global
FORCE="${DEVKIT_FORCE:-false}"
IS_UPDATE=false
SILENT="${DEVKIT_SILENT:-false}"
TOOLS="${DEVKIT_TOOLS:-}"
USER_TOOLS=""
USER_MCP_PATH="${DEVKIT_MCP_PATH:-}"
SKILLS_PROFILE="${DEVKIT_SKILLS_PROFILE:-}"
USER_SKILLS="${DEVKIT_SKILLS:-}"

# 將環境變數的字串布林值轉換為實際布林值
[ "$FORCE" = "true" ] || [ "$FORCE" = "1" ] && FORCE=true || FORCE=false
[ "$SILENT" = "true" ] || [ "$SILENT" = "1" ] && SILENT=true || SILENT=false

# 檢查 scope 是否透過環境變數明確設定
[ -n "${DEVKIT_SCOPE:-}" ] && SCOPE_EXPLICIT=true

OWNER="Fet-ycliang"
REPO="ai-dev-kit"

if [ -n "${DEVKIT_BRANCH:-}" ]; then
  BRANCH="$DEVKIT_BRANCH"
else
  BRANCH="$(
    curl -s "https://api.github.com/repos/${OWNER}/${REPO}/releases/latest" \
    | grep '"tag_name"' \
    | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/'
  )"
  # 若無法取得最新版本，回退至 main
  [ -z "$BRANCH" ] && BRANCH="main"
fi

# 安裝模式預設值
INSTALL_MCP=true
INSTALL_SKILLS=true

# 最低版本需求
MIN_CLI_VERSION="0.278.0"
MIN_SDK_VERSION="0.85.0"

# 顏色設定
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' BL='\033[0;34m' B='\033[1m' D='\033[2m' N='\033[0m'

# Databricks skills（打包於 repo 中）
SKILLS="databricks-agent-bricks databricks-ai-functions databricks-aibi-dashboards databricks-app-python databricks-bundles databricks-config databricks-dbsql databricks-docs databricks-genie databricks-iceberg databricks-jobs databricks-lakebase-autoscale databricks-lakebase-provisioned databricks-metric-views databricks-mlflow-evaluation databricks-model-serving databricks-python-sdk databricks-spark-declarative-pipelines databricks-spark-structured-streaming databricks-synthetic-data-gen databricks-unity-catalog databricks-unstructured-pdf-generation databricks-vector-search databricks-zerobus-ingest spark-python-data-source"

# MLflow skills（從 mlflow/skills repo 下載）
MLFLOW_SKILLS="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
MLFLOW_RAW_URL="https://raw.githubusercontent.com/mlflow/skills/main"

# APX skills（從 Fet-ycliang/apx repo 下載）
APX_SKILLS="databricks-app-apx"
APX_RAW_URL="https://raw.githubusercontent.com/Fet-ycliang/apx/main/skills/apx"

# ─── Skill 設定檔 ──────────────────────────────────────────
# 無論選擇哪個 profile，核心 skills 一定安裝
CORE_SKILLS="databricks-config databricks-docs databricks-python-sdk databricks-unity-catalog"

# Profile 定義（僅非核心 skills──核心 skills 一定加入）
PROFILE_DATA_ENGINEER="databricks-spark-declarative-pipelines databricks-spark-structured-streaming databricks-jobs databricks-bundles databricks-dbsql databricks-iceberg databricks-zerobus-ingest spark-python-data-source databricks-metric-views databricks-synthetic-data-gen"
PROFILE_ANALYST="databricks-aibi-dashboards databricks-dbsql databricks-genie databricks-metric-views"
PROFILE_AIML_ENGINEER="databricks-agent-bricks databricks-ai-functions databricks-vector-search databricks-model-serving databricks-genie databricks-unstructured-pdf-generation databricks-mlflow-evaluation databricks-synthetic-data-gen databricks-jobs"
PROFILE_AIML_MLFLOW="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
PROFILE_APP_DEVELOPER="databricks-app-python databricks-app-apx databricks-lakebase-autoscale databricks-lakebase-provisioned databricks-model-serving databricks-dbsql databricks-jobs databricks-bundles"

# 已選取的 skills（在 profile 選取期間填入）
SELECTED_SKILLS=""
SELECTED_MLFLOW_SKILLS=""
SELECTED_APX_SKILLS=""

# 輸出輔助函式
msg()  { [ "$SILENT" = true ] || echo -e "  $*"; }
ok()   { [ "$SILENT" = true ] || echo -e "  ${G}✓${N} $*"; }
warn() { [ "$SILENT" = true ] || echo -e "  ${Y}!${N} $*"; }
die()  { echo -e "  ${R}✗${N} $*" >&2; exit 1; }  # 一律顯示錯誤
step() { [ "$SILENT" = true ] || echo -e "\n${B}$*${N}"; }

# 解析參數
while [ $# -gt 0 ]; do
    case $1 in
        -p|--profile)     PROFILE="$2"; shift 2 ;;
        -g|--global)      SCOPE="global"; SCOPE_EXPLICIT=true; shift ;;
        -b|--branch)      BRANCH="$2"; shift 2 ;;
        --skills-only)    INSTALL_MCP=false; shift ;;
        --mcp-only)       INSTALL_SKILLS=false; shift ;;
        --mcp-path)       USER_MCP_PATH="$2"; shift 2 ;;
        --skills-profile) SKILLS_PROFILE="$2"; shift 2 ;;
        --skills)         USER_SKILLS="$2"; shift 2 ;;
        --list-skills)    LIST_SKILLS=true; shift ;;
        --silent)         SILENT=true; shift ;;
        --tools)          USER_TOOLS="$2"; shift 2 ;;
        -f|--force)       FORCE=true; shift ;;
        -h|--help)        
            echo "Databricks AI Dev Kit 安裝程式"
            echo ""
            echo "Usage: bash <(curl -sL .../install.sh) [OPTIONS]"
            echo ""
            echo "選項："
            echo "  -p, --profile NAME    Databricks profile（預設：DEFAULT）"
            echo "  -b, --branch NAME     要安裝的 Git 分支/標籤（預設：最新版本）"
            echo "  -g, --global          全域安裝（適用所有專案）"
            echo "  --skills-only         略過 MCP 伺服器設定"
            echo "  --mcp-only            略過 Skills 安裝"
            echo "  --mcp-path PATH       MCP 伺服器安裝路徑（預設：~/.ai-dev-kit）"
            echo "  --silent              靜默模式（僅顯示錯誤）"
            echo "  --tools LIST          以逗號分隔：claude,cursor,copilot,codex,gemini,antigravity"
            echo "  --skills-profile LIST 以逗號分隔的設定檔：all,data-engineer,analyst,ai-ml-engineer,app-developer"
            echo "  --skills LIST         以逗號分隔的 skill 名稱（覆蓋設定檔）"
            echo "  --list-skills         列出可用的 skills 及設定檔後離開"
            echo "  -f, --force           強制重新安裝"
            echo "  -h, --help            顯示此說明"
            echo ""
            echo "環境變數（旗標的替代方式）："
            echo "  DEVKIT_PROFILE        Databricks 設定 profile"
            echo "  DEVKIT_BRANCH         要安裝的 Git 分支/標籤（預設：最新版本）"
            echo "  DEVKIT_SCOPE          'project' 或 'global'"
            echo "  DEVKIT_TOOLS          以逗號分隔的工具清單"
            echo "  DEVKIT_FORCE          設定為 'true' 強制重新安裝"
            echo "  DEVKIT_MCP_PATH       MCP 伺服器安裝路徑"
            echo "  DEVKIT_SKILLS_PROFILE 以逗號分隔的 skill 設定檔"
            echo "  DEVKIT_SKILLS         以逗號分隔的 skill 名稱"
            echo "  DEVKIT_SILENT         設定為 'true' 啟用靜默模式"
            echo "  AIDEVKIT_HOME         安裝目錄（預設：~/.ai-dev-kit）"
            echo ""
            echo "範例："
            echo "  # 使用環境變數"
            echo "  DEVKIT_TOOLS=cursor curl -sL .../install.sh | bash"
            echo ""
            exit 0 ;;
        *) die "未知選項：$1（使用 -h 取得說明）" ;;
    esac
done

# ─── --list-skills 處理器 ─────────────────────────────────────
if [ "${LIST_SKILLS:-false}" = true ]; then
    echo ""
    echo -e "${B}可用的 Skill 設定檔${N}"
    echo "────────────────────────────────"
    echo ""
    echo -e "  ${B}all${N}              全部 34 個 skills（預設）"
    echo -e "  ${B}data-engineer${N}    Pipelines、Spark、Jobs、Streaming（14 個 skills）"
    echo -e "  ${B}analyst${N}          儀表板、SQL、Genie、指標（8 個 skills）"
    echo -e "  ${B}ai-ml-engineer${N}   Agents、RAG、向量搜尋、MLflow（17 個 skills）"
    echo -e "  ${B}app-developer${N}    應用程式、Lakebase、部署（10 個 skills）"
    echo ""
    echo -e "${B}核心 Skills${N}（一定安裝）"
    echo "────────────────────────────────"
    for skill in $CORE_SKILLS; do
        echo -e "  ${G}✓${N} $skill"
    done
    echo ""
    echo -e "${B}資料工程師${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_DATA_ENGINEER; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}商業分析師${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_ANALYST; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}AI/ML 工程師${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_AIML_ENGINEER; do
        echo -e "    $skill"
    done
    echo -e "  ${D}+ MLflow skills：${N}"
    for skill in $PROFILE_AIML_MLFLOW; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}應用程式開發者${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_APP_DEVELOPER; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}MLflow Skills${N}（來自 mlflow/skills repo）"
    echo "────────────────────────────────"
    for skill in $MLFLOW_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}APX Skills${N}（來自 Fet-ycliang/apx repo）"
    echo "────────────────────────────────"
    for skill in $APX_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${D}Usage: bash install.sh --skills-profile data-engineer,ai-ml-engineer${N}"
    echo -e "${D}       bash install.sh --skills databricks-jobs,databricks-dbsql${N}"
    echo ""
    exit 0
fi

# 解析 branch 參數後設定設定 URL
REPO_URL="https://github.com/Fet-ycliang/ai-dev-kit.git"
RAW_URL="https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/${BRANCH}"
INSTALL_DIR="${AIDEVKIT_HOME:-$HOME/.ai-dev-kit}"
REPO_DIR="$INSTALL_DIR/repo"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
MCP_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"

# ─── 互動輔助函式 ────────────────────────────────────────
# 從 /dev/tty 讀取，使提示在透過 curl | bash 執行時也能正常運作

# 簡單文字提示（含預設值）
prompt() {
    local prompt_text=$1
    local default_value=$2
    local result=""

    if [ "$SILENT" = true ]; then
        echo "$default_value"
        return
    fi

    if [ -e /dev/tty ]; then
        printf "  %b [%s]: " "$prompt_text" "$default_value" > /dev/tty
        read -r result < /dev/tty
    elif [ -t 0 ]; then
        printf "  %b [%s]: " "$prompt_text" "$default_value"
        read -r result
    else
        echo "$default_value"
        return
    fi

    if [ -z "$result" ]; then
        echo "$default_value"
    else
        echo "$result"
    fi
}

# 使用方向鍵 + 空白鍵/Enter 的互動核取方塊選擇器
# 輸出以空白鍵分隔的已選取值至 stdout
# 參數："Label|value|on_or_off|hint" ...
checkbox_select() {
    # 解析項目
    local -a labels=()
    local -a values=()
    local -a states=()
    local -a hints=()
    local count=0

    for item in "$@"; do
        IFS='|' read -r label value state hint <<< "$item"
        labels+=("$label")
        values+=("$value")
        hints+=("$hint")
        if [ "$state" = "on" ]; then
            states+=(1)
        else
            states+=(0)
        fi
        count=$((count + 1))
    done

    local cursor=0
    local total_rows=$((count + 2))  # 項目 + 空白行 + Done 按鈕

    # 繪製核取方塊清單 + Done 按鈕
    _checkbox_draw() {
        local i
        for i in $(seq 0 $((count - 1))); do
            local check=" "
            [ "${states[$i]}" = "1" ] && check="\033[0;32m✓\033[0m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "${states[$i]}" = "1" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b[%b] %-16s %b%s\033[0m\n" "$arrow" "$check" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
        # 空白分隔行
        printf "\033[2K\n" > /dev/tty
        # Done 按鈕
        if [ "$cursor" = "$count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    # 顯示操作說明
    printf "\n  \033[2m↑/↓ 導覽 · 空白鍵/Enter 切換選取 · 在確認時按 Enter 完成\033[0m\n\n" > /dev/tty

    # 隱藏游標
    printf "\033[?25l" > /dev/tty

    # 結束時恢復游標（Ctrl+C 安全處理）
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

    # 初始繪製
    _checkbox_draw

    # 輸入迴圈
    while true; do
        # 移回繪製區頂端並重新繪製
        printf "\033[%dA" "$total_rows" > /dev/tty
        _checkbox_draw

        # 讀取輸入
        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;  # 上
                    B) [ "$cursor" -lt "$count" ] && cursor=$((cursor + 1)) ;;  # 下（可移至 Done）
                esac
            fi
        elif [ "$key" = " " ] || [ "$key" = "" ]; then
            # 空白鍵或 Enter
            if [ "$cursor" -lt "$count" ]; then
                # 在核取方塊項目上──切換狀態
                if [ "${states[$cursor]}" = "1" ]; then
                    states[$cursor]=0
                else
                    states[$cursor]=1
                fi
            else
                # 在 Confirm 按鈕上──完成
                printf "\033[%dA" "$total_rows" > /dev/tty
                _checkbox_draw
                break
            fi
        fi
    done

    # 再次顯示游標
    printf "\033[?25h" > /dev/tty
    trap - EXIT

    # 建立結果
    local selected=""
    for i in $(seq 0 $((count - 1))); do
        if [ "${states[$i]}" = "1" ]; then
            selected="${selected:+$selected }${values[$i]}"
        fi
    done

    echo "$selected"
}

# 使用方向鍵 + Enter 的互動單選器
# 輸出已選取的值至 stdout
# 參數："Label|value|selected|hint" ...（恰好一個應設定 selected=on）
radio_select() {
    # 解析項目
    local -a labels=()
    local -a values=()
    local -a hints=()
    local count=0
    local selected=0

    for item in "$@"; do
        IFS='|' read -r label value state hint <<< "$item"
        labels+=("$label")
        values+=("$value")
        hints+=("$hint")
        [ "$state" = "on" ] && selected=$count
        count=$((count + 1))
    done

    local cursor=0
    local total_rows=$((count + 2))  # 項目 + 空白行 + Confirm 按鈕

    _radio_draw() {
        local i
        for i in $(seq 0 $((count - 1))); do
            local dot="○"
            local dot_color="\033[2m"
            [ "$i" = "$selected" ] && dot="●" && dot_color="\033[0;32m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "$i" = "$selected" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b%b%b %-20s %b%s\033[0m\n" "$arrow" "$dot_color" "$dot" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
        printf "\033[2K\n" > /dev/tty
        if [ "$cursor" = "$count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    printf "\n  \033[2m↑/↓ 導覽 · Enter 確認 · 空白鍵預覽\033[0m\n\n" > /dev/tty
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

    _radio_draw

    while true; do
        printf "\033[%dA" "$total_rows" > /dev/tty
        _radio_draw

        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;
                    B) [ "$cursor" -lt "$count" ] && cursor=$((cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = "" ]; then
            # Enter──選取目前項目並立即確認
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
            printf "\033[%dA" "$total_rows" > /dev/tty
            _radio_draw
            break
        elif [ "$key" = " " ]; then
            # 空白鍵──選取但繼續瀏覽
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
        fi
    done

    printf "\033[?25h" > /dev/tty
    trap - EXIT

    echo "${values[$selected]}"
}

# ─── 工具偵測與選擇 ─────────────────────────────────
detect_tools() {
    # 若已透過 --tools 旗標或 TOOLS 環境變數提供，略過偵測和提示
    if [ -n "$USER_TOOLS" ]; then
        TOOLS=$(echo "$USER_TOOLS" | tr ',' ' ')
        return
    elif [ -n "$TOOLS" ]; then
        # TOOLS 環境變數已設定，僅正規化格式
        TOOLS=$(echo "$TOOLS" | tr ',' ' ')
        return
    fi

    # 自動偵測已安裝的工具
    local has_claude=false
    local has_cursor=false
    local has_codex=false
    local has_copilot=false
    local has_gemini=false
    local has_antigravity=false

    command -v claude >/dev/null 2>&1 && has_claude=true
    { [ -d "/Applications/Cursor.app" ] || command -v cursor >/dev/null 2>&1; } && has_cursor=true
    command -v codex >/dev/null 2>&1 && has_codex=true
    { [ -d "/Applications/Visual Studio Code.app" ] || command -v copilot >/dev/null 2>&1; } && has_copilot=true
    { command -v gemini >/dev/null 2>&1 || [ -f "$HOME/.gemini/local/gemini" ]; } && has_gemini=true
    { [ -d "/Applications/Antigravity.app" ] || command -v antigravity >/dev/null 2>&1; } && has_antigravity=true

    # 建立核取方塊項目："Label|value|on_or_off|hint"
    local claude_state="off" cursor_state="off" codex_state="off" copilot_state="off" gemini_state="off" antigravity_state="off"
    local claude_hint="未找到" cursor_hint="未找到" codex_hint="未找到" copilot_hint="未找到" gemini_hint="未找到" antigravity_hint="未找到"
    [ "$has_claude" = true ]        && claude_state="on"        && claude_hint="已偵測"
    [ "$has_cursor" = true ]        && cursor_state="on"        && cursor_hint="已偵測"
    [ "$has_codex" = true ]         && codex_state="on"         && codex_hint="已偵測"
    [ "$has_copilot" = true ]       && copilot_state="on"       && copilot_hint="已偵測"
    [ "$has_gemini" = true ]        && gemini_state="on"        && gemini_hint="已偵測"
    [ "$has_antigravity" = true ]   && antigravity_state="on"   && antigravity_hint="已偵測"

    # 若未偵測到任何工具，預先選取 claude 作為預設
    if [ "$has_claude" = false ] && [ "$has_cursor" = false ] && [ "$has_codex" = false ] && [ "$has_copilot" = false ] && [ "$has_gemini" = false ] && [ "$has_antigravity" = false ]; then
        claude_state="on"
        claude_hint="預設"
    fi

    # 互動模式或回退模式
    if [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}選擇要安裝的工具：${N}"

        TOOLS=$(checkbox_select \
            "Claude Code|claude|${claude_state}|${claude_hint}" \
            "Cursor|cursor|${cursor_state}|${cursor_hint}" \
            "GitHub Copilot|copilot|${copilot_state}|${copilot_hint}" \
            "OpenAI Codex|codex|${codex_state}|${codex_hint}" \
            "Gemini CLI|gemini|${gemini_state}|${gemini_hint}" \
            "Antigravity|antigravity|${antigravity_state}|${antigravity_hint}" \
        )
    else
        # 靜默模式：使用偵測到的預設值
        local tools=""
        [ "$has_claude" = true ]        && tools="claude"
        [ "$has_cursor" = true ]        && tools="${tools:+$tools }cursor"
        [ "$has_copilot" = true ]       && tools="${tools:+$tools }copilot"
        [ "$has_codex" = true ]         && tools="${tools:+$tools }codex"
        [ "$has_gemini" = true ]        && tools="${tools:+$tools }gemini"
        [ "$has_antigravity" = true ]   && tools="${tools:+$tools }antigravity"
        [ -z "$tools" ] && tools="claude"
        TOOLS="$tools"
    fi

    # 驗證至少選取一個工具
    if [ -z "$TOOLS" ]; then
        warn "未選取任何工具，預設使用 Claude Code"
        TOOLS="claude"
    fi
}

# ─── Databricks Profile 選擇 ─────────────────────────────
prompt_profile() {
    # 若已透過 --profile 旗標提供（非預設值），略過提示
    if [ "$PROFILE" != "DEFAULT" ]; then
        return
    fi

    # 靜默模式或非互動環境下略過
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    # 從 ~/.databrickscfg 偵測現有的 profiles
    local cfg_file="$HOME/.databrickscfg"
    local -a profiles=()

    if [ -f "$cfg_file" ]; then
        while IFS= read -r line; do
            # 比對 [PROFILE_NAME] 區段
            if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
                profiles+=("${BASH_REMATCH[1]}")
            fi
        done < "$cfg_file"
    fi

    echo ""
    echo -e "  ${B}選擇 Databricks Profile${N}"

    if [ ${#profiles[@]} -gt 0 ] && [ -e /dev/tty ]; then
        # 建立單選項目："Label|value|on_or_off|hint"
        local -a items=()
        for p in "${profiles[@]}"; do
            local state="off"
            local hint=""
            [ "$p" = "DEFAULT" ] && state="on" && hint="預設"
            items+=("${p}|${p}|${state}|${hint}")
        done
        
        # 在最後加入自訂 profile 選項
        items+=("自訂 Profile 名稱...|__CUSTOM__|off|輸入自訂 Profile 名稱")

        # 若不存在 DEFAULT profile，預先選取第一個
        local has_default=false
        for p in "${profiles[@]}"; do
            [ "$p" = "DEFAULT" ] && has_default=true
        done
        if [ "$has_default" = false ]; then
            items[0]=$(echo "${items[0]}" | sed 's/|off|/|on|/')
        fi

        local selected_profile
        selected_profile=$(radio_select "${items[@]}")
        
        # 若選取了自訂，提示輸入名稱
        if [ "$selected_profile" = "__CUSTOM__" ]; then
            echo ""
            local custom_name
            custom_name=$(prompt "輸入 Profile 名稱" "DEFAULT")
            PROFILE="$custom_name"
        else
            PROFILE="$selected_profile"
        fi
    else
        echo -e "  ${D}找不到 ~/.databrickscfg，可在安裝後執行認證。${N}"
        echo ""
        local selected
        selected=$(prompt "Profile 名稱" "DEFAULT")
        PROFILE="$selected"
    fi
}

# ─── MCP 路徑選擇 ────────────────────────────────────────
prompt_mcp_path() {
    # 若已透過 --mcp-path 旗標提供，略過提示
    if [ -n "$USER_MCP_PATH" ]; then
        INSTALL_DIR="$USER_MCP_PATH"
    elif [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}MCP 伺服器位置${N}"
        [ "$SILENT" = false ] && echo -e "  ${D}MCP 伺服器執行環境（Python venv + 原始碼）將安裝在此。${N}"
        [ "$SILENT" = false ] && echo -e "  ${D}跨所有專案共用──僅設定檔為各專案獨立。${N}"
        [ "$SILENT" = false ] && echo ""

        local selected
        selected=$(prompt "安裝路徑" "$INSTALL_DIR")

        # 展開 ~ 為 $HOME
        INSTALL_DIR="${selected/#\~/$HOME}"
    fi

    # 更新衍生路徑
    REPO_DIR="$INSTALL_DIR/repo"
    VENV_DIR="$INSTALL_DIR/.venv"
    VENV_PYTHON="$VENV_DIR/bin/python"
    MCP_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"
}

# ─── Skill 設定檔選擇 ──────────────────────────────────
# 從 profile 名稱或明確指定的 skill 清單解析已選取的 skills
resolve_skills() {
    local db_skills="" mlflow_skills="" apx_skills=""

    # 優先順序 1：明確的 --skills 旗標（以逗號分隔的 skill 名稱）
    if [ -n "$USER_SKILLS" ]; then
        local user_list
        user_list=$(echo "$USER_SKILLS" | tr ',' ' ')
        # 分類至 DB、MLflow、APX 各組，且一定包含核心 skills
        db_skills="$CORE_SKILLS"
        for skill in $user_list; do
            if echo "$MLFLOW_SKILLS" | grep -qw "$skill"; then
                mlflow_skills="${mlflow_skills:+$mlflow_skills }$skill"
            elif echo "$APX_SKILLS" | grep -qw "$skill"; then
                apx_skills="${apx_skills:+$apx_skills }$skill"
            else
                db_skills="${db_skills:+$db_skills }$skill"
            fi
        done
        # 去除重複
        SELECTED_SKILLS=$(echo "$db_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        SELECTED_MLFLOW_SKILLS=$(echo "$mlflow_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        SELECTED_APX_SKILLS=$(echo "$apx_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        return
    fi

    # 優先順序 2：--skills-profile 旗標或互動選擇
    if [ -z "$SKILLS_PROFILE" ] || [ "$SKILLS_PROFILE" = "all" ]; then
        SELECTED_SKILLS="$SKILLS"
        SELECTED_MLFLOW_SKILLS="$MLFLOW_SKILLS"
        SELECTED_APX_SKILLS="$APX_SKILLS"
        return
    fi

    # 建立已選取 profiles 的聯集（以逗號分隔）
    db_skills="$CORE_SKILLS"
    mlflow_skills=""
    apx_skills=""

    local profiles
    profiles=$(echo "$SKILLS_PROFILE" | tr ',' ' ')
    for profile in $profiles; do
        case $profile in
            all)
                SELECTED_SKILLS="$SKILLS"
                SELECTED_MLFLOW_SKILLS="$MLFLOW_SKILLS"
                SELECTED_APX_SKILLS="$APX_SKILLS"
                return
                ;;
            data-engineer)
                db_skills="$db_skills $PROFILE_DATA_ENGINEER"
                ;;
            analyst)
                db_skills="$db_skills $PROFILE_ANALYST"
                ;;
            ai-ml-engineer)
                db_skills="$db_skills $PROFILE_AIML_ENGINEER"
                mlflow_skills="$mlflow_skills $PROFILE_AIML_MLFLOW"
                ;;
            app-developer)
                db_skills="$db_skills $PROFILE_APP_DEVELOPER"
                apx_skills="$apx_skills $APX_SKILLS"
                ;;
            *)
                warn "未知的 Skill 設定檔：$profile（已略過）"
                ;;
        esac
    done

    # 去除重複
    SELECTED_SKILLS=$(echo "$db_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    SELECTED_MLFLOW_SKILLS=$(echo "$mlflow_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    SELECTED_APX_SKILLS=$(echo "$apx_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
}

# 互動式 Skill 設定檔選擇（多選）
prompt_skills_profile() {
    # 若已透過 --skills 或 --skills-profile 提供，略過互動提示
    if [ -n "$USER_SKILLS" ] || [ -n "$SKILLS_PROFILE" ]; then
        return
    fi

    # 靜默模式或非互動環境下略過
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        SKILLS_PROFILE="all"
        return
    fi

    # 檢查上次的選擇（優先使用範圍本地設定，升級時回退至全域）
    local profile_file="$STATE_DIR/.skills-profile"
    [ ! -f "$profile_file" ] && [ "$SCOPE" = "project" ] && profile_file="$INSTALL_DIR/.skills-profile"
    if [ -f "$profile_file" ]; then
        local prev_profile
        prev_profile=$(cat "$profile_file")
        if [ "$FORCE" != true ]; then
            echo ""
            local display_profile
            display_profile=$(echo "$prev_profile" | tr ',' ', ')
            local keep
            keep=$(prompt "上次的 Skill 設定檔：${B}${display_profile}${N}。保留？${D}(Y/n)${N}" "y")
            if [ "$keep" = "y" ] || [ "$keep" = "Y" ] || [ "$keep" = "yes" ] || [ -z "$keep" ]; then
                SKILLS_PROFILE="$prev_profile"
                return
            fi
        fi
    fi

    echo ""
    echo -e "  ${B}選擇 Skill 設定檔${N}"

    # 自訂核取方塊（互斥邏輯）："All" 取消其他選項，其他選項取消 "All"
    local -a p_labels=("全部 Skills" "資料工程師" "商業分析師" "AI/ML 工程師" "應用程式開發者" "自訂")
    local -a p_values=("all" "data-engineer" "analyst" "ai-ml-engineer" "app-developer" "custom")
    local -a p_hints=("安裝全部（34 個 skills）" "Pipelines、Spark、Jobs、Streaming（14 個 skills）" "儀表板、SQL、Genie、指標（8 個 skills）" "Agents、RAG、向量搜尋、MLflow（17 個 skills）" "應用程式、Lakebase、部署（10 個 skills）" "自行挑選 Skills")
    local -a p_states=(1 0 0 0 0 0)  # 預設選取 "All"
    local p_count=6
    local p_cursor=0
    local p_total_rows=$((p_count + 2))

    _profile_draw() {
        local i
        for i in $(seq 0 $((p_count - 1))); do
            local check=" "
            [ "${p_states[$i]}" = "1" ] && check="\033[0;32m✓\033[0m"
            local arrow="  "
            [ "$i" = "$p_cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "${p_states[$i]}" = "1" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b[%b] %-20s %b%s\033[0m\n" "$arrow" "$check" "${p_labels[$i]}" "$hint_style" "${p_hints[$i]}" > /dev/tty
        done
        printf "\033[2K\n" > /dev/tty
        if [ "$p_cursor" = "$p_count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    printf "\n  \033[2m↑/↓ 導覽 · 空白鍵/Enter 切換選取 · 在確認時按 Enter 完成\033[0m\n\n" > /dev/tty
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

    _profile_draw

    while true; do
        printf "\033[%dA" "$p_total_rows" > /dev/tty
        _profile_draw

        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$p_cursor" -gt 0 ] && p_cursor=$((p_cursor - 1)) ;;
                    B) [ "$p_cursor" -lt "$p_count" ] && p_cursor=$((p_cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = " " ] || [ "$key" = "" ]; then
            if [ "$p_cursor" -lt "$p_count" ]; then
                # 切換目前項目狀態
                if [ "${p_states[$p_cursor]}" = "1" ]; then
                    p_states[$p_cursor]=0
                else
                    p_states[$p_cursor]=1
                    # 互斥邏輯："All"（索引 0）與個別 profiles（1-5）
                    if [ "$p_cursor" = "0" ]; then
                        # 選取 "All" → 取消選取所有其他項目
                        for j in $(seq 1 $((p_count - 1))); do p_states[$j]=0; done
                    else
                        # 選取個別 profile → 取消選取 "All"
                        p_states[0]=0
                    fi
                fi
            else
                # 在 Confirm 上──完成
                printf "\033[%dA" "$p_total_rows" > /dev/tty
                _profile_draw
                break
            fi
        fi
    done

    printf "\033[?25h" > /dev/tty
    trap - EXIT

    # 建立結果
    local selected=""
    for i in $(seq 0 $((p_count - 1))); do
        if [ "${p_states[$i]}" = "1" ]; then
            selected="${selected:+$selected }${p_values[$i]}"
        fi
    done

    # 若未選取任何項目，預設為 all
    if [ -z "$selected" ]; then
        SKILLS_PROFILE="all"
        return
    fi

    # 檢查是否選取了 "all"
    if echo "$selected" | grep -qw "all"; then
        SKILLS_PROFILE="all"
        return
    fi

    # 檢查是否選取了 "custom"──顯示個別 skill 選擇器
    if echo "$selected" | grep -qw "custom"; then
        prompt_custom_skills "$selected"
        return
    fi

    # 儲存以逗號分隔的 profile 名稱
    SKILLS_PROFILE=$(echo "$selected" | tr ' ' ',')
}

# 自訂個別 skill 選擇器
prompt_custom_skills() {
    local preselected_profiles="$1"

    # 從已勾選的 profiles 建立預先選取集合
    local preselected=""
    for profile in $preselected_profiles; do
        case $profile in
            data-engineer) preselected="$preselected $PROFILE_DATA_ENGINEER" ;;
            analyst)       preselected="$preselected $PROFILE_ANALYST" ;;
            ai-ml-engineer) preselected="$preselected $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW" ;;
            app-developer) preselected="$preselected $PROFILE_APP_DEVELOPER $APX_SKILLS" ;;
        esac
    done

    _is_preselected() {
        echo "$preselected" | grep -qw "$1" && echo "on" || echo "off"
    }

    echo ""
    echo -e "  ${B}選擇個別 Skills${N}"
    echo -e "  ${D}核心 Skills（config、docs、python-sdk、unity-catalog）一定安裝${N}"

    local selected
    selected=$(checkbox_select \
        "Spark Pipelines|databricks-spark-declarative-pipelines|$(_is_preselected databricks-spark-declarative-pipelines)|SDP/LDP, CDC, SCD Type 2" \
        "Structured Streaming|databricks-spark-structured-streaming|$(_is_preselected databricks-spark-structured-streaming)|Real-time streaming" \
        "Jobs & Workflows|databricks-jobs|$(_is_preselected databricks-jobs)|Multi-task orchestration" \
        "Asset Bundles|databricks-bundles|$(_is_preselected databricks-bundles)|DABs deployment" \
        "Databricks SQL|databricks-dbsql|$(_is_preselected databricks-dbsql)|SQL warehouse queries" \
        "Iceberg|databricks-iceberg|$(_is_preselected databricks-iceberg)|Apache Iceberg tables" \
        "Zerobus Ingest|databricks-zerobus-ingest|$(_is_preselected databricks-zerobus-ingest)|Streaming ingestion" \
        "Python Data Source|spark-python-data-source|$(_is_preselected spark-python-data-source)|Custom Spark data sources" \
        "Metric Views|databricks-metric-views|$(_is_preselected databricks-metric-views)|Metric definitions" \
        "AI/BI Dashboards|databricks-aibi-dashboards|$(_is_preselected databricks-aibi-dashboards)|Dashboard creation" \
        "Genie|databricks-genie|$(_is_preselected databricks-genie)|Natural language SQL" \
        "Agent Bricks|databricks-agent-bricks|$(_is_preselected databricks-agent-bricks)|Build AI agents" \
        "Vector Search|databricks-vector-search|$(_is_preselected databricks-vector-search)|Similarity search" \
        "Model Serving|databricks-model-serving|$(_is_preselected databricks-model-serving)|Deploy models/agents" \
        "MLflow Evaluation|databricks-mlflow-evaluation|$(_is_preselected databricks-mlflow-evaluation)|Model evaluation" \
        "AI Functions|databricks-ai-functions|$(_is_preselected databricks-ai-functions)|AI Functions, document parsing & RAG" \
        "Unstructured PDF|databricks-unstructured-pdf-generation|$(_is_preselected databricks-unstructured-pdf-generation)|Synthetic PDFs for RAG" \
        "Synthetic Data|databricks-synthetic-data-gen|$(_is_preselected databricks-synthetic-data-gen)|Generate test data" \
        "Lakebase Autoscale|databricks-lakebase-autoscale|$(_is_preselected databricks-lakebase-autoscale)|Managed PostgreSQL" \
        "Lakebase Provisioned|databricks-lakebase-provisioned|$(_is_preselected databricks-lakebase-provisioned)|Provisioned PostgreSQL" \
        "App Python|databricks-app-python|$(_is_preselected databricks-app-python)|Dash, Streamlit, Flask" \
        "App APX|databricks-app-apx|$(_is_preselected databricks-app-apx)|FastAPI + React" \
        "MLflow Onboarding|mlflow-onboarding|$(_is_preselected mlflow-onboarding)|Getting started" \
        "Agent Evaluation|agent-evaluation|$(_is_preselected agent-evaluation)|Evaluate AI agents" \
        "MLflow Tracing|instrumenting-with-mlflow-tracing|$(_is_preselected instrumenting-with-mlflow-tracing)|Instrument with tracing" \
        "Analyze Traces|analyze-mlflow-trace|$(_is_preselected analyze-mlflow-trace)|Analyze trace data" \
        "Retrieve Traces|retrieving-mlflow-traces|$(_is_preselected retrieving-mlflow-traces)|Search & retrieve traces" \
        "Analyze Chat Session|analyze-mlflow-chat-session|$(_is_preselected analyze-mlflow-chat-session)|Chat session analysis" \
        "Query Metrics|querying-mlflow-metrics|$(_is_preselected querying-mlflow-metrics)|MLflow metrics queries" \
        "Search MLflow Docs|searching-mlflow-docs|$(_is_preselected searching-mlflow-docs)|MLflow documentation" \
    )

    # 使用明確的 skills 清單──設定 USER_SKILLS 讓 resolve_skills 處理
    USER_SKILLS=$(echo "$selected" | tr ' ' ',')
}

# 比較語意版本號（若 $1 >= $2 則回傳 0）
version_gte() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

# 檢查 Databricks CLI 版本是否符合最低需求
check_cli_version() {
    local cli_version
    cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)

    if [ -z "$cli_version" ]; then
        warn "無法確認 Databricks CLI 版本"
        return
    fi

    if version_gte "$cli_version" "$MIN_CLI_VERSION"; then
        ok "Databricks CLI v${cli_version}"
    else
        warn "Databricks CLI v${cli_version} 版本過舊（最低需求：v${MIN_CLI_VERSION}）"
        msg "  ${B}升級：${N} curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
    fi
}

# 檢查 MCP venv 中的 Databricks SDK 版本
check_sdk_version() {
    local sdk_version
    sdk_version=$("$VENV_PYTHON" -c "from databricks.sdk.version import __version__; print(__version__)" 2>/dev/null)

    if [ -z "$sdk_version" ]; then
        warn "無法確認 Databricks SDK 版本"
        return
    fi

    if version_gte "$sdk_version" "$MIN_SDK_VERSION"; then
        ok "Databricks SDK v${sdk_version}"
    else
        warn "Databricks SDK v${sdk_version} 版本過舊（最低需求：v${MIN_SDK_VERSION}）"
        msg "  ${B}升級：${N} $VENV_PYTHON -m pip install --upgrade databricks-sdk"
    fi
}

# 檢查必要條件
check_deps() {
    command -v git >/dev/null 2>&1 || die "需要 git"
    ok "git"

    if command -v databricks >/dev/null 2>&1; then
        check_cli_version
    else
        warn "找不到 Databricks CLI。安裝方式：${B}curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${N}"
        msg "${D}仍可繼續安裝，但認證需稍後安裝 CLI。${N}"
    fi

    if [ "$INSTALL_MCP" = true ]; then
        if command -v uv >/dev/null 2>&1; then
            PKG="uv"
            ok "$PKG ($(uv --version 2>/dev/null || echo '未知版本'))"
        else
            die "找不到 uv，請先安裝。
   安裝方式：${B}curl -LsSf https://astral.sh/uv/install.sh | sh${N}
   安裝後重新執行此安裝程式。"
        fi
    fi
}

# 檢查是否需要更新
check_version() {
    local ver_file="$INSTALL_DIR/version"
    [ "$SCOPE" = "project" ] && ver_file=".ai-dev-kit/version"
    
    [ ! -f "$ver_file" ] && return
    [ "$FORCE" = true ] && return

    # 若使用者明確要求不同的 skill profile，略過版本檢查
    if [ -n "$SKILLS_PROFILE" ] || [ -n "$USER_SKILLS" ]; then
        local saved_profile_file="$STATE_DIR/.skills-profile"
        [ ! -f "$saved_profile_file" ] && [ "$SCOPE" = "project" ] && saved_profile_file="$INSTALL_DIR/.skills-profile"
        if [ -f "$saved_profile_file" ]; then
            local saved_profile
            saved_profile=$(cat "$saved_profile_file")
            local requested="${USER_SKILLS:+custom:$USER_SKILLS}"
            [ -z "$requested" ] && requested="$SKILLS_PROFILE"
            [ "$saved_profile" != "$requested" ] && return
        fi
    fi

    local local_ver=$(cat "$ver_file")
    # 使用 -f 讓 HTTP 錯誤（如 404）時失敗
    local remote_ver=$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null || echo "")

    # 驗證遠端版本格式（不應包含 "404" 或其他錯誤文字）
    if [ -n "$remote_ver" ] && [[ ! "$remote_ver" =~ (404|Not Found|error) ]]; then
        if [ "$local_ver" = "$remote_ver" ]; then
            ok "已是最新版本（v${local_ver}）"
            msg "${D}使用 --force 重新安裝，或使用 --skills-profile 更換設定檔${N}"
            exit 0
        fi
    fi
}

# 設定 MCP 伺服器
setup_mcp() {
    step "設定 MCP 伺服器"
    
    # 複製或更新 repo
    if [ -d "$REPO_DIR/.git" ]; then
        git -C "$REPO_DIR" fetch -q --depth 1 origin "$BRANCH" 2>/dev/null || true
        git -C "$REPO_DIR" reset --hard FETCH_HEAD 2>/dev/null || {
            rm -rf "$REPO_DIR"
            git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
        }
    else
        mkdir -p "$INSTALL_DIR"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
    fi
    ok "Repository 複製完成（$BRANCH）"
    
    # 建立 venv 並安裝
    # 在 Rosetta 下的 Apple Silicon，強制使用 arm64 避免與 universal2 Python 二進位檔的架構不符
    # （詳見：github.com/Fet-ycliang/ai-dev-kit/issues/115）
    local arch_prefix=""
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" = "x86_64" ]; then
        if arch -arm64 python3 -c "pass" 2>/dev/null; then
            arch_prefix="arch -arm64"
            warn "偵測到 Apple Silicon 上的 Rosetta，強制使用 arm64 執行 Python"
        fi
    fi

    msg "安裝 Python 套件中..."
    $arch_prefix uv venv --python 3.11 --allow-existing "$VENV_DIR" -q 2>/dev/null || $arch_prefix uv venv --allow-existing "$VENV_DIR" -q
    $arch_prefix uv pip install --python "$VENV_PYTHON" -e "$REPO_DIR/databricks-tools-core" -e "$REPO_DIR/databricks-mcp-server" -q

    "$VENV_PYTHON" -c "import databricks_mcp_server" 2>/dev/null || die "MCP 伺服器安裝失敗"
    ok "MCP 伺服器就緒"
}

# 安裝 skills
install_skills() {
    step "安裝 Skills"

    local base_dir=$1
    local dirs=()

    # 確定目標目錄（陣列格式，以支援含空白的路徑）
    for tool in $TOOLS; do
        case $tool in
            claude) dirs+=("$base_dir/.claude/skills") ;;
            cursor) echo "$TOOLS" | grep -q claude || dirs+=("$base_dir/.cursor/skills") ;;
            copilot) dirs+=("$base_dir/.github/skills") ;;
            codex) dirs+=("$base_dir/.agents/skills") ;;
            gemini) dirs+=("$base_dir/.gemini/skills") ;;
            antigravity)
                if [ "$SCOPE" = "global" ]; then
                    dirs+=("$HOME/.gemini/antigravity/skills")
                else
                    dirs+=("$base_dir/.agents/skills")
                fi
                ;;
        esac
    done

    # 去除重複：每行一個元素，sort -u 後讀回陣列
    local unique=()
    while IFS= read -r d; do
        unique+=("$d")
    done < <(printf '%s\n' "${dirs[@]}" | sort -u)
    dirs=("${unique[@]}")

    # 統計已選取 skills 數量以供顯示
    local db_count=0 mlflow_count=0 apx_count=0
    for _ in $SELECTED_SKILLS; do db_count=$((db_count + 1)); done
    for _ in $SELECTED_MLFLOW_SKILLS; do mlflow_count=$((mlflow_count + 1)); done
    for _ in $SELECTED_APX_SKILLS; do apx_count=$((apx_count + 1)); done
    local total_count=$((db_count + mlflow_count + apx_count))
    msg "正在安裝 ${B}${total_count}${N} 個 skills"

    # 建立本次安裝的所有 skills 集合
    local all_new_skills="$SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS"

    # 清除先前安裝但已取消選取的 skills
    # 優先檢查範圍本地 manifest，升級舊版本時回退至全域
    local manifest="$STATE_DIR/.installed-skills"
    [ ! -f "$manifest" ] && [ "$SCOPE" = "project" ] && [ -f "$INSTALL_DIR/.installed-skills" ] && manifest="$INSTALL_DIR/.installed-skills"
    if [ -f "$manifest" ]; then
        while IFS='|' read -r prev_dir prev_skill; do
            [ -z "$prev_skill" ] && continue
            # 若此 skill 仍在選取清單中，略過
            if echo " $all_new_skills " | grep -qw "$prev_skill"; then
                continue
            fi
            # 僅在目錄存在時移除
            if [ -d "$prev_dir/$prev_skill" ]; then
                rm -rf "$prev_dir/$prev_skill"
                msg "${D}已移除取消選取的 skill：$prev_skill${N}"
            fi
        done < "$manifest"
    fi

    # 開始新的 manifest（一律寫入範圍本地狀態目錄）
    manifest="$STATE_DIR/.installed-skills"
    mkdir -p "$STATE_DIR"
    : > "$manifest.tmp"

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        # 從 repo 安裝 Databricks skills
        for skill in $SELECTED_SKILLS; do
            local src="$REPO_DIR/databricks-skills/$skill"
            [ ! -d "$src" ] && continue
            rm -rf "$dir/$skill"
            cp -r "$src" "$dir/$skill"
            echo "$dir|$skill" >> "$manifest.tmp"
        done
        ok "Databricks skills ($db_count) → ${dir#$HOME/}"

        # 從 mlflow/skills repo 安裝 MLflow skills
        if [ -n "$SELECTED_MLFLOW_SKILLS" ]; then
            for skill in $SELECTED_MLFLOW_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$MLFLOW_RAW_URL/$skill/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # 嘗試下載選用的 MLflow 參考檔案
                    for ref in reference.md examples.md api.md; do
                        curl -fsSL "$MLFLOW_RAW_URL/$skill/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rm -rf "$dest_dir"
                fi
            done
            ok "MLflow skills ($mlflow_count) → ${dir#$HOME/}"
        fi

        # 從 Fet-ycliang/apx repo 安裝 APX skills
        if [ -n "$SELECTED_APX_SKILLS" ]; then
            for skill in $SELECTED_APX_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$APX_RAW_URL/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # 嘗試下載選用的 APX 參考檔案
                    for ref in backend-patterns.md frontend-patterns.md; do
                        curl -fsSL "$APX_RAW_URL/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rmdir "$dest_dir" 2>/dev/null || warn "無法安裝 APX skill '$skill'，若不再需要可考慮移除 $dest_dir"
                fi
            done
            ok "APX skills ($apx_count) → ${dir#$HOME/}"
        fi
    done

    # 儲存已安裝 skills 的 manifest（在切換 profile 時用於清理）
    mv "$manifest.tmp" "$manifest"

    # 儲存已選取的 profile 以供未來重新安裝使用（範圍本地）
    if [ -n "$USER_SKILLS" ]; then
        echo "custom:$USER_SKILLS" > "$STATE_DIR/.skills-profile"
    else
        echo "${SKILLS_PROFILE:-all}" > "$STATE_DIR/.skills-profile"
    fi
}

# 寫入 MCP 設定檔
write_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # 修改前先備份現有檔案
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}已備份 ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$VENV_PYTHON" ];then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('mcpServers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'defer_loading': True, 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    # 回退方案：僅適用於新檔案──拒絕覆蓋可能包含其他設定的現有檔案
    # （如 ~/.claude.json）
    if [ -f "$path" ]; then
        warn "無 Python 環境，無法合併 MCP 設定至 $path，請手動新增。"
        return
    fi

    cat > "$path" << EOF
{
  "mcpServers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "defer_loading": true,
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

write_copilot_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # 修改前先備份現有檔案
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}已備份 ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('servers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    cat > "$path" << EOF
{
  "servers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

write_mcp_toml() {
    local path=$1
    mkdir -p "$(dirname "$path")"
    grep -q "mcp_servers.databricks" "$path" 2>/dev/null && return
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}已備份 ${path##*/} → ${path##*/}.bak${N}"
    fi
    cat >> "$path" << EOF

[mcp_servers.databricks]
command = "$VENV_PYTHON"
args = ["$MCP_ENTRY"]
EOF
}

write_gemini_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # 修改前先備份現有檔案
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}已備份 ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('mcpServers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    cat > "$path" << EOF
{
  "mcpServers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

write_gemini_md() {
    local path=$1
    [ -f "$path" ] && return  # 不覆蓋現有檔案
    cat > "$path" << 'GEMINIEOF'
# Databricks AI Dev Kit

You have access to Databricks skills and MCP tools installed by the Databricks AI Dev Kit.

## Available MCP Tools

The `databricks` MCP server provides 50+ tools for interacting with Databricks, including:
- SQL execution and warehouse management
- Unity Catalog operations (tables, volumes, schemas)
- Jobs and workflow management
- Model serving endpoints
- Genie spaces and AI/BI dashboards
- Databricks Apps deployment

## Available Skills

Skills are installed in `.gemini/skills/` and provide patterns and best practices for:
- Spark Declarative Pipelines, Structured Streaming
- Databricks Jobs, Asset Bundles
- Unity Catalog, SQL, Genie
- MLflow evaluation and tracing
- Model Serving, Vector Search
- Databricks Apps (Python and APX)
- And more

## Getting Started

Try asking: "List my SQL warehouses" or "Show my Unity Catalog schemas"
GEMINIEOF
    ok "GEMINI.md"
}

write_claude_hook() {
    local path=$1
    local script=$2
    mkdir -p "$(dirname "$path")"

    # 若存在 settings.json，使用 Python 安全合併
    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json
path = '$path'
script = '$script'
hook_entry = {'type': 'command', 'command': 'bash ' + script, 'timeout': 5}
try:
    with open(path) as f: cfg = json.load(f)
except: cfg = {}
hooks = cfg.setdefault('hooks', {})
session_hooks = hooks.setdefault('SessionStart', [])
# 檢查 hook 是否已存在
for group in session_hooks:
    for h in group.get('hooks', []):
        if 'check_update.sh' in h.get('command', ''):
            exit(0)  # 已設定
# 附加新的 hook 群組
session_hooks.append({'hooks': [hook_entry]})
with open(path, 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    # 回退方案：寫入新檔案（僅在無現有檔案時）
    [ -f "$path" ] && return  # 未有 Python 時不覆蓋現有設定
    cat > "$path" << EOF
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $script",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
EOF
}

write_mcp_configs() {
    step "設定 MCP"
    
    local base_dir=$1
    for tool in $TOOLS; do
        case $tool in
            claude)
                [ "$SCOPE" = "global" ] && write_mcp_json "$HOME/.claude.json" || write_mcp_json "$base_dir/.mcp.json"
                ok "Claude MCP 設定"
                # 為 Claude 設定加入版本檢查 hook
                local check_script="$REPO_DIR/.claude-plugin/check_update.sh"
                if [ "$SCOPE" = "global" ]; then
                    write_claude_hook "$HOME/.claude/settings.json" "$check_script"
                else
                    write_claude_hook "$base_dir/.claude/settings.json" "$check_script"
                fi
                ok "Claude 版本檢查 hook"
                ;;
            cursor)
                if [ "$SCOPE" = "global" ]; then
                    warn "Cursor 全域模式：需手動設定 MCP"
                    msg "  1. 開啟 ${B}Cursor → 設定 → Cursor Settings → Tools & MCP${N}"
                    msg "  2. 點擊 ${B}New MCP Server${N}"
                    msg "  3. 加入以下 JSON 設定："
                    msg "     {"
                    msg "       \"mcpServers\": {"
                    msg "         \"databricks\": {"
                    msg "           \"command\": \"$VENV_PYTHON\","
                    msg "           \"args\": [\"$MCP_ENTRY\"],"
                    msg "           \"env\": {\"DATABRICKS_CONFIG_PROFILE\": \"$PROFILE\"}"
                    msg "         }"
                    msg "       }"
                    msg "     }"
                else
                    write_mcp_json "$base_dir/.cursor/mcp.json"
                    ok "Cursor MCP 設定"
                fi
                warn "Cursor：MCP 伺服器預設停用。"
                msg "  啟用方式：${B}Cursor → 設定 → Cursor Settings → Tools & MCP → 切換 'databricks'${N}"
                ;;
            copilot)
                if [ "$SCOPE" = "global" ]; then
                    warn "Copilot 全域模式：請在 VS Code 設定中設定 MCP（Ctrl+Shift+P → 'MCP: Open User Configuration'）"
                    msg "  Command: $VENV_PYTHON | Args: $MCP_ENTRY"
                else
                    write_copilot_mcp_json "$base_dir/.vscode/mcp.json"
                    ok "Copilot MCP 設定（.vscode/mcp.json）"
                fi
                warn "Copilot：MCP 伺服器需手動啟用。"
                msg "  在 Copilot Chat 中，點擊 ${B}設定工具${N}（右下角工具圖示），啟用 ${B}databricks${N}"
                ;;
            codex)
                [ "$SCOPE" = "global" ] && write_mcp_toml "$HOME/.codex/config.toml" || write_mcp_toml "$base_dir/.codex/config.toml"
                ok "Codex MCP 設定"
                ;;
            gemini)
                if [ "$SCOPE" = "global" ]; then
                    write_gemini_mcp_json "$HOME/.gemini/settings.json"
                else
                    write_gemini_mcp_json "$base_dir/.gemini/settings.json"
                fi
                ok "Gemini CLI MCP 設定"
                ;;
            antigravity)
                if [ "$SCOPE" = "project" ]; then
                    warn "Antigravity 僅支援全域 MCP 設定。"
                    msg "  設定已寫入 ${B}~/.gemini/antigravity/mcp_config.json${N}"
                fi
                write_gemini_mcp_json "$HOME/.gemini/antigravity/mcp_config.json"
                ok "Antigravity MCP 設定"
                ;;
        esac
    done
}

# 儲存版本
save_version() {
    # 使用 -f 讓 HTTP 錯誤（如 404）時失敗
    local ver=$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null || echo "dev")
    # 驗證版本格式
    [[ "$ver" =~ (404|Not Found|error) ]] && ver="dev"
    echo "$ver" > "$INSTALL_DIR/version"
    if [ "$SCOPE" = "project" ]; then
        mkdir -p ".ai-dev-kit"
        echo "$ver" > ".ai-dev-kit/version"
    fi
}

# 顯示摘要
summary() {
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${G}${B}安裝完成！${N}"
        echo "────────────────────────────────"
        msg "位置：$INSTALL_DIR"
        msg "範圍：    $SCOPE"
        msg "工具：    $(echo "$TOOLS" | tr ' ' ', ')"
        echo ""
        msg "${B}後續步驟：${N}"
        local step=1
        if echo "$TOOLS" | grep -q cursor; then
            msg "${R}${step}. 啟用 Cursor MCP：${B}Cursor → 設定 → Cursor Settings → Tools & MCP → 切換 'databricks'${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q copilot; then
            msg "${step}. 在 Copilot Chat 中，點擊 ${B}設定工具${N}（右下角工具圖示），啟用 ${B}databricks${N}"
            step=$((step + 1))
            msg "${step}. 使用 Copilot ${B}Agent 模式${N}存取 Databricks skills 及 MCP 工具"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q gemini; then
            msg "${step}. 在專案中啟動 Gemini CLI：${B}gemini${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q antigravity; then
            msg "${step}. 在 Antigravity 中開啟專案以使用 Databricks skills 及 MCP 工具"
            step=$((step + 1))
        fi
        msg "${step}. 以您選擇的工具開啟專案"
        step=$((step + 1))
        msg "${step}. 試試看：\"列出我的 SQL Warehouses\""
        echo ""
    fi
}

# 提示選擇安裝範圍
prompt_scope() {
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    echo ""
    echo -e "  ${B}選擇安裝範圍${N}"
    
    # 無 Confirm 按鈕的簡單單選器
    local -a labels=("專案" "全域")
    local -a values=("project" "global")
    local -a hints=("安裝至目前目錄（.cursor/、.claude/、.gemini/）" "安裝至家目錄（~/.cursor/、~/.claude/、~/.gemini/）")
    local count=2
    local selected=0
    local cursor=0
    
    _scope_draw() {
        for i in 0 1; do
            local dot="○"
            local dot_color="\033[2m"
            [ "$i" = "$selected" ] && dot="●" && dot_color="\033[0;32m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "$i" = "$selected" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b%b%b %-20s %b%s\033[0m\n" "$arrow" "$dot_color" "$dot" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
    }
    
    printf "\n  \033[2m↑/↓ 導覽 · Enter 確認\033[0m\n\n" > /dev/tty
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT
    
    _scope_draw
    
    while true; do
        printf "\033[%dA" "$count" > /dev/tty
        _scope_draw
        
        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null
        
        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;
                    B) [ "$cursor" -lt 1 ] && cursor=$((cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = "" ]; then
            selected=$cursor
            printf "\033[%dA" "$count" > /dev/tty
            _scope_draw
            break
        elif [ "$key" = " " ]; then
            selected=$cursor
        fi
    done
    
    printf "\033[?25h" > /dev/tty
    trap - EXIT
    
    SCOPE="${values[$selected]}"
}

# 提示執行認證
prompt_auth() {
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    # 檢查 profile 是否已設定 token
    local cfg_file="$HOME/.databrickscfg"
    if [ -f "$cfg_file" ]; then
        # 讀取所選 profile 區段下的 token 值
        local in_profile=false
        while IFS= read -r line; do
            if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
                [ "${BASH_REMATCH[1]}" = "$PROFILE" ] && in_profile=true || in_profile=false
            elif [ "$in_profile" = true ] && [[ "$line" =~ ^token[[:space:]]*= ]]; then
                ok "Profile ${B}$PROFILE${N} 已設定 token，略過認證"
                return
            fi
        done < "$cfg_file"
    fi

    # 若已設定環境變數，也略過
    if [ -n "$DATABRICKS_TOKEN" ]; then
        ok "已設定 DATABRICKS_TOKEN，略過認證"
        return
    fi

    # OAuth 登入需要 Databricks CLI
    if ! command -v databricks >/dev/null 2>&1; then
        warn "未安裝 Databricks CLI，無法執行 OAuth 登入"
        msg "  請先安裝，然後執行：${B}${BL}databricks auth login --profile $PROFILE${N}"
        return
    fi

    echo ""
    msg "${B}認證${N}"
    msg "即將為 Profile ${B}${BL}$PROFILE${N} 執行 OAuth 登入"
    msg "${D}將開啟瀏覽器視窗，供您登入 Databricks workspace。${N}"
    echo ""
    local run_auth
    run_auth=$(prompt "立即執行 ${B}databricks auth login --profile $PROFILE${N}？${D}(y/n)${N}" "y")
    if [ "$run_auth" = "y" ] || [ "$run_auth" = "Y" ] || [ "$run_auth" = "yes" ]; then
        echo ""
        databricks auth login --profile "$PROFILE"
    fi
}

# 主程式
main() {
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${B}Databricks AI Dev Kit 安裝程式${N}"
        echo "────────────────────────────────"
    fi
    
    # 檢查相依套件
    step "檢查必要條件"
    check_deps

    # ── 步驟 2：互動式工具選擇 ──
    step "選擇工具"
    detect_tools
    ok "已選擇：$(echo "$TOOLS" | tr ' ' ', ')"

    # ── 步驟 3：互動式 profile 選擇 ──
    step "Databricks Profile"
    prompt_profile
    ok "Profile：$PROFILE"

    # ── 步驟 3.5：互動式範圍選擇 ──
    if [ "$SCOPE_EXPLICIT" = false ]; then
        prompt_scope
        ok "範圍：$SCOPE"
    fi

    # 根據範圍設定狀態目錄（用於 profile 及 manifest 儲存）
    if [ "$SCOPE" = "global" ]; then
        STATE_DIR="$INSTALL_DIR"
    else
        STATE_DIR="$(pwd)/.ai-dev-kit"
    fi

    # ── 步驟 4：Skill 設定檔選擇 ──
    if [ "$INSTALL_SKILLS" = true ]; then
        step "Skill 設定檔"
        prompt_skills_profile
        resolve_skills
        # 統計以供顯示
        local sk_count=0
        for _ in $SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS; do sk_count=$((sk_count + 1)); done
        if [ -n "$USER_SKILLS" ]; then
            ok "自訂選擇（$sk_count 個 skills）"
        else
            ok "設定檔：${SKILLS_PROFILE:-all}（$sk_count 個 skills）"
        fi
    fi

    # ── 步驟 5：互動式 MCP 路徑 ──
    if [ "$INSTALL_MCP" = true ]; then
        prompt_mcp_path
        ok "MCP 路徑：$INSTALL_DIR"
    fi

    # ── 步驟 6：確認後繼續 ──
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "  ${B}摘要${N}"
        echo -e "  ────────────────────────────────────"
        echo -e "  工具：       ${G}$(echo "$TOOLS" | tr ' ' ', ')${N}"
        echo -e "  Profile：     ${G}${PROFILE}${N}"
        echo -e "  範圍：       ${G}${SCOPE}${N}"
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP 伺服器：  ${G}${INSTALL_DIR}${N}"
        if [ "$INSTALL_SKILLS" = true ]; then
            if [ -n "$USER_SKILLS" ]; then
                echo -e "  Skills：      ${G}自訂選擇${N}"
            else
                local sk_total=0
                for _ in $SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS; do sk_total=$((sk_total + 1)); done
                echo -e "  Skills：      ${G}${SKILLS_PROFILE:-all}（$sk_total 個 skills）${N}"
            fi
        fi
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP 設定：  ${G}是${N}"
        echo ""
    fi

    if [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        local confirm
        confirm=$(prompt "確認開始安裝？${D}(y/n)${N}" "y")
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && [ "$confirm" != "yes" ]; then
            echo ""
            msg "安裝已取消。"
            exit 0
        fi
    fi

    # ── 步驟 7：版本檢查（若已是最新版本可能提前結束）──
    check_version
    
    # 確定基礎目錄
    local base_dir
    [ "$SCOPE" = "global" ] && base_dir="$HOME" || base_dir="$(pwd)"
    
    # 設定 MCP 伺服器
    if [ "$INSTALL_MCP" = true ]; then
        setup_mcp
    elif [ ! -d "$REPO_DIR" ]; then
        step "下載原始碼"
        mkdir -p "$INSTALL_DIR"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
        ok "Repository 複製完成（$BRANCH）"
    fi
    
    # 安裝 skills
    [ "$INSTALL_SKILLS" = true ] && install_skills "$base_dir"

    # 若選取 gemini，寫入 GEMINI.md
    if echo "$TOOLS" | grep -q gemini; then
        if [ "$SCOPE" = "global" ]; then
            write_gemini_md "$HOME/GEMINI.md"
        else
            write_gemini_md "$base_dir/GEMINI.md"
        fi
    fi

    # 寫入 MCP 設定
    [ "$INSTALL_MCP" = true ] && write_mcp_configs "$base_dir"
    
    # 儲存版本
    save_version
    
    # 提示執行認證
    prompt_auth
    
    # 完成
    summary
}

main "$@"
