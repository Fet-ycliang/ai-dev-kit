#
# Databricks AI Dev Kit - 統一安裝程式（Windows）
#
# 安裝 skills、MCP 伺服器及設定，支援 Claude Code、Cursor、OpenAI Codex、GitHub Copilot、Gemini CLI 及 Antigravity。
#
# Usage: irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1
#        .\install.ps1 [OPTIONS]
#
# 範例：
#   # 基本安裝（使用 DEFAULT profile、專案範圍、最新版本）
#   irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex
#
#   # 下載並以選項執行
#   irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1
#
#   # 全域安裝並強制重新安裝
#   .\install.ps1 -Global -Force
#
#   # 指定 profile 並強制重新安裝
#   .\install.ps1 -Profile DEFAULT -Force
#
#   # 僅安裝指定工具
#   .\install.ps1 -Tools cursor
#
#   # 僅安裝 Skills（略過 MCP 伺服器）
#   .\install.ps1 -SkillsOnly
#
#   # 安裝指定分支或標籤
#   $env:AIDEVKIT_BRANCH = '0.1.0'; .\install.ps1
#

$ErrorActionPreference = "Stop"

# ─── 設定 ────────────────────────────────────────────────────
$Owner = "databricks-solutions"
$Repo  = "ai-dev-kit"

# 決定要使用的分支/標籤
if ($env:AIDEVKIT_BRANCH) {
    $Branch = $env:AIDEVKIT_BRANCH
} else {
    try {
        $latestReleaseUri = "https://api.github.com/repos/$Owner/$Repo/releases/latest"
        $latestRelease = Invoke-WebRequest -Uri $latestReleaseUri -Headers @{ "Accept" = "application/json" } -UseBasicParsing -ErrorAction Stop
        $Branch = ($latestRelease.Content | ConvertFrom-Json).tag_name
    } catch {
        $Branch = "main"
    }
}

$RepoUrl   = "https://github.com/$Owner/$Repo.git"
$RawUrl    = "https://raw.githubusercontent.com/$Owner/$Repo/$Branch"
$InstallDir = if ($env:AIDEVKIT_HOME) { $env:AIDEVKIT_HOME } else { Join-Path $env:USERPROFILE ".ai-dev-kit" }
$RepoDir   = Join-Path $InstallDir "repo"
$VenvDir   = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$McpEntry  = Join-Path $RepoDir "databricks-mcp-server\run_server.py"

# 最低版本需求
$MinCliVersion = "0.278.0"
$MinSdkVersion = "0.85.0"

# ─── 預設值 ─────────────────────────────────────────────────
$script:Profile_     = "DEFAULT"
$script:Scope        = "project"
$script:ScopeExplicit = $false  # Track if --global was explicitly passed
$script:InstallMcp   = $true
$script:InstallSkills = $true
$script:Force        = $false
$script:Silent       = $false
$script:UserTools    = ""
$script:Tools        = ""
$script:UserMcpPath  = ""
$script:Pkg          = ""
$script:ProfileProvided = $false
$script:SkillsProfile = ""
$script:UserSkills   = ""
$script:ListSkills   = $false

# Databricks skills（打包於 repo 中）
$script:Skills = @(
    "databricks-agent-bricks", "databricks-aibi-dashboards", "databricks-app-python",
    "databricks-bundles", "databricks-config", "databricks-dbsql", "databricks-docs", "databricks-genie",
    "databricks-iceberg", "databricks-jobs", "databricks-lakebase-autoscale", "databricks-lakebase-provisioned",
    "databricks-metric-views", "databricks-mlflow-evaluation", "databricks-model-serving", "databricks-ai-functions",
    "databricks-python-sdk", "databricks-spark-declarative-pipelines", "databricks-spark-structured-streaming",
    "databricks-synthetic-data-gen", "databricks-unity-catalog", "databricks-unstructured-pdf-generation",
    "databricks-vector-search", "databricks-zerobus-ingest", "spark-python-data-source"
)

# MLflow skills（從 mlflow/skills repo 下載）
$script:MlflowSkills = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$MlflowRawUrl = "https://raw.githubusercontent.com/mlflow/skills/main"

# APX skills（從 databricks-solutions/apx repo 下載）
$script:ApxSkills = @("databricks-app-apx")
$ApxRawUrl = "https://raw.githubusercontent.com/databricks-solutions/apx/main/skills/apx"

# ─── Skill 設定檔 ──────────────────────────────────────────
$script:CoreSkills = @("databricks-config", "databricks-docs", "databricks-python-sdk", "databricks-unity-catalog")

$script:ProfileDataEngineer = @(
    "databricks-spark-declarative-pipelines", "databricks-spark-structured-streaming",
    "databricks-jobs", "databricks-bundles", "databricks-dbsql", "databricks-iceberg",
    "databricks-zerobus-ingest", "spark-python-data-source", "databricks-metric-views",
    "databricks-synthetic-data-gen"
)
$script:ProfileAnalyst = @(
    "databricks-aibi-dashboards", "databricks-dbsql", "databricks-genie", "databricks-metric-views"
)
$script:ProfileAiMlEngineer = @(
    "databricks-agent-bricks", "databricks-vector-search", "databricks-model-serving",
    "databricks-genie", "databricks-ai-functions", "databricks-unstructured-pdf-generation",
    "databricks-mlflow-evaluation", "databricks-synthetic-data-gen", "databricks-jobs"
)
$script:ProfileAiMlMlflow = @(
    "agent-evaluation", "analyze-mlflow-chat-session", "analyze-mlflow-trace",
    "instrumenting-with-mlflow-tracing", "mlflow-onboarding", "querying-mlflow-metrics",
    "retrieving-mlflow-traces", "searching-mlflow-docs"
)
$script:ProfileAppDeveloper = @(
    "databricks-app-python", "databricks-app-apx", "databricks-lakebase-autoscale",
    "databricks-lakebase-provisioned", "databricks-model-serving", "databricks-dbsql",
    "databricks-jobs", "databricks-bundles"
)

# 已選取的 skills（在 profile 選取期間填入）
$script:SelectedSkills = @()
$script:SelectedMlflowSkills = @()
$script:SelectedApxSkills = @()

# ─── --list-skills 處理器 ────────────────────────────────────
if ($script:ListSkills) {
    Write-Host ""
    Write-Host "可用的 Skill 設定檔" -ForegroundColor White
    Write-Host "--------------------------------"
    Write-Host ""
    Write-Host "  all              " -ForegroundColor White -NoNewline; Write-Host "全部 34 個 skills（預設）"
    Write-Host "  data-engineer    " -ForegroundColor White -NoNewline; Write-Host "Pipelines、Spark、Jobs、Streaming（14 個 skills）"
    Write-Host "  analyst          " -ForegroundColor White -NoNewline; Write-Host "儀表板、SQL、Genie、指標（8 個 skills）"
    Write-Host "  ai-ml-engineer   " -ForegroundColor White -NoNewline; Write-Host "Agents、RAG、向量搜尋、MLflow（17 個 skills）"
    Write-Host "  app-developer    " -ForegroundColor White -NoNewline; Write-Host "應用程式、Lakebase、部署（10 個 skills）"
    Write-Host ""
    Write-Host "核心 Skills（一定安裝）" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:CoreSkills) { Write-Host "  " -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host " $s" }
    Write-Host ""
    Write-Host "資料工程師" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileDataEngineer) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "商業分析師" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAnalyst) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "AI/ML 工程師" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAiMlEngineer) { Write-Host "    $s" }
    Write-Host "  + MLflow skills：" -ForegroundColor DarkGray
    foreach ($s in $script:ProfileAiMlMlflow) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "應用程式開發者" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ProfileAppDeveloper) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "MLflow Skills（來自 mlflow/skills repo）" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:MlflowSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "APX Skills（來自 databricks-solutions/apx repo）" -ForegroundColor White
    Write-Host "--------------------------------"
    foreach ($s in $script:ApxSkills) { Write-Host "    $s" }
    Write-Host ""
    Write-Host "Usage: .\install.ps1 --skills-profile data-engineer,ai-ml-engineer" -ForegroundColor DarkGray
    Write-Host "       .\install.ps1 --skills databricks-jobs,databricks-dbsql" -ForegroundColor DarkGray
    Write-Host ""
    return
}

# ─── 確保工具在 PATH 中 ────────────────────────────────
# Chocolatey 安裝的工具在 SSH session 中可能不在 PATH 裡
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath    = [System.Environment]::GetEnvironmentVariable("Path", "User")
if ($machinePath -or $userPath) {
    $env:Path = "$machinePath;$userPath;$env:Path"
    # 去除重複
    $env:Path = (($env:Path -split ';' | Select-Object -Unique | Where-Object { $_ }) -join ';')
}

