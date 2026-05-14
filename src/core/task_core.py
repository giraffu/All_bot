import asyncio
import logging
import os
import httpx
from typing import Optional, Tuple

from config import MINIO_BUCKET
from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    resolve_storage_object,
)
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
    generate_and_upload_thumbnail,
)
from src.core.video_billing import normalize_requested_billing_resolution
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.storage import storage
from src.services.task_registry import TaskRegistry

logger = logging.getLogger(__name__)


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


class CoreDomainError(Exception):
    pass


class InsufficientCreditsError(CoreDomainError):
    pass


class ConcurrencyLimitError(CoreDomainError):
    pass


def _infer_requested_output_metadata(
    inputs: dict,
) -> Tuple[int | None, int | None, int | None]:
    output_width = None
    output_height = None
    output_duration = None

    resolution = inputs.get("resolution")
    if resolution is not None:
        res_text = str(resolution).replace("p", "")
        if "x" in res_text:
            try:
                width_text, height_text = res_text.split("x", 1)
                output_width = int(width_text)
                output_height = int(height_text)
            except ValueError:
                output_width = None
                output_height = None
        else:
            try:
                output_width = int(res_text)
            except ValueError:
                output_width = None

    duration_value = inputs.get("duration")
    if duration_value is not None:
        try:
            output_duration = int(str(duration_value).replace("s", ""))
        except ValueError:
            output_duration = None

    return output_width, output_height, output_duration


def _infer_requested_billing_resolution(
    inputs: dict, task_type: str
) -> str | None:
    return normalize_requested_billing_resolution(inputs.get("resolution"), task_type)


def schedule_web_history_r2_warmup(
    *,
    user_id: int,
    task_id: str,
    output_file: str,
    media_type: str,
    source: str,
):
    if source != "web" or not user_id or not task_id or not output_file:
        return

    async def _runner():
        bucket_name, object_name = resolve_storage_object(output_file)
        warmup_results = await asyncio.gather(
            storage.async_copy_to_r2(
                bucket_name,
                object_name,
                build_history_r2_media_key(task_id, output_file),
            ),
            generate_and_upload_thumbnail(
                output_file,
                media_type,
                build_history_r2_thumbnail_key(task_id, media_type),
            ),
            return_exceptions=True,
        )
        for step_name, result in zip(("copy", "thumbnail"), warmup_results):
            if isinstance(result, Exception):
                logger.warning(
                    "Web history R2 warmup %s failed for task %s user %s: %s",
                    step_name,
                    task_id,
                    user_id,
                    result,
                )

        try:
            await storage.async_prune_user_web_history_r2_cache(user_id)
        except Exception as exc:
            logger.warning(
                "Web history R2 warmup prune failed for task %s user %s: %s",
                task_id,
                user_id,
                exc,
            )

    asyncio.create_task(_runner())


