from typing import Any, Optional

from src.constants import MODE_NAME_MAP
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_entrypoint_support import (
    build_cleanup_paths,
    build_bot_task_flow_context,
    build_unexpected_error_log_message,
    resolve_video_billing_args,
)
from src.services.task_service_message_support import (
    build_message_spec,
    build_status_message,
    build_translated_cost_status_builder,
    resolve_display_mode_name,
    translate_context_text,
)
from src.services.task_service_types import BotTaskFailurePolicy, BotTaskFlowContext
from src.services.task_service_types import BotTaskRuntimeState


async def resolve_internal_user_id(user_id: int, username: Optional[str]) -> int:
    from src.core import user_core

    internal_user, _ = await user_core.get_or_create_user_by_telegram(
        user_id,
        username,
    )
    return internal_user.id


def build_generation_message_spec(
    *,
    context: Any,
    notice: str | None,
    initial_status_text: str,
    progress_wait_text: str | None = None,
    completion_caption: str | None = None,
) -> Any:
    return build_message_spec(
        initial_status_text=build_status_message(
            initial_status_text,
            notice=notice,
        ),
        progress_wait_text=progress_wait_text,
        completion_caption=completion_caption,
        missing_output_message=translate_context_text(
            context, "task.status_missing_output_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )


def build_generation_submitted_status_builder(
    context: Any,
    status_key: str,
    *,
    notice: str | None,
    **kwargs: Any,
) -> Any:
    return build_translated_cost_status_builder(
        context,
        status_key,
        notice=notice,
        **kwargs,
    )


def resolve_generation_display_mode_name(
    context: Any,
    task_type: str,
) -> str:
    return resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )


def build_generation_completion_caption(
    context: Any,
    task_type: str,
    display_mode_name_override: str | None = None,
) -> str:
    return translate_context_text(
        context,
        "task.status_completion_mode",
        mode_name=display_mode_name_override
        or resolve_generation_display_mode_name(context, task_type),
    )


def resolve_generation_billing_args(
    *,
    is_video: bool,
    resolution: Any,
    task_type: str,
    duration: Any,
    allowed_task_types: tuple[str, ...],
) -> dict[str, Any]:
    return resolve_video_billing_args(
        is_video=is_video,
        resolution=resolution,
        task_type=task_type,
        duration=duration,
        allowed_task_types=allowed_task_types,
    )


def build_generation_flow_context(
    *,
    context: Any,
    chat_id: int,
    status_msg_id: int | None,
    internal_user_id: int,
    username: str,
    task_type: str,
    inputs: dict[str, Any],
    prompt: str,
    is_video: bool,
    source_post_id: Optional[int],
    deduct_quota: bool,
    cost_override: Optional[int] = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    show_queue_status: bool = True,
    user_cancel_allowed: bool = True,
    message_spec: Any,
    submitted_status_builder: Any,
    send_result: bool,
    reply_markup: Any = None,
    result_meta: dict[str, Any] | None = None,
    delete_status: bool,
    allow_contribute: bool,
    record_history: bool = True,
    result_task_type: Optional[str] = None,
    result_prompt: Optional[str] = None,
    result_input_image_indices: Optional[list[int]] = None,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
    images: list[str],
    cleanup: bool,
    entrypoint_name: str,
    runtime_state: BotTaskRuntimeState | None = None,
) -> BotTaskFlowContext:
    failure_policy = BotTaskFailurePolicy(
        unexpected_error_log_message=build_unexpected_error_log_message(entrypoint_name),
        unexpected_error_prefix="出错了",
    )
    return build_bot_task_flow_context(
        context=context,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        prompt=prompt,
        is_video=is_video,
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        cost_override=cost_override,
        base_priority=base_priority,
        user_cancel_allowed=user_cancel_allowed,
        message_spec=message_spec,
        submitted_status_builder=submitted_status_builder,
        send_result=send_result,
        reply_markup=reply_markup,
        result_meta=result_meta,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        record_history=record_history,
        allow_cancel=allow_cancel,
        show_queue_status=show_queue_status,
        result_task_type=result_task_type,
        result_prompt=result_prompt,
        result_input_image_indices=result_input_image_indices,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        cleanup=cleanup,
        cleanup_paths=build_cleanup_paths(images),
        cleanup_files_func=cleanup_task_files,
        task_label=entrypoint_name,
        failure_policy=failure_policy,
        runtime_state=runtime_state,
    )
