# 支援的框架

以下所有框架均已**預裝**於 Databricks Apps runtime。Claude 已知道如何使用它們——本指南僅涵蓋 **Databricks 專屬**的模式。如需完整範例與食譜，請參閱 **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**。

---

## Dash

**最適用於**：生產級儀表板、BI 工具、複雜的互動視覺化。

**重要**：版面與樣式務必使用 `dash-bootstrap-components`。

```python
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="My Dashboard",
)
```

| 細節 | 值 |
|------|-----|
| 預裝版本 | 2.18.1 |
| app.yaml 指令 | `["python", "app.py"]` |
| 預設 port | 8050——在程式碼中覆寫：`app.run(port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))` |
| Auth 標頭 | `request.headers.get('x-forwarded-access-token')`（底層使用 Flask） |

**Databricks 使用提示**：
- 使用 `dbc.themes.BOOTSTRAP` 與 `dbc.icons.FONT_AWESOME` 保持一致的樣式
- `dbc.Badge` 使用 Bootstrap badge 顏色名稱（`"success"`、`"danger"`），而非十六進位色碼
- 耗費資源的 callback 使用 `prevent_initial_call=True`
- 使用 `dcc.Store` 進行客戶端快取

**Cookbook**：[apps-cookbook.dev/docs/category/dash](https://apps-cookbook.dev/docs/category/dash) — 資料表、volumes、AI/ML、工作流程、儀表板、運算、授權、外部服務。

---

## Streamlit

**最適用於**：快速原型、資料科學應用、內部工具、notebook 轉 app 的工作流程。

**重要**：資料庫連線務必使用 `@st.cache_resource`。

```python
import streamlit as st
from databricks.sdk.core import Config
from databricks import sql

st.set_page_config(page_title="My App", layout="wide")  # 必須是第一個指令！

@st.cache_resource(ttl=300)
def get_connection():
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
```

| 細節 | 值 |
|------|-----|
| 預裝版本 | 1.38.0 |
| app.yaml 指令 | `["streamlit", "run", "app.py"]` |
| Auth 標頭 | `st.context.headers.get('x-forwarded-access-token')` |

**Databricks 使用提示**：
- `st.set_page_config()` 必須是**第一個** Streamlit 指令
- 連線／模型使用 `@st.cache_resource`；查詢結果使用 `@st.cache_data(ttl=...)`
- 使用 `st.form()` 批次輸入，防止每次按鍵都觸發重新執行
- 使用 `st.column_config` 格式化 DataFrame（貨幣、日期）

**Cookbook**：[apps-cookbook.dev/docs/category/streamlit](https://apps-cookbook.dev/docs/category/streamlit) — 資料表、volumes、AI/ML、工作流程、視覺化、儀表板、運算、授權、外部服務。

---

## Gradio

**最適用於**：ML 模型示範、對話介面、圖片／音訊／影片處理 UI。

**重要**：使用 `gr.Request` 參數存取 auth 標頭。

```python
import os
import gradio as gr
import requests
from databricks.sdk.core import Config

cfg = Config()

def predict(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")
    # 查詢 model serving endpoint
    headers = {**cfg.authenticate(), "Content-Type": "application/json"}
    resp = requests.post(
        f"https://{cfg.host}/serving-endpoints/my-model/invocations",
        headers=headers,
        json={"inputs": [{"prompt": message}]},
    )
    return resp.json()["predictions"][0]

demo = gr.Interface(fn=predict, inputs="text", outputs="text")
port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
demo.launch(server_name="0.0.0.0", server_port=port)
```

| 細節 | 值 |
|------|-----|
| 預裝版本 | 4.44.0 |
| app.yaml 指令 | `["python", "app.py"]` |
| 預設 port | 7860——在程式碼中覆寫：`server_port=int(os.environ.get("DATABRICKS_APP_PORT", 8000))` |
| Auth 標頭 | 透過 `gr.Request` 取得 `request.headers.get('x-forwarded-access-token')` |

**Databricks 使用提示**：
- 天然適合整合 model serving endpoint
- 對話式 AI 示範使用 `gr.ChatInterface`
- 複雜多元件版面使用 `gr.Blocks`

**官方文件**：[gradio.app/docs](https://www.gradio.app/docs)

---

## Flask

**最適用於**：自訂 REST API、輕量網頁應用、webhook 接收器。

**重要**：以 Gunicorn 部署——絕不在正式環境使用 Flask 的開發伺服器。

```python
from flask import Flask, request, jsonify
from databricks.sdk.core import Config
from databricks import sql

app = Flask(__name__)
cfg = Config()

@app.route("/api/data")
def get_data():
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        credentials_provider=lambda: cfg.authenticate,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return jsonify(cursor.fetchall())
```

| 細節 | 值 |
|------|-----|
| 預裝版本 | 3.0.3 |
| app.yaml 指令 | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| Auth 標頭 | `request.headers.get('x-forwarded-access-token')` |

**Databricks 使用提示**：
- 使用連線池（Flask 不像 Streamlit 會快取連線）
- Gunicorn workers（`-w 4`）處理並行請求
- 使用 `request.headers` 取得使用者授權 token

---

## FastAPI

**最適用於**：現代非同步 API、自動產生 OpenAPI/Swagger 文件、高效能後端。

**重要**：以 uvicorn 部署。

```python
from fastapi import FastAPI, Request
from databricks.sdk.core import Config
from databricks import sql

app = FastAPI(title="My API")
cfg = Config()

@app.get("/api/data")
async def get_data(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path="/sql/1.0/warehouses/<id>",
        access_token=user_token,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return cursor.fetchall()
```

| 細節 | 值 |
|------|-----|
| 預裝版本 | 0.115.0 |
| app.yaml 指令 | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| Auth 標頭 | 透過 `Request` 取得 `request.headers.get('x-forwarded-access-token')` |

**Databricks 使用提示**：
- 在 `/docs`（Swagger）和 `/redoc` 自動產生 OpenAPI 文件
- Databricks SQL connector 為同步——非同步 endpoint 請使用 `asyncio.to_thread()`
- 適合作為 APX（FastAPI + React）應用程式的 API 後端

**Cookbook**：[apps-cookbook.dev/docs/category/fastapi](https://apps-cookbook.dev/docs/category/fastapi) — 入門、endpoint 範例。

---

## Reflex

**最適用於**：具有響應式 UI 的全端 Python 應用程式，無需 JavaScript。

```python
import reflex as rx
from databricks.sdk.core import Config

cfg = Config()

class State(rx.State):
    data: list[dict] = []

    def load_data(self):
        from databricks import sql
        conn = sql.connect(
            server_hostname=cfg.host,
            http_path="/sql/1.0/warehouses/<id>",
            credentials_provider=lambda: cfg.authenticate,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
            self.data = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
```

| 細節 | 值 |
|------|-----|
| app.yaml 指令 | `["reflex", "run", "--env", "prod"]` |
| Auth 標頭 | `session.http_conn.headers.get('x-forwarded-access-token')` |

**Cookbook**：[apps-cookbook.dev/docs/category/reflex](https://apps-cookbook.dev/docs/category/reflex) — 資料表、volumes、AI/ML、工作流程、儀表板、運算、授權、外部服務。

---

## 所有框架通用事項

- 所有框架均已**預裝**——不需要加入 `requirements.txt`
- 只需在 `requirements.txt` 中加入應用程式額外需要的套件
- SDK `Config()` 自動從注入的環境變數偵測認證資訊
- 應用程式必須綁定 `DATABRICKS_APP_PORT` 環境變數（預設 8000）。Streamlit 由 runtime 自動設定；其他框架請在程式碼中讀取該環境變數，或在 `app.yaml` 指令中直接寫 8000。**絕不使用 8080**
- 各框架的部署指令請見 [4-deployment.md](4-deployment.md)
- 授權整合請見 [1-authorization.md](1-authorization.md)
