# Supervisor Agents (MAS)

Supervisor Agents 會協調多個專門代理，根據查詢內容將使用者問題路由到最適合的 agent。

## 什麼是 Supervisor Agent？

Supervisor Agent（前稱 Multi-Agent Supervisor, MAS）可視為多個 AI agents 的交通指揮中心，會將使用者查詢路由到最合適的 agent。它支援五種類型的 agents：

1. **Knowledge Assistants (KA)**：根據 Volumes 中的 PDF／檔案進行文件式問答
2. **Genie Spaces**：將自然語言轉成 SQL 以進行資料探索
3. **Model Serving Endpoints**：自訂 LLM agents、fine-tuned models、RAG 應用
4. **Unity Catalog Functions**：可呼叫的 UC functions，用於資料操作
5. **External MCP Servers**：透過 UC HTTP Connections 連接 JSON-RPC endpoints，以整合外部系統

當使用者提出問題時：
1. **分析**查詢內容以理解意圖
2. **路由**至最合適的專門 agent
3. **回傳**該 agent 的回應給使用者

這讓你可以把多個專門 agents 整合成單一、統一的介面。

## 何時使用

在以下情境適合使用 Supervisor Agent：
- 你有多個專門代理（帳務、技術支援、人資等）
- 使用者不應該需要知道該找哪一個 agent
- 你想提供統一的對話式體驗

## 先決條件

建立 Supervisor Agent 之前，你需要先準備以下其中一種或兩種 agent 類型：

**Model Serving Endpoints** (`endpoint_name`)：
- Knowledge Assistant (KA) endpoints（例如 `ka-abc123-endpoint`）
- 使用 LangChain、LlamaIndex 等建立的自訂 agents
- Fine-tuned models
- RAG 應用

**Genie Spaces** (`genie_space_id`)：
- 現有的 Genie spaces，可用於以 SQL 為基礎的資料探索
- 非常適合分析、指標與資料驅動型問題
- 不需要另外部署 endpoint，直接參考該 space 即可
- 若要依名稱尋找 Genie space，請使用 `find_genie_by_name(display_name="My Genie")`
- **注意**：Genie spaces 沒有 system table——不要嘗試查詢 `system.ai.genie_spaces`

## Unity Catalog Functions

Unity Catalog Functions 讓 Supervisor Agents 可以呼叫已註冊的 UC functions 來執行資料操作。

### 先決條件

- UC Function 已存在（使用 SQL `CREATE FUNCTION` 或 Python UDF）
- Agent service principal 具有 `EXECUTE` 權限：
  ```sql
  GRANT EXECUTE ON FUNCTION catalog.schema.function_name TO `<agent_sp>`;
  ```

### 設定方式

```json
{
  "name": "data_enrichment",
  "uc_function_name": "sales_analytics.utils.enrich_customer_data",
  "description": "以人口統計資料與購買歷史增補客戶記錄"
}
```

**欄位**：`uc_function_name` - 完整限定名稱，格式為 `catalog.schema.function_name`

## External MCP Servers

External MCP Servers 讓 Supervisor Agents 可透過 UC HTTP Connections 與外部系統（ERP、CRM 等）互動。MCP server 會實作 JSON-RPC 2.0 endpoint，並公開工具供 Supervisor Agent 呼叫。

### 先決條件

**1. MCP Server Endpoint**：你的外部系統必須提供一個實作 MCP protocol 的 JSON-RPC 2.0 endpoint（例如 `/api/mcp`）：

```python
# MCP server 工具定義範例
TOOLS = [
    {
        "name": "approve_invoice",
        "description": "核准指定發票",
        "inputSchema": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string", "description": "要核准的發票號碼"},
                "approver": {"type": "string", "description": "核准者姓名／電子郵件"},
            },
            "required": ["invoice_number"],
        },
    },
]

# JSON-RPC methods：initialize、tools/list、tools/call
```

**2. UC HTTP Connection**：建立指向 MCP endpoint 的 Unity Catalog HTTP Connection：

```sql
CREATE CONNECTION my_mcp_connection TYPE HTTP
OPTIONS (
  host 'https://my-app.databricksapps.com',  -- 你的 MCP server URL
  port '443',
  base_path '/api/mcp',                       -- JSON-RPC endpoint 路徑
  client_id '<service_principal_id>',         -- OAuth M2M 認證
  client_secret '<service_principal_secret>',
  oauth_scope 'all-apis',
  token_endpoint 'https://<workspace>.azuredatabricks.net/oidc/v1/token',
  is_mcp_connection 'true'                    -- 必填：標示為 MCP connection
);
```

**3. 授與權限**：Agent service principal 需要可使用該 connection：

