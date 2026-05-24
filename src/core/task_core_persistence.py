import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.core.task_core_persistence_flow import (
    persist_successful_task_result_flow as _persist_successful_task_result_flow_impl,
)
from src.core.task_core_service_providers import get_task_core_image_service
from src.core.media_processor import (
    extract_media_metadata_from_bytes_best_effort,
    extract_media_metadata_from_storage_best_effort,
)
from src.core.task_core_types import TaskSuccessPersistenceResult
from src.logger import UserLogger


@dataclass(frozen=True)
class TaskCorePersistenceMaterializationDependencies:
    download_result_func: Callable[..., Awaitable[Any]]
    download_video_result_func: Callable[..., Awaitable[Any]]
    to_thread_func: Callable[..., Awaitable[Any]]


def _build_task_core_persistence_materialization_dependencies(
    *,
    download_result_func=None,
    download_video_result_func=None,
    to_thread_func=None,
) -> TaskCorePersistenceMaterializationDependencies:
    if to_thread_func is None:
        to_thread_func = asyncio.to_thread

    image_service_impl = get_task_core_image_service()
    return TaskCorePersistenceMaterializationDependencies(
        download_result_func=download_result_func or image_service_impl.download_result,
        download_video_result_func=(
            download_video_result_func or image_service_impl.download_video_result
        ),
        to_thread_func=to_thread_func,
    )


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
    user_logger_factory=None,
    download_result_func=None,
    download_video_result_func=None,
    extract_media_metadata_from_bytes_best_effort_func=None,
    extract_media_metadata_from_storage_best_effort_func=None,
    schedule_web_history_r2_warmup_func=None,
    materialize_successful_task_result_flow_func=None,
    materialize_successful_task_output_func=None,
    refresh_user_group_func=None,
    postprocess_successful_task_persistence_func=None,
) -> TaskSuccessPersistenceResult:
    if materialize_successful_task_result_flow_func is None:
        materialize_successful_task_result_flow_func = (
            _persist_successful_task_result_flow_impl
        )
    if user_logger_factory is None:
        user_logger_factory = UserLogger
    if extract_media_metadata_from_bytes_best_effort_func is None:
        extract_media_metadata_from_bytes_best_effort_func = (
            extract_media_metadata_from_bytes_best_effort
        )
    if extract_media_metadata_from_storage_best_effort_func is None:
        extract_media_metadata_from_storage_best_effort_func = (
            extract_media_metadata_from_storage_best_effort
        )

    materialization_dependencies = (
        _build_task_core_persistence_materialization_dependencies(
            download_result_func=download_result_func,
            download_video_result_func=download_video_result_func,
        )
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
        refresh_user_group_after_log=refresh_user_group_after_log,
        warmup_web_history=warmup_web_history,
        schedule_web_history_r2_warmup_func=schedule_web_history_r2_warmup_func,
        user_logger_factory=user_logger_factory,
        download_result_func=materialization_dependencies.download_result_func,
        download_video_result_func=(
            materialization_dependencies.download_video_result_func
        ),
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
        to_thread_func=materialization_dependencies.to_thread_func,
        postprocess_successful_task_persistence_func=(
            postprocess_successful_task_persistence_func
        ),
    )
