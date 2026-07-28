import asyncio
import copy
import logging
import uuid
from typing import Any

from src.core.task_lifecycle_contract import build_task_terminal_snapshot
from src.core.task_core_types import TaskSubmissionContext, VideoTaskRequest
from src.core.task_status_mapper import (
    BACKEND_STATUS_CANCELLED,
    BACKEND_STATUS_DONE,
    is_backend_terminal_status,
    normalize_backend_status,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.redis_client import redis_client
from src.services.scail2_face_swap_pipeline_service import (
    cleanup_scail2_face_swap_first_frame,
)
from src.services.task_registry import TaskRegistry
from src.services.task_web_terminal_finalization import (
    finalize_monitored_web_task_cancellation_default,
    finalize_monitored_web_task_failure_default,
    finalize_monitored_web_task_success_default,
)
from src.services.task_lifecycle_runner import route_backend_terminal_snapshot

logger = logging.getLogger(__name__)

FREE_EDIT_V3_CONTINUATION_KIND = "free_edit_v3"
FREE_EDIT_V3_TASK_TYPE = "pornmaster_flux2_edit_bf16"
FREE_EDIT_V3_STAGE2_TASK_TYPE = "face_swap_v2"
SCAIL2_FACE_SWAP_CONTINUATION_KIND = "scail2_face_swap_v2"


def _free_edit_v3_stage2_task_id(registry_task_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"allbot:web-free-edit-v3:{registry_task_id}:face-swap",
        )
    )


def _scail2_face_swap_stage2_task_id(registry_task_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"allbot:web-scail2-face-swap:{registry_task_id}:video",
        )
    )


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
        "delivery_context": dict(submission_context.delivery_context),
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
        delivery_context=dict(payload.get("delivery_context") or {}),
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
    serialized_context = _serialize_submission_context(submission_context)
    continuation_marker = serialized_context["metadata"].get("_web_free_edit_v3")
    continuation = None
    if isinstance(continuation_marker, dict):
        continuation = {
            "version": int(continuation_marker.get("version", 1)),
            "kind": FREE_EDIT_V3_CONTINUATION_KIND,
            "stage": "bf16",
            "stage2_task_type": FREE_EDIT_V3_STAGE2_TASK_TYPE,
            "stage2_backend_task_id": _free_edit_v3_stage2_task_id(registry_task_id),
            "original_image": continuation_marker.get("original_image"),
            "stage1_result_path": None,
            "final_allow_contribute": bool(
                continuation_marker.get("final_allow_contribute", True)
            ),
        }
    scail2_marker = serialized_context["metadata"].get(
        "_web_scail2_face_swap_v2"
    )
    if isinstance(scail2_marker, dict):
        video_request = serialized_context.get("video_request") or {}
        continuation = {
            "version": int(scail2_marker.get("version", 1)),
            "kind": SCAIL2_FACE_SWAP_CONTINUATION_KIND,
            "stage": "face_swap_v2",
            "stage2_backend_task_id": _scail2_face_swap_stage2_task_id(
                registry_task_id
            ),
            "first_frame": scail2_marker.get("first_frame"),
            "original_reference": scail2_marker.get("original_reference"),
            "motion_video": scail2_marker.get("motion_video"),
            "duration": int(
                scail2_marker.get("duration")
                or video_request.get("requested_duration")
                or 5
            ),
            "normal_priority": int(serialized_context.get("final_priority", 0)),
            "stage1_result_path": None,
            "final_allow_contribute": bool(
                scail2_marker.get("final_allow_contribute", True)
            ),
        }
    await redis_client.add_pending_web_finalizer(
        registry_task_id,
        {
            "backend_task_id": backend_task_id,
            "internal_user_id": internal_user_id,
            "username": username,
            "registry_task_id": registry_task_id,
            "submission_context": serialized_context,
            "cost": cost,
            **({"continuation": continuation} if continuation else {}),
        },
    )


def _is_free_edit_v3_record(record: dict[str, Any]) -> bool:
    continuation = record.get("continuation")
    return bool(
        isinstance(continuation, dict)
        and continuation.get("version") == 1
        and continuation.get("kind") == FREE_EDIT_V3_CONTINUATION_KIND
    )


def _is_scail2_face_swap_record(record: dict[str, Any]) -> bool:
    continuation = record.get("continuation")
    return bool(
        isinstance(continuation, dict)
        and continuation.get("version") == 1
        and continuation.get("kind") == SCAIL2_FACE_SWAP_CONTINUATION_KIND
    )


