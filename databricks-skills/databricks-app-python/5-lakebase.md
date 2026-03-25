# Lakebase（PostgreSQL）連線

Lakebase 透過受管理的 PostgreSQL 介面，為 Databricks Apps 提供低延遲的交易性儲存。

**官方文件**：https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase

---

## 何時使用 Lakebase

| 使用情境 | 建議後端 |
|---------|---------|
| 對 Delta table 進行分析查詢 | SQL Warehouse |
| 低延遲交易 CRUD | **Lakebase** |
| 應用程式專屬的 metadata／設定 | **Lakebase** |
| 使用者 session 資料 | **Lakebase** |
| 大規模資料探索 | SQL Warehouse |

---

## 設定

1. 在 Databricks UI 中將 Lakebase 新增為應用程式資源（資源類型：**Lakebase database**）
2. Databricks 自動注入 PostgreSQL 連線環境變數：

| 變數 | 說明 |
|------|------|
| `PGHOST` | 資料庫主機名稱 |
| `PGDATABASE` | 資料庫名稱 |
| `PGUSER` | PostgreSQL 角色（每個應用程式個別建立） |
| `PGPASSWORD` | 角色密碼 |
| `PGPORT` | 埠號（通常為 5432） |

3. 在 `app.yaml` 中引用：

```yaml
env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
```

---

## 連線模式

### psycopg2（同步）

```python
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    database=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT", "5432"),
)

with conn.cursor() as cur:
    cur.execute("SELECT * FROM my_table LIMIT 10")
    rows = cur.fetchall()

conn.close()
```

### asyncpg（非同步）

```python
import os
import asyncpg

async def get_data():
    conn = await asyncpg.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=int(os.getenv("PGPORT", "5432")),
    )
    rows = await conn.fetch("SELECT * FROM my_table LIMIT 10")
    await conn.close()
    return rows
```

### SQLAlchemy

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = (
    f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
    f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT', '5432')}"
    f"/{os.getenv('PGDATABASE')}"
)

engine = create_engine(DATABASE_URL)
```

---

## Streamlit 搭配 Lakebase

```python
import streamlit as st
import psycopg2

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
    )
```

---

## 重要：requirements.txt

`psycopg2` 與 `asyncpg` **未預裝**於 Databricks Apps runtime。**必須**將其加入 `requirements.txt`，否則應用程式啟動時會崩潰：

```
psycopg2-binary
```

非同步應用程式：
```
asyncpg
```

**這是 Lakebase 應用程式失敗最常見的原因。**

## 注意事項

- Lakebase 目前為**公開預覽版**
- 每個應用程式獲得專屬的 PostgreSQL 角色，具備 `Can connect and create` 權限
- Lakebase 與 SQL Warehouse 並用效果最佳：Lakebase 處理應用程式狀態，SQL Warehouse 處理分析查詢
