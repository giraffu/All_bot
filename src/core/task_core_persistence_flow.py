import asyncio

from src.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
)
from src.core.task_core_output_materialization import (
    materialize_successful_task_output as _materialize_successful_task_output_impl,
)
from src.core.task_core_persistence_postprocess import (
    postprocess_successful_task_persistence as _postprocess_successful_task_persistence_impl,
)
from src.core.task_core_types import (
    CoreDomainError,
    TaskPersistencePostprocessPlan,
    TaskSuccessPersistenceResult,
)


async def persist_successful_task_result_flow(
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
    result_asset: dict[str, object] | None = None,
    extra_outputs: dict[str, object] | None = None,
    source: str = "bot",
    refresh_user_group_after_log: bool = False,
    warmup_web_history: bool = False,
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
    user_logger_factory=None,
    download_result_func=None,
    download_video_result_func=None,
    extract_media_metadata_from_bytes_best_effort_func=None,
    extract_media_metadata_from_storage_best_effort_func=None,
    schedule_web_history_r2_warmup_func=None,
    materialize_successful_task_output_func=None,
    refresh_user_group_func=None,
    to_thread_func=None,
    postprocess_successful_task_persistence_func=None,
) -> TaskSuccessPersistenceResult:
    materialize_successful_task_output_func = (
        materialize_successful_task_output_func
        or _materialize_successful_task_output_impl
    )
    postprocess_successful_task_persistence_func = (
        postprocess_successful_task_persistence_func
        or _postprocess_successful_task_persistence_impl
    )
    if user_logger_factory is None:
        raise CoreDomainError("user_logger_factory is required")
    if extract_media_metadata_from_bytes_best_effort_func is None:
        extract_media_metadata_from_bytes_best_effort_func = (
            extract_media_metadata_from_bytes_best_effort
        )
    if extract_media_metadata_from_storage_best_effort_func is None:
        extract_media_metadata_from_storage_best_effort_func = (
            extract_media_metadata_from_storage_best_effort
        )
    if to_thread_func is None:
        to_thread_func = asyncio.to_thread
    if postprocess_plan is None:
        postprocess_plan = TaskPersistencePostprocessPlan(
            source=source,
            refresh_user_group_after_log=refresh_user_group_after_log,
            warmup_web_history=warmup_web_history,
        )

    user_logger = user_logger_factory(internal_user_id, username)
    persistence_result = await materialize_successful_task_output_func(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        user_logger=user_logger,
        is_video=is_video,
        result_path=result_path,
        result_asset=result_asset,
        extra_outputs=extra_outputs,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        download_result_func=download_result_func,
        download_video_result_func=download_video_result_func,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort_func
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort_func
        ),
        to_thread_func=to_thread_func,
    )
    media_kind = "video" if is_video else "image"

    if postprocess_plan.record_history:
        await postprocess_successful_task_persistence_func(
            user_logger=user_logger,
            persistence_result=persistence_result,
            registry_task_id=registry_task_id,
            internal_user_id=internal_user_id,
            prompt=prompt,
            task_type=task_type,
            input_images=input_images,
            allow_contribute=allow_contribute,
            source=postprocess_plan.source,
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            media_type=media_kind,
            refresh_user_group_after_log=postprocess_plan.refresh_user_group_after_log,
            warmup_web_history=postprocess_plan.warmup_web_history,
            refresh_user_group_func=refresh_user_group_func,
            schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
        )

    return persistence_result