async def _resume_free_edit_v3_face_swap(
    record: dict[str, Any],
    *,
    stage1_result_path: str | None = None,
) -> None:
    next_record = copy.deepcopy(record)
    continuation = next_record["continuation"]
    if stage1_result_path:
        continuation["stage1_result_path"] = stage1_result_path
    stage1_result_path = continuation.get("stage1_result_path")
    original_image = continuation.get("original_image")
    if not stage1_result_path or not original_image:
        raise ValueError("Free edit v3 continuation is missing a stage input")

    registry_task_id = next_record["registry_task_id"]
    stage2_backend_task_id = continuation["stage2_backend_task_id"]
    # Version-1 free-edit-v3 continuations are V2-only. Normalize missing or
    # stale V1 labels so an upgrade/retry can never silently downgrade stage 2.
    stage2_task_type = FREE_EDIT_V3_STAGE2_TASK_TYPE
    continuation["stage2_task_type"] = FREE_EDIT_V3_STAGE2_TASK_TYPE
    final_allow_contribute = bool(continuation.get("final_allow_contribute", True))
    continuation["stage"] = "face_swap_dispatching"
    next_record["backend_task_id"] = stage2_backend_task_id
    submission_context = next_record["submission_context"]
    submission_context["task_type"] = FREE_EDIT_V3_TASK_TYPE
    submission_context["saved_inputs"] = [original_image]
    submission_context["allow_contribute"] = final_allow_contribute
    submission_context.setdefault("metadata", {}).pop("_web_free_edit_v3", None)

    # The durable intent is written before any external dispatch. A restart can
    # safely reconcile the deterministic second-stage ID without another debit.
    await redis_client.add_pending_web_finalizer(registry_task_id, next_record)
    await TaskRegistry.transition_backend_task(
        registry_task_id,
        backend_task_id=stage2_backend_task_id,
        task_type=FREE_EDIT_V3_TASK_TYPE,
        saved_input_images=[original_image],
        allow_contribute=final_allow_contribute,
        user_cancel_allowed=False,
        status="pending",
    )

    existing_stage2 = await image_service.get_task_status(stage2_backend_task_id)
    if existing_stage2 is None:
        submitted_task_id = await image_service.submit_face_swap_task(
            stage2_backend_task_id,
            face_image_path=original_image,
            body_image_path=stage1_result_path,
            priority=100,
            task_type=stage2_task_type,
        )
        if submitted_task_id != stage2_backend_task_id:
            raise RuntimeError("Face swap backend changed the deterministic task ID")

    continuation["stage"] = "face_swap"
    await redis_client.add_pending_web_finalizer(registry_task_id, next_record)


async def _resume_scail2_face_swap_video(
    record: dict[str, Any],
    *,
    stage1_result_path: str | None = None,
) -> None:
    next_record = copy.deepcopy(record)
    continuation = next_record["continuation"]
    if stage1_result_path:
        continuation["stage1_result_path"] = stage1_result_path
    swapped_reference = continuation.get("stage1_result_path")
    original_reference = continuation.get("original_reference")
    motion_video = continuation.get("motion_video")
    if not swapped_reference or not original_reference or not motion_video:
        raise ValueError("SCAIL-2 face-swap continuation is missing a stage input")

    registry_task_id = next_record["registry_task_id"]
    stage2_backend_task_id = continuation["stage2_backend_task_id"]
    final_allow_contribute = bool(continuation.get("final_allow_contribute", True))
    normal_priority = int(continuation.get("normal_priority", 0))
    duration = int(continuation.get("duration") or 5)
    submission_context = next_record["submission_context"]
    metadata = submission_context.setdefault("metadata", {})
    negative_prompt = str(metadata.get("scail2_negative_prompt") or " ")
    prompt = str(submission_context.get("prompt") or "")

    continuation["stage"] = "scail2_dispatching"
    next_record["backend_task_id"] = stage2_backend_task_id
    submission_context["task_type"] = SCAIL2_FACE_SWAP_CONTINUATION_KIND
    submission_context["saved_inputs"] = [original_reference, motion_video]
    submission_context["allow_contribute"] = final_allow_contribute
    metadata.pop("_web_scail2_face_swap_v2", None)

    await redis_client.add_pending_web_finalizer(registry_task_id, next_record)
    await TaskRegistry.transition_backend_task(
        registry_task_id,
        backend_task_id=stage2_backend_task_id,
        task_type=SCAIL2_FACE_SWAP_CONTINUATION_KIND,
        saved_input_images=[original_reference, motion_video],
        allow_contribute=final_allow_contribute,
        user_cancel_allowed=False,
        status="pending",
    )

    existing_stage2 = await image_service.get_task_status(stage2_backend_task_id)
    if existing_stage2 is None:
        submitted_task_id = await image_service.submit_scail2_video_task(
            stage2_backend_task_id,
            task_type=SCAIL2_FACE_SWAP_CONTINUATION_KIND,
            reference_image_path=swapped_reference,
            motion_video_path=motion_video,
            prompt=prompt,
            negative_prompt=negative_prompt,
            length=duration,
            priority=normal_priority,
            reference_preprocessed=True,
        )
        if submitted_task_id != stage2_backend_task_id:
            raise RuntimeError("SCAIL-2 backend changed the deterministic task ID")

    continuation["stage"] = "scail2"
    await redis_client.add_pending_web_finalizer(registry_task_id, next_record)


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


