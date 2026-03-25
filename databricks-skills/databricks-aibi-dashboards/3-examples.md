# 完整儀表板範例

可直接用於正式環境的範本，你可以依需求調整。

## 基本儀表板（NYC Taxi）

```python
import json

# 步驟 1：檢查資料表 schema
table_info = get_table_details(catalog="samples", schema="nyctaxi")

# 步驟 2：測試查詢
execute_sql("SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, AVG(trip_distance) as avg_distance FROM samples.nyctaxi.trips")
execute_sql("""
    SELECT pickup_zip, COUNT(*) as trip_count
    FROM samples.nyctaxi.trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
""")

# 步驟 3：建立儀表板 JSON
dashboard = {
    "datasets": [
        {
            "name": "summary",
            "displayName": "摘要統計",
            "queryLines": [
                "SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, ",
                "AVG(trip_distance) as avg_distance ",
                "FROM samples.nyctaxi.trips "
            ]
        },
        {
            "name": "by_zip",
            "displayName": "各 ZIP 的行程數",
            "queryLines": [
                "SELECT pickup_zip, COUNT(*) as trip_count ",
                "FROM samples.nyctaxi.trips ",
                "GROUP BY pickup_zip ",
                "ORDER BY trip_count DESC ",
                "LIMIT 10 "
            ]
        }
    ],
    "pages": [{
        "name": "overview",
        "displayName": "NYC Taxi 概覽",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            # 文字標頭 - 不可使用 spec 區塊！標題與副標題請使用分開的元件！
            {
                "widget": {
                    "name": "title",
                    "multilineTextboxSpec": {
                        "lines": ["## NYC Taxi 儀表板"]
                    }
                },
                "position": {"x": 0, "y": 0, "width": 6, "height": 1}
            },
            {
                "widget": {
                    "name": "subtitle",
                    "multilineTextboxSpec": {
                        "lines": ["行程統計與分析"]
                    }
                },
                "position": {"x": 0, "y": 1, "width": 6, "height": 1}
            },
            # 計數器 - version 2，寬度要 2！
            {
                "widget": {
                    "name": "total-trips",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "trips", "expression": "`trips`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "trips", "displayName": "總行程數"}
                        },
                        "frame": {"title": "總行程數", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 2, "width": 2, "height": 3}
            },
            {
                "widget": {
                    "name": "avg-fare",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_fare", "expression": "`avg_fare`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_fare", "displayName": "平均車資"}
                        },
                        "frame": {"title": "平均車資", "showTitle": True}
                    }
                },
                "position": {"x": 2, "y": 2, "width": 2, "height": 3}
            },
            {
                "widget": {
                    "name": "total-distance",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_distance", "expression": "`avg_distance`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_distance", "displayName": "平均距離"}
                        },
                        "frame": {"title": "平均距離", "showTitle": True}
                    }
                },
                "position": {"x": 4, "y": 2, "width": 2, "height": 3}
            },
            # 長條圖 - version 3
            {
                "widget": {
                    "name": "trips-by-zip",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "by_zip",
                            "fields": [
                                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                                {"name": "trip_count", "expression": "`trip_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 3,
                        "widgetType": "bar",
                        "encodings": {
                            "x": {"fieldName": "pickup_zip", "scale": {"type": "categorical"}, "displayName": "ZIP"},
                            "y": {"fieldName": "trip_count", "scale": {"type": "quantitative"}, "displayName": "行程數"}
                        },
                        "frame": {"title": "依上車 ZIP 的行程數", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 5, "width": 6, "height": 5}
            },
            # 資料表 - version 2，欄位屬性保持最少！
            {
                "widget": {
                    "name": "zip-table",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "by_zip",
                            "fields": [
                                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                                {"name": "trip_count", "expression": "`trip_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "table",
                        "encodings": {
                            "columns": [
                                {"fieldName": "pickup_zip", "displayName": "ZIP 郵遞區號"},
                                {"fieldName": "trip_count", "displayName": "行程數"}
                            ]
                        },
                        "frame": {"title": "熱門 ZIP 郵遞區號", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 10, "width": 6, "height": 5}
            }
        ]
    }]
}

# 步驟 4：部署
result = create_or_update_dashboard(
    display_name="NYC Taxi 儀表板",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard),
    warehouse_id=get_best_warehouse(),
)
print(result["url"])
```

## 含全域篩選器的儀表板

```python
import json

# 含有區域全域篩選器的儀表板
dashboard_with_filters = {
    "datasets": [
        {
            "name": "sales",
            "displayName": "銷售資料",
            "queryLines": [
                "SELECT region, SUM(revenue) as total_revenue ",
                "FROM catalog.schema.sales ",
                "GROUP BY region"
            ]
        }
    ],
    "pages": [
        {
            "name": "overview",
            "displayName": "銷售概覽",
            "pageType": "PAGE_TYPE_CANVAS",
            "layout": [
                {
                    "widget": {
                        "name": "total-revenue",
                        "queries": [{
                            "name": "main_query",
                            "query": {
                                "datasetName": "sales",
                                "fields": [{"name": "total_revenue", "expression": "`total_revenue`"}],
                                "disaggregated": True
                            }
                        }],
                        "spec": {
                            "version": 2,  # 計數器使用 version 2！
                            "widgetType": "counter",
                            "encodings": {
                                "value": {"fieldName": "total_revenue", "displayName": "總營收"}
                            },
                            "frame": {"title": "總營收", "showTitle": True}
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 6, "height": 3}
                }
            ]
        },
        {
            "name": "filters",
            "displayName": "篩選器",
            "pageType": "PAGE_TYPE_GLOBAL_FILTERS",  # 全域篩選器頁面必填！
            "layout": [
                {
                    "widget": {
                        "name": "filter_region",
                        "queries": [{
                            "name": "ds_sales_region",
                            "query": {
                                "datasetName": "sales",
                                "fields": [
                                    {"name": "region", "expression": "`region`"}
                                    # 不要使用 associative_filter_predicate_group - 會造成 SQL 錯誤！
                                ],
                                "disaggregated": False  # 篩選器要用 False！
                            }
                        }],
                        "spec": {
                            "version": 2,  # 篩選器使用 version 2！
                            "widgetType": "filter-multi-select",  # 不是 "filter"！
                            "encodings": {
                                "fields": [{
                                    "fieldName": "region",
                                    "displayName": "區域",
                                    "queryName": "ds_sales_region"  # 必須與 query 名稱一致！
                                }]
                            },
                            "frame": {"showTitle": True, "title": "區域"}  # 一律顯示標題！
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 2, "height": 2}
                }
            ]
        }
    ]
}

# 部署含篩選器的儀表板
result = create_or_update_dashboard(
    display_name="含篩選器的銷售儀表板",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard_with_filters),
    warehouse_id=get_best_warehouse(),
)
print(result["url"])
```
