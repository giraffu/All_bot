from dataclasses import dataclass
from typing import Any

from src.core.task_core_types import TaskSubmissionSideEffectPlan

BACKEND_STATUS_PENDING = "pending"
BACKEND_STATUS_RUNNING = "running"
BACKEND_STATUS_DONE = "done"
BACKEND_STATUS_ERROR = "error"
BACKEND_STATUS_CANCELLED = "cancelled"

STREAM_STATUS_SUCCESS = "success"
STREAM_STATUS_FAILED = "failed"
STREAM_STATUS_CANCELLED = "cancelled"

BACKEND_TERMINAL_STATUSES = frozenset(
    {BACKEND_STATUS_DONE, BACKEND_STATUS_ERROR, BACKEND_STATUS_CANCELLED}
)


@dataclass(frozen=True, slots=True)
class TaskTerminalSnapshot:
    status: str | None
    result_path: str | None = None
    extra_outputs: dict[str, Any] | None = None
    error: str | None = None
    message: str | None = None


def normalize_backend_status(status: str | None) -> str | None:
    if status == STREAM_STATUS_SUCCESS:
        return BACKEND_STATUS_DONE
    if status == STREAM_STATUS_FAILED:
        return BACKEND_STATUS_ERROR
    return status


def is_backend_success_status(status: str | None) -> bool:
    return normalize_backend_status(status) == BACKEND_STATUS_DONE


def is_backend_failed_status(status: str | None) -> bool:
    return normalize_backend_status(status) == BACKEND_STATUS_ERROR


def is_backend_cancelled_status(status: str | None) -> bool:
    return normalize_backend_status(status) == BACKEND_STATUS_CANCELLED


def is_backend_terminal_status(status: str | None) -> bool:
    return normalize_backend_status(status) in BACKEND_TERMINAL_STATUSES


def build_task_terminal_snapshot(
    *,
    status: str | None,
    result_path: str | None = None,
    extra_outputs: dict[str, Any] | None = None,
    error: str | None = None,
    message: str | None = None,
) -> TaskTerminalSnapshot:
    return TaskTerminalSnapshot(
        status=normalize_backend_status(status),
        result_path=result_path,
        extra_outputs=extra_outputs,
        error=error,
        message=message,
    )


def normalize_task_submission_side_effect_plan(
    *,
    submission_side_effect_plan: TaskSubmissionSideEffectPlan | None,
    client_type: str | None,
    source_post_id: int | None,
) -> TaskSubmissionSideEffectPlan:
    if submission_side_effect_plan is not None:
        return submission_side_effect_plan
    return TaskSubmissionSideEffectPlan(
        attach_web_monitor=client_type == "web",
        source_post_id=source_post_id,
    )