async def _finalize_terminal_record(
    record: dict[str, Any], status_data: dict[str, Any]
) -> None:
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
        if _is_scail2_face_swap_record(record):
            await cleanup_scail2_face_swap_first_frame(
                record.get("continuation", {}).get("first_frame")
            )
        await redis_client.remove_pending_web_finalizer(registry_task_id)

    submission = record.get("submission_context") or {}
    metadata = submission.get("metadata") or {}
    character_view_marker = metadata.get("_character_reference_view")
    if (
        submission.get("task_type") == "character_reference_build"
        or isinstance(character_view_marker, dict)
    ):
        from src.web_api.services.character_reference_service import (
            finalize_character_reference,
        )

        await finalize_character_reference(
            task_id=registry_task_id,
            status=final_status,
            result_path=status_data.get("result_path"),
        )

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
    del record
    lock_token = await redis_client.acquire_pending_web_finalizer_lock(registry_task_id)
    if not lock_token:
        return False

    try:
        record = await redis_client.get_pending_web_finalizer(registry_task_id)
        if not record:
            return False

        if (
            _is_free_edit_v3_record(record)
            and record["continuation"].get("stage") == "face_swap_dispatching"
        ):
            await _resume_free_edit_v3_face_swap(record)
            return True
        if (
            _is_scail2_face_swap_record(record)
            and record["continuation"].get("stage") == "scail2_dispatching"
        ):
            await _resume_scail2_face_swap_video(record)
            return True

        backend_task_id = record.get("backend_task_id")
        if not backend_task_id:
            return False

        status_data = await image_service.get_task_status(backend_task_id)
        if not status_data:
            status_data = {
                "status": BACKEND_STATUS_CANCELLED,
                "error_msg": "Task not found",
            }

        if not is_backend_terminal_status(status_data.get("status")):
            return False

        if (
            _is_free_edit_v3_record(record)
            and record["continuation"].get("stage") == "bf16"
            and normalize_backend_status(status_data.get("status"))
            == BACKEND_STATUS_DONE
        ):
            if not status_data.get("result_path"):
                await _finalize_terminal_record(
                    record,
                    {
                        "status": "error",
                        "error_msg": "BF16 stage completed without a result path",
                    },
                )
                return True
            await _resume_free_edit_v3_face_swap(
                record,
                stage1_result_path=status_data.get("result_path"),
            )
            return True
        if (
            _is_scail2_face_swap_record(record)
            and record["continuation"].get("stage") == "face_swap_v2"
            and normalize_backend_status(status_data.get("status"))
            == BACKEND_STATUS_DONE
        ):
            if not status_data.get("result_path"):
                await _finalize_terminal_record(
                    record,
                    {
                        "status": "error",
                        "error_msg": (
                            "Face-swap stage completed without a result path"
                        ),
                    },
                )
                return True
            await _resume_scail2_face_swap_video(
                record,
                stage1_result_path=status_data.get("result_path"),
            )
            return True

        await _finalize_terminal_record(record, status_data)
        return True
    finally:
        await redis_client.release_pending_web_finalizer_lock(
            registry_task_id,
            lock_token,
        )


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
