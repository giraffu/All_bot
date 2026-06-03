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
)
from src.services.wan22_video_v2_config import (
    get_wan22_video_v2_resolution_display,
    normalize_wan22_video_v2_resolution_preset,
)
from src.services.wan22_video_v2_context import (
    normalize_wan22_video_v2_chain_task_ids,
    normalize_wan22_video_v2_negative_prompt,
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
    negative_prompt: str | None = None,
    use_end_frame: bool | None = None,
    resolution_preset: str | None = None,
    wan22_prev_task_id: str | None = None,
    wan22_chain_task_ids: Any = None,
    result_meta: dict[str, Any] | None = None,
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
    normalized_resolution_preset = normalize_wan22_video_v2_resolution_preset(
        resolution_preset or resolution
    )
    normalized_negative_prompt = normalize_wan22_video_v2_negative_prompt(
        negative_prompt
    )
    duration_text = "5s"
    duration_value = 5
    resolution_text = get_wan22_video_v2_resolution_display(
        normalized_resolution_preset,
        lang=getattr(context, "lang", "zh"),
    )
    use_end_frame_value = (
        bool(use_end_frame) if use_end_frame is not None else len(images) > 1
    )
    normalized_chain_task_ids = normalize_wan22_video_v2_chain_task_ids(
        wan22_chain_task_ids
    )
    final_result_meta: dict[str, Any] = {
        "wan22_resolution_preset": normalized_resolution_preset,
        "wan22_negative_prompt": normalized_negative_prompt,
        "wan22_use_end_frame": use_end_frame_value,
        "wan22_chain_task_ids": normalized_chain_task_ids,
    }
    normalized_prev_task_id = str(wan22_prev_task_id or "").strip()
    if normalized_prev_task_id:
        final_result_meta["wan22_prev_task_id"] = normalized_prev_task_id
    if isinstance(result_meta, dict):
        final_result_meta.update(result_meta)

    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    display_mode_name = resolve_generation_display_mode_name(context, task_type)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=normalized_resolution_preset,
        duration=duration_value,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame_value,
        resolution_preset=normalized_resolution_preset,
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
        resolution=normalized_resolution_preset,
        duration=duration_text,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
    )
    billing_args = resolve_generation_billing_args(
        is_video=True,
        resolution=normalized_resolution_preset,
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
            result_meta=final_result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=5,
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_image_to_video_task",
        )
    )
