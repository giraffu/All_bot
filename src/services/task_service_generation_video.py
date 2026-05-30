from typing import Any, Optional, Tuple

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO
from src.services.permission_service import permission_service
from src.services.task_service_entrypoint_support import (
    build_log_prompt,
    build_task_inputs,
)
from src.services.task_service_flow import run_bot_task_application
from src.services.task_service_generation_common import (
    build_generation_completion_caption,
    build_generation_flow_context,
    build_generation_message_spec,
    build_generation_submitted_status_builder,
    resolve_internal_user_id,
    resolve_generation_billing_args,
    resolve_generation_display_mode_name,
)
from src.services.task_service_support import (
    get_acceleration_notice,
    resolve_custom_video_settings,
)
from src.services.task_service_message_support import translate_context_text


async def process_image_to_video_generation_task(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    resolution: Any = None,
    duration: Any = None,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = MODE_IMAGE_TO_VIDEO,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: Any = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)
    resolution_text, duration_text, resolution_value, duration_value = (
        await resolve_custom_video_settings(
            context,
            resolution=resolution,
            duration=duration,
        )
    )

    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    display_mode_name = resolve_generation_display_mode_name(context, task_type)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution_value,
        duration=duration_value,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    message_spec = build_generation_message_spec(
        context=context,
        notice=notice,
        initial_status_text=translate_context_text(
            context,
            "task.status_processing_mode_with_settings",
            mode_name=display_mode_name,
            resolution=resolution_text,
            duration=duration_text,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=build_generation_completion_caption(
            context,
            task_type,
        ),
    )
    log_prompt = build_log_prompt(
        prompt,
        resolution=resolution_text,
        duration=duration_text,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
    )
    billing_args = resolve_generation_billing_args(
        is_video=True,
        resolution=resolution_value,
        task_type=task_type,
        duration=duration_value,
        allowed_task_types=(MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO),
    )

    return await run_bot_task_application(
        flow=build_generation_flow_context(
            context=context,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            prompt=log_prompt,
            is_video=True,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            message_spec=message_spec,
            submitted_status_builder=build_generation_submitted_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                wait_key="task.status_wait_generating_video",
                mode_name=display_mode_name,
                resolution=resolution_text,
                duration=duration_text,
            ),
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_image_to_video_task",
        )
    )