async def monitor_task_and_release_lock(
    task_id: str,
    internal_user_id: int,
    username: str,
    registry_task_id: str,
    is_video: bool = False,
    task_type: str = "",
    prompt: str = "",
    input_images: list = None,
    allow_contribute: bool = True,
    cost: int = 0,
    billing_resolution: str | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
    output_duration: int | None = None,
):
    """
    Background task to monitor progress and release concurrency lock.
    """
    import asyncio

    if input_images is None:
        input_images = []

    final_status = None
    result_path = None
    try:
        async for progress in image_service.monitor_progress(task_id, is_video):
            if progress.get("status") in [
                "done",
                "error",
                "cancelled",
                "success",
                "failed",
            ]:
                final_status = progress.get("status")
                result_path = progress.get("result_path")
                break
    except asyncio.CancelledError:
        logger.error(f"Task monitor {task_id} cancelled.")
        final_status = "cancelled"
    except Exception as e:
        logger.error(f"Background monitoring error for task {task_id}: {e}")
        final_status = "error"
    finally:
        # Save to History if successful
        if final_status == "done" and result_path:
            try:
                user_logger = UserLogger(internal_user_id, username)
                history_output_file = ""
                width = output_width
                height = output_height
                duration = output_duration
                media_bytes = await (
                    image_service.download_video_result(task_id)
                    if is_video
                    else image_service.download_result(task_id)
                )
                if media_bytes:
                    width, height, duration = await asyncio.to_thread(
                        extract_media_metadata_from_bytes_best_effort,
                        media_bytes,
                        "video" if is_video else "image",
                        "mp4" if is_video else "png",
                        (width, height, duration),
                    )
                    ext = "mp4" if is_video else "png"
                    saved_output_image = await asyncio.to_thread(
                        user_logger.save_output_image, media_bytes, task_id, ext
                    )
                    await user_logger.log_task(
                        prompt,
                        input_images,
                        saved_output_image,
                        task_id=task_id,
                        type=task_type,
                        allow_contribute=allow_contribute,
                        source="web",
                        billing_resolution=billing_resolution,
                        width=width,
                        height=height,
                        duration=duration,
                    )
                    history_output_file = saved_output_image
                else:
                    width, height, duration = await extract_media_metadata_from_storage_best_effort(
                        result_path,
                        "video" if is_video else "image",
                        (width, height, duration),
                    )
                    await user_logger.log_task(
                        prompt,
                        input_images,
                        result_path,
                        task_id=task_id,
                        type=task_type,
                        allow_contribute=allow_contribute,
                        source="web",
                        billing_resolution=billing_resolution,
                        width=width,
                        height=height,
                        duration=duration,
                    )
                    history_output_file = result_path

                if history_output_file:
                    schedule_web_history_r2_warmup(
                        user_id=internal_user_id,
                        task_id=task_id,
                        output_file=history_output_file,
                        media_type="video" if is_video else "image",
                        source="web",
                    )
            except Exception as log_err:
                logger.error(f"Failed to log task history for {task_id}: {log_err}")
        else:
            if cost > 0:
                try:
                    await asyncio.shield(
                        refund_credits(
                            internal_user_id,
                            cost,
                            task_type=f"refund_async_failed_{final_status}",
                            username=username,
                        )
                    )
                except Exception as refund_err:
                    logger.critical(
                        f"Async refund failed for user {internal_user_id}: {refund_err}"
                    )

        # Use asyncio.create_task for the release to avoid being cancelled
        try:
            await release_concurrency_lock(internal_user_id)
        except Exception as e:
            logger.error(
                f"Failed to release concurrency lock for {internal_user_id}: {e}"
            )

        if registry_task_id:
            try:
                await TaskRegistry.remove_task(registry_task_id)
            except Exception as e:
                logger.error(f"Failed to remove registry task {registry_task_id}: {e}")


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

    if is_video_task:
        resolution = inputs.get("resolution", "512p")
        duration = inputs.get("duration", "5s")

        # Safely parse resolution which might be '1024p' or '1280x704'
        res_str = str(resolution).replace("p", "")
        if "x" in res_str:
            try:
                w, h = map(int, res_str.split("x"))
                res_val = max(w, h)
            except ValueError:
                res_val = 512
        else:
            try:
                res_val = int(res_str)
            except ValueError:
                res_val = 512

        # Safely parse duration
        dur_str = str(duration).replace("s", "")
        try:
            dur_val = int(dur_str)
        except ValueError:
            dur_val = 5

        if task_type != "ltx_video" and res_val >= 1024 and dur_val >= 10:
            raise CoreDomainError(
                "Cannot select 1024p resolution and 10s duration simultaneously due to high resource usage."
            )

    if check_lock:
        can_run, err = await check_concurrency_lock(user_id)
        if not can_run:
            raise ConcurrencyLimitError(err)

    task_submitted_successfully = False
    credits_deducted = False

    try:
        if deduct_quota:
            success, err = await check_and_deduct_credits(
                user_id, cost, task_type, username
            )
            if not success:
                raise InsufficientCreditsError(err)
            credits_deducted = True

        try:
            priority, _, _ = await get_user_priority_and_identity(user_id)
            final_priority = min(base_priority + priority, 100)

            prompts_config = load_prompts()
            prompt = inputs.get("prompt")
            # Only use default prompt if user didn't provide one
            if not prompt or prompt.strip() == "":
                prompt = prompts_config.get(task_type, task_type)

            allow_contribute = not is_template
            registry_task_id = None
            saved_inputs = []
            log_prompt = prompt

            # 1. 统一处理输入图片/视频上传
            paths_to_upload = strategy.get_file_paths_to_upload(inputs)
            saved_inputs = []
            user_logger = UserLogger(user_id, username)
            for path in paths_to_upload:
                processed_img = await _process_input_path(user_logger, path)
                if processed_img:
                    saved_inputs.append(processed_img)

            inputs["saved_input_images"] = saved_inputs
            inputs["prompt"] = prompt  # Ensure updated prompt is in inputs
            metadata = strategy.get_metadata(inputs)

            # 2. 统一落库 TaskRegistry
            output_width = None
            output_height = None
            output_duration = None
            billing_resolution = None
            if is_video_task:
                output_width, output_height, output_duration = (
                    _infer_requested_output_metadata(inputs)
                )
                billing_resolution = _infer_requested_billing_resolution(
                    inputs, task_type
                )

            registry_task_id = await TaskRegistry.add_task(
                task_id=task_id,
                user_id=user_id,
                username=username,
                cost=cost,
                task_type=task_type,
                prompt=log_prompt,
                saved_input_images=metadata.get("saved_inputs", saved_inputs),
                is_video=is_video_task,
                priority=final_priority,
                allow_contribute=allow_contribute,
                metadata=metadata,
            )

            # 3. 统一分发到后端 worker
            try:
                backend_task_id = await dispatch_to_worker(
                    task_id, task_type, inputs, final_priority
                )
                if registry_task_id and backend_task_id:
                    await TaskRegistry.update_backend_task_id(
                        registry_task_id, backend_task_id
                    )
                if not backend_task_id:
                    raise Exception("Failed to submit task to backend API.")
                success = True
                msg = "Task submitted successfully"
            except Exception as e:
                logger.error(f"Dispatch to worker failed: {e}", exc_info=True)
                if registry_task_id:
                    with contextlib.suppress(Exception):
                        await TaskRegistry.mark_task_status(registry_task_id, "failed")
                success = False
                backend_task_id = None
                error_msg = str(e)
                if any(
                    kw in error_msg
                    for kw in [
                        "Circuit is open",
                        "All connection attempts failed",
                        "Connection refused",
                        "timeout",
                        "ConnectError",
                    ]
                ):
                    msg = "当前服务器繁忙，请稍后再试"
                else:
                    msg = f"System error: {error_msg}"
            if not success or not backend_task_id:
                raise CoreDomainError(msg)

            if client_type == "web":
                try:
                    asyncio.create_task(
                        monitor_task_and_release_lock(
                            task_id=backend_task_id,
                            internal_user_id=user_id,
                            username=username,
                            registry_task_id=registry_task_id,
                            is_video=is_video_task,
                            task_type=task_type,
                            prompt=log_prompt,
                            input_images=saved_inputs,
                            allow_contribute=allow_contribute,
                            cost=cost if deduct_quota else 0,
                            billing_resolution=billing_resolution,
                            output_width=output_width,
                            output_height=output_height,
                            output_duration=output_duration,
                        )
                    )
                except Exception as e:
                    # 如果监控挂载失败，由外层的 Saga 补偿机制和 finally 统一处理退款和释放锁
                    raise CoreDomainError(f"后台监控挂载失败: {e}")

            if source_post_id:
                from src.core.gallery_core import record_apply_interaction

                asyncio.create_task(record_apply_interaction(user_id, source_post_id))

            task_submitted_successfully = True

            return {
                "task_id": backend_task_id,
                "registry_task_id": registry_task_id,
                "cost": cost,
                "saved_inputs": saved_inputs,
            }

        except Exception as e:
            # Saga 补偿机制触发
            logger.error(f"Saga Execute Failed: {e}")
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
                        user_id, cost, f"Task Failed: {str(e)}", username
                    )

            with contextlib.suppress(Exception):
                await asyncio.shield(TaskRegistry.remove_task(task_id))

            raise CoreDomainError(f"系统派发失败，灵石已全额退还。错误: {str(e)}")

    finally:
        # 兜底保障：确保并发锁释放
        if check_lock and not task_submitted_successfully:
            await asyncio.shield(release_concurrency_lock(user_id))


