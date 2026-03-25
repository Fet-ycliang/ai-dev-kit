---
name: databricks-docs
description: "透過 llms.txt 索引參考 Databricks 文件。當其他技能未涵蓋某個主題、需要查詢不熟悉的 Databricks 功能，或需要 API、設定或平台能力的權威文件時使用。"
---

# Databricks 文件參考

此技能透過 llms.txt 提供完整的 Databricks 文件索引存取能力——可將它作為 **參考資源**，用來補充其他技能並協助你使用 MCP tools。

## 此技能的角色

這是一個 **參考技能**，不是操作技能。可用於：

- 當其他技能未涵蓋某個主題時查找文件
- 取得 Databricks 概念與 API 的權威指引
- 找到詳細資訊，協助你判斷如何使用 MCP tools
- 發掘你可能尚未知曉的功能與能力

**執行操作時，請一律優先使用 MCP tools**（execute_sql、create_or_update_pipeline 等），而 **工作流程則請載入對應的特定技能**（databricks-python-sdk、databricks-spark-declarative-pipelines 等）。當你需要參考文件時，再使用此技能。

## 使用方式

擷取 llms.txt 文件索引：

**URL:** `https://docs.databricks.com/llms.txt`

使用 WebFetch 取得此索引，然後：

1. 搜尋相關章節／連結
2. 擷取特定文件頁面以取得詳細指引
3. 使用適當的 MCP tools 套用你學到的內容

## 文件結構

llms.txt 檔案依類別組織：

- **概覽與快速開始** - 基本概念與教學
- **資料工程** - Lakeflow, Spark, Delta Lake, pipelines
- **SQL 與分析** - Warehouses, queries, dashboards
- **AI/ML** - MLflow, model serving, GenAI
- **治理** - Unity Catalog, permissions, security
- **開發工具** - SDKs, CLI, APIs, Terraform

## 範例：補充其他技能

**情境：** 使用者想建立 Delta Live Tables pipeline

1. 載入 `databricks-spark-declarative-pipelines` 技能以取得工作流程模式
2. 若需要釐清特定 DLT 功能，再用此技能擷取文件
3. 使用 `create_or_update_pipeline` MCP tool 實際建立 pipeline

**情境：** 使用者詢問不熟悉的 Databricks 功能

1. 擷取 llms.txt 以找出相關文件
2. 閱讀特定文件以了解該功能
3. 判斷適用的技能／tools，然後使用它們

## 相關技能

- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - 以 SDK 模式進行程式化 Databricks 存取
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - DLT / Lakeflow pipeline 工作流程
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - 治理與 catalog 管理
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - serving endpoints 與 model 部署
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - MLflow 3 GenAI evaluation 工作流程