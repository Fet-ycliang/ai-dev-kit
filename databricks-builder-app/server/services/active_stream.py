"""非同步 agent 執行的 Active stream 管理器。

處理 Claude agent 的背景執行，包含事件累積
及基於游標的分頁輪詢。

事件會持久化到資料庫以實現 session 獨立性，
允許使用者在離開後重新連接。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# 批次大小用於將事件持久化到資料庫
EVENT_PERSIST_BATCH_SIZE = 10
# 資料庫同步之間的最大時間（秒）
EVENT_PERSIST_INTERVAL = 5.0


@dataclass
class StreamEvent:
    """來自 agent stream 的單一事件。"""

    timestamp: float
    data: dict[str, Any]


@dataclass
class ActiveStream:
    """管理背景 agent 執行與事件累積。

    事件儲存於 append-only 列表中以供基於游標的檢索。
    stream 可被取消，清理會自動進行。
    事件也會持久化到資料庫以實現 session 獨立性。
    """

    execution_id: str
    conversation_id: str
    project_id: str
    user_email: str = ''  # 用於資料庫持久化
    events: list[StreamEvent] = field(default_factory=list)
    is_complete: bool = False
    is_cancelled: bool = False
    error: str | None = None
    task: asyncio.Task | None = None
    persist_task: asyncio.Task | None = None
    created_at: float = field(default_factory=time.time)
    _pending_events: list[dict] = field(default_factory=list)
    _last_persist_time: float = field(default_factory=time.time)
    _persist_index: int = 0  # 追蹤哪些事件已持久化

    def add_event(self, event_data: dict[str, Any]) -> None:
        """新增事件到 stream 並排入佇列等待持久化。"""
        event = StreamEvent(
            timestamp=time.time(),
            data=event_data,
        )
        self.events.append(event)
        # 將事件排入資料庫持久化佇列
        self._pending_events.append({
            'timestamp': event.timestamp,
            **event_data,
        })

    def get_events_since(self, cursor: float = 0.0) -> tuple[list[dict[str, Any]], float]:
        """取得給定游標時間戳之後的所有事件。

        Args:
            cursor: 取得此之後的事件（不含）的時間戳

        Returns:
            Tuple (events 列表, 新游標時間戳)
        """
        new_events = [
            {**e.data, '_cursor': e.timestamp} for e in self.events
            if e.timestamp > cursor
        ]

        # 回傳最後一個事件的時間戳作為新游標
        new_cursor = self.events[-1].timestamp if self.events else cursor
        return new_events, new_cursor

    def mark_complete(self) -> None:
        """標記 stream 為完成。"""
        self.is_complete = True
        self.add_event({'type': 'stream.completed', 'is_error': False})

    def mark_error(self, error: str) -> None:
        """標記 stream 失敗並記錄錯誤。"""
        self.error = error
        self.is_complete = True
        self.add_event({'type': 'error', 'error': error})
        self.add_event({'type': 'stream.completed', 'is_error': True})

    def cancel(self) -> bool:
        """若 stream 仍在執行則取消。

        Returns:
            若取消已啟動則回傳 True，若已完成/取消則回傳 False
        """
        if self.is_complete or self.is_cancelled:
            return False

        self.is_cancelled = True
        if self.task and not self.task.done():
            self.task.cancel()

        self.add_event({'type': 'stream.cancelled'})
        self.add_event({'type': 'stream.completed', 'is_error': False})
        self.is_complete = True
        return True

    def get_pending_events(self) -> list[dict]:
        """取得並清除待持久化的事件。"""
        events = self._pending_events.copy()
        self._pending_events.clear()
        self._last_persist_time = time.time()
        return events

    def should_persist(self) -> bool:
        """檢查是否應該現在持久化事件。"""
        if not self._pending_events:
            return False
        if len(self._pending_events) >= EVENT_PERSIST_BATCH_SIZE:
            return True
        elapsed = time.time() - self._last_persist_time
        if elapsed >= EVENT_PERSIST_INTERVAL:
            return True
        return False


class ActiveStreamManager:
    """管理多個 active streams 並自動清理。"""

    # 超過此時間的 streams 將被清理（5 分鐘）
    CLEANUP_THRESHOLD_SECONDS = 300

    def __init__(self):
        self._streams: dict[str, ActiveStream] = {}
        self._lock = asyncio.Lock()

    async def create_stream(
        self,
        project_id: str,
        conversation_id: str,
        user_email: str = '',
    ) -> ActiveStream:
        """建立新的 active stream。

        Args:
            project_id: Project ID
            conversation_id: Conversation ID
            user_email: 使用者 email，用於資料庫持久化

        Returns:
            新的 ActiveStream 實例
        """
        execution_id = str(uuid.uuid4())

        stream = ActiveStream(
            execution_id=execution_id,
            conversation_id=conversation_id,
            project_id=project_id,
            user_email=user_email,
        )

        async with self._lock:
            self._streams[execution_id] = stream
            await self._cleanup_old_streams()

        # 持久化到資料庫以實現 session 獨立性
        if user_email:
            await self._persist_stream_to_db(stream)

        logger.info(
            f"Created active stream {execution_id} "
            f"for conversation {conversation_id}"
        )
        return stream

    async def _persist_stream_to_db(self, stream: ActiveStream) -> None:
        """將 stream 持久化到資料庫。"""
        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.create(stream.execution_id)
            logger.debug(f"Persisted stream {stream.execution_id} to database")
        except Exception as e:
            logger.warning(f"Failed to persist stream to database: {e}")

    async def persist_events(self, stream: ActiveStream) -> None:
        """將待處理事件持久化到資料庫。"""
        if not stream.user_email:
            return

        events = stream.get_pending_events()
        if not events:
            return

        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.add_events(stream.execution_id, events)
            logger.debug(
                f"Persisted {len(events)} events for "
                f"stream {stream.execution_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to persist events to database: {e}")

    async def update_stream_status(
        self,
        stream: ActiveStream,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """更新資料庫中的 stream 狀態。"""
        if not stream.user_email:
            return

        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.update_status(stream.execution_id, status, error)
            logger.debug(
                f"Updated stream {stream.execution_id} status to {status}"
            )
        except Exception as e:
            logger.warning(f"Failed to update stream status: {e}")

    async def get_stream(self, execution_id: str) -> ActiveStream | None:
        """透過 execution ID 取得 stream。"""
        async with self._lock:
            return self._streams.get(execution_id)

    async def remove_stream(self, execution_id: str) -> None:
        """從管理器移除 stream。"""
        async with self._lock:
            if execution_id in self._streams:
                del self._streams[execution_id]
                logger.info(f"Removed active stream {execution_id}")

    async def _cleanup_old_streams(self) -> None:
        """移除超過清理閾值的 streams。"""
        now = time.time()
        to_remove = [
            eid for eid, stream in self._streams.items()
            if stream.is_complete and (now - stream.created_at) > self.CLEANUP_THRESHOLD_SECONDS
        ]

        for eid in to_remove:
            del self._streams[eid]
            logger.debug(f"Cleaned up old stream {eid}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old streams")

    async def start_stream(
        self,
        stream: ActiveStream,
        agent_coroutine: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """在背景啟動 agent 執行。

        Args:
            stream: 要填入事件的 ActiveStream
            agent_coroutine: 產生事件的非同步函式
        """
        manager = self  # 巢狀函式的參考

        async def run_agent():
            try:
                await agent_coroutine()
            except asyncio.CancelledError:
                logger.info(f"Stream {stream.execution_id} was cancelled")
                if not stream.is_complete:
                    stream.is_cancelled = True
                    stream.is_complete = True
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error(
                    f"Stream {stream.execution_id} error: "
                    f"{type(e).__name__}: {e}"
                )
                logger.error(
                    f"Stream {stream.execution_id} traceback:\n{error_details}"
                )
                if not stream.is_complete:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    if 'Stream closed' in str(e):
                        error_msg = (
                            f"Agent communication interrupted "
                            f"({type(e).__name__}): {str(e)}. "
                            f"Operations may have exceeded timeout."
                        )
                    stream.mark_error(error_msg)
            finally:
                # 最後一次持久化所有剩餘事件
                await manager.persist_events(stream)
                # 更新最終狀態
                if stream.is_cancelled:
                    await manager.update_stream_status(
                        stream, 'cancelled'
                    )
                elif stream.error:
                    await manager.update_stream_status(
                        stream, 'error', stream.error
                    )
                else:
                    await manager.update_stream_status(
                        stream, 'completed'
                    )

        async def persist_loop():
            """定期將事件持久化到資料庫。"""
            while not stream.is_complete and not stream.is_cancelled:
                await asyncio.sleep(EVENT_PERSIST_INTERVAL)
                if stream.should_persist():
                    await manager.persist_events(stream)

        stream.task = asyncio.create_task(run_agent())
        # 若設定 user_email 則啟動持久化迴圈
        if stream.user_email:
            stream.persist_task = asyncio.create_task(persist_loop())
        logger.info(f"Started agent task for stream {stream.execution_id}")


# 全域單例實例
_manager: ActiveStreamManager | None = None


def get_stream_manager() -> ActiveStreamManager:
    """取得全域 ActiveStreamManager 實例。"""
    global _manager
    if _manager is None:
        _manager = ActiveStreamManager()
    return _manager
