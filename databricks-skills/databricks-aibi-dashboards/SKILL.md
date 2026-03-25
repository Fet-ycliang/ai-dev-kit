---
name: databricks-aibi-dashboards
description: "建立 Databricks AI/BI 儀表板。適用於建立、更新或部署 Lakeview 儀表板。重要：部署前必須透過 execute_sql 測試所有 SQL 查詢。請嚴格遵守操作指引。"
---

# AI/BI 儀表板 Skill

建立 Databricks AI/BI 儀表板（原稱 Lakeview 儀表板）。**請嚴格遵守以下操作指引。**

## 重要：必要驗證流程

**必須完整執行以下流程。跳過驗證步驟將導致儀表板損壞。**

```
┌─────────────────────────────────────────────────────────────────────┐
│  步驟 1：透過 get_table_details(catalog, schema) 取得資料表 schema  │
├─────────────────────────────────────────────────────────────────────┤
│  步驟 2：為每個 dataset 撰寫 SQL 查詢                               │
├─────────────────────────────────────────────────────────────────────┤
│  步驟 3：透過 execute_sql() 測試每一個查詢 ← 不可跳過！             │
│          - 查詢失敗時，修正後再繼續                                  │
│          - 確認欄位名稱與 widget 參照的名稱一致                      │
│          - 確認資料型別正確（日期、數字、字串）                      │
├─────────────────────────────────────────────────────────────────────┤
│  步驟 4：僅使用已驗證的查詢建構儀表板 JSON                          │
├─────────────────────────────────────────────────────────────────────┤
│  步驟 5：透過 create_or_update_dashboard() 部署                     │
└─────────────────────────────────────────────────────────────────────┘
```

**警告：若未測試查詢即部署，widget 將顯示「Invalid widget definition」錯誤！**

## 可用 MCP 工具

| 工具 | 說明 |
|------|------|
| `get_table_details` | **步驟 1**：取得資料表 schema 以設計查詢 |
| `execute_sql` | **步驟 3**：測試 SQL 查詢——部署前必須執行！ |
| `get_best_warehouse` | 取得可用的 warehouse ID |
| `create_or_update_dashboard` | **步驟 5**：部署儀表板 JSON（僅在驗證後執行！） |
| `get_dashboard` | 依 ID 取得儀表板詳情，或列出所有儀表板（省略 dashboard_id） |
| `delete_dashboard` | 將儀表板移至垃圾桶 |
| `publish_dashboard` | 發布（`publish=True`）或取消發布（`publish=False`）儀表板 |

## 參考文件

| 您要建立的內容 | 參考文件 |
|--------------|---------|
| 任何 widget（文字、計數器、表格、圖表） | [1-widget-specifications.md](1-widget-specifications.md) |
| 含篩選器的儀表板（全域或頁面層級） | [2-filters.md](2-filters.md) |
| 需要完整可用的範本來改寫 | [3-examples.md](3-examples.md) |
| 除錯損壞的儀表板 | [4-troubleshooting.md](4-troubleshooting.md) |

---

## 實作指引

### 1) DATASET 架構（嚴格規範）

- **一個 domain 對應一個 dataset**（例如：訂單、客戶、產品）
- **每個 dataset 恰好只有一個有效 SQL 查詢**（不可用 `;` 分隔多個查詢）
- 一律使用**完整限定的資料表名稱**：`catalog.schema.table_name`
- SELECT 必須包含 widget 所需的所有維度欄位，以及透過 `AS` 別名定義的衍生欄位
- 所有業務邏輯（CASE/WHEN、COALESCE、比率計算）均放入 dataset 的 SELECT 並使用明確別名
- **契約規則**：每個 widget 的 `fieldName` 必須完全對應 dataset 的欄位名稱或別名

### 2) WIDGET 欄位表達式

> **重要：欄位名稱對應規則**
> `query.fields` 中的 `name` 必須與 `encodings` 中的 `fieldName` 完全相符。
> 若不一致，widget 將顯示「no selected fields to visualize」錯誤！

**聚合函式的正確寫法：**
```json
// 在 query.fields 中：
{"name": "sum(spend)", "expression": "SUM(`spend`)"}

// 在 encodings 中（必須一致！）：
{"fieldName": "sum(spend)", "displayName": "Total Spend"}
```

**錯誤寫法——名稱不一致：**
```json
// 在 query.fields 中：
{"name": "spend", "expression": "SUM(`spend`)"}  // name 為 "spend"

// 在 encodings 中：
{"fieldName": "sum(spend)", ...}  // 錯誤："sum(spend)" ≠ "spend"
```

