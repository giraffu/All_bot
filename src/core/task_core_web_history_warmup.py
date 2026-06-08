import asyncio
import logging
from collections.abc import Awaitable, Callable

from src.core.media_paths import resolve_storage_object
from src.core.media_paths import build_history_r2_media_key, build_history_r2_thumbnail_key
from src.core.media_processor import generate_and_upload_thumbnail
from src.core.task_core_default_dependencies import (
    build_default_task_core_warmup_dependencies,
)


def schedule_web_history_r2_warmup(
    *,
    user_id: int,
    task_id: str,
    output_file: str,
    media_type: str,
    source: str,
    resolve_storage_object_func: Callable[[str], tuple[str, str]],
    copy_to_r2_func: Callable[[str, str, str], Awaitable[object]],
    generate_and_upload_thumbnail_func: Callable[[str, str, str], Awaitable[object]],
    prune_user_web_history_r2_cache_func: Callable[[int], Awaitable[object]],
    logger: logging.Logger,
    create_task_func: Callable[[Awaitable[None]], object] | None = None,
):
    if create_task_func is None:
        create_task_func = asyncio.create_task

    if (
        source not in {"web", "bot"}
        or not user_id
        or not task_id
        or not output_file
    ):
        return

    async def _runner():
        bucket_name, object_name = resolve_storage_object_func(output_file)
        warmup_results = await asyncio.gather(
            copy_to_r2_func(
                bucket_name,
                object_name,
                build_history_r2_media_key(task_id, output_file),
            ),
            generate_and_upload_thumbnail_func(
                output_file,
                media_type,
                build_history_r2_thumbnail_key(task_id, media_type),
            ),
            return_exceptions=True,
        )
        for step_name, result in zip(("copy", "thumbnail"), warmup_results):
            if isinstance(result, Exception):
                logger.warning(
                    "History R2 warmup %s failed for task %s user %s source %s: %s",
                    step_name,
                    task_id,
                    user_id,
                    source,
                    result,
                )

        if source == "web":
            try:
                await prune_user_web_history_r2_cache_func(user_id)
            except Exception as exc:
                logger.warning(
                    "Web history R2 warmup prune failed for task %s user %s: %s",
                    task_id,
                    user_id,
                    exc,
                )

    warmup_coro = _runner()
    try:
        create_task_func(warmup_coro, name="task-core-web-history-warmup")
    except TypeError:
        create_task_func(warmup_coro)


def schedule_web_history_r2_warmup_default(
    *,
    user_id: int,
    task_id: str,
    output_file: str,
    media_type: str,
    source: str,
    logger_override: logging.Logger | None = None,
):
    dependencies = build_default_task_core_warmup_dependencies(
        create_task_func=asyncio.create_task,
        resolve_storage_object_func=resolve_storage_object,
        generate_and_upload_thumbnail_func=generate_and_upload_thumbnail,
        logger_override=logger_override or logging.getLogger(__name__),
    )
    return schedule_web_history_r2_warmup(
        user_id=user_id,
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        source=source,
        resolve_storage_object_func=dependencies.resolve_storage_object_func,
        copy_to_r2_func=dependencies.copy_to_r2_func,
        generate_and_upload_thumbnail_func=(
            dependencies.generate_and_upload_thumbnail_func
        ),
        prune_user_web_history_r2_cache_func=(
            dependencies.prune_user_web_history_r2_cache_func
        ),
        logger=dependencies.logger,
        create_task_func=dependencies.create_task_func,
    )
