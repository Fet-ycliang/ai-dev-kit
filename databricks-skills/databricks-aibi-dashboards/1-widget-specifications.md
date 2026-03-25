# 元件規格

各種 AI/BI 儀表板元件類型的詳細 JSON 寫法。

## 元件命名慣例（重要）

- `widget.name`：僅能使用英數字 + 連字號 + 底線（不可有空格、括號、冒號）
- `frame.title`：人類可讀名稱（可使用任何字元）
- `widget.queries[0].name`：一律使用 `"main_query"`

## 版本需求

| 元件類型 | 版本 |
|-------------|---------|
| counter | 2 |
| table | 2 |
| filter-multi-select | 2 |
| filter-single-select | 2 |
| filter-date-range-picker | 2 |
| bar | 3 |
| line | 3 |
| pie | 3 |
| text | N/A（無 spec 區塊） |

---

## Text（標頭/說明）

- **重要：Text 元件不可使用 spec 區塊！**
- 直接在 widget 上使用 `multilineTextboxSpec`
- 支援 markdown：`#`、`##`、`###`、`**bold**`、`*italic*`
- **重要：`lines` 陣列中的多個項目會串接成同一行，不會分行顯示！**
- 若要同時顯示標題 + 副標題，請在不同 y 位置使用**分開的文字元件**

```json
// 正確：標題與副標題使用分開的元件
{
  "widget": {
    "name": "title",
    "multilineTextboxSpec": {
      "lines": ["## 儀表板標題"]
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 1}
},
{
  "widget": {
    "name": "subtitle",
    "multilineTextboxSpec": {
      "lines": ["說明文字放這裡"]
    }
  },
  "position": {"x": 0, "y": 1, "width": 6, "height": 1}
}

// 錯誤：多行會串接成同一行！
{
  "widget": {
    "name": "title-widget",
    "multilineTextboxSpec": {
      "lines": ["## 儀表板標題", "說明文字放這裡"]  // 會變成 "## 儀表板標題說明文字放這裡"
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 2}
}
```

---

## Counter（KPI）

- `version`：**2**（不是 3！）
- `widgetType`: "counter"
- **資料中的百分比值必須是 0-1**（不是 0-100）

**Counter 有兩種寫法：**

**寫法 1：預先彙總的資料集（1 列，無篩選器）**
- 資料集必須剛好回傳 1 列
- 使用 `"disaggregated": true` 與簡單欄位參照
- 欄位 `name` 直接對應資料集欄位

```json
{
  "widget": {
    "name": "total-revenue",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "summary_ds",
        "fields": [{"name": "revenue", "expression": "`revenue`"}],
        "disaggregated": true
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "counter",
      "encodings": {
        "value": {"fieldName": "revenue", "displayName": "總營收"}
      },
      "frame": {"showTitle": true, "title": "總營收"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 3}
}
```

**寫法 2：具彙總的元件（多列資料集，支援篩選器）**
- 資料集回傳多列（例如依某個篩選維度分組）
- 使用 `"disaggregated": false` 與彙總 expression
- **重要**：欄位 `name` 必須與 `fieldName` 完全一致（例如 `"sum(spend)"`）

```json
{
  "widget": {
    "name": "total-spend",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "by_category",
        "fields": [{"name": "sum(spend)", "expression": "SUM(`spend`)"}],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "counter",
      "encodings": {
        "value": {"fieldName": "sum(spend)", "displayName": "總支出"}
      },
      "frame": {"showTitle": true, "title": "總支出"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 3}
}
```

---

## 資料表

- `version`：**2**（不是 1 或 3！）
- `widgetType`: "table"
- **欄只需要 `fieldName` 和 `displayName`** - 不要加入其他屬性！
- 原始資料列請使用 `"disaggregated": true`

```json
{
  "widget": {
    "name": "details-table",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "details_ds",
        "fields": [
          {"name": "name", "expression": "`name`"},
          {"name": "value", "expression": "`value`"}
        ],
        "disaggregated": true
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "table",
      "encodings": {
        "columns": [
          {"fieldName": "name", "displayName": "名稱"},
          {"fieldName": "value", "displayName": "數值"}
        ]
      },
      "frame": {"showTitle": true, "title": "明細"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 6}
}
```

---

## 折線圖 / 長條圖

- `version`: **3**
- `widgetType`: "line" or "bar"
- 使用 `x`、`y` 與可選的 `color` encodings
- `scale.type`：`"temporal"`（日期）、`"quantitative"`（數值）、`"categorical"`（字串）
- 對預先彙總的資料集資料使用 `"disaggregated": true`

**多條線圖 - 兩種方式：**

1. **Multi-Y Fields**（同一張圖上的不同指標）：
```json
"y": {
  "scale": {"type": "quantitative"},
  "fields": [
    {"fieldName": "sum(orders)", "displayName": "訂單數"},
    {"fieldName": "sum(returns)", "displayName": "退貨數"}
  ]
}
```

2. **顏色分組**（相同指標依維度拆分）：
```json
"y": {"fieldName": "sum(revenue)", "scale": {"type": "quantitative"}},
"color": {"fieldName": "region", "scale": {"type": "categorical"}, "displayName": "區域"}
```

**長條圖模式：**
- **堆疊**（預設）：不需要 `mark` 欄位 - 長條會上下堆疊
- **群組**：加入 `"mark": {"layout": "group"}` - 長條會左右並排以利比較

## 圓餅圖

- `version`: **3**
- `widgetType`: "pie"
- `angle`：數值彙總
- `color`：類別維度
- 為了可讀性，請限制在 3-8 個類別
