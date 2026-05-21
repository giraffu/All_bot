import asyncio
import logging

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
from src.core.task_core_types import CoreDomainError, TaskSuccessPersistenceResult
from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.storage import storage

logger = logging.getLogger(__name__)


def schedule_web_history_r2_warmup(
    *,
    user_id: int,
    task_id: str,
    output_file: str,
    media_type: str,
    source: str,
):
    from src.core import task_core as compat_task_core

    if source != "web" or not user_id or not task_id or not output_file:
        return

    async def _runner():
        compat_logger = compat_task_core.logger
        bucket_name, object_name = compat_task_core.resolve_storage_object(output_file)
        warmup_results = await asyncio.gather(
            compat_task_core.storage.async_copy_to_r2(
                bucket_name,
                object_name,
                build_history_r2_media_key(task_id, output_file),
            ),
            compat_task_core.generate_and_upload_thumbnail(
                output_file,
                media_type,
                build_history_r2_thumbnail_key(task_id, media_type),
            ),
            return_exceptions=True,
        )
        for step_name, result in zip(("copy", "thumbnail"), warmup_results):
            if isinstance(result, Exception):
                compat_logger.warning(
                    "Web history R2 warmup %s failed for task %s user %s: %s",
                    step_name,
                    task_id,
                    user_id,
                    result,
                )

        try:
            await compat_task_core.storage.async_prune_user_web_history_r2_cache(user_id)
        except Exception as exc:
            compat_logger.warning(
                "Web history R2 warmup prune failed for task %s user %s: %s",
                task_id,
                user_id,
                exc,
            )

    asyncio.create_task(_runner())


async def _persist_successful_web_history(
    *,
    backend_task_id: str,
    registry_task_id: str,
    internal_user_id: int,
    username: str,
    prompt: str,
    task_type: str,
    input_images: list[str],
    allow_contribute: bool,
    is_video: bool,
    result_path: str,
    billing_resolution: str | None,
    output_width: int | None,
    output_height: int | None,
    output_duration: int | None,
    requested_duration: int | None,
):
    from src.core import task_core as compat_task_core

    await compat_task_core.persist_successful_task_result(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        result_path=result_path,
        billing_resolution=billing_resolution,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        requested_duration=requested_duration,
        source="web",
        warmup_web_history=True,
    )


async def persist_successful_task_result(
    *,
    backend_task_id: str,
    registry_task_id: str,
    internal_user_id: int,
    username: str,
    prompt: str,
    task_type: str,
    input_images: list[str],
    allow_contribute: bool,
    is_video: bool,
    billing_resolution: str | None,
    requested_duration: int | None,
    output_width: int | None = None,
    output_height: int | None = None,
    output_duration: int | None = None,
    result_path: str | None = None,
    source: str = "bot",
    refresh_user_group_after_log: bool = False,
    warmup_web_history: bool = False,
) -> TaskSuccessPersistenceResult:
    from src.core import task_core as compat_task_core

    user_logger = compat_task_core.UserLogger(internal_user_id, username)
    width = output_width
    height = output_height
    duration = output_duration
    media_kind = "video" if is_video else "image"
    file_ext = "mp4" if is_video else "png"
    media_bytes = await (
        image_service.download_video_result(backend_task_id)
        if is_video
        else image_service.download_result(backend_task_id)
    )

    if media_bytes:
        width, height, duration = await asyncio.to_thread(
            compat_task_core.extract_media_metadata_from_bytes_best_effort,
            media_bytes,
            media_kind,
            file_ext,
            (width, height, duration),
        )
        output_file = await asyncio.to_thread(
            user_logger.save_output_image,
            media_bytes,
            registry_task_id,
            file_ext,
        )
    else:
        if not result_path:
            raise CoreDomainError("任务成功但缺少结果文件路径，无法写入历史")
        width, height, duration = await compat_task_core.extract_media_metadata_from_storage_best_effort(
            result_path,
            media_kind,
            (width, height, duration),
        )
        output_file = result_path

    await user_logger.log_task(
        prompt,
        input_images,
        output_file,
        task_id=registry_task_id,
        type=task_type,
        allow_contribute=allow_contribute,
        source=source,
        billing_resolution=billing_resolution,
        width=width,
        height=height,
        duration=duration,
        requested_duration=requested_duration,
    )

    if refresh_user_group_after_log:
        from src.services.permission_service import permission_service

        await permission_service.refresh_user_group(internal_user_id)

    if warmup_web_history and output_file:
        compat_task_core.schedule_web_history_r2_warmup(
            user_id=internal_user_id,
            task_id=registry_task_id,
            output_file=output_file,
            media_type=media_kind,
            source=source,
        )

    return TaskSuccessPersistenceResult(
        media_bytes=media_bytes,
        output_file=output_file,
        width=width,
        height=height,
        duration=duration,
    )
