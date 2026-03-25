# Databricks Apps 授權

Databricks Apps 支援兩種互補的授權模型。依應用程式需求選擇其中一種或兩種並用。

**官方文件**：https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth

---

## App 授權（Service Principal）

每個應用程式有專屬的 service principal。Databricks 自動注入認證資訊：

- `DATABRICKS_CLIENT_ID` — OAuth client ID
- `DATABRICKS_CLIENT_SECRET` — OAuth client secret

**您不需要手動讀取這些變數。** SDK 的 `Config()` 會自動偵測：

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()  # 自動從環境偵測 SP 認證資訊
conn = sql.connect(
    server_hostname=cfg.host,
    http_path="/sql/1.0/warehouses/<id>",
    credentials_provider=lambda: cfg.authenticate,
)
```

**適用於**：背景任務、共享資料存取、記錄、外部服務呼叫。

**限制**：所有使用者共用相同權限——無法做到個別使用者的存取控制。

---

## 使用者授權（代理使用者）

允許應用程式以當前使用者的身份執行操作。Databricks 透過 HTTP 標頭將使用者的 access token 轉發給應用程式。

**適用於**：使用者專屬的資料查詢、Unity Catalog 的列／欄篩選、稽核軌跡。

**前提條件**：workspace 管理員須先啟用使用者授權（公開預覽版）。在 UI 中建立或編輯應用程式時新增 scope。

### 各框架取得使用者 Token 的方式

```python
# Streamlit
import streamlit as st
user_token = st.context.headers.get("x-forwarded-access-token")

# Dash / Flask
from flask import request
user_token = request.headers.get("x-forwarded-access-token")

# Gradio
import gradio as gr
def handler(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")

# FastAPI
from fastapi import Request
async def endpoint(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")

# Reflex
user_token = session.http_conn.headers.get("x-forwarded-access-token")
```

### 使用使用者 Token 進行查詢

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()
user_token = get_user_token()  # 依框架使用上方對應的方式取得

conn = sql.connect(
    server_hostname=cfg.host,
    http_path="/sql/1.0/warehouses/<id>",
    access_token=user_token,  # 使用者的 token，不是 SP 認證資訊
)
```

---

## 同時使用兩種模型

共享操作使用 app 授權，使用者專屬資料使用使用者授權：

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()

def get_app_connection(warehouse_http_path: str):
    """App 授權——共享資料、記錄、背景任務。"""
    return sql.connect(
        server_hostname=cfg.host,
        http_path=warehouse_http_path,
        credentials_provider=lambda: cfg.authenticate,
    )

def get_user_connection(warehouse_http_path: str, user_token: str):
    """使用者授權——遵守 Unity Catalog 的列／欄篩選。"""
    return sql.connect(
        server_hostname=cfg.host,
        http_path=warehouse_http_path,
        access_token=user_token,
    )
```

---

## OAuth Scope

新增使用者授權時，只選擇應用程式所需的 scope：

| Scope | 授予存取 |
|-------|---------|
| `sql` | SQL Warehouse 查詢 |
| `files.files` | 檔案與目錄 |
| `dashboards.genie` | Genie space |
| `iam.access-control:read` | 存取控制（預設） |
| `iam.current-user:read` | 當前使用者身份（預設） |

**最佳實踐**：只申請最少必要的 scope。即使使用者擁有更廣泛的權限，Databricks 也會封鎖未在已核准 scope 範圍內的存取。

---

## 何時使用哪種模型

| 情境 | 模型 |
|------|------|
| 所有使用者看到相同資料 | 僅 App 授權 |
| 使用者專屬的列／欄篩選 | 使用者授權 |
| 背景作業、記錄 | App 授權 |
| 每位使用者的稽核軌跡 | 使用者授權 |
| 混合共享與個人資料 | 兩者皆用 |

---

## 最佳實踐

- 絕不記錄、列印或將 token 寫入檔案
- 授予 service principal 資源所需的最少必要權限
- `CAN MANAGE` 僅授予受信任的開發人員；`CAN USE` 授予應用程式使用者
- 正式部署前強制執行 app 程式碼的同儕審查
- Cookbook 授權範例：[Streamlit](https://apps-cookbook.dev/docs/streamlit/authentication/users_get_current) · [Dash](https://apps-cookbook.dev/docs/dash/authentication/users_get_current) · [Reflex](https://apps-cookbook.dev/docs/reflex/authentication/users_get_current)
