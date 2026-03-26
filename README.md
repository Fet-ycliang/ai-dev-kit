# Databricks AI Dev Kit

<p align="center">
  <img src="https://img.shields.io/badge/Databricks-Certified%20Gold%20Project-FFD700?style=for-the-badge&logo=databricks&logoColor=black" alt="Databricks Certified Gold Project">
</p>

---

## 概覽

在 Databricks 上進行 AI 驅動的開發（vibe coding）已變得更加出色。**AI Dev Kit** 為您的 AI 程式助手（Claude Code、Cursor、Antigravity、Windsurf 等）提供所需的可信資源，讓您在 Databricks 上開發更快、更智慧。

<p align="center">
  <img src="databricks-tools-core/docs/architecture.svg" alt="Architecture" width="700">
</p>

---

## 我能建構什麼？

- **Spark 宣告式管道**（串流資料表、CDC、SCD Type 2、Auto Loader）
- **Databricks Jobs**（排程工作流程、多任務 DAG）
- **AI/BI 儀表板**（視覺化、KPI、分析）
- **Unity Catalog**（資料表、volumes、治理）
- **Genie Spaces**（自然語言資料探索）
- **知識助手**（基於 RAG 的文件問答）
- **MLflow 實驗**（評估、評分、追蹤）
- **模型服務**（將 ML 模型和 AI Agent 部署至端點）
- **Databricks Apps**（整合基礎模型的全端 Web 應用程式）
- ...以及更多

---

## 選擇您的探索路徑

