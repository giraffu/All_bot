import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from src.media_paths import build_r2_media_materialization_plan, resolve_storage_object
from src.media_processor import generate_and_upload_thumbnail
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
        started = time.monotonic()
        plan = build_r2_media_materialization_plan(
            task_id=task_id,
            output_file=output_file,
            media_type=media_type,
        )
        step_names = []
        warmup_steps = []
        if plan.original_copy_key:
            bucket_name, object_name = resolve_storage_object_func(output_file)
            step_names.append("copy")
            warmup_steps.append(
                copy_to_r2_func(bucket_name, object_name, plan.original_copy_key)
            )
        step_names.append("thumbnail")
        warmup_steps.append(
            generate_and_upload_thumbnail_func(
                output_file,
                media_type,
                plan.thumbnail_key,
            )
        )
        warmup_results = await asyncio.gather(*warmup_steps, return_exceptions=True)
        result_by_step = dict(zip(step_names, warmup_results))
        for step_name, result in result_by_step.items():
            if isinstance(result, Exception):
                logger.warning(
                    "History R2 warmup %s failed for task %s user %s source %s: %s",
                    step_name,
                    task_id,
                    user_id,
                    source,
                    result,
                )
        event = (
            "history_r2_compatibility_warmup_completed"
            if plan.uses_history_compatibility
            else "canonical_r2_media_materialization_completed"
        )
        logger.info(
            event,
            extra={
                "event": event,
                "task_id": task_id,
                "source": source,
                "media_type": media_type,
                "history_compatibility_used": plan.uses_history_compatibility,
                "telemetry_key": (
                    "compat.r2.history_media_prefix"
                    if plan.uses_history_compatibility
                    else None
                ),
                "copy_required": plan.original_copy_key is not None,
                "copy_succeeded": not isinstance(
                    result_by_step.get("copy"), Exception
                ),
                "thumbnail_succeeded": not isinstance(
                    result_by_step["thumbnail"], Exception
                ),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            },
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
