---
name: databricks-genie
description: "建立並查詢 Databricks Genie Spaces，以自然語言進行 SQL 探索。當需要建置 Genie Spaces、匯出與匯入 Genie Spaces、在不同工作區或環境之間遷移 Genie Spaces，或透過 Genie Conversation API 提問時使用。"
---

# Databricks Genie

建立、管理與查詢 Databricks Genie Spaces，也就是用於以自然語言進行 SQL 型資料探索的介面。

## 概觀

Genie Spaces 讓使用者可以針對 Unity Catalog 中的結構化資料提出自然語言問題。系統會將問題轉換成 SQL 查詢、在 SQL warehouse 上執行，並以對話方式呈現結果。

## 何時使用此技能

在下列情況使用此技能：
- 建立新的 Genie Space 以進行資料探索
- 新增範例問題來引導使用者
- 將 Unity Catalog 資料表連接到對話式介面
- 以程式方式向 Genie Space 提問（Conversation API）
- 匯出 Genie Space 設定（`serialized_space`）以供備份或遷移
- 從序列化承載資料匯入／複製 Genie Space
- 在不同工作區或環境之間遷移 Genie Space（dev → staging → prod）
    - 僅支援不同環境之間 catalog 名稱不同時的 catalog 對應
    - 不支援 schema 和／或 table 名稱在不同環境之間不同的情況
    - 不包含資料表在不同環境之間的遷移（僅遷移 Genie Spaces）

## MCP 工具

### Genie Space 管理

| 工具 | 用途 |
|------|------|
| `create_or_update_genie` | 建立或更新 Genie Space（支援 `serialized_space`） |
| `get_genie` | 取得 Space 詳細資料（提供 ID 時可搭配 `include_serialized_space` 參數），或在未提供 ID 時列出所有 Genie Spaces |
| `delete_genie` | 刪除 Genie Space |
| `migrate_genie` | 匯出（`type="export"`）或匯入（`type="import"`）Genie Space，以供複製／遷移 |

### Conversation API

| 工具 | 用途 |
|------|------|
| `ask_genie` | 提出問題或追問（`conversation_id` 為選填） |

### 輔助工具

| 工具 | 用途 |
|------|------|
| `get_table_details` | 在建立 Space 前檢視資料表 schema |
| `execute_sql` | 直接測試 SQL 查詢 |

## 快速開始

### 1. 檢視資料表

建立 Genie Space 之前，先了解你的資料：

```python
get_table_details(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

### 2. 建立 Genie Space

```python
create_or_update_genie(
    display_name="銷售分析",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders"
    ],
    description="以自然語言探索銷售資料",
    sample_questions=[
        "上個月的總銷售額是多少？",
        "我們的前 10 大客戶是誰？"
    ]
)
```

### 3. 提問（Conversation API）

```python
ask_genie(
    space_id="your_space_id",
    question="上個月的總銷售額是多少？"
)
# 回傳：SQL、columns、data、row_count
```

### 4. 匯出與匯入（複製／遷移）

匯出 Space（會保留所有資料表、`instructions`、SQL 範例與版面配置）：

```python
exported = migrate_genie(type="export", space_id="your_space_id")
# exported["serialized_space"] 會包含完整設定
```

複製到新的 Space（相同 catalog）：

```python
migrate_genie(
    type="import",
    warehouse_id=exported["warehouse_id"],
    serialized_space=exported["serialized_space"],
    title=exported["title"],  # 覆寫標題；省略則保留原值
    description=exported["description"],
)
```

> **跨工作區遷移：** 每個 MCP server 都綁定單一工作區。請在 IDE 的 MCP config 中為每個工作區 profile 設定一個 server 項目，接著從來源 server 執行 `migrate_genie(type="export")`，再透過目標 server 執行 `migrate_genie(type="import")`。完整流程請參閱 [spaces.md 的「跨工作區遷移並重新對應 Catalog」章節](spaces.md#migrating-across-workspaces-with-catalog-remapping)。

## 參考檔案

- [spaces.md](spaces.md) - 建立與管理 Genie Spaces
- [conversation.md](conversation.md) - 透過 Conversation API 提問

## 先決條件

建立 Genie Space 之前：

1. **Unity Catalog 中的資料表** - 含有資料的 Bronze/silver/gold tables
2. **SQL Warehouse** - 用來執行查詢的 warehouse（若未指定會自動偵測）

### 建立資料表

依序使用以下技能：
1. `databricks-synthetic-data-gen` - 產生原始 parquet 檔案
2. `databricks-spark-declarative-pipelines` - 建立 bronze/silver/gold tables

## 常見問題

完整的問題與解法清單請參閱 [spaces.md 的「疑難排解」章節](spaces.md#troubleshooting)。

## 相關技能

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - 在 Supervisor Agents 中將 Genie Spaces 當成 agent 使用
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - 產生原始 parquet 資料，供 Genie 使用的資料表載入資料
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - 建立供 Genie Spaces 使用的 bronze/silver/gold tables
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - 管理 Genie 查詢所使用的 catalogs、schemas 與 tables
