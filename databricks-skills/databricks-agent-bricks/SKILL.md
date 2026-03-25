---
name: databricks-agent-bricks
description: "建立與管理 Databricks Agent Bricks：包含用於文件問答的 Knowledge Assistant (KA)、用於 SQL 探索的 Genie Space，以及用於多代理協作編排的 Supervisor Agent (MAS)。適用於在 Databricks 上建置對話式 AI 應用程式。"
---

# Agent Bricks

建立與管理 Databricks Agent Bricks——這些是用來建置對話式應用程式的預建 AI 元件。

## 概觀

在 Databricks 中，Agent Bricks 分為三種預建 AI 磚塊：

| Brick | 用途 | 資料來源 |
|-------|------|----------|
| **Knowledge Assistant (KA)** | 使用 RAG 進行以文件為基礎的問答 | Volumes 中的 PDF／文字檔 |
| **Genie Space** | 自然語言轉 SQL | Unity Catalog 資料表 |
| **Supervisor Agent (MAS)** | 多代理協作編排 | Model serving endpoints |

## 先決條件

在建立 Agent Bricks 之前，請先確認你已具備所需資料：

### 針對 Knowledge Assistants
- **Volume 中的文件**：儲存在 Unity Catalog volume 內的 PDF、文字或其他檔案
- 如有需要，可使用 `databricks-unstructured-pdf-generation` skill 產生合成文件

### 針對 Genie Spaces
- 完整的 Genie Space 指南請參閱 `databricks-genie` skill
- 在 Unity Catalog 中建立包含待探索資料的資料表
- 使用 `databricks-synthetic-data-gen` skill 產生原始資料
- 使用 `databricks-spark-declarative-pipelines` skill 建立資料表

### 針對 Supervisor Agents
- **Model Serving Endpoints**：已部署的 agent endpoints（KA endpoints、自訂 agents、fine-tuned models）
- **Genie Spaces**：現有的 Genie spaces 可直接作為 agent，處理以 SQL 為基礎的查詢
- 可在同一個 Supervisor Agent 中混用 endpoint 型與 Genie 型 agents

### 針對 Unity Catalog Functions
- **現有 UC Function**：已註冊於 Unity Catalog 的 function
- Agent service principal 對該 function 具有 `EXECUTE` 權限

### 針對 External MCP Servers
- **現有 UC HTTP Connection**：已設定 `is_mcp_connection: 'true'` 的 connection
- Agent service principal 對該 connection 具有 `USE CONNECTION` 權限

## MCP 工具

### Knowledge Assistant 工具

**manage_ka** - 管理 Knowledge Assistants（KA）
- `action`："create_or_update"、"get"、"find_by_name" 或 "delete"
- `name`：KA 名稱（供 create_or_update、find_by_name 使用）
- `volume_path`：文件路徑（例如 `/Volumes/catalog/schema/volume/folder`）（供 create_or_update 使用）
- `description`：（選用）KA 的用途（供 create_or_update 使用）
- `instructions`：（選用）KA 應如何回答（供 create_or_update 使用）
- `tile_id`：KA 的 tile ID（供 get、delete，或透過 create_or_update 更新時使用）
- `add_examples_from_volume`：（選用，預設: true）自動從 JSON 檔加入範例（供 create_or_update 使用）

可用動作：
- **create_or_update**：需要 `name`、`volume_path`。可選擇傳入 `tile_id` 以進行更新。
- **get**：需要 `tile_id`。回傳 tile_id、name、description、endpoint_status、knowledge_sources、examples_count。
- **find_by_name**：需要 `name`（完全比對）。回傳 found、tile_id、name、endpoint_name、endpoint_status。當你知道 KA 名稱但不知道 tile_id 時，可用它查找現有的 KA。
- **delete**：需要 `tile_id`。

### Genie Space 工具

**如需完整的 Genie 指南，請使用 `databricks-genie` skill。**

可用的基本工具：

- `create_or_update_genie` - 建立或更新 Genie Space
- `get_genie` - 取得 Genie Space 詳細資料
- `delete_genie` - 刪除 Genie Space

請參閱 `databricks-genie` skill 了解：
- 資料表檢查工作流程
- 範例問題最佳實務
- 策展（instructions、certified queries）

**重要**：Genie spaces 沒有 system table（例如 `system.ai.genie_spaces` 不存在）。若要依名稱尋找 Genie space，請使用 `find_genie_by_name` 工具。

### Supervisor Agent 工具

**manage_mas** - 管理 Supervisor Agents（MAS）
- `action`："create_or_update"、"get"、"find_by_name" 或 "delete"
- `name`：Supervisor Agent 名稱（供 create_or_update、find_by_name 使用）
- `agents`：agent 設定清單（供 create_or_update 使用），每個項目包含：
  - `name`：agent 識別子（必填）
  - `description`：此 agent 負責的內容——對路由至關重要（必填）
  - `ka_tile_id`：Knowledge Assistant tile ID（用於文件問答 agents，建議用於 KA）
  - `genie_space_id`：Genie space ID（用於以 SQL 為基礎的資料 agents）
  - `endpoint_name`：Model serving endpoint 名稱（用於自訂 agents）
  - `uc_function_name`：Unity Catalog function 名稱，格式為 `catalog.schema.function_name`
  - `connection_name`：Unity Catalog connection 名稱（用於 External MCP Servers）
  - 注意：`ka_tile_id`、`genie_space_id`、`endpoint_name`、`uc_function_name` 或 `connection_name` 必須且只能提供其中一個
