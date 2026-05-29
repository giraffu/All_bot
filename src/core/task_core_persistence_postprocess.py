from collections.abc import Awaitable, Callable

from src.core.task_core_types import TaskSuccessPersistenceResult


async def postprocess_successful_task_persistence(
    *,
    user_logger,
    persistence_result: TaskSuccessPersistenceResult,
    registry_task_id: str,
    internal_user_id: int,
    prompt: str,
    task_type: str,
    input_images: list[str],
    allow_contribute: bool,
    source: str,
    billing_resolution: str | None,
    requested_duration: int | None,
    media_type: str,
    refresh_user_group_after_log: bool,
    warmup_web_history: bool,
    refresh_user_group_func: Callable[[int], Awaitable[object]] | None,
    schedule_web_history_r2_warmup_func: Callable[..., object],
):
    await user_logger.log_task(
        prompt,
        input_images,
        persistence_result.output_file,
        task_id=registry_task_id,
        type=task_type,
        allow_contribute=allow_contribute,
        source=source,
        billing_resolution=billing_resolution,
        width=persistence_result.width,
        height=persistence_result.height,
        duration=persistence_result.duration,
        requested_duration=requested_duration,
        extra_outputs=persistence_result.extra_outputs,
    )

    if refresh_user_group_after_log and refresh_user_group_func is not None:
        await refresh_user_group_func(internal_user_id)

    if warmup_web_history and persistence_result.output_file:
        schedule_web_history_r2_warmup_func(
            user_id=internal_user_id,
            task_id=registry_task_id,
            output_file=persistence_result.output_file,
            media_type=media_type,
            source=source,
        )