# ─── 輸出輔助函式 ───────────────────────────────────────────
function Write-Msg  { param([string]$Text) if (-not $script:Silent) { Write-Host "  $Text" } }
function Write-Ok   { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host " $Text" } }
function Write-Warn { param([string]$Text) if (-not $script:Silent) { Write-Host "  " -NoNewline; Write-Host "!" -ForegroundColor Yellow -NoNewline; Write-Host " $Text" } }
function Write-Err  {
    param([string]$Text)
    Write-Host "  " -NoNewline; Write-Host "x" -ForegroundColor Red -NoNewline; Write-Host " $Text"
    Write-Host ""
    Write-Host "  按任意鍵離開..." -ForegroundColor DarkGray
    try { $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch {}
    exit 1
}
function Write-Step { param([string]$Text) if (-not $script:Silent) { Write-Host ""; Write-Host "$Text" -ForegroundColor White } }

# ─── 解析參數 ─────────────────────────────────────────
$i = 0
while ($i -lt $args.Count) {
    switch ($args[$i]) {
        { $_ -in "-p", "--profile" }  { $script:Profile_ = $args[$i + 1]; $script:ProfileProvided = $true; $i += 2 }
        { $_ -in "-g", "--global", "-Global" }  { $script:Scope = "global"; $script:ScopeExplicit = $true; $i++ }
        { $_ -in "--skills-only", "-SkillsOnly" } { $script:InstallMcp = $false; $i++ }
        { $_ -in "--mcp-only", "-McpOnly" }    { $script:InstallSkills = $false; $i++ }
        { $_ -in "--mcp-path", "-McpPath" }    { $script:UserMcpPath = $args[$i + 1]; $i += 2 }
        { $_ -in "--silent", "-Silent" }       { $script:Silent = $true; $i++ }
        { $_ -in "--tools", "-Tools" }         { $script:UserTools = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills-profile", "-SkillsProfile" } { $script:SkillsProfile = $args[$i + 1]; $i += 2 }
        { $_ -in "--skills", "-Skills" }       { $script:UserSkills = $args[$i + 1]; $i += 2 }
        { $_ -in "--list-skills", "-ListSkills" } { $script:ListSkills = $true; $i++ }
        { $_ -in "-f", "--force", "-Force" }   { $script:Force = $true; $i++ }
        { $_ -in "-h", "--help", "-Help" } {
            Write-Host "Databricks AI Dev Kit 安裝程式（Windows）"
            Write-Host ""
            Write-Host "Usage: irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1"
            Write-Host "       .\install.ps1 [OPTIONS]"
            Write-Host ""
            Write-Host "選項："
            Write-Host "  -p, --profile NAME    Databricks profile（預設：DEFAULT）"
            Write-Host "  -g, --global          全域安裝（適用所有專案）"
            Write-Host "  --skills-only         略過 MCP 伺服器設定"
            Write-Host "  --mcp-only            略過 Skills 安裝"
            Write-Host "  --mcp-path PATH       MCP 伺服器安裝路徑"
            Write-Host "  --silent              靜默模式（僅顯示錯誤）"
            Write-Host "  --tools LIST          以逗號分隔：claude,cursor,copilot,codex,gemini,antigravity"
            Write-Host "  --skills-profile LIST 以逗號分隔的設定檔：all,data-engineer,analyst,ai-ml-engineer,app-developer"
            Write-Host "  --skills LIST         以逗號分隔的 skill 名稱（覆蓋設定檔）"
            Write-Host "  --list-skills         列出可用的 skills 及設定檔後離開"
            Write-Host "  -f, --force           強制重新安裝"
            Write-Host "  -h, --help            顯示此說明"
            Write-Host ""
            Write-Host "環境變數："
            Write-Host "  AIDEVKIT_BRANCH       要安裝的分支或標籤（預設：最新版本）"
            Write-Host "  AIDEVKIT_HOME         安裝目錄（預設：~/.ai-dev-kit）"
            Write-Host ""
            Write-Host "範例："
            Write-Host "  # 基本安裝"
            Write-Host "  irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex"
            Write-Host ""
            Write-Host "  # 下載並以選項執行"
            Write-Host "  irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 -OutFile install.ps1"
            Write-Host "  .\install.ps1 -Global -Force"
            Write-Host ""
            Write-Host "  # 指定 profile 並強制重新安裝"
            Write-Host "  .\install.ps1 -Profile DEFAULT -Force"
            return
        }
        default { Write-Err "未知選項：$($args[$i])（使用 -h 取得說明）"; $i++ }
    }
}

# ─── 互動輔助函式 ──────────────────────────────────────

function Test-Interactive {
    if ($script:Silent) { return $false }
    try {
        $host.UI.RawUI.KeyAvailable | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Read-Prompt {
    param([string]$PromptText, [string]$Default)

    if ($script:Silent) { return $Default }

    $isInteractive = Test-Interactive
    if ($isInteractive) {
        Write-Host "  $PromptText [$Default]: " -NoNewline
        $result = Read-Host
        if ([string]::IsNullOrWhiteSpace($result)) { return $Default }
        return $result
    } else {
        return $Default
    }
}

# 互動式核取方塊選擇器，使用方向鍵 + 空白鍵/Enter
# 回傳以空白分隔的已選取值
function Select-Checkbox {
    param(
        [array]$Items  # 每項：@{ Label; Value; State; Hint }
    )

    $count  = $Items.Count
    $cursor = 0
    $states = @()
    foreach ($item in $Items) {
        $states += $item.State
    }

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # 備援模式：顯示編號清單，接受以逗號分隔的數字
        Write-Host ""
        for ($j = 0; $j -lt $count; $j++) {
            $mark = if ($states[$j]) { "[X]" } else { "[ ]" }
            $hint = $Items[$j].Hint
            Write-Host "  $($j + 1). $mark $($Items[$j].Label)  ($hint)"
        }
        Write-Host ""
        Write-Host "  輸入數字以切換（例如 1,3），或按 Enter 接受預設值： " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            # 重設所有狀態
            for ($j = 0; $j -lt $count; $j++) { $states[$j] = $false }
            $nums = $input_ -split ',' | ForEach-Object { $_.Trim() }
            foreach ($n in $nums) {
                $idx = [int]$n - 1
                if ($idx -ge 0 -and $idx -lt $count) { $states[$idx] = $true }
            }
        }
        $selected = @()
        for ($j = 0; $j -lt $count; $j++) {
            if ($states[$j]) { $selected += $Items[$j].Value }
        }
        return ($selected -join ' ')
    }

    # 完整互動模式
    Write-Host ""
    Write-Host "  ↑/↓ 導覽，空白鍵切換選取，在確認時按 Enter 完成" -ForegroundColor DarkGray
    Write-Host ""

    $totalRows = $count + 2  # items + blank + Confirm

    # 隱藏游標
    try { [Console]::CursorVisible = $false } catch {}

    # 繪製函式 — 使用相對游標移動以處理終端捲動
    $drawCheckbox = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
            $line = "  "
            if ($j -eq $cursor) {
                Write-Host "  " -NoNewline
                Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline
            } else {
                Write-Host "    " -NoNewline
            }
            if ($states[$j]) {
                Write-Host "[" -NoNewline
                Write-Host "v" -ForegroundColor Green -NoNewline
                Write-Host "]" -NoNewline
            } else {
                Write-Host "[ ]" -NoNewline
            }
            $padLabel = $Items[$j].Label.PadRight(16)
            Write-Host " $padLabel " -NoNewline
            if ($states[$j]) {
                Write-Host $Items[$j].Hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $Items[$j].Hint -ForegroundColor DarkGray -NoNewline
            }
            # 清除剩餘行內容
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
        # 空白行
        Write-Host (' ' * ([Console]::WindowWidth - 1))
        # 確認按鈕
        if ($cursor -eq $count) {
            Write-Host "  " -NoNewline
            Write-Host ">" -ForegroundColor Blue -NoNewline
            Write-Host " " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
        } else {
            Write-Host "    " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
        }
        $pos = [Console]::CursorLeft
        $remaining = [Console]::WindowWidth - $pos - 1
        if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
        Write-Host ""
    }

    # 初始繪製 — 先預留行數
    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawCheckbox

    # 輸入迴圈
    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { # 上方向鍵
                if ($cursor -gt 0) { $cursor-- }
            }
            40 { # 下方向鍵
                if ($cursor -lt $count) { $cursor++ }
            }
            32 { # 空白鍵
                if ($cursor -lt $count) {
                    $states[$cursor] = -not $states[$cursor]
                }
            }
            13 { # Enter
                if ($cursor -lt $count) {
                    $states[$cursor] = -not $states[$cursor]
                } else {
                    # 在確認按鈕上按 Enter — 完成
                    & $drawCheckbox
                    break
                }
            }
        }
        if ($key.VirtualKeyCode -eq 13 -and $cursor -eq $count) { break }

        & $drawCheckbox
    }

    # 顯示游標
    try { [Console]::CursorVisible = $true } catch {}

    $selected = @()
    for ($j = 0; $j -lt $count; $j++) {
        if ($states[$j]) { $selected += $Items[$j].Value }
    }
    return ($selected -join ' ')
}