- `description`：（選用）Supervisor Agent 的用途（供 create_or_update 使用）
- `instructions`：（選用）supervisor 的路由指示（供 create_or_update 使用）
- `tile_id`：Supervisor Agent 的 tile ID（供 get、delete，或透過 create_or_update 更新時使用）
- `examples`：（選用）範例問題清單，每個項目含 `question` 與 `guideline` 欄位（供 create_or_update 使用）

可用動作：
- **create_or_update**：需要 `name`、`agents`。可選擇傳入 `tile_id` 以進行更新。
- **get**：需要 `tile_id`。回傳 tile_id、name、description、endpoint_status、agents、examples_count。
- **find_by_name**：需要 `name`（完全比對）。回傳 found、tile_id、name、endpoint_status、agents_count。當你知道 Supervisor Agent 名稱但不知道 tile_id 時，可用它查找現有的 Supervisor Agent。
- **delete**：需要 `tile_id`。

## 典型工作流程

### 1. 產生來源資料

在建立 Agent Bricks 之前，先產生所需的來源資料：

**針對 KA（文件問答）**：
```
1. 使用 `databricks-unstructured-pdf-generation` skill 產生 PDF
2. PDF 會儲存在 Volume，並附帶對應的 JSON 檔案（question/guideline 配對）
```

**針對 Genie（SQL 探索）**：
```
1. 使用 `databricks-synthetic-data-gen` skill 建立原始 parquet 資料
2. 使用 `databricks-spark-declarative-pipelines` skill 建立 bronze/silver/gold 資料表
```

### 2. 建立 Agent Brick

使用 `manage_ka(action="create_or_update", ...)` 或 `manage_mas(action="create_or_update", ...)`，並搭配你的資料來源。

### 3. 等待佈建完成

新建立的 KA 與 MAS tile 需要一些時間佈建。endpoint 狀態會依序變化：
- `PROVISIONING` - 正在建立（約需 2-5 分鐘）
- `ONLINE` - 可開始使用
- `OFFLINE` - 目前未執行

### 4. 自動加入範例

對於 KA，若 `add_examples_from_volume=true`，系統會自動從 volume 中的 JSON 檔擷取範例，並在 endpoint 進入 `ONLINE` 後加入。

## 最佳實務

1. **使用有意義的名稱**：名稱會自動清理（空白會變成底線）
2. **提供 description**：幫助使用者理解這個 brick 的用途
3. **加入 instructions**：引導 AI 的行為與語氣
4. **納入範例問題**：讓使用者知道如何與 brick 互動
5. **遵循工作流程**：先產生資料，再建立 brick

## 範例：多模態 Supervisor Agent

```python
manage_mas(
    action="create_or_update",
    name="企業支援 Supervisor",
    agents=[
        {
            "name": "knowledge_base",
            "ka_tile_id": "f32c5f73-466b-...",
            "description": "回答來自已建立索引檔案中，與公司政策、流程及文件相關的問題"
        },
        {
            "name": "analytics_engine",
            "genie_space_id": "01abc123...",
            "description": "針對使用量指標、效能統計與營運資料執行 SQL 分析"
        },
        {
            "name": "ml_classifier",
            "endpoint_name": "custom-classification-endpoint",
            "description": "使用自訂 ML model 對支援工單進行分類並預測解決時間"
        },
        {
            "name": "data_enrichment",
            "uc_function_name": "support.utils.enrich_ticket_data",
            "description": "以客戶歷史與情境資料增補支援工單內容"
        },
        {
            "name": "ticket_operations",
            "connection_name": "ticket_system_mcp",
            "description": "在外部工單系統中建立、更新、指派與關閉支援工單"
        }
    ],
    description="整合知識檢索、分析、ML、資料增補與工單作業的企業支援代理",
    instructions="""
    請依下列方式路由查詢：
    1. 政策／流程問題 → knowledge_base
    2. 資料分析請求 → analytics_engine
    3. 工單分類 → ml_classifier
    4. 客戶情境查詢 → data_enrichment
    5. 工單建立／更新 → ticket_operations

    如果查詢橫跨多個領域，請串接多個 agent：
    - 先蒐集資訊（analytics_engine 或 knowledge_base）
    - 再執行動作（ticket_operations）
    """
)
```

## 相關 Skills

- **[databricks-genie](../databricks-genie/SKILL.md)** - 完整的 Genie Space 建立、策展與 Conversation API 指南
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - 產生可提供給 Knowledge Assistants 使用的合成 PDF
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - 為 Genie Space 資料表建立原始資料
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - 建立供 Genie Spaces 使用的 bronze/silver/gold 資料表
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - 部署作為 MAS agent 使用的自訂 agent endpoints
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** - 建立可與 KA 搭配使用的 RAG 應用程式 vector indexes

## 另請參閱

- `1-knowledge-assistants.md` - 詳細的 KA 模式與範例
- `databricks-genie` skill - 詳細的 Genie 模式、策展與範例
- `2-supervisor-agents.md` - 詳細的 MAS 模式與範例
