import asyncio
import logging
import os
from typing import Optional

from config import MINIO_BUCKET
from src.core.media_paths import resolve_storage_object
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
)
from src.core.task_core_finalization import (
    finalize_task_cancellation,
    finalize_task_failure,
    finalize_terminated_task,
    handle_failed_task_exception,
    refund_cancelled_task,
    refund_failed_task,
)
from src.core.task_core_persistence import (
    _persist_successful_web_history,
    persist_successful_task_result,
    schedule_web_history_r2_warmup,
)
from src.core.task_core_runtime import (
    cancel_user_task,
    cleanup_task_runtime_state,
    force_terminate_task,
    get_system_task_stats,
    sync_user_concurrency,
)
from src.core.task_core_types import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    TaskCancellationFinalizationResult,
    TaskFailureFinalizationResult,
    TaskSubmissionContext,
    TaskSubmissionExecutionResult,
    TaskSuccessPersistenceResult,
    TaskTerminationFinalizationResult,
    VideoTaskRequest,
    build_failed_task_user_message,
    build_video_task_request,
    infer_requested_billing_resolution,
    infer_requested_output_metadata,
    is_task_backend_busy_error,
    normalize_terminal_status,
)
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.storage import storage
from src.services.task_registry import TaskRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "ConcurrencyLimitError",
    "CoreDomainError",
    "InsufficientCreditsError",
    "TaskCancellationFinalizationResult",
    "TaskFailureFinalizationResult",
    "TaskSubmissionContext",
    "TaskSubmissionExecutionResult",
    "TaskSuccessPersistenceResult",
    "TaskTerminationFinalizationResult",
    "VideoTaskRequest",
    "build_failed_task_user_message",
    "_infer_requested_billing_resolution",
    "_infer_requested_output_metadata",
    "cancel_user_task",
    "cleanup_task_runtime_state",
    "extract_media_metadata_from_bytes_best_effort",
    "extract_media_metadata_from_storage_best_effort",
    "finalize_task_cancellation",
    "finalize_task_failure",
    "finalize_terminated_task",
    "force_terminate_task",
    "generate_and_upload_thumbnail",
    "get_system_task_stats",
    "handle_failed_task_exception",
    "is_task_backend_busy_error",
    "persist_successful_task_result",
    "process_and_submit_task",
    "refund_cancelled_task",
    "refund_failed_task",
    "resolve_storage_object",
    "schedule_web_history_r2_warmup",
    "storage",
    "sync_user_concurrency",
]

_infer_requested_output_metadata = infer_requested_output_metadata
_infer_requested_billing_resolution = infer_requested_billing_resolution


async def _process_input_path(user_logger: UserLogger, path: str) -> str:
    if not path:
        return ""
    if path.startswith("template:"):
        return path
    if path.startswith(f"{MINIO_BUCKET}/"):
        return path.replace(f"{MINIO_BUCKET}/", "", 1)

    # Existing history records may already store a plain object key without bucket prefix.
    # Only treat the value as a local file when it is an absolute path or actually exists on disk.
    is_local_file = os.path.isabs(path) or os.path.exists(path)
    if not is_local_file:
        return path

    if not os.path.exists(path):
        raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")

    # Upload local files to MinIO before dispatching to workers.
    import asyncio

    processed = await asyncio.to_thread(user_logger.save_input_image, path)
    if processed:
        return processed

    raise CoreDomainError(f"本地输入文件上传失败，无法继续派发任务: {path}")


from src.core.billing_core import (
    check_and_deduct_credits,
    check_concurrency_lock,
    get_user_priority_and_identity,
    refund_credits,
    release_concurrency_lock,
)
from src.core.task_dispatcher import StrategyFactory, dispatch_to_worker
from src.utils import load_prompts
import contextlib

def _validate_local_input_paths(paths_to_upload: list[str]):
    for path in paths_to_upload:
        if not path:
            continue
        if path.startswith("template:") or path.startswith(f"{MINIO_BUCKET}/"):
            continue
        is_local_file = os.path.isabs(path) or os.path.exists(path)
        if is_local_file and not os.path.exists(path):
            raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")


async def _prepare_task_submission_payload(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict,
    strategy,
    base_priority: int,
    is_template: bool,
    is_video_task: bool,
    video_request: VideoTaskRequest,
) -> TaskSubmissionContext:
    user_logger = UserLogger(user_id, username)
    paths_to_upload = strategy.get_file_paths_to_upload(inputs)
    _validate_local_input_paths(paths_to_upload)

    priority, _, _ = await get_user_priority_and_identity(user_id)
    final_priority = min(base_priority + priority, 100)

    prompts_config = load_prompts()
    prompt = inputs.get("prompt")
    if not prompt or prompt.strip() == "":
        prompt = prompts_config.get(task_type, task_type)

    saved_inputs = []
    for path in paths_to_upload:
        processed_img = await _process_input_path(user_logger, path)
        if processed_img:
            saved_inputs.append(processed_img)

    allow_contribute = not is_template
    submission_context = TaskSubmissionContext(
        task_type=task_type,
        is_video_task=is_video_task,
        user_logger=user_logger,
        prompt=prompt,
        saved_inputs=saved_inputs,
        metadata={},
        allow_contribute=allow_contribute,
        final_priority=final_priority,
        video_request=video_request,
    )
    submission_context.apply_to_inputs(inputs)
    metadata = strategy.get_metadata(inputs)
    submission_context.metadata = metadata
    return submission_context


