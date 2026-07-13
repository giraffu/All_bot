import asyncio
from collections.abc import Awaitable, Callable

from src.core.task_core_types import CoreDomainError, TaskSuccessPersistenceResult


async def materialize_successful_task_output(
    *,
    backend_task_id: str,
    registry_task_id: str,
    user_logger,
    is_video: bool,
    result_path: str | None,
    output_width: int | None,
    output_height: int | None,
    output_duration: int | None,
    extra_outputs: dict[str, object] | None,
    download_result_func: Callable[[str], Awaitable[bytes | None]],
    download_video_result_func: Callable[[str], Awaitable[bytes | None]],
    extract_media_metadata_from_bytes_best_effort_func: Callable[..., tuple[int | None, int | None, int | None]],
    extract_media_metadata_from_storage_best_effort_func: Callable[..., Awaitable[tuple[int | None, int | None, int | None]]],
    to_thread_func: Callable[..., Awaitable[object]] = asyncio.to_thread,
) -> TaskSuccessPersistenceResult:
    width = output_width
    height = output_height
    duration = output_duration
    media_kind = "video" if is_video else "image"
    file_ext = "mp4" if is_video else "png"
    media_bytes = await (
        download_video_result_func(backend_task_id)
        if is_video
        else download_result_func(backend_task_id)
    )

    if media_bytes:
        width, height, duration = await to_thread_func(
            extract_media_metadata_from_bytes_best_effort_func,
            media_bytes,
            media_kind,
            file_ext,
            (width, height, duration),
        )
        output_file = await to_thread_func(
            user_logger.save_output_image,
            media_bytes,
            registry_task_id,
            file_ext,
        )
    else:
        if not result_path:
            raise CoreDomainError("任务成功但缺少结果文件路径，无法写入历史")
        width, height, duration = await (
            extract_media_metadata_from_storage_best_effort_func(
                result_path,
                media_kind,
                (width, height, duration),
            )
        )
        output_file = result_path

    return TaskSuccessPersistenceResult(
        media_bytes=media_bytes,
        output_file=output_file,
        width=width,
        height=height,
        duration=duration,
        extra_outputs=extra_outputs if isinstance(extra_outputs, dict) else None,
    )
