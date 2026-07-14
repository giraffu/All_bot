from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.core.video_billing import normalize_requested_billing_resolution
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_types import (
    BotTaskBillingContext,
    BotTaskCleanupPolicy,
    BotTaskFailurePolicy,
    BotTaskFlowContext,
    BotTaskPresentationContext,
    BotTaskRequestContext,
    BotTaskRuntimeState,
)


@dataclass(frozen=True)
class TelegramTaskActorContext:
    chat_id: int
    user_id: int
    username: Optional[str]


def extract_actor_from_update(update: Any) -> TelegramTaskActorContext:
    effective_chat = getattr(update, "effective_chat", None)
    effective_user = getattr(update, "effective_user", None)
    chat_id = getattr(effective_chat, "id", None)
    user_id = getattr(effective_user, "id", None)

    if chat_id is None or user_id is None:
        raise ValueError("Telegram update 缺少有效的 chat_id 或 user_id")

    return TelegramTaskActorContext(
        chat_id=chat_id,
        user_id=user_id,
        username=getattr(effective_user, "username", None),
    )


def build_task_inputs(
    *,
    prompt: str,
    images: list[str],
    resolution: Any,
    duration: Any,
    **extra_fields: Any,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "images": images,
        "resolution": resolution,
        "duration": duration,
        **extra_fields,
    }


def resolve_video_billing_args(
    *,
    is_video: bool,
    resolution: Any,
    task_type: str,
    duration: Any = None,
    include_requested_duration: bool = True,
    allowed_task_types: set[str] | tuple[str, ...] | None = None,
    duration_transform: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    if not is_video:
        return {"billing_resolution": None, "requested_duration": None}

    requested_duration = None
    allow_duration = include_requested_duration and (
        allowed_task_types is None or task_type in allowed_task_types
    )
    if allow_duration:
        requested_duration = duration_transform(duration) if duration_transform else duration

    return {
        "billing_resolution": normalize_requested_billing_resolution(resolution, task_type),
        "requested_duration": requested_duration,
    }


def build_log_prompt(
    prompt: str,
    *,
    resolution: Any = None,
    duration: Any = None,
    lora_name: str | None = None,
    task_type: str | None = None,
    lora_task_types: set[str] | tuple[str, ...] | None = None,
) -> str:
    result = prompt
    if lora_name and lora_task_types and task_type in lora_task_types:
        result = f"[模型: {lora_name}] {result}"
    if resolution is not None and duration is not None:
        result = f"[{resolution}|{duration}] {result}"
    return result


def build_cleanup_paths(paths: Iterable[str | None]) -> list[str] | None:
    cleaned = [path for path in paths if path]
    return cleaned or None


def build_unexpected_error_log_message(task_label: str, *, verb: str = "in") -> str:
    if verb == "processing":
        return f"Error processing {task_label} for {{internal_user_id}}: {{error}}"
    return f"Error in {task_label} for user {{internal_user_id}}: {{error}}"


def build_default_bot_task_failure_policy(task_label: str) -> BotTaskFailurePolicy:
    return BotTaskFailurePolicy(
        unexpected_error_log_message=build_unexpected_error_log_message(task_label),
        unexpected_error_prefix="出错了",
    )


def build_default_bot_task_cleanup_policy(
    paths: Iterable[str | None] | None,
    *,
    cleanup: bool,
    cleanup_files_func=cleanup_task_files,
) -> BotTaskCleanupPolicy:
    cleanup_paths = build_cleanup_paths(paths or [])
    return BotTaskCleanupPolicy(
        cleanup_paths=cleanup_paths,
        cleanup_enabled=cleanup,
        cleanup_files_func=cleanup_files_func,
    )


def build_bot_task_flow_context(
    *,
    context: Any,
    chat_id: int,
    internal_user_id: int,
    username: Optional[str],
    task_type: str,
    inputs: dict[str, Any],
    prompt: str,
    is_video: bool,
    message_spec: Any,
    task_label: str,
    cleanup: bool,
    cleanup_paths: Iterable[str | None],
    status_msg_id: Optional[int] = None,
    update: Any = None,
    source_post_id: Optional[int] = None,
    deduct_quota: bool = True,
    cost_override: Optional[int] = None,
    base_priority: int = 0,
    user_cancel_allowed: bool = True,
    submitted_status_builder: Any = None,
    send_result: bool = True,
    reply_markup: Any = None,
    result_meta: dict[str, Any] | None = None,
    delete_status: bool = True,
    allow_contribute: bool = True,
    record_history: bool = True,
    allow_cancel: bool = True,
    result_task_type: Optional[str] = None,
    result_prompt: Optional[str] = None,
    result_input_image_indices: Optional[list[int]] = None,
    prefer_edit_status: bool = False,
    billing_resolution: Optional[str] = None,
    requested_duration: Optional[int] = None,
    missing_output_should_refund: Optional[bool] = None,
    runtime_state: Optional[BotTaskRuntimeState] = None,
    failure_policy: Optional[BotTaskFailurePolicy] = None,
    cleanup_files_func=cleanup_task_files,
) -> BotTaskFlowContext:
    if runtime_state is None:
        runtime_state = BotTaskRuntimeState()
    if failure_policy is None:
        failure_policy = build_default_bot_task_failure_policy(task_label)
    if missing_output_should_refund is None:
        missing_output_should_refund = deduct_quota

    return BotTaskFlowContext(
        runtime_state=runtime_state,
        request=BotTaskRequestContext(
            context=context,
            update=update,
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
        ),
        presentation=BotTaskPresentationContext(
            message_spec=message_spec,
            submitted_status_builder=submitted_status_builder,
            send_result=send_result,
            reply_markup=reply_markup,
            result_meta=result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            record_history=record_history,
            allow_cancel=allow_cancel,
            result_task_type=result_task_type,
            result_prompt=result_prompt,
            result_input_image_indices=result_input_image_indices,
            prefer_edit_status=prefer_edit_status,
        ),
        billing=BotTaskBillingContext(
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            missing_output_should_refund=missing_output_should_refund,
        ),
        failure_policy=failure_policy,
        cleanup_policy=build_default_bot_task_cleanup_policy(
            cleanup_paths,
            cleanup=cleanup,
            cleanup_files_func=cleanup_files_func,
        ),
    )