async def _register_task_submission(
    *,
    registry_task_id: str,
    user_id: int,
    username: str,
    cost: int,
    submission_context: TaskSubmissionContext,
) -> str:
    return await TaskRegistry.add_task(
        task_id=registry_task_id,
        user_id=user_id,
        username=username,
        cost=cost,
        task_type=submission_context.task_type,
        prompt=submission_context.log_prompt,
        saved_input_images=submission_context.registry_saved_inputs(),
        is_video=submission_context.is_video_task,
        priority=submission_context.final_priority,
        allow_contribute=submission_context.allow_contribute,
        metadata=submission_context.metadata,
    )


async def _dispatch_registered_task(
    *,
    registry_task_id: str,
    task_type: str,
    inputs: dict,
    final_priority: int,
) -> str:
    try:
        backend_task_id = await dispatch_to_worker(
            registry_task_id, task_type, inputs, final_priority
        )
        if registry_task_id and backend_task_id:
            await TaskRegistry.update_backend_task_id(registry_task_id, backend_task_id)
        if not backend_task_id:
            raise Exception("Failed to submit task to backend API.")
        return backend_task_id
    except Exception as e:
        logger.error(f"Dispatch to worker failed: {e}", exc_info=True)
        if registry_task_id:
            with contextlib.suppress(Exception):
                await TaskRegistry.mark_task_status(registry_task_id, "failed")
        error_msg = str(e)
        if is_task_backend_busy_error(error_msg):
            raise CoreDomainError("当前服务器繁忙，请稍后再试") from e
        raise CoreDomainError(f"System error: {error_msg}") from e


async def _execute_task_submission_saga(
    *,
    task_type: str,
    inputs: dict,
    registry_task_id: str,
    cost: int,
    submission_context: TaskSubmissionContext,
) -> TaskSubmissionExecutionResult:
    registry_task_id = await _register_task_submission(
        registry_task_id=registry_task_id,
        user_id=submission_context.user_logger.user_id,
        username=submission_context.user_logger.username,
        cost=cost,
        submission_context=submission_context,
    )

    backend_task_id = await _dispatch_registered_task(
        registry_task_id=registry_task_id,
        task_type=task_type,
        inputs=inputs,
        final_priority=submission_context.final_priority,
    )

    return TaskSubmissionExecutionResult(
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        submission_context=submission_context,
    )


async def _compensate_failed_submission(
    *,
    user_id: int,
    username: str,
    cost: int,
    error: Exception,
    credits_deducted: bool,
    registry_task_id: str,
):
    if credits_deducted:
        try:
            await asyncio.shield(
                refund_credits(
                    user_id,
                    cost,
                    task_type="refund_saga_failed",
                    username=username,
                )
            )
        except Exception as refund_err:
            logger.critical(
                f"REFUND FAILED! Log to Outbox. User: {user_id}, Amount: {cost}, Error: {refund_err}"
            )
            from src.services.redis_client import redis_client

            await redis_client.add_pending_refund(
                user_id, cost, f"Task Failed: {str(error)}", username
            )

    with contextlib.suppress(Exception):
        await asyncio.shield(TaskRegistry.remove_task(registry_task_id))


def _attach_web_task_monitor(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
):
    asyncio.create_task(
        monitor_task_and_release_lock(
            backend_task_id=backend_task_id,
            internal_user_id=internal_user_id,
            username=username,
            registry_task_id=registry_task_id,
            submission_context=submission_context,
            cost=cost,
        )
    )


def _schedule_apply_interaction(user_id: int, source_post_id: Optional[int]):
    if not source_post_id:
        return
    from src.core.gallery_core import record_apply_interaction

    asyncio.create_task(record_apply_interaction(user_id, source_post_id))


def _attach_submission_side_effects(
    *,
    client_type: str,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int,
    source_post_id: Optional[int],
):
    if client_type == "web":
        try:
            _attach_web_task_monitor(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                cost=cost,
            )
        except Exception as e:
            raise CoreDomainError(f"后台监控挂载失败: {e}")

    _schedule_apply_interaction(internal_user_id, source_post_id)


async def _finalize_monitored_web_task_success(
    *,
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    result_path: str,
):
    try:
        await _persist_successful_web_history(
            backend_task_id=backend_task_id,
            registry_task_id=registry_task_id,
            internal_user_id=internal_user_id,
            username=username,
            prompt=submission_context.log_prompt,
            task_type=submission_context.task_type,
            input_images=submission_context.saved_inputs,
            allow_contribute=submission_context.allow_contribute,
            is_video=submission_context.is_video_task,
            result_path=result_path,
            billing_resolution=submission_context.billing_resolution,
            output_width=submission_context.output_width,
            output_height=submission_context.output_height,
            output_duration=submission_context.output_duration,
            requested_duration=submission_context.requested_duration,
        )
    except Exception as log_err:
        logger.error(
            f"Failed to log task history for {registry_task_id}: {log_err}"
        )
    await cleanup_task_runtime_state(
        internal_user_id=internal_user_id,
        registry_task_id=registry_task_id,
    )