```sql
GRANT USE CONNECTION ON my_mcp_connection TO `<agent_sp>`;
```

### 設定方式

使用 `connection_name` 欄位來參考 UC Connection：

```python
{
    "name": "external_operations",
    "connection_name": "my_mcp_connection",
    "description": "執行外部系統操作：核准發票、建立記錄、觸發工作流程"
}
```

**欄位**：`connection_name` - 已設定為 MCP server 的 Unity Catalog HTTP Connection 名稱

**重要**：請將 description 寫得完整且清楚——它會引導 Supervisor Agent 判斷何時要呼叫此 agent。

### 完整範例：多系統 Supervisor

以下範例展示如何整合 Genie、KA 與外部 MCP：

```python
manage_mas(
    action="create_or_update",
    name="AP_Invoice_Supervisor",
    agents=[
        {
            "name": "billing_analyst",
            "genie_space_id": "01abc123...",
            "description": "針對 AP 發票資料執行 SQL 分析：支出趨勢、供應商分析、帳齡報表"
        },
        {
            "name": "policy_expert",
            "ka_tile_id": "f32c5f73...",
            "description": "根據政策文件回答 AP 政策、核准工作流程與合規要求相關問題"
        },
        {
            "name": "ap_operations",
            "connection_name": "ap_invoice_mcp",
            "description": (
                "執行 AP 操作：核准／拒絕／標記發票、查詢發票明細、"
                "取得供應商摘要、觸發批次工作流程。凡是任何動作或寫入操作都請使用此 agent。"
            )
        }
    ],
    description="具備分析、政策指引與作業動作的 AP 自動化助理",
    instructions="""
    請依下列方式路由查詢：
    - 資料問題（發票數量、支出分析、供應商指標）→ billing_analyst
    - 政策問題（門檻、SLA、合規規則）→ policy_expert
    - 動作請求（核准、拒絕、標記、查詢、工作流程）→ ap_operations

    當使用者要求核准、拒絕或標記發票時，一律使用 ap_operations。
    """
)
```

### MCP Connection 測試

在加入 MAS 前，先驗證你的 connection：

```sql
-- 測試 tools/list method
SELECT http_request(
  conn => 'my_mcp_connection',
  method => 'POST',
  path => '',
  json => '{"jsonrpc":"2.0","method":"tools/list","id":1}'
);
```

### 參考資源

