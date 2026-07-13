from typing import Any, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_IMAGE_TO_VIDEO, MODE_NAME_MAP
from src.services.permission_service import permission_service
from src.services.task_service_generation_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import (
    extract_actor_from_update,
    build_bot_task_flow_context,
    build_cleanup_paths,
    build_log_prompt,
    build_task_inputs,
    build_unexpected_error_log_message,
    resolve_video_billing_args,
)
from src.services.task_service_support import (
    get_acceleration_notice,
    resolve_custom_video_settings,
)
from src.services.task_service_message_support import (
    build_translated_cost_status_builder,
    build_message_spec,
    build_status_message,
    resolve_display_mode_name,
    translate_context_text,
)
from src.services.task_service_flow import run_bot_task_application
from src.services.task_service_types import BotTaskFailurePolicy
from src.utils import load_prompts


async def process_video_task_template(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    default_prompt_key: str,
    default_prompt_text: str,
    prompt_override: Optional[str] = None,
    negative_prompt: str | None = None,
    display_mode_name_override: Optional[str] = None,
    result_meta: dict[str, Any] | None = None,
    lora_name: str | None = None,
    lora_strength: float | None = None,
    update: Update | None = None,
    image_path: str,
    end_image_path: str | None = None,
    use_end_frame: bool | None = None,
    cleanup: bool = True,
    send_result: bool = True,
    delete_status: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    status_msg_id: Optional[int] = None,
    resolution: Any = None,
    duration: Any = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    user_cancel_allowed: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    if update is not None:
        actor = extract_actor_from_update(update)
        chat_id = actor.chat_id
        user_id = actor.user_id
        username = actor.username
    if chat_id is None or user_id is None:
        raise ValueError("process_video_task_template 缺少用户或聊天上下文")
    internal_user_id = await resolve_internal_user_id(user_id, username)

    resolution, duration_str, res_val, duration = await resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
        resolution=resolution,
        duration=duration,
    )

    prompts_config = load_prompts()
    base_prompt = prompt_override or prompts_config.get(
        default_prompt_key, default_prompt_text
    )

    display_mode_name = display_mode_name_override or resolve_display_mode_name(
        mode,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context,
                "task.status_processing_mode_with_settings",
                mode_name=display_mode_name,
                resolution=resolution,
                duration=duration_str,
            ),
            notice=notice,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=translate_context_text(
            context, "task.status_completion_mode", mode_name=display_mode_name
        ),
        missing_output_message=translate_context_text(
            context, "task.status_missing_task_info_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )
    extra_inputs = {}
    normalized_lora_name = str(lora_name or "").strip()
    if normalized_lora_name:
        extra_inputs["lora_name"] = normalized_lora_name
        extra_inputs["lora_strength"] = 1.0 if lora_strength is None else lora_strength
    submit_images = [image_path] if image_path else []
    if end_image_path:
        submit_images.append(end_image_path)
    if use_end_frame is not None:
        extra_inputs["use_end_frame"] = bool(use_end_frame and end_image_path)
    if negative_prompt is not None:
        extra_inputs["negative_prompt"] = negative_prompt

    inputs = build_task_inputs(
        prompt=base_prompt,
        images=submit_images,
        resolution=res_val,
        duration=duration,
        **extra_inputs,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
    )

    return await run_bot_task_application(
        flow=build_bot_task_flow_context(
            context=context,
            update=update,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=build_log_prompt(
                base_prompt,
                resolution=resolution,
                duration=duration_str,
                lora_name=normalized_lora_name or None,
                task_type=mode,
                lora_task_types=(MODE_IMAGE_TO_VIDEO,),
            ),
            is_video=True,
            source_post_id=source_post_id,
            base_priority=base_priority,
            allow_cancel=allow_cancel,
            user_cancel_allowed=user_cancel_allowed,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                mode_name=display_mode_name,
                resolution=resolution,
                duration=duration_str,
            ),
            result_meta=result_meta,
            send_result=send_result,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths(submit_images),
            task_label=f"{mode} task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    f"{mode} task"
                ),
                unexpected_error_prefix="出错了",
            ),
        )
    )