# 互動式單選選擇器，使用方向鍵 + Enter
# 回傳已選取的值
function Select-Radio {
    param(
        [array]$Items  # 每項：@{ Label; Value; Selected; Hint }
    )

    $count    = $Items.Count
    $cursor   = 0
    $selected = 0

    for ($j = 0; $j -lt $count; $j++) {
        if ($Items[$j].Selected) { $selected = $j }
    }

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # 備援模式：編號清單
        Write-Host ""
        for ($j = 0; $j -lt $count; $j++) {
            $mark = if ($j -eq $selected) { "(*)" } else { "( )" }
            $hint = $Items[$j].Hint
            Write-Host "  $($j + 1). $mark $($Items[$j].Label)  $hint"
        }
        Write-Host ""
        Write-Host "  輸入數字選擇（或按 Enter 接受預設值）： " -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            $idx = [int]$input_ - 1
            if ($idx -ge 0 -and $idx -lt $count) { $selected = $idx }
        }
        return $Items[$selected].Value
    }

    # 完整互動模式
    Write-Host ""
    Write-Host "  ↑/↓ 導覽，Enter 確認" -ForegroundColor DarkGray
    Write-Host ""

    $totalRows = $count + 2  # items + blank + Confirm

    try { [Console]::CursorVisible = $false } catch {}

    # 繪製函式 — 使用相對游標移動以處理終端捲動
    $drawRadio = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
            if ($j -eq $cursor) {
                Write-Host "  " -NoNewline
                Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline
            } else {
                Write-Host "    " -NoNewline
            }
            if ($j -eq $selected) {
                Write-Host "(*)" -ForegroundColor Green -NoNewline
            } else {
                Write-Host "( )" -ForegroundColor DarkGray -NoNewline
            }
            $padLabel = $Items[$j].Label.PadRight(20)
            Write-Host " $padLabel " -NoNewline
            if ($j -eq $selected) {
                Write-Host $Items[$j].Hint -ForegroundColor Green -NoNewline
            } else {
                Write-Host $Items[$j].Hint -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
        Write-Host (' ' * ([Console]::WindowWidth - 1))
        if ($cursor -eq $count) {
            Write-Host "  " -NoNewline
            Write-Host ">" -ForegroundColor Blue -NoNewline
            Write-Host " " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
        } else {
            Write-Host "    " -NoNewline
            Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
        }
        $pos = [Console]::CursorLeft
        $remaining = [Console]::WindowWidth - $pos - 1
        if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
        Write-Host ""
    }

    # 預留行數

    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }
            40 { if ($cursor -lt $count) { $cursor++ } }
            32 { # 空白鍵 — 選取但繼續瀏覽
                if ($cursor -lt $count) { $selected = $cursor }
            }
            13 { # Enter — 選取並確認
                if ($cursor -lt $count) { $selected = $cursor }
                & $drawRadio
                break
            }
        }
        if ($key.VirtualKeyCode -eq 13) { break }

        & $drawRadio
    }

    try { [Console]::CursorVisible = $true } catch {}

    return $Items[$selected].Value
}

# ─── 工具偵測與選擇 ───────────────────────────────
function Invoke-DetectTools {
    if (-not [string]::IsNullOrWhiteSpace($script:UserTools)) {
        $script:Tools = $script:UserTools -replace ',', ' '
        return
    }

    $hasClaude  = $null -ne (Get-Command claude -ErrorAction SilentlyContinue)
    $hasCursor  = ($null -ne (Get-Command cursor -ErrorAction SilentlyContinue)) -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe")
    $hasCodex   = $null -ne (Get-Command codex -ErrorAction SilentlyContinue)
    $hasCopilot = ($null -ne (Get-Command code -ErrorAction SilentlyContinue)) -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe")
    $hasGemini  = $null -ne (Get-Command gemini -ErrorAction SilentlyContinue)
    $hasAntigravity = ($null -ne (Get-Command antigravity -ErrorAction SilentlyContinue)) -or
                      (Test-Path "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe")

    $claudeState  = $hasClaude;  $claudeHint  = if ($hasClaude)  { "已偵測" } else { "未找到" }
    $cursorState  = $hasCursor;  $cursorHint  = if ($hasCursor)  { "已偵測" } else { "未找到" }
    $codexState   = $hasCodex;   $codexHint   = if ($hasCodex)   { "已偵測" } else { "未找到" }
    $copilotState = $hasCopilot; $copilotHint = if ($hasCopilot) { "已偵測" } else { "未找到" }
    $geminiState  = $hasGemini;  $geminiHint  = if ($hasGemini)  { "已偵測" } else { "未找到" }
    $antigravityState = $hasAntigravity; $antigravityHint = if ($hasAntigravity) { "已偵測" } else { "未找到" }

    # 若未偵測到任何工具，預設使用 claude
    if (-not $hasClaude -and -not $hasCursor -and -not $hasCodex -and -not $hasCopilot -and -not $hasGemini -and -not $hasAntigravity) {
        $claudeState = $true
        $claudeHint  = "預設"
    }

    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  選擇要安裝的工具：" -ForegroundColor White
    }

    $items = @(
        @{ Label = "Claude Code";    Value = "claude";       State = $claudeState;       Hint = $claudeHint }
        @{ Label = "Cursor";         Value = "cursor";       State = $cursorState;       Hint = $cursorHint }
        @{ Label = "GitHub Copilot"; Value = "copilot";      State = $copilotState;      Hint = $copilotHint }
        @{ Label = "OpenAI Codex";   Value = "codex";        State = $codexState;        Hint = $codexHint }
        @{ Label = "Gemini CLI";     Value = "gemini";       State = $geminiState;       Hint = $geminiHint }
        @{ Label = "Antigravity";    Value = "antigravity";  State = $antigravityState;  Hint = $antigravityHint }
    )

    $result = Select-Checkbox -Items $items

    if ([string]::IsNullOrWhiteSpace($result)) {
        Write-Warn "未選擇任何工具，預設使用 Claude Code"
        $result = "claude"
    }

    $script:Tools = $result
}

# ─── Databricks Profile 選擇 ────────────────────────────
function Invoke-PromptProfile {
    if ($script:ProfileProvided) { return }
    if ($script:Silent) { return }

    $cfgFile = Join-Path $env:USERPROFILE ".databrickscfg"
    $profiles = @()

    if (Test-Path $cfgFile) {
        $lines = Get-Content $cfgFile
        foreach ($line in $lines) {
            if ($line -match '^\[([a-zA-Z0-9_-]+)\]$') {
                $profiles += $Matches[1]
            }
        }
    }

    Write-Host ""
    Write-Host "  選擇 Databricks Profile" -ForegroundColor White

    if ($profiles.Count -gt 0) {
        $items = @()
        $hasDefault = $profiles -contains "DEFAULT"
        foreach ($p in $profiles) {
            $sel  = $false
            $hint = ""
            if ($p -eq "DEFAULT") { $sel = $true; $hint = "default" }
            $items += @{ Label = $p; Value = $p; Selected = $sel; Hint = $hint }
        }
        
        # 在結尾新增自訂 Profile 選項
        $items += @{ Label = "自訂 Profile 名稱…"; Value = "__CUSTOM__"; Selected = $false; Hint = "輸入自訂 Profile 名稱" }
        
        if (-not $hasDefault -and $items.Count -gt 1) {
            $items[0].Selected = $true
        }

        $selectedProfile = Select-Radio -Items $items
        
        # 若選取自訂，提示輸入名稱
        if ($selectedProfile -eq "__CUSTOM__") {
            Write-Host ""
            $script:Profile_ = Read-Prompt -PromptText "輸入 Profile 名稱" -Default "DEFAULT"
        } else {
            $script:Profile_ = $selectedProfile
        }
    } else {
        Write-Host "  找不到 ~/.databrickscfg，可在安裝後執行認證。" -ForegroundColor DarkGray
        Write-Host ""
        $script:Profile_ = Read-Prompt -PromptText "Profile 名稱" -Default "DEFAULT"
    }
}

# ─── MCP 路徑選擇 ──────────────────────────────────────
function Invoke-PromptMcpPath {
    if (-not [string]::IsNullOrWhiteSpace($script:UserMcpPath)) {
        $script:InstallDir = $script:UserMcpPath
    } elseif (-not $script:Silent) {
        Write-Host ""
        Write-Host "  MCP 伺服器位置" -ForegroundColor White
        Write-Host "  MCP 伺服器執行環境（Python venv + 原始碼）將安裝在此。" -ForegroundColor DarkGray
        Write-Host "  跨所有專案共用──僅設定檔為各專案獨立。" -ForegroundColor DarkGray
        Write-Host ""

        $selected = Read-Prompt -PromptText "安裝路徑" -Default $InstallDir
        $script:InstallDir = $selected
    }

    # 更新衍生路徑
    $script:RepoDir    = Join-Path $script:InstallDir "repo"
    $script:VenvDir    = Join-Path $script:InstallDir ".venv"
    $script:VenvPython = Join-Path $script:VenvDir "Scripts\python.exe"
    $script:McpEntry   = Join-Path $script:RepoDir "databricks-mcp-server\run_server.py"
}

# ─── 檢查必要條件 ─────────────────────────────────────
function Test-Dependencies {
    # Git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Err "需要 git。安裝方式：choco install git -y"
    }
    Write-Ok "git"

    # Databricks CLI
    if (Get-Command databricks -ErrorAction SilentlyContinue) {
        try {
            $cliOutput = & databricks --version 2>&1
            if ($cliOutput -match '(\d+\.\d+\.\d+)') {
                $cliVersion = $Matches[1]
                if ([version]$cliVersion -ge [version]$MinCliVersion) {
                    Write-Ok "Databricks CLI v$cliVersion"
                } else {
                    Write-Warn "Databricks CLI v$cliVersion 版本過舊（最低需求：v$MinCliVersion）"
                    Write-Msg "  Upgrade: winget upgrade Databricks.DatabricksCLI"
                }
            } else {
                Write-Warn "無法確認 Databricks CLI 版本"
            }
        } catch {
            Write-Warn "無法確認 Databricks CLI 版本"
        }
    } else {
        Write-Warn "找不到 Databricks CLI。安裝方式：winget install Databricks.DatabricksCLI"
        Write-Msg "仍可繼續安裝，但認證需稍後安裝 CLI。"
    }

    # Python 套件管理工具
    if ($script:InstallMcp) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            $script:Pkg = "uv"
        } elseif (Get-Command pip3 -ErrorAction SilentlyContinue) {
            $script:Pkg = "pip3"
        } elseif (Get-Command pip -ErrorAction SilentlyContinue) {
            $script:Pkg = "pip"
        } else {
            Write-Err "需要 Python 套件管理工具。安裝 Python：choco install python -y"
        }
        Write-Ok $script:Pkg
    }
}

