# 建立 Genie Spaces

本指南說明如何為以 SQL 為基礎的資料探索建立與管理 Genie Spaces。

## 什麼是 Genie Space？

Genie Space 會連接 Unity Catalog 資料表，並將自然語言問題轉換成 SQL——理解 schema、產生查詢、在 SQL warehouse 上執行，並以對話方式呈現結果。

## 建立流程

### 步驟 1：檢視資料表 schema（必要）

**在建立 Genie Space 之前，你務必先檢視資料表 schema**，以了解有哪些資料可用：

```python
get_table_details(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

這會回傳：
- 資料表名稱與資料列數
- 欄位名稱與資料型別
- 範例值與基數
- Null 計數與統計資料

### 步驟 2：分析與規劃

根據 schema 資訊：

1. **選擇相關資料表** - 挑選能支援使用者情境的資料表
2. **識別關鍵欄位** - 記下日期欄位、指標、維度與外鍵
3. **理解關聯** - 資料表之間如何 join？
4. **規劃範例問題** - 這份資料可以回答哪些問題？

### 步驟 3：建立 Genie Space

請依照實際資料建立適合的 Space 內容：

```python
create_or_update_genie(
    display_name="銷售分析",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products"
    ],
    description="""使用三個相關資料表探索零售銷售資料：
- customers：客戶人口統計資料，包含區域、客群與註冊日期
- orders：交易歷程，包含 order_date、total_amount 與 status
- products：產品目錄，包含類別、價格與庫存

資料表透過 customer_id 與 product_id 進行 join。""",
    sample_questions=[
        "上個月的總銷售額是多少？",
        "依 total_amount 計算，我們的前 10 大客戶是誰？",
        "Q4 各區域下了多少筆訂單？",
        "各客戶客群的平均訂單金額是多少？",
        "哪些產品類別的營收最高？",
        "顯示 90 天內未下單的客戶"
    ]
)
```

## 為什麼這個流程很重要

**引用實際欄位名稱的範例問題** 能幫助 Genie：
- 學習你的資料詞彙
- 產生更精準的 SQL 查詢
- 提供更好的自動完成建議

**說明資料表關聯的 `description`** 能幫助 Genie：
- 正確理解如何 join 資料表
- 知道哪個資料表包含哪些資訊
- 提供更貼近需求的答案

## 自動偵測 SQL Warehouse

未指定 `warehouse_id` 時，工具會：

1. 列出工作區中的所有 SQL warehouses
2. 依下列順序優先挑選：
   - **Running** 的 warehouses 優先（已可直接使用）
   - **Starting** 的 warehouses 次之
   - **較小的規模** 優先（成本較有效率）
3. 若沒有任何 warehouse，則回傳錯誤

若要使用特定 warehouse，請明確提供 `warehouse_id`。

## 資料表選擇

請審慎選擇資料表，以獲得最佳結果：

| 層級 | 建議 | 原因 |
|------|------|------|
| Bronze | 否 | 原始資料，可能有品質問題 |
| Silver | 是 | 已清理並完成驗證 |
| Gold | 是 | 已彙總，適合分析 |

### 資料表選擇提示

- **納入相關資料表**：如果使用者會問客戶與訂單，就把兩者都納入
- **使用具描述性的欄位名稱**：`customer_name` 會比 `cust_nm` 更好
- **加入資料表註解**：Genie 會利用中繼資料來理解資料

## 範例問題

範例問題可以幫助使用者了解他們能問什麼：

**良好的範例問題：**
- 「上個月的總銷售額是多少？」
- 「依營收計算，我們的前 10 大客戶是誰？」
- 「Q4 下了多少筆訂單？」
- 「各區域的平均訂單金額是多少？」

這些問題會顯示在 Genie UI 中，引導使用者提問。

## 最佳實務

### 為 Genie 設計資料表

1. **具描述性的名稱**：使用 `customer_lifetime_value`，不要用 `clv`
2. **加入註解**：`COMMENT ON TABLE sales.customers IS '客戶主檔資料'`
3. **主鍵**：清楚定義關聯
4. **日期欄位**：針對時間型查詢，提供適當的 date/timestamp 欄位

### `description` 與上下文

在 `description` 中提供上下文：

```
探索我們 e-commerce 平台的零售銷售資料，內容包含：
- 客戶：人口統計、客群與帳戶狀態
- 訂單：交易歷程、金額與日期
- 產品：產品目錄、類別與定價