async def _finalize_monitored_web_task_cancellation(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
):
    try:
        await finalize_task_cancellation(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            task_submitted=True,
            registry_task_id=registry_task_id,
        )
    except Exception as refund_err:
        logger.critical(
            f"Async cancellation finalize failed for user {internal_user_id}: {refund_err}"
        )


async def _finalize_monitored_web_task_failure(
    *,
    internal_user_id: int,
    username: str,
    cost: int,
    registry_task_id: str,
    final_status: str | None,
):
    try:
        await finalize_task_failure(
            internal_user_id=internal_user_id,
            username=username,
            cost=cost,
            should_refund=cost > 0,
            registry_task_id=registry_task_id,
            refund_task_type=f"refund_async_failed_{final_status}",
        )
    except Exception as refund_err:
        logger.critical(
            f"Async refund failed for user {internal_user_id}: {refund_err}"
        )

async def monitor_task_and_release_lock(
    backend_task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    submission_context: TaskSubmissionContext,
    cost: int = 0,
):
    """
    Background task to monitor progress and release concurrency lock.
    """
    import asyncio

    final_status = None
    result_path = None
    try:
        async for progress in image_service.monitor_progress(
            backend_task_id, submission_context.is_video_task
        ):
            normalized_status = normalize_terminal_status(progress.get("status"))
            if normalized_status in [
                "done",
                "error",
                "cancelled",
            ]:
                final_status = normalized_status
                result_path = progress.get("result_path")
                break
    except asyncio.CancelledError:
        logger.error(f"Task monitor {backend_task_id} cancelled.")
        final_status = "cancelled"
    except Exception as e:
        logger.error(f"Background monitoring error for task {backend_task_id}: {e}")
        final_status = "error"
    finally:
        if final_status == "done" and result_path:
            await _finalize_monitored_web_task_success(
                backend_task_id=backend_task_id,
                internal_user_id=internal_user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=submission_context,
                result_path=result_path,
            )
        elif final_status == "cancelled":
            await _finalize_monitored_web_task_cancellation(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
            )
        else:
            await _finalize_monitored_web_task_failure(
                internal_user_id=internal_user_id,
                username=username,
                cost=cost,
                registry_task_id=registry_task_id,
                final_status=final_status,
            )


async def process_and_submit_task(
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict,
    task_id: str,
    base_priority: int = 0,
    is_template: bool = False,
    client_type: str = "web",
    deduct_quota: bool = True,
    check_lock: bool = True,
    source_post_id: Optional[int] = None,
) -> dict:
    import asyncio

    strategy = StrategyFactory.get_strategy(task_type)
    cost = strategy.get_cost(inputs)
    from src.constants import VIDEO_TASK_TYPES

    is_video_task = task_type in VIDEO_TASK_TYPES

    video_request = (
        build_video_task_request(task_type, inputs)
        if is_video_task
        else VideoTaskRequest()
    )

    if check_lock:
        can_run, err = await check_concurrency_lock(user_id)
        if not can_run:
            raise ConcurrencyLimitError(err)

    task_submitted_successfully = False
    credits_deducted = False
    registry_task_id = task_id

    try:
        submission_context = await _prepare_task_submission_payload(
            user_id=user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            strategy=strategy,
            base_priority=base_priority,
            is_template=is_template,
            is_video_task=is_video_task,
            video_request=video_request,
        )

        if deduct_quota:
            success, err = await check_and_deduct_credits(
                user_id, cost, task_type, username
            )
            if not success:
                raise InsufficientCreditsError(err)
            credits_deducted = True

        try:
            execution_result = await _execute_task_submission_saga(
                task_type=task_type,
                inputs=inputs,
                registry_task_id=registry_task_id,
                cost=cost,
                submission_context=submission_context,
            )
            registry_task_id = execution_result.registry_task_id
            _attach_submission_side_effects(
                client_type=client_type,
                backend_task_id=execution_result.backend_task_id,
                internal_user_id=user_id,
                username=username,
                registry_task_id=registry_task_id,
                submission_context=execution_result.submission_context,
                cost=cost if deduct_quota else 0,
                source_post_id=source_post_id,
            )

            task_submitted_successfully = True

            return {
                "task_id": registry_task_id,
                "registry_task_id": registry_task_id,
                "backend_task_id": execution_result.backend_task_id,
                "cost": cost,
                "saved_inputs": execution_result.submission_context.saved_inputs,
            }

        except Exception as e:
            logger.error(f"Saga Execute Failed: {e}")
            await _compensate_failed_submission(
                user_id=user_id,
                username=username,
                cost=cost,
                error=e,
                credits_deducted=credits_deducted,
                registry_task_id=registry_task_id,
            )
            raise CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(e)}")

    finally:
        # 兜底保障：确保并发锁释放
        if check_lock and not task_submitted_successfully:
            await asyncio.shield(release_concurrency_lock(user_id))
