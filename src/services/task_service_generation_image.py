from typing import Any, Optional, Tuple

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_WAN22_VIDEO_V2,
)
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
)
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task,
)
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task,
)
from src.services.task_service_message_support import translate_context_text
from src.services.task_service_support import get_acceleration_notice


async def process_standard_generation_task(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    is_video: bool = False,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = None,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: Any = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    resolution: Any = None,
    duration: Any = None,
    negative_prompt: str | None = None,
    cost_override: int | None = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    user_cancel_allowed: bool = True,
    result_task_type: str | None = None,
    result_prompt: str | None = None,
    result_input_image_indices: list[int] | None = None,
    display_mode_name_override: str | None = None,
    result_meta: dict[str, Any] | None = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)

    if not task_type:
        task_type = "video" if is_video else "image"

    if is_video and task_type in [MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO]:
        video_kwargs = {
            "context": context,
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "prompt": prompt,
            "images": images,
            "resolution": resolution,
            "duration": duration,
            "negative_prompt": negative_prompt,
            "status_msg_id": status_msg_id,
            "delete_status": delete_status,
            "task_type": task_type,
            "cleanup": cleanup,
            "send_result": send_result,
            "deduct_quota": deduct_quota,
            "reply_markup": reply_markup,
            "lora_name": lora_name,
            "lora_strength": lora_strength,
            "allow_contribute": allow_contribute,
            "source_post_id": source_post_id,
            "base_priority": base_priority,
            "allow_cancel": allow_cancel,
            "user_cancel_allowed": user_cancel_allowed,
        }
        if display_mode_name_override is not None:
            video_kwargs["display_mode_name_override"] = display_mode_name_override
        if result_meta is not None:
            video_kwargs["result_meta"] = result_meta
        return await process_image_to_video_generation_task(**video_kwargs)
    if is_video and task_type == MODE_WAN22_VIDEO_V2:
        wan22_kwargs = {
            "context": context,
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "prompt": prompt,
            "negative_prompt": negative_prompt or "",
            "images": images,
            "resolution_preset": resolution,
            "duration": duration,
            "use_end_frame": len(images) > 1,
            "status_msg_id": status_msg_id,
            "delete_status": delete_status,
            "task_type": task_type,
            "cleanup": cleanup,
            "send_result": send_result,
            "deduct_quota": deduct_quota,
            "reply_markup": reply_markup,
            "allow_contribute": allow_contribute,
            "source_post_id": source_post_id,
            "base_priority": base_priority,
            "allow_cancel": allow_cancel,
            "user_cancel_allowed": user_cancel_allowed,
        }
        if display_mode_name_override is not None:
            wan22_kwargs["display_mode_name_override"] = display_mode_name_override
        if result_meta is not None:
            wan22_kwargs["result_meta"] = result_meta
        return await process_wan22_video_v2_generation_task(**wan22_kwargs)

    resolution = 512
    duration = 5
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    extra_inputs: dict[str, Any] = {
        "lora_name": lora_name,
        "lora_strength": lora_strength,
    }
    if negative_prompt is not None:
        extra_inputs["negative_prompt"] = negative_prompt
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution,
        duration=duration,
        **extra_inputs,
    )
    log_prompt = build_log_prompt(
        prompt,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
    )
    message_spec = build_generation_message_spec(
        context=context,
        notice=notice,
        initial_status_text=(
            translate_context_text(context, "task.status_processing_video")
            if is_video
            else translate_context_text(
                context, "task.status_processing_images", image_count=len(images)
            )
        ),
        completion_caption=build_generation_completion_caption(
            context,
            task_type,
            display_mode_name_override=display_mode_name_override,
        ),
    )
    billing_args = resolve_generation_billing_args(
        is_video=is_video,
        resolution=resolution,
        task_type=task_type,
        duration=duration,
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
            is_video=is_video,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            message_spec=message_spec,
            submitted_status_builder=build_generation_submitted_status_builder(
                context,
                "task.status_submitted_video"
                if is_video
                else "task.status_submitted_images",
                notice=notice,
                image_count=len(images),
            ),
            send_result=send_result,
            reply_markup=reply_markup,
            result_meta=result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            cost_override=cost_override,
            base_priority=base_priority,
            allow_cancel=allow_cancel,
            user_cancel_allowed=user_cancel_allowed,
            result_task_type=result_task_type,
            result_prompt=result_prompt,
            result_input_image_indices=result_input_image_indices,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_generation_task",
        )
    )
