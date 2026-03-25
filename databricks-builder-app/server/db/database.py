"""非同步資料庫連線與 session 管理。

透過 Lakebase 使用 PostgreSQL，搭配非同步 SQLAlchemy 與 psycopg3 driver。

實作自動 OAuth token 更新機制用於 Databricks Apps 部署：
- Token 每 50 分鐘更新一次（在 1 小時過期前）
- SQLAlchemy 的 do_connect event 注入最新 tokens 到連線中
- 本地開發環境回退使用靜態 LAKEBASE_PG_URL

註：使用 psycopg3 (postgresql+psycopg) driver，支援 hostaddr
參數用於 macOS 的 DNS 解析方案。
"""

import asyncio
import logging
import os
import socket
import subprocess
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

logger = logging.getLogger(__name__)

# 全域 engine 與 session factory
_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None

# Token 更新狀態
_current_token: Optional[str] = None
_token_refresh_task: Optional[asyncio.Task] = None
_lakebase_instance_name: Optional[str] = None

# Token 更新間隔（50 分鐘 - tokens 在 1 小時後過期）
TOKEN_REFRESH_INTERVAL_SECONDS = 50 * 60

# 快取解析的 hostaddr 用於 DNS 方案
_resolved_hostaddr: Optional[str] = None


def _resolve_hostname(hostname: str) -> Optional[str]:
    """使用系統 DNS 工具將 hostname 解析為 IP 位址。

    Python 的 socket.getaddrinfo() 在 macOS 上對長 hostname（如
    Lakebase instance hostnames）會失敗。此函式使用 'dig' 命令作為
    後備方案來解析 hostname。

    Args:
        hostname: 要解析的 hostname

    Returns:
        IP 位址字串，若解析失敗則回傳 None
    """
    # 先嘗試 Python 原生解析
    try:
        result = socket.getaddrinfo(hostname, 5432)
        if result:
            return result[0][4][0]
    except socket.gaierror:
        pass

    # 回退到 dig 命令（macOS/Linux 可用）
    try:
        result = subprocess.run(
            ["dig", "+short", hostname, "A"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ips = [line for line in result.stdout.strip().split("\n") if line and line[0].isdigit()]
        if ips:
            logger.info(f"Resolved {hostname} -> {ips[0]} via dig (Python DNS failed)")
            return ips[0]
    except Exception as e:
        logger.warning(f"dig resolution failed for {hostname}: {e}")

    return None


def _has_oauth_credentials() -> bool:
    """檢查環境中是否已設定 OAuth credentials (SP)。"""
    import os
    return bool(os.environ.get('DATABRICKS_CLIENT_ID') and os.environ.get('DATABRICKS_CLIENT_SECRET'))


def _get_workspace_client():
    """取得用於產生 token 的 Databricks WorkspaceClient。

    在 Databricks Apps 中，明確使用 OAuth M2M 以避免與其他認證方法衝突。
    若非在 Databricks 環境中執行則回傳 None。
    """
    try:
        import os
        from databricks.sdk import WorkspaceClient
        from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION

        product_kwargs = dict(product=PRODUCT_NAME, product_version=PRODUCT_VERSION)
        if _has_oauth_credentials():
            # 明確設定 OAuth M2M 以避免認證衝突
            return WorkspaceClient(
                host=os.environ.get('DATABRICKS_HOST', ''),
                client_id=os.environ.get('DATABRICKS_CLIENT_ID', ''),
                client_secret=os.environ.get('DATABRICKS_CLIENT_SECRET', ''),
                auth_type='oauth-m2m',
                **product_kwargs,
            )
        # 開發模式 - 使用預設 SDK 認證
        return WorkspaceClient(**product_kwargs)
    except Exception as e:
        logger.debug(f"Could not create WorkspaceClient: {e}")
        return None


def _generate_lakebase_token(instance_name: str) -> Optional[str]:
    """為 Lakebase 連線產生新的 OAuth token。

    支援 autoscale (LAKEBASE_ENDPOINT) 與 provisioned (instance_name) 兩種模式。

    Args:
        instance_name: Lakebase instance name (provisioned) 或 endpoint name (autoscale)

    Returns:
        OAuth token 字串，若產生失敗則回傳 None
    """
    client = _get_workspace_client()
    if not client:
        return None

    try:
        endpoint_name = os.environ.get("LAKEBASE_ENDPOINT")
        if endpoint_name:
            # Autoscale: 使用 client.postgres 搭配 endpoint resource name
            cred = client.postgres.generate_database_credential(endpoint=endpoint_name)
        else:
            # Provisioned: 使用 client.database 搭配 instance_names
            cred = client.database.generate_database_credential(
                request_id=str(uuid.uuid4()),
                instance_names=[instance_name],
            )
        logger.info(f"Generated new Lakebase token for instance: {instance_name}")
        return cred.token
    except Exception as e:
        logger.error(f"Failed to generate Lakebase token: {e}")
        return None


async def _token_refresh_loop():
    """背景任務，每 50 分鐘更新 Lakebase OAuth token。"""
    global _current_token, _lakebase_instance_name

    while True:
        try:
            await asyncio.sleep(TOKEN_REFRESH_INTERVAL_SECONDS)

            if _lakebase_instance_name:
                new_token = await asyncio.to_thread(
                    _generate_lakebase_token, _lakebase_instance_name
                )
                if new_token:
                    _current_token = new_token
                    logger.info("Lakebase token refreshed successfully")
                else:
                    logger.warning("Failed to refresh Lakebase token")
        except asyncio.CancelledError:
            logger.info("Token refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in token refresh loop: {e}")
            # 繼續迴圈，將於下一間隔重試


async def start_token_refresh():
    """啟動背景 token 更新任務。"""
    global _token_refresh_task

    if _token_refresh_task is not None:
        logger.warning("Token refresh task already running")
        return

    _token_refresh_task = asyncio.create_task(_token_refresh_loop())
    logger.info("Started Lakebase token refresh background task")


async def stop_token_refresh():
    """停止背景 token 更新任務。"""
    global _token_refresh_task

    if _token_refresh_task is not None:
        _token_refresh_task.cancel()
        try:
            await _token_refresh_task
        except asyncio.CancelledError:
            pass
        _token_refresh_task = None
        logger.info("Stopped Lakebase token refresh background task")


def get_database_url() -> Optional[str]:
    """從環境變數取得資料庫 URL。

    必要時將標準 PostgreSQL URL 轉換為 psycopg3 非同步格式。

    Returns:
        資料庫 URL 字串，若未設定則回傳 None
    """
    url = os.environ.get("LAKEBASE_PG_URL")
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _prepare_async_url(url: str) -> tuple[str, dict]:
    """為 psycopg3 非同步 driver 準備 URL。

    擷取 hostname 用於 DNS 解析方案並準備 connect_args。

    Args:
        url: 資料庫 URL（可能包含 sslmode 參數）

    Returns:
        Tuple (cleaned_url, connect_args)
    """
    global _resolved_hostaddr

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

    parsed = urlparse(url)
    connect_args = {}

    # 嘗試解析 hostname 用於 DNS 方案
    if parsed.hostname:
        hostaddr = _resolve_hostname(parsed.hostname)
        if hostaddr:
            connect_args["hostaddr"] = hostaddr
            _resolved_hostaddr = hostaddr
            logger.info(f"Static URL: resolved {parsed.hostname} -> {hostaddr}")

    return url, connect_args


def _get_current_user_email() -> Optional[str]:
    """從 Databricks SDK 取得目前使用者的 email。"""
    client = _get_workspace_client()
    if client:
        try:
            me = client.current_user.me()
            return me.user_name
        except Exception as e:
            logger.debug(f"Could not get current user: {e}")
    return None


def _build_lakebase_url(
    instance_name: str,
    database_name: str,
    username: Optional[str] = None,
    host: Optional[str] = None,
    port: int = 5432,
) -> str:
    """建構 Lakebase 連線 URL（不含密碼 - 透過 do_connect 注入）。

    Args:
        instance_name: Lakebase instance name (provisioned) 或 endpoint resource name (autoscale)
        database_name: 要連線的資料庫名稱
        username: 資料庫使用者名稱（預設為目前使用者的 email）
        host: 資料庫主機（預設為 instance endpoint）
        port: 資料庫埠（預設 5432）

    Returns:
        PostgreSQL 連線 URL
    """
    # username 預設為目前使用者的 email
    if not username:
        username = os.environ.get("LAKEBASE_USERNAME")
    if not username:
        username = _get_current_user_email()
    if not username:
        username = instance_name  # 後備方案

    # URL-encode username（emails 包含 @）
    from urllib.parse import quote
    encoded_username = quote(username, safe="")

    # Host 預設為 Lakebase instance endpoint
    if not host:
        host = os.environ.get("LAKEBASE_HOST")
    if not host:
        # Lakebase endpoints 遵循此模式
        host = f"{instance_name}.database.us-east-1.cloud.databricks.com"

    # URL 格式：postgresql+asyncpg://username@host:port/database
    # 密碼透過 do_connect event 注入
    return f"postgresql+asyncpg://{encoded_username}@{host}:{port}/{database_name}"


def init_database(database_url: Optional[str] = None) -> AsyncEngine:
    """初始化非同步資料庫連線。

    支援兩種模式：
    1. 靜態 URL 模式（本地開發）：使用 LAKEBASE_PG_URL 含嵌入密碼
    2. 動態 token 模式（正式環境）：使用 Databricks SDK 取得 OAuth tokens

    Args:
        database_url: 可選資料庫 URL。若未提供，從環境變數讀取

    Returns:
        SQLAlchemy AsyncEngine 實例

    Raises:
        ValueError: 若無可用資料庫設定
    """
    global _engine, _async_session_maker, _current_token, _lakebase_instance_name

    # 先檢查靜態 URL（向後相容 / 本地開發）
    url = database_url or get_database_url()

    if url:
        # 靜態 URL 模式 - 直接使用
        logger.info("Using static LAKEBASE_PG_URL for database connection")
        url, connect_args = _prepare_async_url(url)
    else:
        # 動態 token 模式 - 從組件建構 URL
        endpoint_name = os.environ.get("LAKEBASE_ENDPOINT")
        instance_name = os.environ.get("LAKEBASE_INSTANCE_NAME")
        database_name = os.environ.get("LAKEBASE_DATABASE_NAME")

        if not (endpoint_name or instance_name) or not database_name:
            raise ValueError(
                "No database configuration found. Set either:\n"
                "  - LAKEBASE_PG_URL (static URL with password), or\n"
                "  - LAKEBASE_ENDPOINT and LAKEBASE_DATABASE_NAME (autoscale, dynamic OAuth), or\n"
                "  - LAKEBASE_INSTANCE_NAME and LAKEBASE_DATABASE_NAME (provisioned, dynamic OAuth)"
            )

        client = _get_workspace_client()
        if not client:
            raise ValueError("Could not create Databricks WorkspaceClient")

        if endpoint_name:
            # Autoscale 模式：從 endpoint resource 取得 host，token 透過 client.postgres
            _lakebase_instance_name = endpoint_name
            endpoint = client.postgres.get_endpoint(name=endpoint_name)
            host = endpoint.status.hosts.host
            logger.info(f"Using autoscale Lakebase endpoint: {endpoint_name} ({host})")
        else:
            # Provisioned 模式：從 instance 取得 host，token 透過 client.database
            _lakebase_instance_name = instance_name
            instance = client.database.get_database_instance(name=instance_name)
            host = instance.read_write_dns
            logger.info(f"Using provisioned Lakebase instance: {instance_name} ({host})")

        # 產生初始 token
        _current_token = _generate_lakebase_token(_lakebase_instance_name)
        if not _current_token:
            raise ValueError(
                f"Failed to generate initial Lakebase token for: {_lakebase_instance_name}"
            )

        # 取得 username（在 Databricks Apps 使用 service principal 時優先採用明確設定的環境變數）
        username = os.environ.get("LAKEBASE_USERNAME") or _get_current_user_email() or _lakebase_instance_name

        # 解析 hostname 以處理 DNS 問題（macOS 的 Python 在長 hostname 上可能有 DNS 問題）
        global _resolved_hostaddr
        _resolved_hostaddr = _resolve_hostname(host)
        if _resolved_hostaddr:
            logger.info(f"Resolved {host} -> {_resolved_hostaddr}")

        # 使用 URL.create() 建構 URL，搭配 psycopg3 driver（支援 hostaddr）
        url = URL.create(
            drivername="postgresql+psycopg",  # psycopg3 非同步 driver
            username=username,
            password="",  # 將由 do_connect event handler 設定
            host=host,  # 用於 TLS handshake 的 SNI
            port=int(os.environ.get("DATABRICKS_DATABASE_PORT", "5432")),
            database=database_name,
        )

        # psycopg3 的連線參數搭配 DNS 方案
        connect_args = {
            "sslmode": "require",
            "options": f"-c search_path={os.environ.get('LAKEBASE_SCHEMA_NAME', 'builder_app')},public",
        }
        # 若需要 DNS 解析則加入 hostaddr（繞過 Python 的 getaddrinfo）
        if _resolved_hostaddr:
            connect_args["hostaddr"] = _resolved_hostaddr

    _engine = create_async_engine(
        url,
        pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=int(os.environ.get("DB_POOL_RECYCLE_INTERVAL", "3600")),
        pool_timeout=int(os.environ.get("DB_POOL_TIMEOUT", "10")),
        echo=False,
        connect_args=connect_args,
    )

    # 註冊 do_connect event 以注入最新 tokens
    if _lakebase_instance_name:
        @event.listens_for(_engine.sync_engine, "do_connect")
        def provide_token(dialect, conn_rec, cargs, cparams):
            """將目前 OAuth token 注入到連線參數中。"""
            if _current_token:
                cparams["password"] = _current_token

    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    return _engine


def get_engine() -> AsyncEngine:
    """取得資料庫 engine，必要時初始化。"""
    global _engine
    if _engine is None:
        init_database()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """取得非同步 session factory，必要時初始化。"""
    global _async_session_maker
    if _async_session_maker is None:
        init_database()
    return _async_session_maker


async def get_session() -> AsyncSession:
    """建立新的非同步資料庫 session。"""
    factory = get_session_factory()
    return factory()


# scale-to-zero 喚醒的重試設定（autoscale Lakebase）
_SESSION_MAX_RETRIES = int(os.environ.get("DB_SESSION_MAX_RETRIES", "3"))
_SESSION_RETRY_BASE_DELAY = float(os.environ.get("DB_SESSION_RETRY_DELAY", "1.0"))


def _is_connection_error(exc: Exception) -> bool:
    """檢查例外是否為值得重試的暫時性連線錯誤。"""
    from sqlalchemy.exc import OperationalError, InterfaceError

    if not isinstance(exc, (OperationalError, InterfaceError, OSError)):
        return False

    msg = str(exc).lower()
    transient_patterns = [
        "connection refused",
        "connection reset",
        "connection timed out",
        "could not connect",
        "connection failed",
        "server closed the connection",
        "ssl connection has been closed",
        "broken pipe",
        "network is unreachable",
        "password authentication failed",  # 可能在 compute 喚醒期間發生
    ]
    return any(p in msg for p in transient_patterns)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """提供圍繞一系列操作的交易範圍。

    遇到暫時性連線錯誤（例如 autoscale compute 從閒置喚醒）時
    會以指數退避重試，然後才傳播失敗。

    Yields:
        SQLAlchemy AsyncSession 實例

    Example:
        async with session_scope() as session:
            result = await session.execute(select(Model))
    """
    last_exc: Optional[Exception] = None

    for attempt in range(_SESSION_MAX_RETRIES + 1):
        session = await get_session()
        try:
            yield session
            await session.commit()
            return
        except Exception as exc:
            await session.rollback()
            if attempt < _SESSION_MAX_RETRIES and _is_connection_error(exc):
                delay = _SESSION_RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Database connection error (attempt {attempt + 1}/{_SESSION_MAX_RETRIES + 1}), "
                    f"retrying in {delay:.1f}s: {exc}"
                )
                last_exc = exc
                await asyncio.sleep(delay)
                continue
            raise
        finally:
            await session.close()

    if last_exc:
        raise last_exc


async def create_tables():
    """非同步建立所有資料庫表格。

    正式環境請改用 Alembic migrations。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def is_postgres_configured() -> bool:
    """檢查 PostgreSQL 是否已設定（靜態 URL 或動態 OAuth）。"""
    return bool(
        os.environ.get("LAKEBASE_PG_URL")
        or (
            os.environ.get("LAKEBASE_INSTANCE_NAME")
            and os.environ.get("LAKEBASE_DATABASE_NAME")
        )
        or (
            os.environ.get("LAKEBASE_ENDPOINT")
            and os.environ.get("LAKEBASE_DATABASE_NAME")
        )
    )


def is_dynamic_token_mode() -> bool:
    """檢查是否使用動態 OAuth token 模式（相對於靜態 URL）。"""
    return bool(
        not os.environ.get("LAKEBASE_PG_URL")
        and os.environ.get("LAKEBASE_DATABASE_NAME")
        and (
            os.environ.get("LAKEBASE_INSTANCE_NAME")
            or os.environ.get("LAKEBASE_ENDPOINT")
        )
    )


def get_lakebase_project_id() -> Optional[str]:
    """從環境變數取得 Lakebase project ID。"""
    return os.environ.get("LAKEBASE_PROJECT_ID") or None


async def test_database_connection() -> Optional[str]:
    """測試資料庫連線，若失敗則回傳錯誤訊息。

    Returns:
        連線成功則回傳 None，失敗則回傳錯誤訊息字串
    """
    if not is_postgres_configured():
        return None

    try:
        from sqlalchemy import text

        if _engine is None:
            init_database()

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        return None
    except Exception as e:
        return str(e)


def run_migrations() -> None:
    """程式化執行 Alembic migrations。

    可安全執行多次 - Alembic 會追蹤已套用的 migrations。
    """
    if not is_postgres_configured():
        return

    import logging
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    logger = logging.getLogger(__name__)
    logger.info("Running database migrations...")

    try:
        # 找到 app root 目錄（alembic.ini 所在位置）
        # 此檔案位於 server/db/database.py，所以 app root 在往上 2 層
        app_root = Path(__file__).parent.parent.parent

        # 檢查多個可能的 alembic.ini 位置
        possible_paths = [
            app_root / "alembic.ini",  # 標準位置
            Path("/app/python/source_code") / "alembic.ini",  # Databricks Apps
            Path(".") / "alembic.ini",  # 目前目錄後備方案
        ]

        alembic_ini_path = None
        for path in possible_paths:
            if path.exists():
                alembic_ini_path = path
                break

        if not alembic_ini_path:
            logger.warning(
                f"alembic.ini not found in any of: {[str(p) for p in possible_paths]}. "
                "Skipping migrations."
            )
            return

        logger.info(f"Using alembic config from: {alembic_ini_path}")

        alembic_cfg = Config(str(alembic_ini_path))

        # 設定 script_location 為絕對路徑以避免工作目錄問題
        alembic_dir = alembic_ini_path.parent / "alembic"
        if alembic_dir.exists():
            alembic_cfg.set_main_option("script_location", str(alembic_dir))

        # 透過 config 傳遞 schema name 給 Alembic env.py
        schema_name = os.environ.get("LAKEBASE_SCHEMA_NAME", "builder_app")
        alembic_cfg.set_main_option("lakebase_schema_name", schema_name)

        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