| 探索路徑                        | 最適合對象 | 從這裡開始 |
|----------------------------------|----------|------------|
| :star: [**安裝 AI Dev Kit**](#install-in-existing-project) | **從這裡開始！** 依照快速安裝說明加入現有專案資料夾 | [快速入門（安裝）](#install-in-existing-project)
| [**視覺化 Builder App**](#visual-builder-app) | 基於 Web UI 的 Databricks 開發 | `databricks-builder-app/` |
| [**核心程式庫**](#core-library) | 建構自訂整合（LangChain、OpenAI 等） | `pip install` |
| [**僅安裝 Skills**](databricks-skills/) | 提供 Databricks 模式與最佳實踐（不含 MCP 函式） | 安裝 skills |
| [**Genie Code Skills**](databricks-skills/install_skills_to_genie_code.sh) | 安裝 Databricks skills 供 Genie Code 參考 | [Genie Code skills（安裝）](#genie-code-skills) |
| [**僅安裝 MCP Tools**](databricks-mcp-server/) | 僅執行操作（無指引） | 註冊 MCP server |
| [**系統架構說明**](ARCHITECTURE.md) | 深入了解元件設計與開發指南 | [ARCHITECTURE.md](ARCHITECTURE.md) |
---

## 快速入門

### 前置需求

- [uv](https://github.com/astral-sh/uv) - Python 套件管理工具
- [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/) - Databricks 命令列介面
- AI 程式開發環境（一個或多個）：
  - [Claude Code](https://claude.ai/code)
  - [Cursor](https://cursor.com)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)
  - [Antigravity](https://antigravity.google)


### 安裝至現有專案 {#install-in-existing-project}
預設情況下，安裝範圍為專案層級而非使用者層級。這通常是較佳的選擇，但需要您從安裝時所使用的確切目錄執行客戶端。
_注意：專案設定檔可在其他專案中重複使用。這些設定檔位於 .claude、.cursor、.gemini 或 .agents 目錄下_

#### Mac / Linux

**基本安裝**（使用 DEFAULT 設定檔，專案範圍）

```bash
bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh)
```

<details>
<summary><strong>進階選項</strong>（點擊展開）</summary>

**全域安裝並強制重新安裝**

```bash
bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --global --force
```

**指定設定檔並強制重新安裝**

```bash
bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --profile DEFAULT --force
```

**僅安裝特定工具**

```bash
bash <(curl -sL https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.sh) --tools cursor,gemini,antigravity
```

</details>

**後續步驟：** 依提示回應並遵循畫面上的指示。
- 注意：Cursor 和 Copilot 在安裝後需手動更新設定。

#### Windows (PowerShell)

**基本安裝**（使用 DEFAULT 設定檔，專案範圍）

```powershell
irm https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.ps1 | iex
```

<details>
<summary><strong>進階選項</strong>（點擊展開）</summary>

**先下載腳本**

```powershell
irm https://raw.githubusercontent.com/Fet-ycliang/ai-dev-kit/main/install.ps1 -OutFile install.ps1
```

**全域安裝並強制重新安裝**

```powershell
.\install.ps1 -Global -Force
```

**指定設定檔並強制重新安裝**

```powershell
.\install.ps1 -Profile DEFAULT -Force
```

**僅安裝特定工具**

```powershell
.\install.ps1 -Tools cursor,gemini,antigravity
```

</details>

**後續步驟：** 依提示回應並遵循畫面上的指示。
- 注意：Cursor 和 Copilot 在安裝後需手動更新設定。


### 視覺化 Builder App {#visual-builder-app}

具備聊天 UI 的全端 Web 應用程式，用於 Databricks 開發：

```bash
cd ai-dev-kit/databricks-builder-app
./scripts/setup.sh
# 依照指示啟動應用程式
```


### 核心程式庫 {#core-library}

在您的 Python 專案中直接使用 `databricks-tools-core`：

```python
from databricks_tools_core.sql import execute_sql

results = execute_sql("SELECT * FROM my_catalog.schema.table LIMIT 10")
```

可與 LangChain、OpenAI Agents SDK 或任何 Python 框架搭配使用。詳情請參閱 [databricks-tools-core/](databricks-tools-core/)。

---
## Genie Code Skills {#genie-code-skills}

  將所有可用的 skills 安裝並部署至您的個人 skills 目錄，供所有 Genie Code 工作階段在 UI 中直接規劃/建構時參考。安裝後無需額外設定，安裝過程中會自動設定工作區供 Genie Code 使用這些 skills。

  **基本安裝**（使用 DEFAULT 設定檔）

```bash
cd ai-dev-kit/databricks-skills
./install_skills_to_genie_code.sh
```

**進階安裝**（使用指定設定檔）

```bash
cd ai-dev-kit/databricks-skills
./install_skills_to_genie_code <profile_name>
```

**修改 Skill 或建立自訂 Skill**

腳本成功將 skills 安裝至工作區後，您可在 `/Workspace/Users/<your_user_name>/.assistant/skills` 下找到這些 skills。

此目錄可自訂，您可以選擇只使用特定 skills，甚至建立與您組織相關的自訂 skills 以進一步提升 Genie Code 的效能。您可以修改/移除現有 skills，或建立新的 skills 資料夾，Genie Code 將在任何工作階段中自動使用。

## 包含哪些內容

| 元件 | 說明 |
|-----------|-------------|
| [`databricks-tools-core/`](databricks-tools-core/) | 提供高層次 Databricks 函式的 Python 程式庫 |
| [`databricks-mcp-server/`](databricks-mcp-server/) | 為 AI 助手提供 50+ 工具的 MCP server |
| [`databricks-skills/`](databricks-skills/) | 20 個教授 Databricks 模式的 Markdown skills |
| [`databricks-builder-app/`](databricks-builder-app/) | 整合 Claude Code 的全端 Web 應用程式 |

---

## Star 歷史

<a href="https://star-history.com/#Fet-ycliang/ai-dev-kit&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Fet-ycliang/ai-dev-kit&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Fet-ycliang/ai-dev-kit&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Fet-ycliang/ai-dev-kit&type=Date" />
 </picture>
</a>

---

## 授權條款

(c) 2026 Databricks, Inc. 保留所有權利。

本專案中的原始碼依 [Databricks License](https://databricks.com/db-license-source) 授權提供。詳情請參閱 [LICENSE.md](LICENSE.md)。

<details>
<summary><strong>第三方授權條款</strong></summary>

| 套件 | 版本 | 授權 | 專案網址 |
|---------|---------|---------|-------------|
| [fastmcp](https://github.com/jlowin/fastmcp) | ≥0.1.0 | MIT | https://github.com/jlowin/fastmcp |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | ≥1.0.0 | MIT | https://github.com/modelcontextprotocol/python-sdk |
| [sqlglot](https://github.com/tobymao/sqlglot) | ≥20.0.0 | MIT | https://github.com/tobymao/sqlglot |
| [sqlfluff](https://github.com/sqlfluff/sqlfluff) | ≥3.0.0 | MIT | https://github.com/sqlfluff/sqlfluff |
| [litellm](https://github.com/BerriAI/litellm) | ≥1.0.0 | MIT | https://github.com/BerriAI/litellm |
| [pymupdf](https://github.com/pymupdf/PyMuPDF) | ≥1.24.0 | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |
| [claude-agent-sdk](https://github.com/anthropics/claude-code) | ≥0.1.19 | MIT | https://github.com/anthropics/claude-code |
| [fastapi](https://github.com/fastapi/fastapi) | ≥0.115.8 | MIT | https://github.com/fastapi/fastapi |
| [uvicorn](https://github.com/encode/uvicorn) | ≥0.34.0 | BSD-3-Clause | https://github.com/encode/uvicorn |
| [httpx](https://github.com/encode/httpx) | ≥0.28.0 | BSD-3-Clause | https://github.com/encode/httpx |
| [sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) | ≥2.0.41 | MIT | https://github.com/sqlalchemy/sqlalchemy |
| [alembic](https://github.com/sqlalchemy/alembic) | ≥1.16.1 | MIT | https://github.com/sqlalchemy/alembic |
| [asyncpg](https://github.com/MagicStack/asyncpg) | ≥0.30.0 | Apache-2.0 | https://github.com/MagicStack/asyncpg |
| [greenlet](https://github.com/python-greenlet/greenlet) | ≥3.0.0 | MIT | https://github.com/python-greenlet/greenlet |
| [psycopg2-binary](https://github.com/psycopg/psycopg2) | ≥2.9.11 | LGPL-3.0 | https://github.com/psycopg/psycopg2 |

</details>

---

<details>
<summary><strong>致謝</strong></summary>

MCP Databricks 指令執行 API 來自 [databricks-exec-code](https://github.com/Fet-ycliang/databricks-exec-code-mcp)，由 Natyra Bajraktari 和 Henryk Borzymowski 開發。

</details>
