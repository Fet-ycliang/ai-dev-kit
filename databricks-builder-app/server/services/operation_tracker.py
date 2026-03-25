"""執行緒安全的 operation tracker，用於非同步工具執行。

當 MCP 工具執行時間超過安全閾值時，會立即回傳 operation ID。
作業會在背景繼續執行，可透過 check_operation_status() 查詢狀態。

這樣做可在長時間執行的作業期間維持 Claude 連線，
透過頻繁的輪詢互動而非阻塞式呼叫來保持連線活躍。
"""

import threading
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

# 已完成作業的 TTL（1 小時）
OPERATION_TTL_SECONDS = 3600


@dataclass
class TrackedOperation:
    """代表可輪詢狀態的背景作業。"""

    operation_id: str
    tool_name: str
    args: dict
    status: str = "running"  # running, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


# 執行緒安全的作業儲存
_operations: Dict[str, TrackedOperation] = {}
_lock = threading.Lock()


def create_operation(tool_name: str, args: dict) -> str:
    """建立新的追蹤作業。

    Args:
        tool_name: 正在執行的 MCP 工具名稱
        args: 傳遞給工具的參數

    Returns:
        operation_id: 用於輪詢的簡短唯一 ID
    """
    op_id = str(uuid.uuid4())[:8]

    with _lock:
        # 建立新作業前先清理舊作業
        _cleanup_expired_operations()

        _operations[op_id] = TrackedOperation(
            operation_id=op_id,
            tool_name=tool_name,
            args=args,
        )

    logger.info(f"Created async operation {op_id} for tool {tool_name}")
    return op_id


def get_operation(op_id: str) -> Optional[TrackedOperation]:
    """根據 ID 取得作業。

    Args:
        op_id: create_operation 回傳的作業 ID

    Returns:
        TrackedOperation，若找不到則回傳 None
    """
    with _lock:
        return _operations.get(op_id)


def complete_operation(op_id: str, result: Any = None, error: str = None):
    """將作業標記為已完成或失敗。

    Args:
        op_id: 作業 ID
        result: 成功結果（若無錯誤）
        error: 錯誤訊息（若失敗）
    """
    with _lock:
        op = _operations.get(op_id)
        if op:
            op.status = "failed" if error else "completed"
            op.result = result
            op.error = error
            op.completed_at = time.time()
            logger.info(
                f"Operation {op_id} {op.status}: "
                f"{error if error else 'success'}"
            )


def list_operations(status: Optional[str] = None) -> list:
    """列出所有作業，可選擇性依狀態過濾。

    Args:
        status: 選擇性過濾條件（'running'、'completed'、'failed'）

    Returns:
        作業摘要清單
    """
    with _lock:
        ops = _operations.values()
        if status:
            ops = [op for op in ops if op.status == status]

        return [
            {
                "operation_id": op.operation_id,
                "tool_name": op.tool_name,
                "status": op.status,
                "started_at": op.started_at,
                "elapsed_seconds": time.time() - op.started_at,
            }
            for op in ops
        ]


def _cleanup_expired_operations():
    """移除超過 TTL 的已完成作業。

    在已持有鎖定時於內部呼叫。
    """
    now = time.time()
    expired = [
        op_id
        for op_id, op in _operations.items()
        if op.completed_at and (now - op.completed_at) > OPERATION_TTL_SECONDS
    ]

    for op_id in expired:
        del _operations[op_id]
        logger.debug(f"Cleaned up expired operation {op_id}")

    if expired:
        logger.info(f"Cleaned up {len(expired)} expired operations")