# ─── 版本檢查 ───────────────────────────────────────────
function Test-Version {
    $verFile = Join-Path $script:InstallDir "version"
    if ($script:Scope -eq "project") {
        $verFile = Join-Path (Get-Location) ".ai-dev-kit\version"
    }

    if (-not (Test-Path $verFile)) { return }
    if ($script:Force) { return }

    # 若使用者明確要求不同的 skill 設定檔，略過版本檢查
    if (-not [string]::IsNullOrWhiteSpace($script:SkillsProfile) -or -not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        $savedProfileFile = Join-Path $script:StateDir ".skills-profile"
        if (-not (Test-Path $savedProfileFile) -and $script:Scope -eq "project") {
            $savedProfileFile = Join-Path $script:InstallDir ".skills-profile"
        }
        if (Test-Path $savedProfileFile) {
            $savedProfile = (Get-Content $savedProfileFile -Raw).Trim()
            $requested = if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) { "custom:$($script:UserSkills)" } else { $script:SkillsProfile }
            if ($savedProfile -ne $requested) { return }
        }
    }

    $localVer = (Get-Content $verFile -Raw).Trim()

    try {
        $remoteVer = (Invoke-WebRequest -Uri "$RawUrl/VERSION" -UseBasicParsing -ErrorAction Stop).Content.Trim()
    } catch {
        return
    }

    if ($remoteVer -and $remoteVer -notmatch '(404|Not Found|error)') {
        if ($localVer -eq $remoteVer) {
            Write-Ok "已是最新版本（v$localVer）"
            Write-Msg "使用 --force 重新安裝，或使用 --skills-profile 更換設定檔"
            exit 0
        }
    }
}

# ─── 設定 MCP 伺服器 ────────────────────────────────────────
function Install-McpServer {
    Write-Step "設定 MCP 伺服器"

    # 原生命令（git、pip）會將資訊訊息寫入 stderr。
    # 暫時放寬錯誤處理，避免這些訊息終止腳本。
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # 複製或更新 repo
    if (Test-Path (Join-Path $script:RepoDir ".git")) {
        & git -C $script:RepoDir fetch -q --depth 1 origin $Branch 2>&1 | Out-Null
        & git -C $script:RepoDir reset --hard FETCH_HEAD 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -Recurse -Force $script:RepoDir -ErrorAction SilentlyContinue
            & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
        }
    } else {
        if (-not (Test-Path $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
    }
    if ($LASTEXITCODE -ne 0) {
        $ErrorActionPreference = $prevEAP
        Write-Err "複製 repository 失敗"
    }
    Write-Ok "Repository 複製完成（$Branch）"

    # 建立 venv 並安裝
    Write-Msg "安裝 Python 套件中..."
    if ($script:Pkg -eq "uv") {
        & uv venv --python 3.11 --allow-existing $script:VenvDir -q 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            & uv venv --allow-existing $script:VenvDir -q 2>&1 | Out-Null
        }
        & uv pip install --python $script:VenvPython -e "$($script:RepoDir)\databricks-tools-core" -e "$($script:RepoDir)\databricks-mcp-server" -q 2>&1 | Out-Null
    } else {
        if (-not (Test-Path $script:VenvDir)) {
            & python -m venv $script:VenvDir 2>&1 | Out-Null
        }
        & $script:VenvPython -m pip install -q -e "$($script:RepoDir)\databricks-tools-core" -e "$($script:RepoDir)\databricks-mcp-server" 2>&1 | Out-Null
    }

    # 驗證
    & $script:VenvPython -c "import databricks_mcp_server" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $ErrorActionPreference = $prevEAP
        Write-Err "MCP 伺服器安裝失敗"
    }

    $ErrorActionPreference = $prevEAP
    Write-Ok "MCP 伺服器就緒"

    # 檢查 Databricks SDK 版本
    try {
        $sdkOutput = & $script:VenvPython -c "from databricks.sdk.version import __version__; print(__version__)" 2>&1
        if ($sdkOutput -match '(\d+\.\d+\.\d+)') {
            $sdkVersion = $Matches[1]
            if ([version]$sdkVersion -ge [version]$MinSdkVersion) {
                Write-Ok "Databricks SDK v$sdkVersion"
            } else {
                Write-Warn "Databricks SDK v$sdkVersion 版本過舊（最低需求：v$MinSdkVersion）"
                Write-Msg "  Upgrade: $($script:VenvPython) -m pip install --upgrade databricks-sdk"
            }
        } else {
            Write-Warn "無法確認 Databricks SDK 版本"
        }
    } catch {
        Write-Warn "無法確認 Databricks SDK 版本"
    }
}

# ─── Skill 設定檔選擇 ──────────────────────────────────
function Resolve-Skills {
    # 優先級 1：明確的 --skills 旗標
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        $userList = $script:UserSkills -split ','
        $dbSkills = @() + $script:CoreSkills
        $mlflowSkills = @()
        $apxSkills = @()
        foreach ($skill in $userList) {
            $skill = $skill.Trim()
            if ($script:MlflowSkills -contains $skill) {
                $mlflowSkills += $skill
            } elseif ($script:ApxSkills -contains $skill) {
                $apxSkills += $skill
            } else {
                $dbSkills += $skill
            }
        }
        $script:SelectedSkills = $dbSkills | Select-Object -Unique
        $script:SelectedMlflowSkills = $mlflowSkills | Select-Object -Unique
        $script:SelectedApxSkills = $apxSkills | Select-Object -Unique
        return
    }

    # 優先級 2：--skills-profile 旗標或互動式選擇
    if ([string]::IsNullOrWhiteSpace($script:SkillsProfile) -or $script:SkillsProfile -eq "all") {
        $script:SelectedSkills = $script:Skills
        $script:SelectedMlflowSkills = $script:MlflowSkills
        $script:SelectedApxSkills = $script:ApxSkills
        return
    }

    # 建立已選取設定檔的聯集
    $dbSkills = @() + $script:CoreSkills
    $mlflowSkills = @()
    $apxSkills = @()

    foreach ($profile in ($script:SkillsProfile -split ',')) {
        $profile = $profile.Trim()
        switch ($profile) {
            "all" {
                $script:SelectedSkills = $script:Skills
                $script:SelectedMlflowSkills = $script:MlflowSkills
                $script:SelectedApxSkills = $script:ApxSkills
                return
            }
            "data-engineer"  { $dbSkills += $script:ProfileDataEngineer }
            "analyst"        { $dbSkills += $script:ProfileAnalyst }
            "ai-ml-engineer" {
                $dbSkills += $script:ProfileAiMlEngineer
                $mlflowSkills += $script:ProfileAiMlMlflow
            }
            "app-developer" {
                $dbSkills += $script:ProfileAppDeveloper
                $apxSkills += $script:ApxSkills
            }
            default { Write-Warn "未知的 Skill 設定檔：$profile（已略過）" }
        }
    }

    $script:SelectedSkills = $dbSkills | Select-Object -Unique
    $script:SelectedMlflowSkills = $mlflowSkills | Select-Object -Unique
    $script:SelectedApxSkills = $apxSkills | Select-Object -Unique
}