時間範圍：最近 6 個月的資料
```

### 範例問題

撰寫範例問題時，請讓它們：
- 涵蓋常見使用情境
- 展現資料能提供的能力
- 使用自然語言（不要使用 SQL 術語）

## 更新 Genie Space

`create_or_update_genie` 會自動處理建立與更新。它有兩種方式可定位既有 Space 以進行更新：

- **透過 `space_id`**（明確、建議優先使用）：傳入 `space_id=` 以指定特定 Space。
- **透過 `display_name`**（隱含後備方式）：若省略 `space_id`，工具會搜尋名稱相符的 Space；若找到則更新，否則建立新的 Space。

### 簡單欄位更新（資料表、問題、warehouse）

若要在沒有序列化設定的情況下更新中繼資料：

```python
create_or_update_genie(
    display_name="銷售分析",
    space_id="01abc123...",           # 省略時會改以名稱比對
    table_identifiers=[               # 更新後的資料表清單
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products",
    ],
    sample_questions=[                # 更新後的範例問題
        "上個月的總銷售額是多少？",
        "依營收計算，我們的前 10 大客戶是誰？",
    ],
    warehouse_id="abc123def456",      # 省略則保留目前值／自動偵測
    description="已更新的說明。",
)
```

### 透過 `serialized_space` 更新完整設定

若要把完整的序列化設定推送到既有 Space（該 `dict` 包含所有一般資料表中繼資料，並會保留所有 `instructions`、SQL 範例、join specs 等）：

```python
create_or_update_genie(
    display_name="銷售分析",         # 覆寫 serialized_space 內嵌的標題
    table_identifiers=[],             # 提供 serialized_space 時會被忽略
    space_id="01abc123...",           # 要覆寫的目標 Space
    warehouse_id="abc123def456",      # 覆寫 serialized_space 內嵌的 warehouse
    description="已更新的說明。",      # 覆寫 serialized_space 內嵌的 description；省略則保留承載資料中的值
    serialized_space=remapped_config, # 來自 migrate_genie(type="export") 的 JSON 字串（若需要，先完成 catalog 對應）
)
```

> **注意：** 提供 `serialized_space` 時，`table_identifiers` 與 `sample_questions` 會被忽略——完整設定會來自序列化承載資料。不過 `display_name`、`warehouse_id` 與 `description` 仍會作為最上層覆寫值套用在序列化承載資料之上。若想保留 `serialized_space` 內嵌的值，請省略對應欄位。

## 匯出、匯入與遷移

`migrate_genie(type="export")` 會回傳一個包含五個最上層鍵的字典：

| 鍵 | 說明 |
|----|------|
| `space_id` | 匯出的 Space ID |
| `title` | Space 的顯示名稱 |
| `description` | Space 的說明 |
| `warehouse_id` | 與 Space 關聯的 SQL warehouse（僅限該工作區使用——**不要**跨工作區重用） |
| `serialized_space` | 包含完整 Space 設定的 JSON 編碼字串（見下文） |

這個封裝可支援複製、備份與跨工作區遷移。所有匯出／匯入操作都請使用 `migrate_genie(type="export")` 與 `migrate_genie(type="import")`——不需要直接呼叫 REST。

## 什麼是 `serialized_space`？

`serialized_space` 是內嵌在匯出封裝中的 JSON 字串（第 2 版）。它的最上層鍵如下：

| 鍵 | 內容 |
|----|------|
| `version` | Schema 版本（目前為 `2`） |
| `config` | Space 層級設定：顯示在 UI 中的 `sample_questions` |
| `data_sources` | `tables` 陣列——每個項目都包含完整限定名稱 `identifier`（`catalog.schema.table`），以及選填的 `column_configs`（格式協助、各欄位的實體比對） |
| `instructions` | `example_question_sqls`（認證問答配對）、`join_specs`（資料表之間的 join 關係）、`sql_snippets`（含顯示名稱與使用說明的 `filters` 與 `measures`） |
| `benchmarks` | 用於衡量 Space 品質的評估問答配對 |

Catalog 名稱會出現在 `serialized_space` 的**各處**——包含 `data_sources.tables[].identifier`、`example_question_sqls` 內的 SQL 字串、`join_specs` 與 `sql_snippets`。只要對整個字串做一次 `.replace(src_catalog, tgt_catalog)`，就足以完成 catalog 對應。

最小結構：
```json
{"version": 2, "data_sources": {"tables": [{"identifier": "catalog.schema.table"}]}}
```

### 匯出 Space

使用 `migrate_genie(type="export")` 匯出完整設定（需要 CAN EDIT 權限）：

```python
exported = migrate_genie(type="export", space_id="01abc123...")
# 回傳：
# {
#   "space_id": "01abc123...",
#   "title": "銷售分析",
#   "description": "探索銷售資料...",
#   "warehouse_id": "abc123def456",
#   "serialized_space": "{\"version\":2,\"data_sources\":{...},\"instructions\":{...}}"
# }
```

你也可以透過 `get_genie` 直接取得 `serialized_space`：

```python
details = get_genie(space_id="01abc123...", include_serialized_space=True)
serialized = details["serialized_space"]
```

### 複製 Space（相同工作區）

```python
# 步驟 1：匯出來源 Space
source = migrate_genie(type="export", space_id="01abc123...")

