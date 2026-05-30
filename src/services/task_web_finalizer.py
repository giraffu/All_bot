import asyncio
import logging
from typing import Any

from src.core.task_lifecycle_contract import build_task_terminal_snapshot
from src.core.task_core_types import TaskSubmissionContext, VideoTaskRequest
from src.core.task_status_mapper import (
    BACKEND_STATUS_CANCELLED,
    is_backend_terminal_status,
    normalize_backend_status,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.redis_client import redis_client
from src.services.task_web_terminal_finalization import (
    finalize_monitored_web_task_cancellation_default,
    finalize_monitored_web_task_failure_default,
    finalize_monitored_web_task_success_default,
)
from src.services.task_lifecycle_runner import route_backend_terminal_snapshot

logger = logging.getLogger(__name__)


def _serialize_submission_context(
    submission_context: TaskSubmissionContext,
) -> dict[str, Any]:
    return {
        "task_type": submission_context.task_type,
        "is_video_task": submission_context.is_video_task,
        "prompt": submission_context.prompt,
        "saved_inputs": list(submission_context.saved_inputs),
        "metadata": dict(submission_context.metadata),
        "allow_contribute": submission_context.allow_contribute,
        "final_priority": submission_context.final_priority,
        "video_request": {
            "requested_duration": submission_context.requested_duration,
            "output_width": submission_context.output_width,
            "output_height": submission_context.output_height,
            "output_duration": submission_context.output_duration,
            "billing_resolution": submission_context.billing_resolution,
        },
    }


def _deserialize_submission_context(
    *,
    internal_user_id: int,
    username: str,
    payload: dict[str, Any],
) -> TaskSubmissionContext:
    video_request_payload = payload.get("video_request") or {}
    return TaskSubmissionContext(
        task_type=payload["task_type"],
        is_video_task=bool(payload.get("is_video_task")),
        user_logger=UserLogger(internal_user_id, username),
        prompt=payload.get("prompt", ""),
        saved_inputs=list(payload.get("saved_inputs") or []),
        metadata=dict(payload.get("metadata") or {}),
        allow_contribute=bool(payload.get("allow_contribute", True)),
        final_priority=int(payload.get("final_priority", 0)),
        video_request=VideoTaskRequest(
            requested_duration=video_request_payload.get("requested_duration"),
            output_width=video_request_payload.get("output_width"),
            output_height=video_request_payload.get("output_height"),
            output_duration=video_request_payload.get("output_duration"),
            billing_resolution=video_request_payload.get("billing_resolution"),
        ),
    )


async def enqueue_pending_web_finalizer(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
) -> None:
    await redis_client.add_pending_web_finalizer(
        registry_task_id,
        {
            "backend_task_id": backend_task_id,
            "internal_user_id": internal_user_id,
            "username": username,
            "registry_task_id": registry_task_id,
            "submission_context": _serialize_submission_context(submission_context),
            "cost": cost,
        },
    )


async def _finalize_pending_web_success(
    *,
    record: dict[str, Any],
    registry_task_id: str,
    terminal_snapshot,
    remove_record_func,
) -> None:
    await finalize_monitored_web_task_success_default(
        backend_task_id=record["backend_task_id"],
        internal_user_id=record["internal_user_id"],
        username=record["username"],
        registry_task_id=registry_task_id,
        submission_context=_deserialize_submission_context(
            internal_user_id=record["internal_user_id"],
            username=record["username"],
            payload=record["submission_context"],
        ),
        result_path=terminal_snapshot.result_path,
        extra_outputs=terminal_snapshot.extra_outputs,
        logger_override=logger,
    )
    await remove_record_func()


async def _finalize_pending_web_cancellation(
    *,
    record: dict[str, Any],
    registry_task_id: str,
    remove_record_func,
) -> None:
    await finalize_monitored_web_task_cancellation_default(
        internal_user_id=record["internal_user_id"],
        username=record["username"],
        cost=int(record.get("cost", 0)),
        registry_task_id=registry_task_id,
        logger_override=logger,
    )
    await remove_record_func()


async def _finalize_pending_web_failure(
    *,
    record: dict[str, Any],
    registry_task_id: str,
    terminal_snapshot,
    remove_record_func,
) -> None:
    await finalize_monitored_web_task_failure_default(
        internal_user_id=record["internal_user_id"],
        username=record["username"],
        cost=int(record.get("cost", 0)),
        registry_task_id=registry_task_id,
        final_status=terminal_snapshot.status,
        logger_override=logger,
    )
    await remove_record_func()


async def _finalize_terminal_record(record: dict[str, Any], status_data: dict[str, Any]) -> None:
    final_status = normalize_backend_status(status_data.get("status"))
    registry_task_id = record["registry_task_id"]
    terminal_snapshot = build_task_terminal_snapshot(
        status=final_status,
        result_path=status_data.get("result_path"),
        extra_outputs=status_data.get("extra_outputs"),
        error=status_data.get("error") or status_data.get("error_msg"),
        message=status_data.get("message"),
    )

    async def _remove_record() -> None:
        await redis_client.remove_pending_web_finalizer(registry_task_id)

    await route_backend_terminal_snapshot(
        terminal_snapshot=terminal_snapshot,
        handle_success=lambda snapshot: _finalize_pending_web_success(
            record=record,
            registry_task_id=registry_task_id,
            terminal_snapshot=snapshot,
            remove_record_func=_remove_record,
        ),
        handle_cancelled=lambda _snapshot: _finalize_pending_web_cancellation(
            record=record,
            registry_task_id=registry_task_id,
            remove_record_func=_remove_record,
        ),
        handle_failure=lambda snapshot: _finalize_pending_web_failure(
            record=record,
            registry_task_id=registry_task_id,
            terminal_snapshot=snapshot,
            remove_record_func=_remove_record,
        ),
    )


async def process_pending_web_finalizer(
    registry_task_id: str,
    *,
    record: dict[str, Any] | None = None,
) -> bool:
    record = record or await redis_client.get_pending_web_finalizer(registry_task_id)
    if not record:
        return False

    backend_task_id = record.get("backend_task_id")
    if not backend_task_id:
        return False

    status_data = await image_service.get_task_status(backend_task_id)
    if not status_data:
        status_data = {"status": BACKEND_STATUS_CANCELLED, "error_msg": "Task not found"}

    if not is_backend_terminal_status(status_data.get("status")):
        return False

    await _finalize_terminal_record(record, status_data)
    return True


async def process_all_pending_web_finalizers() -> int:
    finalized_count = 0
    pending_finalizers = await redis_client.get_pending_web_finalizers()
    for registry_task_id, record in pending_finalizers.items():
        try:
            finalized = await process_pending_web_finalizer(
                registry_task_id,
                record=record,
            )
        except Exception:
            logger.exception(
                "Failed to process pending web finalizer for %s",
                registry_task_id,
            )
            continue
        if finalized:
            finalized_count += 1
    return finalized_count


async def run_pending_web_finalizer_loop(
    *,
    interval_seconds: float = 5.0,
) -> None:
    while True:
        try:
            await process_all_pending_web_finalizers()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Pending web finalizer loop failed.")
        await asyncio.sleep(interval_seconds)