function Invoke-PromptSkillsProfile {
    # 若已透過 --skills 或 --skills-profile 提供，略過互動式提示
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills) -or -not [string]::IsNullOrWhiteSpace($script:SkillsProfile)) {
        return
    }

    # 靜默模式下略過
    if ($script:Silent) {
        $script:SkillsProfile = "all"
        return
    }

    # 先檢查範圍本地的上次選取記錄，若無則退回全域（供舊版升級使用）
    $profileFile = Join-Path $script:StateDir ".skills-profile"
    if (-not (Test-Path $profileFile) -and $script:Scope -eq "project") {
        $profileFile = Join-Path $script:InstallDir ".skills-profile"
    }
    if (Test-Path $profileFile) {
        $prevProfile = (Get-Content $profileFile -Raw).Trim()
        if (-not $script:Force) {
            Write-Host ""
            $displayProfile = $prevProfile -replace ',', ', '
            $keep = Read-Prompt -PromptText "上次的 Skill 設定檔：$displayProfile。保留？(Y/n)" -Default "y"
            if ($keep -in @("y", "Y", "yes", "")) {
                $script:SkillsProfile = $prevProfile
                return
            }
        }
    }

    Write-Host ""
    Write-Host "  選擇 Skill 設定檔" -ForegroundColor White

    # 自訂核取方塊，具互斥邏輯：選取「全部」會取消其他選項，選取其他會取消「全部」
    $pLabels = @("全部 Skills", "資料工程師", "商業分析師", "AI/ML 工程師", "應用程式開發者", "自訂")
    $pValues = @("all", "data-engineer", "analyst", "ai-ml-engineer", "app-developer", "custom")
    $pHints  = @("安裝全部（34 個 skills）", "Pipelines、Spark、Jobs、Streaming（14 個 skills）", "儀表板、SQL、Genie、指標（8 個 skills）", "Agents、RAG、向量搜尋、MLflow（17 個 skills）", "應用程式、Lakebase、部署（10 個 skills）", "自行挑選 Skills")
    $pStates = @($true, $false, $false, $false, $false, $false)
    $pCount  = 6
    $pCursor = 0
    $pTotalRows = $pCount + 2

    $isInteractive = Test-Interactive

    if (-not $isInteractive) {
        # 備援模式：編號清單
        Write-Host ""
        for ($j = 0; $j -lt $pCount; $j++) {
            $mark = if ($pStates[$j]) { "[X]" } else { "[ ]" }
            Write-Host "  $($j + 1). $mark $($pLabels[$j])  ($($pHints[$j]))"
        }
        Write-Host ""
        Write-Host "  輸入數字以切換（例如 2,4），或按 Enter 選擇全部：" -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_)) {
            for ($j = 0; $j -lt $pCount; $j++) { $pStates[$j] = $false }
            $nums = $input_ -split ',' | ForEach-Object { $_.Trim() }
            foreach ($n in $nums) {
                $idx = [int]$n - 1
                if ($idx -ge 0 -and $idx -lt $pCount) { $pStates[$idx] = $true }
            }
        }
    } else {
        Write-Host ""
        Write-Host "  ↑/↓ 導覽，空白鍵切換選取，在確認時按 Enter 完成" -ForegroundColor DarkGray
        Write-Host ""

        try { [Console]::CursorVisible = $false } catch {}

        $drawProfiles = {
            [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $pTotalRows))
            for ($j = 0; $j -lt $pCount; $j++) {
                if ($j -eq $pCursor) {
                    Write-Host "  " -NoNewline; Write-Host ">" -ForegroundColor Blue -NoNewline; Write-Host " " -NoNewline
                } else {
                    Write-Host "    " -NoNewline
                }
                if ($pStates[$j]) {
                    Write-Host "[" -NoNewline; Write-Host "v" -ForegroundColor Green -NoNewline; Write-Host "]" -NoNewline
                } else {
                    Write-Host "[ ]" -NoNewline
                }
                $padLabel = $pLabels[$j].PadRight(20)
                Write-Host " $padLabel " -NoNewline
                if ($pStates[$j]) {
                    Write-Host $pHints[$j] -ForegroundColor Green -NoNewline
                } else {
                    Write-Host $pHints[$j] -ForegroundColor DarkGray -NoNewline
                }
                $pos = [Console]::CursorLeft
                $remaining = [Console]::WindowWidth - $pos - 1
                if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
                Write-Host ""
            }
            Write-Host (' ' * ([Console]::WindowWidth - 1))
            if ($pCursor -eq $pCount) {
                Write-Host "  " -NoNewline; Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline; Write-Host "[ Confirm ]" -ForegroundColor Green -NoNewline
            } else {
                Write-Host "    " -NoNewline; Write-Host "[ Confirm ]" -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }

        for ($j = 0; $j -lt $pTotalRows; $j++) { Write-Host "" }
        & $drawProfiles

        while ($true) {
            $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

            switch ($key.VirtualKeyCode) {
                38 { if ($pCursor -gt 0) { $pCursor-- } }
                40 { if ($pCursor -lt $pCount) { $pCursor++ } }
                32 { # 空白鍵
                    if ($pCursor -lt $pCount) {
                        $pStates[$pCursor] = -not $pStates[$pCursor]
                        if ($pStates[$pCursor]) {
                            if ($pCursor -eq 0) {
                                # 選取「全部」→ 取消其他選項
                                for ($j = 1; $j -lt $pCount; $j++) { $pStates[$j] = $false }
                            } else {
                                # 選取個別項目 → 取消「全部」
                                $pStates[0] = $false
                            }
                        }
                    }
                }
                13 { # Enter
                    if ($pCursor -lt $pCount) {
                        $pStates[$pCursor] = -not $pStates[$pCursor]
                        if ($pStates[$pCursor]) {
                            if ($pCursor -eq 0) {
                                for ($j = 1; $j -lt $pCount; $j++) { $pStates[$j] = $false }
                            } else {
                                $pStates[0] = $false
                            }
                        }
                    } else {
                        & $drawProfiles
                        break
                    }
                }
            }
            if ($key.VirtualKeyCode -eq 13 -and $pCursor -eq $pCount) { break }
            & $drawProfiles
        }

        try { [Console]::CursorVisible = $true } catch {}
    }

    # 從狀態建立結果
    $selectedProfiles = @()
    for ($j = 0; $j -lt $pCount; $j++) {
        if ($pStates[$j]) { $selectedProfiles += $pValues[$j] }
    }
    $selected = $selectedProfiles -join ' '

    if ([string]::IsNullOrWhiteSpace($selected)) {
        $script:SkillsProfile = "all"
        return
    }

    if ($selected -match '\ball\b') {
        $script:SkillsProfile = "all"
        return
    }

    if ($selected -match '\bcustom\b') {
        Invoke-PromptCustomSkills -PreselectedProfiles $selected
        return
    }

    $script:SkillsProfile = ($selectedProfiles -join ',')
}

function Invoke-PromptCustomSkills {
    param([string]$PreselectedProfiles)

    # 從已勾選的設定檔建立預選集合
    $preselected = @()
    foreach ($profile in ($PreselectedProfiles -split ' ')) {
        switch ($profile) {
            "data-engineer"  { $preselected += $script:ProfileDataEngineer }
            "analyst"        { $preselected += $script:ProfileAnalyst }
            "ai-ml-engineer" { $preselected += $script:ProfileAiMlEngineer + $script:ProfileAiMlMlflow }
            "app-developer"  { $preselected += $script:ProfileAppDeveloper + $script:ApxSkills }
        }
    }

    Write-Host ""
    Write-Host "  選擇個別 Skills" -ForegroundColor White
    Write-Host "  核心 Skills（config、docs、python-sdk、unity-catalog）一定安裝" -ForegroundColor DarkGray

    $items = @(
        @{ Label = "Spark Pipelines";      Value = "databricks-spark-declarative-pipelines"; State = ($preselected -contains "databricks-spark-declarative-pipelines"); Hint = "SDP/LDP, CDC, SCD Type 2" }
        @{ Label = "Streaming";            Value = "databricks-spark-structured-streaming";  State = ($preselected -contains "databricks-spark-structured-streaming");  Hint = "Real-time streaming" }
        @{ Label = "Jobs & Workflows";     Value = "databricks-jobs";                        State = ($preselected -contains "databricks-jobs");                        Hint = "Multi-task orchestration" }
        @{ Label = "Asset Bundles";        Value = "databricks-bundles";               State = ($preselected -contains "databricks-bundles");               Hint = "DABs deployment" }
        @{ Label = "Databricks SQL";       Value = "databricks-dbsql";                       State = ($preselected -contains "databricks-dbsql");                       Hint = "SQL warehouse queries" }
        @{ Label = "Iceberg";              Value = "databricks-iceberg";                     State = ($preselected -contains "databricks-iceberg");                     Hint = "Apache Iceberg tables" }
        @{ Label = "Zerobus Ingest";       Value = "databricks-zerobus-ingest";              State = ($preselected -contains "databricks-zerobus-ingest");              Hint = "Streaming ingestion" }
        @{ Label = "Python Data Src";      Value = "spark-python-data-source";               State = ($preselected -contains "spark-python-data-source");               Hint = "Custom Spark data sources" }
        @{ Label = "Metric Views";         Value = "databricks-metric-views";                State = ($preselected -contains "databricks-metric-views");                Hint = "Metric definitions" }
        @{ Label = "AI/BI Dashboards";     Value = "databricks-aibi-dashboards";             State = ($preselected -contains "databricks-aibi-dashboards");             Hint = "Dashboard creation" }
        @{ Label = "Genie";                Value = "databricks-genie";                       State = ($preselected -contains "databricks-genie");                       Hint = "Natural language SQL" }
        @{ Label = "Agent Bricks";         Value = "databricks-agent-bricks";                State = ($preselected -contains "databricks-agent-bricks");                Hint = "Build AI agents" }
        @{ Label = "Vector Search";        Value = "databricks-vector-search";               State = ($preselected -contains "databricks-vector-search");               Hint = "Similarity search" }
        @{ Label = "Model Serving";        Value = "databricks-model-serving";               State = ($preselected -contains "databricks-model-serving");               Hint = "Deploy models/agents" }
        @{ Label = "MLflow Evaluation";    Value = "databricks-mlflow-evaluation";           State = ($preselected -contains "databricks-mlflow-evaluation");           Hint = "Model evaluation" }
        @{ Label = "AI Functions";          Value = "databricks-ai-functions";                State = ($preselected -contains "databricks-ai-functions");                Hint = "AI Functions, document parsing & RAG" }
        @{ Label = "Unstructured PDF";     Value = "databricks-unstructured-pdf-generation"; State = ($preselected -contains "databricks-unstructured-pdf-generation"); Hint = "Synthetic PDFs for RAG" }
        @{ Label = "Synthetic Data";       Value = "databricks-synthetic-data-gen";          State = ($preselected -contains "databricks-synthetic-data-gen");          Hint = "Generate test data" }
        @{ Label = "Lakebase Autoscale";   Value = "databricks-lakebase-autoscale";          State = ($preselected -contains "databricks-lakebase-autoscale");          Hint = "Managed PostgreSQL" }
        @{ Label = "Lakebase Provisioned"; Value = "databricks-lakebase-provisioned";        State = ($preselected -contains "databricks-lakebase-provisioned");        Hint = "Provisioned PostgreSQL" }
        @{ Label = "App Python";           Value = "databricks-app-python";                  State = ($preselected -contains "databricks-app-python");                  Hint = "Dash, Streamlit, Flask" }
        @{ Label = "App APX";              Value = "databricks-app-apx";                     State = ($preselected -contains "databricks-app-apx");                     Hint = "FastAPI + React" }
        @{ Label = "MLflow Onboarding";    Value = "mlflow-onboarding";                      State = ($preselected -contains "mlflow-onboarding");                      Hint = "Getting started" }
        @{ Label = "Agent Evaluation";     Value = "agent-evaluation";                       State = ($preselected -contains "agent-evaluation");                       Hint = "Evaluate AI agents" }
        @{ Label = "MLflow Tracing";       Value = "instrumenting-with-mlflow-tracing";      State = ($preselected -contains "instrumenting-with-mlflow-tracing");      Hint = "Instrument with tracing" }
        @{ Label = "Analyze Traces";       Value = "analyze-mlflow-trace";                   State = ($preselected -contains "analyze-mlflow-trace");                   Hint = "Analyze trace data" }
        @{ Label = "Retrieve Traces";      Value = "retrieving-mlflow-traces";               State = ($preselected -contains "retrieving-mlflow-traces");               Hint = "Search & retrieve traces" }
        @{ Label = "Analyze Chat";         Value = "analyze-mlflow-chat-session";            State = ($preselected -contains "analyze-mlflow-chat-session");            Hint = "Chat session analysis" }
        @{ Label = "Query Metrics";        Value = "querying-mlflow-metrics";                State = ($preselected -contains "querying-mlflow-metrics");                Hint = "MLflow metrics queries" }
        @{ Label = "Search MLflow Docs";   Value = "searching-mlflow-docs";                  State = ($preselected -contains "searching-mlflow-docs");                  Hint = "MLflow documentation" }
    )

    $selected = Select-Checkbox -Items $items
    $script:UserSkills = ($selected -split ' ') -join ','
}

