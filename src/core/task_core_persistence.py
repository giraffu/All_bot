import asyncio

from src.core.task_core_persistence_flow import (
    persist_successful_task_result_flow as _persist_successful_task_result_flow_impl,
)
from src.core.task_core_types import (
    TaskPersistencePostprocessPlan,
    TaskSuccessPersistenceResult,
)


def get_default_task_core_persistence_dependencies():
    from src.task_core_persistence_defaults import (
        build_runtime_default_task_core_persistence_dependencies,
    )

    return build_runtime_default_task_core_persistence_dependencies()


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
    extra_outputs: dict[str, object] | None = None,
    billing_resolution: str | None,
    output_width: int | None,
    output_height: int | None,
    output_duration: int | None,
    requested_duration: int | None,
    persist_successful_task_result_func=None,
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
):
    if persist_successful_task_result_func is None:
        persist_successful_task_result_func = persist_successful_task_result
    if postprocess_plan is None:
        postprocess_plan = TaskPersistencePostprocessPlan(
            source="web",
            warmup_web_history=True,
        )

    await persist_successful_task_result_func(
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
        extra_outputs=extra_outputs,
        billing_resolution=billing_resolution,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        requested_duration=requested_duration,
        postprocess_plan=postprocess_plan,
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
    extra_outputs: dict[str, object] | None = None,
    source: str = "bot",
    refresh_user_group_after_log: bool = False,
    warmup_web_history: bool = False,
    user_logger_factory=None,
    download_result_func=None,
    download_video_result_func=None,
    extract_media_metadata_from_bytes_best_effort_func=None,
    extract_media_metadata_from_storage_best_effort_func=None,
    schedule_web_history_r2_warmup_func=None,
    materialize_successful_task_result_flow_func=None,
    materialize_successful_task_output_func=None,
    to_thread_func=None,
    refresh_user_group_func=None,
    postprocess_successful_task_persistence_func=None,
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
    dependencies=None,
) -> TaskSuccessPersistenceResult:
    if materialize_successful_task_result_flow_func is None:
        materialize_successful_task_result_flow_func = (
            _persist_successful_task_result_flow_impl
        )
    needs_default_dependencies = any(
        value is None
        for value in (
            user_logger_factory,
            download_result_func,
            download_video_result_func,
            extract_media_metadata_from_bytes_best_effort_func,
            extract_media_metadata_from_storage_best_effort_func,
            schedule_web_history_r2_warmup_func,
            refresh_user_group_func,
        )
    )
    if needs_default_dependencies:
        dependencies = dependencies or get_default_task_core_persistence_dependencies()
        if user_logger_factory is None:
            user_logger_factory = dependencies.user_logger_factory
        if download_result_func is None:
            download_result_func = dependencies.download_result_func
        if download_video_result_func is None:
            download_video_result_func = dependencies.download_video_result_func
        if extract_media_metadata_from_bytes_best_effort_func is None:
            extract_media_metadata_from_bytes_best_effort_func = (
                dependencies.extract_media_metadata_from_bytes_best_effort_func
            )
        if extract_media_metadata_from_storage_best_effort_func is None:
            extract_media_metadata_from_storage_best_effort_func = (
                dependencies.extract_media_metadata_from_storage_best_effort_func
            )
        if schedule_web_history_r2_warmup_func is None:
            schedule_web_history_r2_warmup_func = (
                dependencies.schedule_web_history_r2_warmup_func
            )
        if refresh_user_group_func is None:
            refresh_user_group_func = dependencies.refresh_user_group_func
    if to_thread_func is None:
        to_thread_func = asyncio.to_thread
    if postprocess_plan is None:
        postprocess_plan = TaskPersistencePostprocessPlan(
            source=source,
            refresh_user_group_after_log=refresh_user_group_after_log,
            warmup_web_history=warmup_web_history,
        )

    return await materialize_successful_task_result_flow_func(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        source=source,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        result_path=result_path,
        extra_outputs=extra_outputs,
        refresh_user_group_after_log=refresh_user_group_after_log,
        warmup_web_history=warmup_web_history,
        postprocess_plan=postprocess_plan,
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
        user_logger_factory=user_logger_factory,
        download_result_func=download_result_func,
        download_video_result_func=download_video_result_func,
        extract_media_metadata_from_bytes_best_effort_func=(
            extract_media_metadata_from_bytes_best_effort_func
        ),
        extract_media_metadata_from_storage_best_effort_func=(
            extract_media_metadata_from_storage_best_effort_func
        ),
        materialize_successful_task_output_func=(
            materialize_successful_task_output_func
        ),
        refresh_user_group_func=refresh_user_group_func,
        to_thread_func=to_thread_func,
        postprocess_successful_task_persistence_func=(
            postprocess_successful_task_persistence_func
        ),
    )


async def persist_successful_task_result_default(
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
    extra_outputs: dict[str, object] | None = None,
    source: str = "bot",
    refresh_user_group_after_log: bool = False,
    warmup_web_history: bool = False,
    postprocess_plan: TaskPersistencePostprocessPlan | None = None,
    dependencies=None,
) -> TaskSuccessPersistenceResult:
    dependencies = dependencies or get_default_task_core_persistence_dependencies()
    return await persist_successful_task_result(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        is_video=is_video,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        result_path=result_path,
        extra_outputs=extra_outputs,
        source=source,
        refresh_user_group_after_log=refresh_user_group_after_log,
        warmup_web_history=warmup_web_history,
        postprocess_plan=postprocess_plan,
        dependencies=dependencies,
    )


async def persist_successful_web_history_default(
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
    extra_outputs: dict[str, object] | None = None,
    billing_resolution: str | None,
    output_width: int | None,
    output_height: int | None,
    output_duration: int | None,
    requested_duration: int | None,
):
    await _persist_successful_web_history(
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
        extra_outputs=extra_outputs,
        billing_resolution=billing_resolution,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        requested_duration=requested_duration,
        persist_successful_task_result_func=persist_successful_task_result_default,
    )
