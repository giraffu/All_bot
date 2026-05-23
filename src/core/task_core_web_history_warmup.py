import asyncio
import logging
from collections.abc import Awaitable, Callable

from src.core.media_paths import build_history_r2_media_key, build_history_r2_thumbnail_key


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

    if source != "web" or not user_id or not task_id or not output_file:
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
                    "Web history R2 warmup %s failed for task %s user %s: %s",
                    step_name,
                    task_id,
                    user_id,
                    result,
                )

        try:
            await prune_user_web_history_r2_cache_func(user_id)
        except Exception as exc:
            logger.warning(
                "Web history R2 warmup prune failed for task %s user %s: %s",
                task_id,
                user_id,
                exc,
            )

    create_task_func(_runner())