# ─── 安裝 Skills ──────────────────────────────────────────
function Install-Skills {
    param([string]$BaseDir)

    Write-Step "安裝 Skills"

    $dirs = @()
    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" { $dirs += Join-Path $BaseDir ".claude\skills" }
            "cursor" {
                if ($script:Tools -notmatch 'claude') {
                    $dirs += Join-Path $BaseDir ".cursor\skills"
                }
            }
            "copilot" { $dirs += Join-Path $BaseDir ".github\skills" }
            "codex"   { $dirs += Join-Path $BaseDir ".agents\skills" }
            "gemini"  { $dirs += Join-Path $BaseDir ".gemini\skills" }
            "antigravity" {
                if ($script:Scope -eq "global") {
                    $dirs += Join-Path $env:USERPROFILE ".gemini\antigravity\skills"
                } else {
                    $dirs += Join-Path $BaseDir ".agents\skills"
                }
            }
        }
    }
    $dirs = $dirs | Select-Object -Unique

    # 統計已選取的 skills 數量供顯示用
    $dbCount = $script:SelectedSkills.Count
    $mlflowCount = $script:SelectedMlflowSkills.Count
    $apxCount = $script:SelectedApxSkills.Count
    $totalCount = $dbCount + $mlflowCount + $apxCount
    Write-Msg "正在安裝 $totalCount 個 skills"

    # 建立本次安裝的所有 skills 集合
    $allNewSkills = @()
    $allNewSkills += $script:SelectedSkills
    $allNewSkills += $script:SelectedMlflowSkills
    $allNewSkills += $script:SelectedApxSkills

    # 清理先前已安裝但已取消選取的 skills
    # 先檢查範圍本地的清單，若無則退回全域（供舊版升級使用）
    $manifest = Join-Path $script:StateDir ".installed-skills"
    if (-not (Test-Path $manifest) -and $script:Scope -eq "project" -and (Test-Path (Join-Path $script:InstallDir ".installed-skills"))) {
        $manifest = Join-Path $script:InstallDir ".installed-skills"
    }
    if (Test-Path $manifest) {
        foreach ($line in (Get-Content $manifest)) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $parts = $line -split '\|', 2
            if ($parts.Count -ne 2) { continue }
            $prevDir = $parts[0]
            $prevSkill = $parts[1]
            # 若此 skill 仍在選取清單中則略過
            if ($allNewSkills -contains $prevSkill) { continue }
            # 僅在目錄存在時才刪除
            $prevPath = Join-Path $prevDir $prevSkill
            if (Test-Path $prevPath) {
                Remove-Item -Recurse -Force $prevPath
                Write-Msg "已移除取消選取的 skill：$prevSkill"
            }
        }
    }

    # 重新建立清單
    $manifestEntries = @()

    foreach ($dir in $dirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # 從 repo 安裝 Databricks skills
        foreach ($skill in $script:SelectedSkills) {
            $src = Join-Path $script:RepoDir "databricks-skills\$skill"
            if (-not (Test-Path $src)) { continue }
            $dest = Join-Path $dir $skill
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Copy-Item -Recurse $src $dest
            $manifestEntries += "$dir|$skill"
        }
        $shortDir = $dir -replace [regex]::Escape($env:USERPROFILE), '~'
        Write-Ok "Databricks skills（$dbCount）→ $shortDir"

        # 從 mlflow/skills repo 安裝 MLflow skills
        if ($script:SelectedMlflowSkills.Count -gt 0) {
            $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedMlflowSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$MlflowRawUrl/$skill/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("reference.md", "examples.md", "api.md")) {
                        try {
                            Invoke-WebRequest -Uri "$MlflowRawUrl/$skill/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item -Recurse -Force $destDir -ErrorAction SilentlyContinue
                }
            }
            $ErrorActionPreference = $prevEAP
            Write-Ok "MLflow skills（$mlflowCount）→ $shortDir"
        }

        # 從 databricks-solutions/apx repo 安裝 APX skills
        if ($script:SelectedApxSkills.Count -gt 0) {
            $prevEAP2 = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($skill in $script:SelectedApxSkills) {
                $destDir = Join-Path $dir $skill
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                $url = "$ApxRawUrl/SKILL.md"
                try {
                    Invoke-WebRequest -Uri $url -OutFile (Join-Path $destDir "SKILL.md") -UseBasicParsing -ErrorAction Stop
                    foreach ($ref in @("backend-patterns.md", "frontend-patterns.md")) {
                        try {
                            Invoke-WebRequest -Uri "$ApxRawUrl/$ref" -OutFile (Join-Path $destDir $ref) -UseBasicParsing -ErrorAction Stop
                        } catch {}
                    }
                    $manifestEntries += "$dir|$skill"
                } catch {
                    Remove-Item $destDir -ErrorAction SilentlyContinue
                    Write-Warning "無法安裝 APX skill '$skill'──如不再需要，請考慮移除 $destDir"
                }
            }
            $ErrorActionPreference = $prevEAP2
            Write-Ok "APX skills（$apxCount）→ $shortDir"
        }
    }

    # 將清單與設定檔儲存至範圍本地的狀態目錄
    if (-not (Test-Path $script:StateDir)) {
        New-Item -ItemType Directory -Path $script:StateDir -Force | Out-Null
    }
    $manifest = Join-Path $script:StateDir ".installed-skills"
    Set-Content -Path $manifest -Value ($manifestEntries -join "`n") -Encoding UTF8

    # 儲存已選取的設定檔供未來重新安裝使用
    if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
        Set-Content -Path (Join-Path $script:StateDir ".skills-profile") -Value "custom:$($script:UserSkills)" -Encoding UTF8
    } else {
        $profileValue = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
        Set-Content -Path (Join-Path $script:StateDir ".skills-profile") -Value $profileValue -Encoding UTF8
    }
}