# 步驟 2：匯入成新的 Space
migrate_genie(
    type="import",
    warehouse_id=source["warehouse_id"],
    serialized_space=source["serialized_space"],
    title=source["title"],  # 覆寫標題；省略則保留原值
    description=source["description"],
)
# 回傳：{"space_id": "01def456...", "title": "銷售分析（Dev 複本）", "operation": "imported"}
```

<a id="migrating-across-workspaces-with-catalog-remapping"></a>
### 跨工作區遷移並重新對應 Catalog

在不同環境之間遷移時（例如 prod → dev），Unity Catalog 名稱通常不同。`serialized_space` 字串會在**各處**包含來源 catalog 名稱——包括資料表識別子、SQL 查詢、join specs 與 filter snippets。你必須在匯入前先完成對應。

**Agent 工作流程（3 個步驟）：**

**步驟 1——從來源工作區匯出：**
```python
exported = migrate_genie(type="export", space_id="01f106e1239d14b28d6ab46f9c15e540")
# exported 鍵包含：warehouse_id、title、description、serialized_space
# exported["serialized_space"] 含有所有對來源 catalog 的參照
```

**步驟 2——在 `serialized_space` 中重新對應 catalog 名稱：**

Agent 會在兩次 MCP 呼叫之間，直接進行這個內嵌字串取代：
```python
modified_serialized = exported["serialized_space"].replace(
    "source_catalog_name",     # 例如 "healthverity_claims_sample_patient_dataset"
    "target_catalog_name"      # 例如 "healthverity_claims_sample_patient_dataset_dev"
)
```
這會替換所有出現的位置——資料表識別子、SQL FROM 子句、join specs 與 filter snippets。

**步驟 3——匯入到目標工作區：**
```python
migrate_genie(
    type="import",
    warehouse_id="<target_warehouse_id>",   # 由目標端的 list_warehouses() 取得
    serialized_space=modified_serialized,
    title=exported["title"],
    description=exported["description"]
)
```

### 批次遷移多個 Spaces

若要一次遷移多個 Spaces，請對每個 Space ID 迴圈處理。Agent 會逐一匯出、重新對應 catalog，再完成匯入：

```
對於 [id1, id2, id3] 中的每個 space_id：
  1. exported = migrate_genie(type="export", space_id=space_id)
  2. modified  = exported["serialized_space"].replace(src_catalog, tgt_catalog)
  3. result    = migrate_genie(type="import", warehouse_id=wh_id, serialized_space=modified, title=exported["title"], description=exported["description"])
  4. 記錄 result["space_id"]，供更新 databricks.yml 使用
