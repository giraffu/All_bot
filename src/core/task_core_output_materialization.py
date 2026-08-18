import asyncio
from collections.abc import Awaitable, Callable
import re

from src.core.media_paths import normalize_storage_object_key
from src.core.task_core_types import CoreDomainError, TaskSuccessPersistenceResult


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _trusted_durable_result_metadata(
    *,
    backend_task_id: str,
    result_path: str | None,
    result_asset: dict[str, object] | None,
    is_video: bool,
) -> tuple[str, int, int, int | None] | None:
    if not isinstance(result_asset, dict):
        return None
    canonical_path = normalize_storage_object_key(str(result_path or ""))
    expected_prefix = f"task-results/{backend_task_id}/"
    object_key = normalize_storage_object_key(
        str(result_asset.get("object_key") or "")
    )
    if (
        not canonical_path.startswith(expected_prefix)
        or object_key != canonical_path
    ):
        return None
    sha256 = str(result_asset.get("sha256") or "").strip().lower()
    content_type = str(result_asset.get("content_type") or "").strip().lower()
    try:
        byte_size = int(result_asset.get("byte_size"))
        width = int(result_asset.get("width"))
        height = int(result_asset.get("height"))
    except (TypeError, ValueError):
        return None
    expected_media_prefix = "video/" if is_video else "image/"
    if (
        not _SHA256.fullmatch(sha256)
        or byte_size < 0
        or width <= 0
        or height <= 0
        or not content_type.startswith(expected_media_prefix)
    ):
        return None
    duration: int | None = None
    if is_video:
        try:
            actual_duration = float(result_asset.get("duration"))
        except (TypeError, ValueError):
            return None
        if actual_duration <= 0:
            return None
        duration = max(1, round(actual_duration))
    return canonical_path, width, height, duration


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
    result_asset: dict[str, object] | None = None,
    to_thread_func: Callable[..., Awaitable[object]] = asyncio.to_thread,
) -> TaskSuccessPersistenceResult:
    width = output_width
    height = output_height
    duration = output_duration
    media_kind = "video" if is_video else "image"
    file_ext = "mp4" if is_video else "png"
    trusted_metadata = _trusted_durable_result_metadata(
        backend_task_id=backend_task_id,
        result_path=result_path,
        result_asset=result_asset,
        is_video=is_video,
    )
    if trusted_metadata is not None:
        output_file, width, height, duration = trusted_metadata
        return TaskSuccessPersistenceResult(
            media_bytes=None,
            output_file=output_file,
            width=width,
            height=height,
            duration=duration,
            extra_outputs=extra_outputs if isinstance(extra_outputs, dict) else None,
        )
    media_bytes = await (
        download_video_result_func(backend_task_id)
        if is_video
        else download_result_func(backend_task_id)
    )
    canonical_result_path = normalize_storage_object_key(str(result_path or ""))
    durable_result_prefix = f"task-results/{backend_task_id}/"

    if media_bytes:
        width, height, duration = await to_thread_func(
            extract_media_metadata_from_bytes_best_effort_func,
            media_bytes,
            media_kind,
            file_ext,
            (width, height, duration),
        )
        if canonical_result_path.startswith(durable_result_prefix):
            output_file = canonical_result_path
        else:
            output_file = await to_thread_func(
                user_logger.save_output_image,
                media_bytes,
                backend_task_id,
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
