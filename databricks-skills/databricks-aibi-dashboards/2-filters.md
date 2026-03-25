# 篩選器（全域 vs 頁面層級）

> **重要**：篩選器元件使用的 widget type 與圖表不同！
> - 有效類型：`filter-multi-select`、`filter-single-select`、`filter-date-range-picker`
> - **不要**使用 `widgetType: "filter"` - 這個類型不存在，且會造成錯誤
> - 篩選器使用 `spec.version: 2`
> - **篩選器元件一律包含 `frame` 並設定 `showTitle: true`**

**篩選器元件類型：**
- `filter-date-range-picker`：用於 DATE/TIMESTAMP 欄位
- `filter-single-select`：單選類別欄位
- `filter-multi-select`：多選類別欄位

---

## 全域篩選器 vs 頁面層級篩選器

| 類型 | 放置位置 | 影響範圍 | 使用情境 |
|------|-----------|-------|----------|
| **全域篩選器** | 使用 `"pageType": "PAGE_TYPE_GLOBAL_FILTERS"` 的專用頁面 | 影響所有包含該篩選欄位資料集的頁面 | 跨儀表板篩選（例如日期範圍、活動） |
| **頁面層級篩選器** | 使用 `"pageType": "PAGE_TYPE_CANVAS"` 的一般頁面 | 只影響同一頁上的元件 | 頁面專屬篩選（例如只在 breakdown 頁使用 platform 篩選器） |

**關鍵概念**：篩選器只會影響包含該篩選欄位的資料集。若要讓篩選器只影響特定頁面：
1. 在需要被篩選的頁面資料集中納入該篩選維度
2. 在不應被篩選的頁面資料集中排除該篩選維度

---

## 篩選器元件結構

> **重要**：不要使用 `associative_filter_predicate_group` - 這會造成 SQL 錯誤！
> 請改用簡單欄位 expression。

```json
{
  "widget": {
    "name": "filter_region",
    "queries": [{
      "name": "ds_data_region",
      "query": {
        "datasetName": "ds_data",
        "fields": [
          {"name": "region", "expression": "`region`"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "filter-multi-select",
      "encodings": {
        "fields": [{
          "fieldName": "region",
          "displayName": "區域",
          "queryName": "ds_data_region"
        }]
      },
      "frame": {"showTitle": true, "title": "區域"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
}
```

---

## 全域篩選器範例

放在專用的篩選器頁面上：

```json
{
  "name": "filters",
  "displayName": "篩選器",
  "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
  "layout": [
    {
      "widget": {
        "name": "filter_campaign",
        "queries": [{
          "name": "ds_campaign",
          "query": {
            "datasetName": "overview",
            "fields": [{"name": "campaign_name", "expression": "`campaign_name`"}],
            "disaggregated": false
          }
        }],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {
            "fields": [{
              "fieldName": "campaign_name",
              "displayName": "活動",
              "queryName": "ds_campaign"
            }]
          },
          "frame": {"showTitle": true, "title": "活動"}
        }
      },
      "position": {"x": 0, "y": 0, "width": 2, "height": 2}
    }
  ]
}
```

---

## 頁面層級篩選器範例

直接放在 canvas 頁面上（只影響該頁）：

```json
{
  "name": "platform_breakdown",
  "displayName": "平台拆解",
  "pageType": "PAGE_TYPE_CANVAS",
  "layout": [
    {
      "widget": {
        "name": "page-title",
        "multilineTextboxSpec": {"lines": ["## 平台拆解"]}
      },
      "position": {"x": 0, "y": 0, "width": 4, "height": 1}
    },
    {
      "widget": {
        "name": "filter_platform",
        "queries": [{
          "name": "ds_platform",
          "query": {
            "datasetName": "platform_data",
            "fields": [{"name": "platform", "expression": "`platform`"}],
            "disaggregated": false
          }
        }],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {
            "fields": [{
              "fieldName": "platform",
              "displayName": "平台",
              "queryName": "ds_platform"
            }]
          },
          "frame": {"showTitle": true, "title": "平台"}
        }
      },
      "position": {"x": 4, "y": 0, "width": 2, "height": 2}
    }
    // ... 此頁上的其他元件
  ]
}
```

---

## 篩選器版面配置指引

- 全域篩選器：放在專用篩選器頁面上，於 `x=0` 垂直堆疊
- 頁面層級篩選器：放在頁面標頭區域（例如右上角）
- 常見尺寸：`width: 2, height: 2`