Widget 查詢中允許使用的表達式（不可使用 CAST 或其他 SQL 函式）：

**數值：**
```json
{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}
{"name": "avg(price)", "expression": "AVG(`price`)"}
{"name": "count(orders)", "expression": "COUNT(`order_id`)"}
{"name": "countdistinct(customers)", "expression": "COUNT(DISTINCT `customer_id`)"}
{"name": "min(date)", "expression": "MIN(`order_date`)"}
{"name": "max(date)", "expression": "MAX(`order_date`)"}
```

**日期**（時間序列用 daily，分組比較用 weekly/monthly）：
```json
{"name": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"}
{"name": "weekly(date)", "expression": "DATE_TRUNC(\"WEEK\", `date`)"}
{"name": "monthly(date)", "expression": "DATE_TRUNC(\"MONTH\", `date`)"}
```

**簡單欄位參照**（用於已預先聚合的資料）：
```json
{"name": "category", "expression": "`category`"}
```

若需條件邏輯或多欄位公式，請先在 dataset SQL 中計算衍生欄位。

### 3) SPARK SQL 語法規範

- 日期運算：`date_sub(current_date(), N)` 計算天數，`add_months(current_date(), -N)` 計算月數
- 日期截斷：`DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **避免**使用 `INTERVAL` 語法，改用函式

### 4) 版面配置（6 欄格線，不可有空隙）

每個 widget 均有位置屬性：`{"x": 0, "y": 0, "width": 2, "height": 4}`

**重要**：每一列的 width 總和必須恰好等於 6，不可有空隙。

**建議的 widget 尺寸：**

| Widget 類型 | Width | Height | 備注 |
|------------|-------|--------|------|
| 文字標題 | 6 | 1 | 全寬；標題與副標題使用**獨立** widget |
| 計數器/KPI | 2 | **3-4** | **絕對不能 height=2**——太擁擠！ |
| 折線/長條圖 | 3 | **5-6** | 並排兩個填滿一列 |
| 圓餅圖 | 3 | **5-6** | 需要空間顯示圖例 |
| 全寬圖表 | 6 | 5-7 | 適合詳細時間序列 |
| 資料表 | 6 | 5-8 | 全寬以提升可讀性 |

**標準儀表板結構：**
```text
y=0:  標題（w=6, h=1）——儀表板標題（請使用獨立 widget！）
y=1:  副標題（w=6, h=1）——說明文字（請使用獨立 widget！）
y=2:  KPI（w=2 各，h=3）——3 個關鍵指標並排
y=5:  區段標題（w=6, h=1）——「趨勢」或類似名稱
y=6:  圖表（w=3 各，h=5）——兩個圖表並排
y=11: 區段標題（w=6, h=1）——「詳細資料」
y=12: 資料表（w=6, h=6）——詳細資料
```

### 5) 基數與可讀性（重要）

**儀表板可讀性取決於限制不同值的數量：**

| 維度類型 | 最大值數量 | 範例 |
|---------|-----------|------|
| 圖表顏色/分組 | **3-8** | 4 個地區、5 個產品線、3 個等級 |
| 篩選器 | 4-10 | 8 個國家、5 個管道 |
| 高基數欄位 | **僅限資料表** | customer_id、order_id、SKU |

**建立任何含顏色/分組的圖表前：**
1. 檢查欄位基數（使用 `get_table_details` 查看不同值數量）
2. 若不同值超過 10 個，則聚合至更高層級，或使用前 N 名 + 「其他」分組
3. 高基數維度請使用資料表 widget 而非圖表

### 6) 品質檢查清單

部署前請確認：
1. 所有 widget 名稱僅使用英數字元、連字號及底線
2. 每一列的 width 總和為 6 且無空隙
3. KPI 使用 height 3-4，圖表使用 height 5-6
4. 圖表維度的不同值不超過 8 個
5. 所有 widget 的 fieldName 與 dataset 欄位完全一致
6. **query.fields 中的 `name` 與 encodings 中的 `fieldName` 完全一致**（例如，兩者均為 `"sum(spend)"`）
7. 計數器 dataset：1 列資料使用 `disaggregated: true`，多列資料使用 `disaggregated: false` 搭配聚合函式
8. 百分比值為 0-1 範圍（非 0-100）
9. SQL 使用 Spark 語法（date_sub，而非 INTERVAL）
10. **所有 SQL 查詢已透過 `execute_sql` 測試並回傳預期資料**

---

## 相關 Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — 用於查詢底層資料與系統資料表
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — 用於建立提供儀表板資料的管道
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — 用於排程儀表板資料更新