# ─── 寫入 MCP 設定 ───────────────────────────────────────
function Write-McpJson {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # 備份現有設定
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "已備份 $(Split-Path $Path -Leaf) → $(Split-Path $Path -Leaf).bak"
    }

    # 嘗試合併至現有設定
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        # 合併至現有設定 — 使用正斜線以確保 JSON 相容性
        if (-not $existing.mcpServers) {
            $existing | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.mcpServers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        # 寫入全新設定 — 使用正斜線以確保跨平台 JSON 相容性
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "mcpServers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-CopilotMcpJson {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # 備份現有設定
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "已備份 $(Split-Path $Path -Leaf) → $(Split-Path $Path -Leaf).bak"
    }

    # 嘗試合併至現有設定
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        if (-not $existing.servers) {
            $existing | Add-Member -NotePropertyName "servers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.servers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "servers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-McpToml {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # 檢查是否已設定
    if (Test-Path $Path) {
        $content = Get-Content $Path -Raw
        if ($content -match 'mcp_servers\.databricks') { return }
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "已備份 $(Split-Path $Path -Leaf) → $(Split-Path $Path -Leaf).bak"
    }

    $pythonPath = $script:VenvPython -replace '\\', '/'
    $entryPath  = $script:McpEntry -replace '\\', '/'
    $tomlBlock = @"

[mcp_servers.databricks]
command = "$pythonPath"
args = ["$entryPath"]
"@
    Add-Content -Path $Path -Value $tomlBlock -Encoding UTF8
}

function Write-GeminiMcpJson {
    param([string]$Path)

    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # 備份現有設定
    if (Test-Path $Path) {
        Copy-Item $Path "$Path.bak" -Force
        Write-Msg "已備份 $(Split-Path $Path -Leaf) → $(Split-Path $Path -Leaf).bak"
    }

    # 嘗試合併至現有設定
    if ((Test-Path $Path) -and (Test-Path $script:VenvPython)) {
        try {
            $existing = Get-Content $Path -Raw | ConvertFrom-Json
        } catch {
            $existing = $null
        }
    }

    if ($existing) {
        if (-not $existing.mcpServers) {
            $existing | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{}) -Force
        }
        $dbEntry = [PSCustomObject]@{
            command = $script:VenvPython -replace '\\', '/'
            args    = @($script:McpEntry -replace '\\', '/')
            env     = [PSCustomObject]@{ DATABRICKS_CONFIG_PROFILE = $script:Profile_ }
        }
        $existing.mcpServers | Add-Member -NotePropertyName "databricks" -NotePropertyValue $dbEntry -Force
        $existing | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding UTF8
    } else {
        $pythonPath = $script:VenvPython -replace '\\', '/'
        $entryPath  = $script:McpEntry -replace '\\', '/'
        $json = @"
{
  "mcpServers": {
    "databricks": {
      "command": "$pythonPath",
      "args": ["$entryPath"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$($script:Profile_)"}
    }
  }
}
"@
        Set-Content -Path $Path -Value $json -Encoding UTF8
    }
}

function Write-GeminiMd {
    param([string]$Path)

    if (Test-Path $Path) { return }  # Don't overwrite existing file

    $content = @"
# Databricks AI Dev Kit

You have access to Databricks skills and MCP tools installed by the Databricks AI Dev Kit.

## Available MCP Tools

The ``databricks`` MCP server provides 50+ tools for interacting with Databricks, including:
- SQL execution and warehouse management
- Unity Catalog operations (tables, volumes, schemas)
- Jobs and workflow management
- Model serving endpoints
- Genie spaces and AI/BI dashboards
- Databricks Apps deployment

## Available Skills

Skills are installed in ``.gemini/skills/`` and provide patterns and best practices for:
- Spark Declarative Pipelines, Structured Streaming
- Databricks Jobs, Asset Bundles
- Unity Catalog, SQL, Genie
- MLflow evaluation and tracing
- Model Serving, Vector Search
- Databricks Apps (Python and APX)
- And more

## Getting Started

Try asking: "List my SQL warehouses" or "Show my Unity Catalog schemas"
"@
    Set-Content -Path $Path -Value $content -Encoding UTF8
    Write-Ok "GEMINI.md"
}

function Write-McpConfigs {
    param([string]$BaseDir)

    Write-Step "設定 MCP"

    foreach ($tool in ($script:Tools -split ' ')) {
        switch ($tool) {
            "claude" {
                if ($script:Scope -eq "global") {
                    Write-McpJson (Join-Path $env:USERPROFILE ".claude\mcp.json")
                } else {
                    Write-McpJson (Join-Path $BaseDir ".mcp.json")
                }
                Write-Ok "Claude MCP config"
            }
            "cursor" {
                if ($script:Scope -eq "global") {
                    Write-Warn "Cursor 全域模式：需手動設定 MCP"
                    Write-Msg "  1. 開啟 Cursor → 設定 → Cursor Settings → Tools & MCP"
                    Write-Msg "  2. 點擊 New MCP Server"
                    Write-Msg "  3. 加入以下 JSON 設定："
                    Write-Msg "     {"
                    Write-Msg "       `"mcpServers`": {"
                    Write-Msg "         `"databricks`": {"
                    Write-Msg "           `"command`": `"$($script:VenvPython)`","
                    Write-Msg "           `"args`": [`"$($script:McpEntry)`"],"
                    Write-Msg "           `"env`": {`"DATABRICKS_CONFIG_PROFILE`": `"$($script:Profile)`"}"
                    Write-Msg "         }"
                    Write-Msg "       }"
                    Write-Msg "     }"
                } else {
                    Write-McpJson (Join-Path $BaseDir ".cursor\mcp.json")
                    Write-Ok "Cursor MCP config"
                }
                Write-Warn "Cursor：MCP 伺服器預設停用。"
                Write-Msg "  啟用方式：Cursor → 設定 → Cursor Settings → Tools & MCP → 切換 'databricks'"
            }
            "copilot" {
                if ($script:Scope -eq "global") {
                    Write-Warn "Copilot 全域模式：請在 VS Code 設定中設定 MCP（Ctrl+Shift+P → 'MCP: Open User Configuration'）"
                    Write-Msg "  Command: $($script:VenvPython) | Args: $($script:McpEntry)"
                } else {
                    Write-CopilotMcpJson (Join-Path $BaseDir ".vscode\mcp.json")
                    Write-Ok "Copilot MCP config (.vscode/mcp.json)"
                }
                Write-Warn "Copilot：MCP 伺服器需手動啟用。"
                Write-Msg "  在 Copilot Chat 中，點擊「設定工具」（右下角工具圖示），啟用 'databricks'"
            }
            "codex" {
                if ($script:Scope -eq "global") {
                    Write-McpToml (Join-Path $env:USERPROFILE ".codex\config.toml")
                } else {
                    Write-McpToml (Join-Path $BaseDir ".codex\config.toml")
                }
                Write-Ok "Codex MCP config"
            }
            "gemini" {
                if ($script:Scope -eq "global") {
                    Write-GeminiMcpJson (Join-Path $env:USERPROFILE ".gemini\settings.json")
                } else {
                    Write-GeminiMcpJson (Join-Path $BaseDir ".gemini\settings.json")
                }
                Write-Ok "Gemini CLI MCP config"
            }
            "antigravity" {
                if ($script:Scope -eq "project") {
                    Write-Warn "Antigravity 僅支援全域 MCP 設定。"
                    Write-Msg "  設定已寫入 ~/.gemini/antigravity/mcp_config.json"
                }
                Write-GeminiMcpJson (Join-Path $env:USERPROFILE ".gemini\antigravity\mcp_config.json")
                Write-Ok "Antigravity MCP config"
            }
        }
    }
}

# ─── 儲存版本 ────────────────────────────────────────────
function Save-Version {
    try {
        $ver = (Invoke-WebRequest -Uri "$RawUrl/VERSION" -UseBasicParsing -ErrorAction Stop).Content.Trim()
    } catch {
        $ver = "dev"
    }
    if ($ver -match '(404|Not Found|error)') { $ver = "dev" }

    Set-Content -Path (Join-Path $script:InstallDir "version") -Value $ver -Encoding UTF8

    if ($script:Scope -eq "project") {
        $projDir = Join-Path (Get-Location) ".ai-dev-kit"
        if (-not (Test-Path $projDir)) {
            New-Item -ItemType Directory -Path $projDir -Force | Out-Null
        }
        Set-Content -Path (Join-Path $projDir "version") -Value $ver -Encoding UTF8
    }
}

# ─── 摘要 ─────────────────────────────────────────────────
function Show-Summary {
    if ($script:Silent) { return }

    Write-Host ""
    Write-Host "安裝完成！" -ForegroundColor Green
    Write-Host "--------------------------------"
    Write-Msg "位置：$($script:InstallDir)"
    Write-Msg "範圍：    $($script:Scope)"
    Write-Msg "工具：    $(($script:Tools -split ' ') -join ', ')"
    Write-Host ""
    Write-Msg "後續步驟："
    $step = 1
    if ($script:Tools -match 'cursor') {
        Write-Msg "$step. 啟用 Cursor MCP：Cursor → 設定 → Cursor Settings → Tools & MCP → 切換 'databricks'"
        $step++
    }
    if ($script:Tools -match 'copilot') {
        Write-Msg "$step. 在 Copilot Chat 中，點擊「設定工具」（右下角工具圖示），啟用 'databricks'"
        $step++
        Write-Msg "$step. 使用 Copilot Agent 模式存取 Databricks skills 及 MCP 工具"
        $step++
    }
    if ($script:Tools -match 'gemini') {
        Write-Msg "$step. 在專案中啟動 Gemini CLI：gemini"
        $step++
    }
    if ($script:Tools -match 'antigravity') {
        Write-Msg "$step. 在 Antigravity 中開啟專案以使用 Databricks skills 及 MCP 工具"
        $step++
    }
    Write-Msg "$step. 以您選擇的工具開啟專案"
    $step++
    Write-Msg "$step. 試試看：`"列出我的 SQL Warehouses`""
    Write-Host ""
}

# ─── 範圍選擇 ─────────────────────────────────────────────
function Invoke-PromptScope {
    if ($script:Silent) { return }

    Write-Host ""
    Write-Host "  選擇安裝範圍" -ForegroundColor White
    
    $labels = @("專案", "全域")
    $values = @("project", "global")
    $hints = @("安裝至目前目錄（.cursor/、.claude/、.gemini/）", "安裝至家目錄（~/.cursor/、~/.claude/、~/.gemini/）")
    $count = 2
    $selected = 0
    $cursor = 0
    
    $isInteractive = Test-Interactive
    
    if (-not $isInteractive) {
        # 備援模式：編號清單
        Write-Host ""
        Write-Host "  1. (*) 專案  安裝至目前目錄（.cursor/、.claude/、.gemini/）"
        Write-Host "  2. ( ) 全域   安裝至家目錄（~/.cursor/、~/.claude/、~/.gemini/）"
        Write-Host ""
        Write-Host "  輸入數字選擇（或按 Enter 接受預設值）：" -NoNewline
        $input_ = Read-Host
        if (-not [string]::IsNullOrWhiteSpace($input_) -and $input_ -eq "2") {
            $selected = 1
        }
        $script:Scope = $values[$selected]
        return
    }
    
    # 互動模式
    Write-Host ""
    Write-Host "  ↑/↓ 導覽，Enter 確認" -ForegroundColor DarkGray
    Write-Host ""
    
    $totalRows = $count
    
    try { [Console]::CursorVisible = $false } catch {}
    
    $drawScope = {
        [Console]::SetCursorPosition(0, [Math]::Max(0, [Console]::CursorTop - $totalRows))
        for ($j = 0; $j -lt $count; $j++) {
            if ($j -eq $cursor) {
                Write-Host "  " -NoNewline
                Write-Host ">" -ForegroundColor Blue -NoNewline
                Write-Host " " -NoNewline
            } else {
                Write-Host "    " -NoNewline
            }
            if ($j -eq $selected) {
                Write-Host "(*)" -ForegroundColor Green -NoNewline
            } else {
                Write-Host "( )" -ForegroundColor DarkGray -NoNewline
            }
            $padLabel = $labels[$j].PadRight(20)
            Write-Host " $padLabel " -NoNewline
            if ($j -eq $selected) {
                Write-Host $hints[$j] -ForegroundColor Green -NoNewline
            } else {
                Write-Host $hints[$j] -ForegroundColor DarkGray -NoNewline
            }
            $pos = [Console]::CursorLeft
            $remaining = [Console]::WindowWidth - $pos - 1
            if ($remaining -gt 0) { Write-Host (' ' * $remaining) -NoNewline }
            Write-Host ""
        }
    }
    
    # 預留行數
    for ($j = 0; $j -lt $totalRows; $j++) { Write-Host "" }
    & $drawScope
    
    while ($true) {
        $key = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        
        switch ($key.VirtualKeyCode) {
            38 { if ($cursor -gt 0) { $cursor-- } }
            40 { if ($cursor -lt 1) { $cursor++ } }
            32 { $selected = $cursor }
            13 {
                $selected = $cursor
                & $drawScope
                break
            }
        }
        if ($key.VirtualKeyCode -eq 13) { break }
        
        & $drawScope
    }
    
    try { [Console]::CursorVisible = $true } catch {}
    
    $script:Scope = $values[$selected]
}

# ─── 認證提示 ──────────────────────────────────────────────
function Invoke-PromptAuth {
    if ($script:Silent) { return }

    # 檢查 profile 是否已設定 token
    $cfgFile = Join-Path $env:USERPROFILE ".databrickscfg"
    if (Test-Path $cfgFile) {
        $inProfile = $false
        foreach ($line in (Get-Content $cfgFile)) {
            if ($line -match '^\[([a-zA-Z0-9_-]+)\]$') {
                $inProfile = $Matches[1] -eq $script:Profile_
            } elseif ($inProfile -and $line -match '^token\s*=') {
                Write-Ok "Profile $($script:Profile_) 已設定 token，略過認證"
                return
            }
        }
    }

    # 檢查環境變數
    if ($env:DATABRICKS_TOKEN) {
        Write-Ok "已設定 DATABRICKS_TOKEN，略過認證"
        return
    }

    # 檢查 CLI 是否已安裝
    if (-not (Get-Command databricks -ErrorAction SilentlyContinue)) {
        Write-Warn "未安裝 Databricks CLI，無法執行 OAuth 登入"
        Write-Msg "  請先安裝，然後執行：databricks auth login --profile $($script:Profile_)"
        return
    }

    Write-Host ""
    Write-Msg "認證"
    Write-Msg "即將為 Profile $($script:Profile_) 執行 OAuth 登入"
    Write-Msg "將開啟瀏覽器視窗，供您登入 Databricks workspace。"
    Write-Host ""
    $runAuth = Read-Prompt -PromptText "立即執行 databricks auth login --profile $($script:Profile_)？(y/n)" -Default "y"
    if ($runAuth -in @("y", "Y", "yes")) {
        Write-Host ""
        & databricks auth login --profile $script:Profile_
    }
}

# ─── 主函式 ─────────────────────────────────────────────────────
function Invoke-Main {
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "Databricks AI Dev Kit 安裝程式" -ForegroundColor White
        Write-Host "--------------------------------"
    }

    # 檢查必要條件
    Write-Step "檢查必要條件"
    Test-Dependencies

    # 工具選擇
    Write-Step "選擇工具"
    Invoke-DetectTools
    Write-Ok "已選擇：$(($script:Tools -split ' ') -join ', ')"

    # Profile 選擇
    Write-Step "Databricks Profile"
    Invoke-PromptProfile
    Write-Ok "Profile：$($script:Profile_)"

    # 範圍選擇
    if (-not $script:ScopeExplicit) {
        Invoke-PromptScope
        Write-Ok "範圍：$($script:Scope)"
    }

    # 依範圍設定狀態目錄（用於儲存設定檔/清單）
    if ($script:Scope -eq "global") {
        $script:StateDir = $script:InstallDir
    } else {
        $script:StateDir = Join-Path (Get-Location) ".ai-dev-kit"
    }

    # Skill 設定檔選擇
    if ($script:InstallSkills) {
        Write-Step "Skill 設定檔"
        Invoke-PromptSkillsProfile
        Resolve-Skills
        $skCount = $script:SelectedSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count
        if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
            Write-Ok "自訂選擇（$skCount 個 skills）"
        } else {
            $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
            Write-Ok "設定檔：$profileDisplay（$skCount 個 skills）"
        }
    }

    # MCP 路徑
    if ($script:InstallMcp) {
        Invoke-PromptMcpPath
        Write-Ok "MCP 路徑：$($script:InstallDir)"
    }

    # 確認摘要
    if (-not $script:Silent) {
        Write-Host ""
        Write-Host "  摘要" -ForegroundColor White
        Write-Host "  ------------------------------------"
        Write-Host "  工具：       " -NoNewline; Write-Host "$(($script:Tools -split ' ') -join ', ')" -ForegroundColor Green
        Write-Host "  Profile：     " -NoNewline; Write-Host $script:Profile_ -ForegroundColor Green
        Write-Host "  範圍：       " -NoNewline; Write-Host $script:Scope -ForegroundColor Green
        if ($script:InstallMcp) {
            Write-Host "  MCP 伺服器：  " -NoNewline; Write-Host $script:InstallDir -ForegroundColor Green
        }
        if ($script:InstallSkills) {
            $skTotal = $script:SelectedSkills.Count + $script:SelectedMlflowSkills.Count + $script:SelectedApxSkills.Count
            if (-not [string]::IsNullOrWhiteSpace($script:UserSkills)) {
                Write-Host "  Skills：      " -NoNewline; Write-Host "自訂選擇（$skTotal 個 skills）" -ForegroundColor Green
            } else {
                $profileDisplay = if ([string]::IsNullOrWhiteSpace($script:SkillsProfile)) { "all" } else { $script:SkillsProfile }
                Write-Host "  Skills：      " -NoNewline; Write-Host "$profileDisplay（$skTotal 個 skills）" -ForegroundColor Green
            }
        }
        if ($script:InstallMcp) {
            Write-Host "  MCP 設定：   " -NoNewline; Write-Host "是" -ForegroundColor Green
        }
        Write-Host ""
    }

    if (-not $script:Silent) {
        $confirm = Read-Prompt -PromptText "確認開始安裝？(y/n)" -Default "y"
        if ($confirm -notin @("y", "Y", "yes")) {
            Write-Host ""
            Write-Msg "安裝已取消。"
            return
        }
    }

    # 版本檢查
    Test-Version

    # 決定基礎目錄
    if ($script:Scope -eq "global") {
        $baseDir = $env:USERPROFILE
    } else {
        $baseDir = (Get-Location).Path
    }

    # 設定 MCP 伺服器
    if ($script:InstallMcp) {
        Install-McpServer
    } elseif (-not (Test-Path $script:RepoDir)) {
        Write-Step "下載原始碼"
        if (-not (Test-Path $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & git -c advice.detachedHead=false clone -q --depth 1 --branch $Branch $RepoUrl $script:RepoDir 2>&1 | Out-Null
        $ErrorActionPreference = $prevEAP
        Write-Ok "Repository 複製完成（$Branch）"
    }

    # 安裝 skills
    if ($script:InstallSkills) {
        Install-Skills -BaseDir $baseDir
    }

    # 若已選擇 gemini，寫入 GEMINI.md
    if ($script:Tools -match 'gemini') {
        if ($script:Scope -eq "global") {
            Write-GeminiMd (Join-Path $env:USERPROFILE "GEMINI.md")
        } else {
            Write-GeminiMd (Join-Path $baseDir "GEMINI.md")
        }
    }

    # 寫入 MCP 設定
    if ($script:InstallMcp) {
        Write-McpConfigs -BaseDir $baseDir
    }

    # 儲存版本
    Save-Version

    # 認證提示
    Invoke-PromptAuth

    # 摘要
    Show-Summary
}

Invoke-Main
