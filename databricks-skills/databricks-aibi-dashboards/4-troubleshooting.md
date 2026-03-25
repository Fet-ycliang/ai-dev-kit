# 疑難排解

AI/BI 儀表板的常見錯誤與修正方式。

## 元件顯示「no selected fields to visualize」

**這是 field name 不一致的錯誤。** `query.fields` 中的 `name` 必須與 `encodings` 中的 `fieldName` 完全一致。

**修正：**請確認名稱完全一致：
```json
// 錯誤 - 名稱不一致
"fields": [{"name": "spend", "expression": "SUM(`spend`)"}]
"encodings": {"value": {"fieldName": "sum(spend)", ...}}  // 錯誤！

// 正確 - 名稱一致
"fields": [{"name": "sum(spend)", "expression": "SUM(`spend`)"}]
"encodings": {"value": {"fieldName": "sum(spend)", ...}}  // 正確！
```

## 元件顯示「Invalid widget definition」

**檢查版本號：**
- 計數器：`version: 2`
- 資料表：`version: 2`
- 篩選器：`version: 2`
- 長條圖/折線圖/圓餅圖：`version: 3`

**文字元件錯誤：**
- 文字元件不可有 `spec` 區塊
- 直接在 widget 物件上使用 `multilineTextboxSpec`
- 不要使用 `widgetType: "text"` - 這是無效的

**資料表元件錯誤：**
- 使用 `version: 2`（不是 1 或 3）
- 欄物件只需要 `fieldName` 和 `displayName`
- 不要加入 `type`、`numberFormat` 或其他欄屬性

**計數器元件錯誤：**
- 使用 `version: 2`（不是 3）
- 確保資料集剛好回傳 1 列

## 儀表板出現空白元件
- 直接執行資料集 SQL 查詢，確認有資料存在
- 確認欄位 alias 與元件欄位 expression 一致
- 檢查 `disaggregated` 旗標（預先彙總資料應為 `true`）

## 版面配置有空隙
- 確保每一列的寬度總和為 width=6
- 檢查 y 位置是否沒有跳號

## 篩選器顯示「Invalid widget definition」
- 檢查 `widgetType` 是否為下列其中之一：`filter-multi-select`、`filter-single-select`、`filter-date-range-picker`
- **不要**使用 `widgetType: "filter"` - 這是無效的
- 確認 `spec.version` 為 `2`
- 確保 encodings 中的 `queryName` 與查詢 `name` 一致
- 確認篩選器查詢使用 `disaggregated: false`
- 確保有包含 `frame` 並設定 `showTitle: true`

## 篩選器未影響預期頁面
- **全域篩選器**（位於 `PAGE_TYPE_GLOBAL_FILTERS` 頁面）會影響所有包含該篩選欄位的資料集
- **頁面層級篩選器**（位於 `PAGE_TYPE_CANVAS` 頁面）只會影響同一頁上的元件
- 篩選器只會作用於包含該篩選維度欄位的資料集

## 篩選器對 `associative_filter_predicate_group` 顯示「UNRESOLVED_COLUMN」錯誤
- **不要**在篩選器查詢中使用 `COUNT_IF(\`associative_filter_predicate_group\`)`
- 此內部 expression 會在儀表板執行查詢時造成 SQL 錯誤
- 請改用簡單欄位 expression：`{"name": "field", "expression": "\`field\`"}`

## 文字元件將標題與說明顯示在同一行
- `lines` 陣列中的多個項目會**串接**，不會分行顯示
- 請在不同 y 位置為標題與副標題使用**分開的文字元件**
- 例如：標題放在 y=0、height=1，副標題放在 y=1、height=1
