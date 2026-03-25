# Lakebase 自動擴展連線模式

## 概觀

本文件說明 Lakebase 自動擴展的各種連線模式，從簡單腳本到具權杖更新機制的生產應用。

## 認證方式

Lakebase 自動擴展支援兩種認證方式：

| 方法 | 權杖有效時間 | 最佳用途 |
|--------|---------------|----------|
| **OAuth tokens** | 1 小時（需要更新） | 互動式工作階段、與 workspace 整合的應用 |
| **Native Postgres passwords** | 不會過期 | 長時間運作的程序、不支援權杖輪替的工具 |

**兩種方式皆有的連線逾時：**
- **24 小時閒置逾時**：連線 24 小時無活動會被關閉
- **最長 3 天連線壽命**：超過 3 天的連線可能被關閉

請為應用程式設計重試邏輯以處理連線逾時。

## 連線方式

### 1. 直接 psycopg 連線（簡單腳本）

適用於單次腳本或 Notebook：

```python
import psycopg
from databricks.sdk import WorkspaceClient

def get_connection(project_id: str, branch_id: str = "production",
                   endpoint_id: str = None, database_name: str = "databricks_postgres"):
    """取得帶有最新 OAuth 權杖的資料庫連線。"""
    w = WorkspaceClient()

    # 取得 endpoint 詳細資訊以取得 host
    if endpoint_id:
        ep_name = f"projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}"
    else:
        # 列出 endpoints，選擇主要 R/W
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{project_id}/branches/{branch_id}"
        ))
        ep_name = endpoints[0].name

    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    # 產生 OAuth 權杖（有效 1 小時）
    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    # 建立連線字串
    conn_string = (
        f"host={host} "
        f"dbname={database_name} "
        f"user={w.current_user.me().user_name} "
        f"password={cred.token} "
        f"sslmode=require"
    )

    return psycopg.connect(conn_string)

# 使用方式
with get_connection("my-app") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW()")
        print(cur.fetchone())
```

### 2. 具權杖更新的連線池（生產環境）

適用於需要連線池的長時間運作應用：

```python
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from databricks.sdk import WorkspaceClient


class LakebaseAutoscaleConnectionManager:
    """管理 Lakebase 自動擴展連線並自動更新權杖。"""

    def __init__(
        self,
        project_id: str,
        branch_id: str = "production",
        database_name: str = "databricks_postgres",
        pool_size: int = 5,
        max_overflow: int = 10,
        token_refresh_seconds: int = 3000  # 50 分鐘
    ):
        self.project_id = project_id
        self.branch_id = branch_id
        self.database_name = database_name
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.token_refresh_seconds = token_refresh_seconds

        self._current_token: Optional[str] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._engine = None
        self._session_maker = None

    def _generate_token(self) -> str:
        """產生最新的 OAuth 權杖。"""
        w = WorkspaceClient()
        # 取得主要 endpoint 名稱作為權杖作用範圍
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        endpoint_name = endpoints[0].name if endpoints else None
        cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
        return cred.token

    def _get_host(self) -> str:
        """從主要 endpoint 取得連線 host。"""
        w = WorkspaceClient()
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        if not endpoints:
            raise RuntimeError(
                f"projects/{self.project_id}/branches/{self.branch_id} 未找到端點"
            )
        endpoint = w.postgres.get_endpoint(name=endpoints[0].name)
        return endpoint.status.hosts.host

    async def _refresh_loop(self):
        """背景工作定期刷新權杖。"""
        while True:
            await asyncio.sleep(self.token_refresh_seconds)
            try:
                self._current_token = await asyncio.to_thread(self._generate_token)
            except Exception as e:
                print(f"權杖刷新失敗：{e}")

    def initialize(self):
        """初始化資料庫引擎並啟動權杖更新。"""
        w = WorkspaceClient()

        # 取得 host
        host = self._get_host()
        username = w.current_user.me().user_name

        # 產生初始權杖
        self._current_token = self._generate_token()

        # 建立引擎（透過 event 注入密碼）
        url = (
            f"postgresql+psycopg://{username}@"
            f"{host}:5432/{self.database_name}"
        )

        self._engine = create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=3600,
            connect_args={"sslmode": "require"}
        )

        # 連線時注入權杖
        @event.listens_for(self._engine.sync_engine, "do_connect")
        def inject_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = self._current_token

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    def start_refresh(self):
        """啟動背景權杖更新工作。"""
        if not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop_refresh(self):
        """停止權杖更新工作。"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """取得資料庫 session。"""
        async with self._session_maker() as session:
            yield session

    async def close(self):
        """關閉所有連線。"""
        await self.stop_refresh()
        if self._engine:
            await self._engine.dispose()


# FastAPI 使用方式
from fastapi import FastAPI

app = FastAPI()
db_manager = LakebaseAutoscaleConnectionManager("my-app", "production", "my_database")

@app.on_event("startup")
async def startup():
    db_manager.initialize()
    db_manager.start_refresh()

@app.on_event("shutdown")
async def shutdown():
    await db_manager.close()

@app.get("/data")
async def get_data():
    async with db_manager.session() as session:
        result = await session.execute("SELECT * FROM my_table")
        return result.fetchall()
```

### 3. 靜態 URL 模式（本機開發）

本機開發可使用靜態連線 URL：

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine

# 環境變數需包含完整連線 URL
# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database

def get_database_url() -> str:
    """從環境變數取得資料庫 URL。"""
    url = os.environ.get("LAKEBASE_PG_URL")
    if url and url.startswith("postgresql://"):
        # 轉換為 psycopg3 async driver
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_async_engine(
    get_database_url(),
    pool_size=5,
    connect_args={"sslmode": "require"}
)
```

### 4. DNS 解析因應方案（macOS）

Python 的 `socket.getaddrinfo()` 在 macOS 上遇到長主機名稱可能失敗，可使用 `dig` 作為備援：

```python
import subprocess
import socket

def resolve_hostname(hostname: str) -> str:
    """使用 dig 指令解析主機名稱（macOS 因應方案）。"""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        pass

    try:
        result = subprocess.run(
            ["dig", "+short", hostname],
            capture_output=True, text=True, timeout=5
        )
        ips = result.stdout.strip().split('\n')
        for ip in ips:
            if ip and not ip.startswith(';'):
                return ip
    except Exception:
        pass

    raise RuntimeError(f"無法解析主機名稱：{hostname}")

# 搭配 psycopg 使用
conn_params = {
    "host": hostname,       # TLS SNI 使用
    "hostaddr": resolve_hostname(hostname),  # 實際 IP
    "dbname": database_name,
    "user": username,
    "password": token,
    "sslmode": "require"
}
conn = psycopg.connect(**conn_params)
```

## 最佳實務

1. **務必使用 SSL**：所有連線設 `sslmode=require`
2. **實作權杖更新**：權杖 1 小時失效，建議 50 分鐘更新
3. **使用連線池**：避免每個請求建立新連線
4. **處理 macOS DNS 問題**：必要時使用 `hostaddr` 因應方案
5. **正確關閉連線**：使用 context manager 或顯式清理
6. **應對 scale-to-zero 喚醒**：閒置後首次連線可能花 2-5 秒
7. **紀錄權杖更新事件**：有助於除錯認證問題
