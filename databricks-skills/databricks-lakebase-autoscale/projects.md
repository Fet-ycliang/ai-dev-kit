# Lakebase Autoscaling Projects

## 概觀

Project 是 Lakebase Autoscaling 資源的最上層容器，包含 branches、computes、databases 與 roles。每個 project 彼此隔離，並具備自己的 Postgres 版本、compute 預設值與還原視窗設定。

## 專案結構

```
Project
  └── Branches (production, development, staging, etc.)
        ├── Computes (R/W compute, read replicas)
        ├── Roles (Postgres roles)
        └── Databases (Postgres databases)
```

建立 project 時，預設包含：
- `production` 分支（預設分支）
- 主要 read-write compute（8-32 CU，啟用 autoscaling、停用 scale-to-zero）
- `databricks_postgres` 資料庫
- 為建立者 Databricks 身分建立的 Postgres role

## 資源命名

Project 採階層式命名規則：
```
projects/{project_id}
```

**Resource ID 規範：**
- 長度 1-63 個字元
- 只能使用小寫字母、數字與連字號
- 不可以連字號作為開頭或結尾
- 建立後不可變更

## 建立 Project

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Project, ProjectSpec

w = WorkspaceClient()

# 建立專案（長時間執行的操作）
operation = w.postgres.create_project(
    project=Project(
        spec=ProjectSpec(
            display_name="My Application",
            pg_version="17"
        )
    ),
    project_id="my-app"
)

# 等待完成
result = operation.wait()
print(f"Created project: {result.name}")
print(f"Display name: {result.status.display_name}")
print(f"Postgres version: {result.status.pg_version}")
```

### CLI

```bash
databricks postgres create-project \
    --project-id my-app \
    --json '{
        "spec": {
            "display_name": "My Application",
            "pg_version": "17"
        }
    }'
```

## 取得 Project 詳細資訊

### Python SDK

```python
project = w.postgres.get_project(name="projects/my-app")

print(f"Project: {project.name}")
print(f"Display name: {project.status.display_name}")
print(f"Postgres version: {project.status.pg_version}")
```

### CLI

```bash
databricks postgres get-project projects/my-app
```

**注意：** GET 操作不會填入 `spec` 欄位，所有屬性皆回傳於 `status`。

## 列出 Projects

```python
projects = w.postgres.list_projects()

for project in projects:
    print(f"Project: {project.name}")
    print(f"  Display name: {project.status.display_name}")
    print(f"  Postgres version: {project.status.pg_version}")
```

## 更新 Project

更新時需使用 `update_mask` 指定要修改的欄位：

```python
from databricks.sdk.service.postgres import Project, ProjectSpec, FieldMask

# 更新顯示名稱
operation = w.postgres.update_project(
    name="projects/my-app",
    project=Project(
        name="projects/my-app",
        spec=ProjectSpec(
            display_name="My Updated Application"
        )
    ),
    update_mask=FieldMask(field_mask=["spec.display_name"])
)
result = operation.wait()
```

### CLI

```bash
databricks postgres update-project projects/my-app spec.display_name \
    --json '{
        "spec": {
            "display_name": "My Updated Application"
        }
    }'
```

## 刪除 Project

**警告：** 刪除 project 為永久操作，會同時刪除所有 branches、computes、databases、roles 與資料。

刪除前請先清除所有 Unity Catalog catalogs 與 synced tables。

```python
operation = w.postgres.delete_project(name="projects/my-app")
# 這是長時間執行的操作
```

### CLI

```bash
databricks postgres delete-project projects/my-app
```

## Project 設定

### Compute 預設值

新建主要 compute 的預設設定：
- Compute 規模範圍（0.5-112 CU）
- Scale-to-zero 逾時（預設 5 分鐘）

### Instant Restore

設定還原視窗長度（2-35 天），時間越長儲存成本越高。

### Postgres 版本

支援 Postgres 16 與 Postgres 17。

## Project 限制

| 資源 | 上限 |
|----------|-------|
| 同時運作的 computes | 20 |
| 每個 project 的 branches | 500 |
| 每個 branch 的 Postgres roles | 500 |
| 每個 branch 的 Postgres databases | 500 |
| 每個 branch 的邏輯資料量 | 8 TB |
| 每個 workspace 的 projects | 1000 |
| Protected branches | 1 |
| Root branches | 3 |
| 未封存 branches | 10 |
| Snapshots | 10 |
| 最大歷史保留 | 35 天 |
| 最小 scale-to-zero 時間 | 60 秒 |

## 長時間操作（LRO）

所有 create、update、delete 操作都會回傳 long-running operation（LRO）。可於 SDK 中使用 `.wait()` 等待完成：

```python
# 啟動操作
operation = w.postgres.create_project(...)

# 等待完成
result = operation.wait()

# 或手動查詢狀態
op_status = w.postgres.get_operation(name=operation.name)
print(f"Done: {op_status.done}")
```