async def get_system_task_stats() -> Tuple[dict, dict]:
    """
    获取全系统任务统计信息。
    返回 (active_tasks, user_concurrencies)
    """
    from src.services.redis_client import redis_client

    active_tasks = await redis_client.get_active_tasks()
    user_concurrencies = await redis_client.get_all_user_concurrencies()
    return active_tasks, user_concurrencies


async def force_terminate_task(task_id: str, user_id: Optional[int] = None):
    """
    强制终止一个活跃任务并释放对应的用户锁
    """
    from src.services.redis_client import redis_client

    if user_id:
        await release_concurrency_lock(user_id)
    await redis_client.remove_active_task(task_id)


async def sync_user_concurrency(user_id: int, actual_count: int):
    """
    同步用户并发锁到指定数量，当 actual_count 为 0 时删除锁
    """
    from config import REDIS_PREFIX
    from src.services.redis_client import redis_client

    key = f"{REDIS_PREFIX}user_concurrency:{user_id}"

    if actual_count > 0:
        await redis_client.redis.set(key, actual_count)
        await redis_client.redis.expire(key, 3600)
    else:
        await redis_client.redis.delete(key)


async def cancel_user_task(task_id: str, user_id: int):
    """供用户主动调用的任务撤销逻辑"""
    from src.services.redis_client import redis_client
    tasks = await redis_client.get_active_tasks()
    if not tasks or task_id not in tasks:
        raise CoreDomainError("任务不存在或已脱离排队阶段")
    
    task = tasks[task_id]
    if task.get("user_id") != user_id:
        raise CoreDomainError("无权撤销该任务")

    # 仅调用中控移除排队，触发 cancelled 事件广播
    from src.api_client import api_client
    try:
        await api_client.cancel_task(task_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise CoreDomainError("任务已在执行中，无法撤销")
        raise CoreDomainError(f"撤销请求失败: HTTP {e.response.status_code}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"中控取消任务网络异常: {e}")
        raise CoreDomainError("撤销请求失败，请稍后重试")