```

遷移完成後，請用新的 dev `space_id` 值更新 `databricks.yml` 中 `dev` target 底下的 `genie_space_ids` 變數。

### 以新設定更新既有 Space

若要把序列化設定推送到已存在的 Space（而不是建立新的 Space），請使用同時帶有 `space_id=` 與 `serialized_space=` 的 `create_or_update_genie`。匯出 → 對應 → 推送的模式與上述遷移步驟完全相同；只要把最後一步的 `migrate_genie(type="import")` 換成 `create_or_update_genie(space_id=TARGET_SPACE_ID, ...)` 即可。

### 所需權限

| 操作 | 所需權限 |
|------|----------|
| `migrate_genie(type="export")` / `get_genie(include_serialized_space=True)` | 來源 Space 的 CAN EDIT |
| `migrate_genie(type="import")` | 可在目標工作區資料夾中建立項目 |
| `create_or_update_genie` 搭配 `serialized_space`（更新） | 目標 Space 的 CAN EDIT |

## 範例端到端流程

1. 使用 `databricks-synthetic-data-gen` 技能**產生合成資料**：
   - 在 `/Volumes/catalog/schema/raw_data/` 建立 parquet 檔案

2. 使用 `databricks-spark-declarative-pipelines` 技能**建立資料表**：
   - 建立 `catalog.schema.bronze_*` → `catalog.schema.silver_*` → `catalog.schema.gold_*`

3. **檢視資料表**：
   ```python
   get_table_details(catalog="catalog", schema="schema")
   ```

4. **建立 Genie Space**：
   - `display_name`: "我的資料探索器"
   - `table_identifiers`: `["catalog.schema.silver_customers", "catalog.schema.silver_orders"]`

5. 根據實際欄位名稱**新增範例問題**

6. 在 Databricks UI 中**測試**

<a id="troubleshooting"></a>
## 疑難排解

### 沒有可用的 warehouse

- 在 Databricks 工作區中建立 SQL warehouse
- 或提供特定的 `warehouse_id`

### 查詢速度緩慢

- 確認 warehouse 正在執行（不是 `stopped`）
- 考慮使用較大的 warehouse 規模
- 檢查資料表是否已最佳化（OPTIMIZE、Z-ORDER）

### 查詢產生品質不佳

- 使用具描述性的欄位名稱
- 加入資料表與欄位註解
- 納入能示範詞彙的範例問題
- 透過 Databricks Genie UI 新增 `instructions`

### `migrate_genie(type="export")` 回傳空的 `serialized_space`

至少需要該 Space 的 **CAN EDIT** 權限。

### `migrate_genie(type="import")` 因權限錯誤而失敗

請確認你在目標工作區資料夾中具有 CREATE 權限。

### 遷移後找不到資料表

代表 catalog 名稱尚未重新對應——請在呼叫 `migrate_genie(type="import")` 前，先替換 `serialized_space` 中的來源 catalog 名稱。catalog 會出現在資料表識別子、SQL FROM 子句、join specs 與 filter snippets；對整個字串做一次 `.replace(src_catalog, tgt_catalog)` 即可涵蓋所有出現位置。

### `migrate_genie` 落在錯誤的工作區

每個 MCP server 都綁定單一工作區。請在 IDE 的 MCP config 中設定兩個具名的 MCP server 項目（每個 profile 一個），不要在同一個 session 中途切換單一 server 的 profile。

### MCP server 未偵測到 profile 變更

MCP 程序只會在啟動時讀取一次 `DATABRICKS_CONFIG_PROFILE`——編輯 config 檔後，必須重新載入 IDE 才會生效。

### `migrate_genie(type="import")` 因 JSON 解析錯誤而失敗

`serialized_space` 字串可能包含帶有 `\n` escape sequences 的多行 SQL 陣列。傳入前請先把 SQL 陣列攤平成單行字串，以避免重複 escape 的問題。
