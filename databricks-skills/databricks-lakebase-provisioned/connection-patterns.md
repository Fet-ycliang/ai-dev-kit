# Lakebase 連線模式

## 概觀

本文涵蓋 Lakebase Provisioned 的不同連線模式，從簡易腳本到帶有 token 重新整理的正式環境應用程式。

## 連線方式

### 1. 直接使用 psycopg 連線（簡易腳本）

適用於一次性的腳本或 Notebook：

```python
import psycopg
from databricks.sdk import WorkspaceClient
import uuid

def get_connection(instance_name: str, database_name: str = "postgres"):
    """取得具最新 OAuth token 的資料庫連線。"""
    w = WorkspaceClient()
    
    # 取得實例詳細資料
    instance = w.database.get_database_instance(name=instance_name)
    
    # 產生 OAuth token（有效期限 1 小時）
    cred = w.database.generate_database_credential(
        request_id=str(uuid.uuid4()),
        instance_names=[instance_name]
    )
    
    # 建立連線字串
    conn_string = (
        f"host={instance.read_write_dns} "
        f"dbname={database_name} "
        f"user={w.current_user.me().user_name} "
        f"password={cred.token} "
        f"sslmode=require"
    )
    
    return psycopg.connect(conn_string)

# 使用方式
with get_connection("my-instance") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW()")
        print(cur.fetchone())
```

### 2. 具 token 重新整理的連線池（正式環境）

適用於需要連線池的長時間執行應用程式：

```python
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from databricks.sdk import WorkspaceClient

class LakebaseConnectionManager:
    """管理具自動 token 重新整理的 Lakebase 連線。"""
    
    def __init__(
        self,
        instance_name: str,
        database_name: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        token_refresh_seconds: int = 3000  # 50 minutes
    ):
        self.instance_name = instance_name
        self.database_name = database_name
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.token_refresh_seconds = token_refresh_seconds
        
        self._current_token: Optional[str] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._engine = None
        self._session_maker = None
    
    def _generate_token(self) -> str:
        """產生最新的 OAuth token。"""
        w = WorkspaceClient()
        cred = w.database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=[self.instance_name]
        )
        return cred.token
    
    async def _refresh_loop(self):
        """週期性在背景重新整理 token。"""
        while True:
            await asyncio.sleep(self.token_refresh_seconds)
            try:
                self._current_token = await asyncio.to_thread(self._generate_token)
            except Exception as e:
                print(f"Token refresh failed: {e}")
    
    def initialize(self):
        """初始化資料庫引擎並啟動 token 重新整理。"""
        w = WorkspaceClient()
        
        # 取得實例資訊
        instance = w.database.get_database_instance(name=self.instance_name)
        username = w.current_user.me().user_name
        
        # 產生初始 token
        self._current_token = self._generate_token()
        
        # 建立引擎（密碼透過事件注入）
        url = (
            f"postgresql+psycopg://{username}@"
            f"{instance.read_write_dns}:5432/{self.database_name}"
        )
        
        self._engine = create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=3600,
            connect_args={"sslmode": "require"}
        )
        
        # 在連線時注入 token
        @event.listens_for(self._engine.sync_engine, "do_connect")
        def inject_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = self._current_token
        
        self._session_maker = async_sessionmaker(
            self._engine, 
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    def start_refresh(self):
        """啟動背景 token 重新整理工作。"""
        if not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._refresh_loop())
    
    async def stop_refresh(self):
        """停止 token 重新整理工作。"""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """取得資料庫工作階段。"""
        async with self._session_maker() as session:
            yield session
    
    async def close(self):
        """關閉所有連線。"""
        await self.stop_refresh()
        if self._engine:
            await self._engine.dispose()

# 在 FastAPI 中的用法
from fastapi import FastAPI

app = FastAPI()
db_manager = LakebaseConnectionManager("my-instance", "my_database")

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

於本機開發時可使用靜態連線 URL：

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine

# 設定包含完整連線 URL 的環境變數
# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database

def get_database_url() -> str:
    """從環境變數取得資料庫 URL。"""
    url = os.environ.get("LAKEBASE_PG_URL")
    if url and url.startswith("postgresql://"):
        # 轉換為 psycopg3 非同步驅動
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_async_engine(
    get_database_url(),
    pool_size=5,
    connect_args={"sslmode": "require"}
)
```

### 4. DNS 解析替代方案（macOS）

Python 的 `socket.getaddrinfo()` 在 macOS 上遇到長主機名稱會失敗，可改用 `dig` 當作備援：

```python
import subprocess
import socket

def resolve_hostname(hostname: str) -> str:
    """使用 dig 指令解析主機名稱（macOS 替代方案）。"""
    try:
        # 先嘗試 Python 內建解析
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        pass
    
    # 退回使用 dig 指令
    try:
        result = subprocess.run(
            ["dig", "+short", hostname],
            capture_output=True,
            text=True,
            timeout=5
        )
        ips = result.stdout.strip().split('\n')
        for ip in ips:
            if ip and not ip.startswith(';'):
                return ip
    except Exception:
        pass
    
    raise RuntimeError(f"Could not resolve hostname: {hostname}")

# 搭配 psycopg 使用
conn_params = {
    "host": hostname,  # For TLS SNI
    "hostaddr": resolve_hostname(hostname),  # 實際 IP
    "dbname": database_name,
    "user": username,
    "password": token,
    "sslmode": "require"
}
conn = psycopg.connect(**conn_params)
```

## 環境變數

| 變數 | 說明 | 是否必填 |
|------|------|----------|
| `LAKEBASE_PG_URL` | 靜態 PostgreSQL URL（本機開發） | 與 instance/database 擇一 |
| `LAKEBASE_INSTANCE_NAME` | Lakebase 實例名稱 | 與 DATABASE_NAME 搭配 |
| `LAKEBASE_DATABASE_NAME` | 資料庫名稱 | 與 INSTANCE_NAME 搭配 |
| `LAKEBASE_USERNAME` | 覆寫使用者名稱 | 否 |
| `LAKEBASE_HOST` | 覆寫主機名稱 | 否 |
| `DB_POOL_SIZE` | 連線池大小 | 否（預設 5） |
| `DB_MAX_OVERFLOW` | 連線池最大溢出 | 否（預設 10） |
| `DB_POOL_RECYCLE_INTERVAL` | 連線池回收秒數 | 否（預設 3600） |

## 最佳實務

1. **務必使用 SSL**：在所有連線中設定 `sslmode=require`
2. **實作 token 重新整理**：token 1 小時後過期，於 50 分鐘時重新整理
3. **使用連線池**：避免每個請求都新建連線
4. **處理 macOS DNS 問題**：必要時使用 `hostaddr` 替代方案
5. **妥善關閉連線**：使用 context manager 或明確清理
6. **記錄 token 重新整理事件**：有助偵錯驗證問題