- **MCP Protocol 規格**：[Model Context Protocol](https://modelcontextprotocol.io)

## 建立 Supervisor Agent

使用 `manage_mas` 工具並指定 `action="create_or_update"`：

- `name`: "客戶支援 MAS"
- `agents`:
  ```json
  [
    {
      "name": "policy_agent",
      "ka_tile_id": "f32c5f73-466b-4798-b3a0-5396b5ece2a5",
      "description": "根據已建立索引的文件回答公司政策與流程相關問題"
    },
    {
      "name": "usage_analytics",
      "genie_space_id": "01abc123-def4-5678-90ab-cdef12345678",
      "description": "回答使用量指標、趨勢與統計等資料問題"
    },
    {
      "name": "custom_agent",
      "endpoint_name": "my-custom-endpoint",
      "description": "透過自訂 model endpoint 處理專門查詢"
    }
  ]
  ```
- `description`: "將客戶查詢路由到專門的支援 agents"
- `instructions`: "分析使用者的問題並路由到最合適的 agent。若無法判斷，請要求澄清。"

此範例示範如何混用 Knowledge Assistants（policy_agent）、Genie spaces（usage_analytics）與自訂 endpoints（custom_agent）。

## Agent 設定

`agents` 清單中的每個 agent 都需要：

| 欄位 | 是否必填 | 說明 |
|------|----------|------|
| `name` | 是 | agent 的內部識別子 |
| `description` | 是 | 此 agent 負責的內容（對路由至關重要） |
| `ka_tile_id` | 擇一提供 | Knowledge Assistant tile ID（用於文件問答 agents） |
| `genie_space_id` | 擇一提供 | Genie space ID（用於以 SQL 為基礎的資料 agents） |
| `endpoint_name` | 擇一提供 | Model serving endpoint 名稱（用於自訂 agents） |
| `uc_function_name` | 擇一提供 | Unity Catalog function 名稱，格式為 `catalog.schema.function_name` |
| `connection_name` | 擇一提供 | Unity Catalog connection 名稱（用於 External MCP Servers） |

**注意**：`ka_tile_id`、`genie_space_id`、`endpoint_name`、`uc_function_name` 或 `connection_name` 必須且只能提供其中一個。

若要尋找 KA 的 tile_id，請使用 `manage_ka(action="find_by_name", name="Your KA Name")`。
若要尋找 Genie 的 space_id，請使用 `find_genie_by_name(display_name="Your Genie Name")`。

### 撰寫 descriptions

`description` 欄位對路由非常重要。請盡量具體：

**好的 descriptions：**
- "處理帳務問題，包括發票、付款、退款與訂閱變更"
- "回答 API 錯誤、整合問題與產品 bug 等技術問題"
- "提供 HR 政策、PTO、福利與員工手冊相關資訊"

**不好的 descriptions：**
- "帳務 agent"（太籠統）
- "處理各種事情"（沒有幫助）
- "技術"（不夠具體）

## 佈建時程

建立後，Supervisor Agent endpoint 需要時間完成佈建：

| 狀態 | 說明 | 時間 |
|------|------|------|
| `PROVISIONING` | 正在建立 supervisor | 2-5 分鐘 |
| `ONLINE` | 可開始路由查詢 | - |
| `OFFLINE` | 目前未執行 | - |

使用 `manage_mas` 並指定 `action="get"` 可檢查狀態。

## 加入範例問題

範例問題有助於評估，也能協助最佳化路由：

```json
{
  "examples": [
    {
      "question": "我這個月的發票還沒收到",
      "guideline": "應路由到 billing_agent"
    },
    {
      "question": "API 回傳 500 錯誤",
      "guideline": "應路由到 technical_agent"
    },
    {
      "question": "我還有幾天特休？",
      "guideline": "應路由到 hr_agent"
    }
  ]
}
```

如果 Supervisor Agent 尚未進入 `ONLINE`，範例會先排入佇列，待就緒後自動加入。

## 最佳實務

### Agent 設計

1. **專門化 agents**：每個 agent 都應有清楚且明確的用途
2. **避免領域重疊**：不要讓多個 agents 擁有相似的 descriptions
3. **明確界線**：定義每個 agent 負責與不負責的範圍

### 撰寫 Instructions

請提供路由指示：

```
你是一位客戶支援 supervisor。你的工作是將使用者查詢路由給正確的專家：

1. 帳務、付款或訂閱問題 → billing_agent
2. 技術問題、bug 或 API 問題 → technical_agent
3. HR、福利或政策問題 → hr_agent

如果查詢內容不清楚或橫跨多個領域，請要求使用者澄清。
```

### Fallback 處理

可考慮加入一個通用 agent，處理無法歸類的查詢：

```json
{
  "name": "general_agent",
  "endpoint_name": "general-support-endpoint",
  "description": "處理不屬於其他類別的一般問題，並提供導引協助"
}
```

## 範例工作流程

1. **部署專門 agents** 作為 model serving endpoints：
   - `billing-assistant-endpoint`
   - `tech-support-endpoint`
   - `hr-assistant-endpoint`

2. **建立 MAS**：
   - 為 agents 設定清楚的 descriptions
   - 加入路由 instructions

3. **等待 `ONLINE` 狀態**（2-5 分鐘）

4. **加入範例問題** 供評估使用

5. **測試路由**，涵蓋不同類型的查詢

## 更新 Supervisor Agent

若要更新現有的 Supervisor Agent：

1. **新增／移除 agents**：呼叫 `manage_mas` 並指定 `action="create_or_update"`，傳入更新後的 `agents` 清單
2. **更新 descriptions**：調整 agent descriptions 以改善路由
3. **修改 instructions**：更新路由規則

工具會依名稱找到現有的 Supervisor Agent 並加以更新。

## 疑難排解

### 查詢被路由到錯誤的 agent

- 檢查並改善 agent descriptions
- 讓 descriptions 更具體且彼此區隔
- 加入能展示正確路由的範例

### Endpoint 沒有回應

- 確認每個底層 model serving endpoint 都正在執行
- 檢查 endpoint logs 是否有錯誤
- 確認 endpoints 可接受預期的輸入格式

### 回應緩慢

- 檢查底層 endpoints 的延遲
- 考慮 endpoint 擴充設定
- 監控是否有 cold start 問題

## 進階：階層式路由

在複雜情境中，你可以建立多層級的 Supervisor Agents：

```
頂層 Supervisor
├── Customer Support Supervisor
│   ├── billing_agent
│   ├── technical_agent
│   └── general_agent
├── Sales Supervisor
│   ├── pricing_agent
│   ├── demo_agent
│   └── contract_agent
└── Internal Supervisor
    ├── hr_agent
    └── it_helpdesk_agent
```

每個子 supervisor 都會部署為一個 endpoint，並在頂層 supervisor 中作為 agent 進行設定。
