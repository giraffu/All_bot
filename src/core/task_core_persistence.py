import asyncio

from src.core.task_core_output_materialization import (
    materialize_successful_task_output as _materialize_successful_task_output_impl,
)
from src.core.task_core_persistence_postprocess import (
    postprocess_successful_task_persistence as _postprocess_successful_task_persistence_impl,
)
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
)
from src.core.task_core_types import TaskSuccessPersistenceResult
from src.logger import UserLogger
from src.services.image_service import image_service


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
    persist_successful_task_result_func=None,
):
    if persist_successful_task_result_func is None:
        persist_successful_task_result_func = persist_successful_task_result

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
    user_logger_factory=UserLogger,
    extract_media_metadata_from_bytes_best_effort_func=extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort_func=extract_media_metadata_from_storage_best_effort,
    schedule_web_history_r2_warmup_func=None,
    materialize_successful_task_output_func=_materialize_successful_task_output_impl,
    refresh_user_group_func=None,
    postprocess_successful_task_persistence_func=_postprocess_successful_task_persistence_impl,
) -> TaskSuccessPersistenceResult:
    if refresh_user_group_func is None and refresh_user_group_after_log:
        from src.services.permission_service import permission_service

        refresh_user_group_func = permission_service.refresh_user_group

    user_logger = user_logger_factory(internal_user_id, username)
    persistence_result = await materialize_successful_task_output_func(
        backend_task_id=backend_task_id,
        registry_task_id=registry_task_id,
        user_logger=user_logger,
        is_video=is_video,
        result_path=result_path,
        output_width=output_width,
        output_height=output_height,
        output_duration=output_duration,
        download_result_func=image_service.download_result,
        download_video_result_func=image_service.download_video_result,
        extract_media_metadata_from_bytes_best_effort_func=extract_media_metadata_from_bytes_best_effort_func,
        extract_media_metadata_from_storage_best_effort_func=extract_media_metadata_from_storage_best_effort_func,
        to_thread_func=asyncio.to_thread,
    )
    media_kind = "video" if is_video else "image"

    await postprocess_successful_task_persistence_func(
        user_logger=user_logger,
        persistence_result=persistence_result,
        registry_task_id=registry_task_id,
        internal_user_id=internal_user_id,
        prompt=prompt,
        task_type=task_type,
        input_images=input_images,
        allow_contribute=allow_contribute,
        source=source,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        media_type=media_kind,
        refresh_user_group_after_log=refresh_user_group_after_log,
        warmup_web_history=warmup_web_history,
        refresh_user_group_func=refresh_user_group_func,
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
    )

    return persistence_result
