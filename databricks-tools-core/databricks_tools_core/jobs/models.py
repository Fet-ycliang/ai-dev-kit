"""
Jobs - 資料模型與列舉

用於 job 作業的資料類別與列舉。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class JobStatus(Enum):
    """Job 生命週期狀態列舉。"""

    RUNNING = "RUNNING"
    QUEUED = "QUEUED"
    TERMINATED = "TERMINATED"
    TERMINATING = "TERMINATING"
    PENDING = "PENDING"
    SKIPPED = "SKIPPED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RunLifecycleState(Enum):
    """Run 生命週期狀態列舉。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    SKIPPED = "SKIPPED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    QUEUED = "QUEUED"
    WAITING_FOR_RETRY = "WAITING_FOR_RETRY"
    BLOCKED = "BLOCKED"


class RunResultState(Enum):
    """Run 結果狀態列舉。"""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEDOUT = "TIMEDOUT"
    CANCELED = "CANCELED"
    EXCLUDED = "EXCLUDED"
    SUCCESS_WITH_FAILURES = "SUCCESS_WITH_FAILURES"
    UPSTREAM_FAILED = "UPSTREAM_FAILED"
    UPSTREAM_CANCELED = "UPSTREAM_CANCELED"


@dataclass
class JobRunResult:
    """
    job run 作業的結果，包含供 LLM 使用的詳細狀態資訊。

    此 dataclass 提供 job runs 的完整資訊，
    協助 LLM 瞭解發生了什麼事並採取適當動作。
    """

    # Job 識別資訊
    job_id: int
    run_id: int
    job_name: Optional[str] = None

    # Run 狀態
    lifecycle_state: Optional[str] = None
    result_state: Optional[str] = None
    success: bool = False

    # 時間資訊
    duration_seconds: Optional[float] = None
    start_time: Optional[int] = None  # epoch 毫秒
    end_time: Optional[int] = None  # epoch 毫秒

    # Run 詳細資訊
    run_page_url: Optional[str] = None
    state_message: Optional[str] = None

    # 錯誤詳細資訊（若失敗）
    error_message: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # 人類可讀狀態
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可供 JSON 序列化的字典。"""
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "job_name": self.job_name,
            "lifecycle_state": self.lifecycle_state,
            "result_state": self.result_state,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "run_page_url": self.run_page_url,
            "state_message": self.state_message,
            "error_message": self.error_message,
            "errors": self.errors,
            "message": self.message,
        }


class JobError(Exception):
    """job 相關錯誤所引發的例外。"""

    def __init__(self, message: str, job_id: Optional[int] = None, run_id: Optional[int] = None):
        self.job_id = job_id
        self.run_id = run_id
        super().__init__(message)
