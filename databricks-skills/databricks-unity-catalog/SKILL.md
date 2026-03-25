---
name: databricks-unity-catalog
description: "Unity Catalog 系統資料表與 Volumes。適用於查詢系統資料表（稽核、資料血緣、計費）或進行 Volume 檔案操作（上傳、下載、列出 /Volumes/ 中的檔案）。"
---

# Unity Catalog

Unity Catalog 系統資料表、Volumes 與資料治理使用指南。

## 適用情境

在以下情況使用此 Skill：
- 操作 **Volumes**（上傳、下載、列出 `/Volumes/` 中的檔案）
- 查詢**資料血緣**（資料表依賴關係、欄位層級血緣）
- 分析**稽核日誌**（誰存取了什麼、權限變更紀錄）
- 監控**計費與使用量**（DBU 消耗、成本分析）
- 追蹤**計算資源**（叢集使用率、Warehouse 指標）
- 檢視 **Job 執行紀錄**（執行歷程、成功率、失敗紀錄）
- 分析**查詢效能**（慢查詢、Warehouse 使用率）
- 評估**資料品質**（資料側寫、漂移偵測、指標資料表）

## 參考文件

| 主題 | 檔案 | 說明 |
|------|------|------|
| 系統資料表 | [5-system-tables.md](5-system-tables.md) | 資料血緣、稽核、計費、計算、Jobs、查詢歷程 |
| Volumes | [6-volumes.md](6-volumes.md) | Volume 檔案操作、權限管理、最佳實踐 |
| 資料側寫 | [7-data-profiling.md](7-data-profiling.md) | 資料側寫、漂移偵測、側寫指標 |

## 快速入門

### Volume 檔案操作（MCP 工具）

```python
# 列出 Volume 中的檔案
list_volume_files(volume_path="/Volumes/catalog/schema/volume/folder/")

# 上傳檔案至 Volume
upload_to_volume(
    local_path="/tmp/data.csv",
    volume_path="/Volumes/catalog/schema/volume/data.csv"
)

# 從 Volume 下載檔案
download_from_volume(
    volume_path="/Volumes/catalog/schema/volume/data.csv",
    local_path="/tmp/downloaded.csv"
)

# 建立目錄
create_volume_directory(volume_path="/Volumes/catalog/schema/volume/new_folder")
```

### 啟用系統資料表存取權限

```sql
-- 授予系統資料表存取權限
GRANT USE CATALOG ON CATALOG system TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA system.access TO `data_engineers`;
GRANT SELECT ON SCHEMA system.access TO `data_engineers`;
```

### 常用查詢範例

```sql
-- 資料血緣：哪些資料表提供資料給此資料表？
SELECT source_table_full_name, source_column_name
FROM system.access.table_lineage
WHERE target_table_full_name = 'catalog.schema.table'
  AND event_date >= current_date() - 7;

-- 稽核：近期權限變更紀錄
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE action_name LIKE '%GRANT%' OR action_name LIKE '%REVOKE%'
ORDER BY event_time DESC
LIMIT 100;

-- 計費：各工作區 DBU 使用量
SELECT workspace_id, sku_name, SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY workspace_id, sku_name;
```

## MCP 工具整合

使用 `mcp__databricks__execute_sql` 查詢系統資料表：

```python
# 查詢資料血緣
mcp__databricks__execute_sql(
    sql_query="""
        SELECT source_table_full_name, target_table_full_name
        FROM system.access.table_lineage
        WHERE event_date >= current_date() - 7
    """,
    catalog="system"
)
```

## 最佳實踐

1. **加入日期篩選** — 系統資料表資料量龐大，務必使用日期條件過濾
2. **確認資料保留期限** — 瞭解工作區的資料保留設定
3. **授予最小必要權限** — 系統資料表包含敏感的中繼資料
4. **排程定期報告** — 建立排程查詢以進行例行監控

## 相關 Skills

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — 建立寫入 Unity Catalog 資料表的管道
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — 系統資料表中可見的 Job 執行資料
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — 生成儲存於 Unity Catalog Volumes 的資料
- **[databricks-aibi-dashboards](../databricks-aibi-dashboards/SKILL.md)** — 在 Unity Catalog 資料之上建立儀表板

## 參考資源

- [Unity Catalog 系統資料表](https://docs.databricks.com/administration-guide/system-tables/)
- [稽核日誌參考](https://docs.databricks.com/administration-guide/account-settings/audit-logs.html)
