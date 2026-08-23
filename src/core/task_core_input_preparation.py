import asyncio
import inspect
import os
from collections.abc import Awaitable, Callable
from typing import Any

from src.core.task_core_types import CoreDomainError, TaskSubmissionContext, VideoTaskRequest
from src.core.user_logger_protocol import UserLoggerProtocol


def _call_with_supported_kwargs(func, **kwargs):
    signature = inspect.signature(func)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return func(**kwargs)

    supported_kwargs = {
        key: value
        for key, value in kwargs.items()
        if key in signature.parameters
    }
    return func(**supported_kwargs)


async def process_input_path(
    *,
    user_logger: UserLoggerProtocol,
    path: str,
    bucket_name: str,
) -> str:
    if not path:
        return ""
    if path.startswith("template:"):
        return path
    if path.startswith(f"{bucket_name}/"):
        return path.replace(f"{bucket_name}/", "", 1)

    # Existing history records may already store a plain object key without bucket prefix.
    # Only treat the value as a local file when it is an absolute path or actually exists on disk.
    is_local_file = os.path.isabs(path) or os.path.exists(path)
    if not is_local_file:
        return path

    if not os.path.exists(path):
        raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")

    processed = await asyncio.to_thread(user_logger.save_input_image, path)
    if processed:
        return processed

    raise CoreDomainError(f"本地输入文件上传失败，无法继续派发任务: {path}")


def validate_local_input_paths(*, paths_to_upload: list[str], bucket_name: str):
    for path in paths_to_upload:
        if not path:
            continue
        if path.startswith("template:") or path.startswith(f"{bucket_name}/"):
            continue
        is_local_file = os.path.isabs(path) or os.path.exists(path)
        if is_local_file and not os.path.exists(path):
            raise CoreDomainError(f"本地输入文件不存在，无法继续派发任务: {path}")


async def prepare_task_submission_payload(
    *,
    user_id: int,
    username: str,
    task_type: str,
    inputs: dict,
    registry_task_id: str | None = None,
    strategy: Any,
    base_priority: int,
    is_template: bool,
    is_video_task: bool,
    video_request: VideoTaskRequest,
    user_logger_factory: Callable[[int, str], UserLoggerProtocol],
    validate_local_input_paths_func: Callable[..., None],
    get_user_priority_and_identity_func: Callable[[int], Awaitable[tuple[int, Any, Any]]],
    load_prompts_func: Callable[[], dict[str, str]],
    process_input_path_func: Callable[..., Awaitable[str]],
    promote_staged_inputs_func: Callable[..., Awaitable[list[str]]] | None = None,
    bucket_name: str,
) -> TaskSubmissionContext:
    user_logger = user_logger_factory(user_id, username)
    paths_to_upload = strategy.get_file_paths_to_upload(inputs)
    _call_with_supported_kwargs(
        validate_local_input_paths_func,
        paths_to_upload=paths_to_upload,
        bucket_name=bucket_name,
    )
    if promote_staged_inputs_func is not None and registry_task_id and paths_to_upload:
        paths_to_upload = await promote_staged_inputs_func(
            input_refs=paths_to_upload,
            task_id=registry_task_id,
            user_id=user_id,
        )

    priority, _, _ = await get_user_priority_and_identity_func(user_id)
    final_priority = min(base_priority + priority, 100)

    prompts_config = load_prompts_func()
    prompt = inputs.get("prompt")
    if not prompt or prompt.strip() == "":
        prompt = prompts_config.get(task_type, task_type)

    saved_inputs = []
    for path in paths_to_upload:
        processed_img = await _call_with_supported_kwargs(
            process_input_path_func,
            user_logger=user_logger,
            path=path,
            bucket_name=bucket_name,
        )
        if processed_img:
            saved_inputs.append(processed_img)

    submission_context = TaskSubmissionContext(
        task_type=task_type,
        is_video_task=is_video_task,
        user_logger=user_logger,
        prompt=prompt,
        saved_inputs=saved_inputs,
        metadata={},
        allow_contribute=not is_template,
        final_priority=final_priority,
        video_request=video_request,
    )
    submission_context.apply_to_inputs(inputs)
    submission_context.metadata = strategy.get_metadata(inputs)
    return submission_context
