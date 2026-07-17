from typing import Any, Optional, Tuple

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO
from src.domain_config.wan22_aio_video import (
    WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
    WAN22_VIDEO_V2_MODEL_PROFILE,
    Wan22AioVideoProfile,
    build_wan22_aio_video_result_meta,
    get_wan22_video_v2_duration_label,
    get_wan22_video_v2_resolution_display,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_negative_prompt,
    normalize_wan22_video_v2_resolution_preset,
    normalize_wan22_lora_items,
    resolve_wan22_aio_video_profile,
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
    resolve_generation_billing_args,
    resolve_generation_display_mode_name,
    resolve_internal_user_id,
)
from src.services.task_service_message_support import translate_context_text
from src.services.task_service_support import get_acceleration_notice


def _is_legacy_profile(profile: Wan22AioVideoProfile) -> bool:
    return profile.name == WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE


def _build_wan22_aio_inputs(
    *,
    profile: Wan22AioVideoProfile,
    prompt: str,
    images: list[str],
    resolution_preset: str,
    duration_seconds: int,
    negative_prompt: str,
    use_end_frame: bool,
    lora_name: str | None,
    lora_strength: float | None,
    lora_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if _is_legacy_profile(profile):
        return build_task_inputs(
            prompt=prompt,
            images=images,
            resolution=resolution_preset,
            duration=duration_seconds,
            negative_prompt=negative_prompt,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            wan22_model_profile=profile.model_profile,
            lora_name=lora_name,
            lora_strength=lora_strength,
            lora_items=lora_items,
            extract_last_frame=True,
        )

    return build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=None,
        duration=duration_seconds,
        negative_prompt=negative_prompt,
        use_end_frame=use_end_frame,
        resolution_preset=resolution_preset,
        wan22_model_profile=profile.model_profile,
        upscale=False,
        extract_last_frame=True,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
    )


async def process_wan22_aio_video_generation_task(
    *,
    profile_name: str,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    negative_prompt: str | None = None,
    use_end_frame: bool | None = None,
    resolution: Any = None,
    duration: Any = None,
    resolution_preset: str | None = None,
    wan22_prev_task_id: str | None = None,
    wan22_chain_task_ids: Any = None,
    result_meta: dict[str, Any] | None = None,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str | None = None,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: Any = None,
    lora_name: str | None = None,
    lora_strength: float | None = None,
    lora_items: list[dict[str, Any]] | None = None,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    display_mode_name_override: str | None = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    show_queue_status: bool = True,
    user_cancel_allowed: bool = True,
) -> Tuple[Optional[bytes], Optional[str]]:
    profile = resolve_wan22_aio_video_profile(profile_name)
    public_task_type = task_type or profile.public_task_types[0]
    internal_user_id = await resolve_internal_user_id(user_id, username)
    normalized_resolution_preset = normalize_wan22_video_v2_resolution_preset(
        resolution_preset or resolution
    )
    normalized_duration_seconds = normalize_wan22_video_v2_duration_seconds(
        duration
    )
    normalized_negative_prompt = normalize_wan22_video_v2_negative_prompt(
        negative_prompt
    )
    use_end_frame_value = (
        bool(use_end_frame) if use_end_frame is not None else len(images) > 1
    )
    normalized_lora_items = (
        normalize_wan22_lora_items(
            lora_items,
            lora_name=lora_name,
            lora_strength=lora_strength,
        )
        if profile.allow_lora
        else []
    )
    first_lora = normalized_lora_items[0] if normalized_lora_items else None
    normalized_lora_name = str(first_lora["name"]) if first_lora else ""
    normalized_lora_strength = float(first_lora["strength"]) if first_lora else 1.0
    final_result_meta = build_wan22_aio_video_result_meta(
        profile=profile,
        resolution_preset=normalized_resolution_preset,
        duration_seconds=normalized_duration_seconds,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame_value,
        prev_task_id=wan22_prev_task_id,
        chain_task_ids=wan22_chain_task_ids,
        lora_name=normalized_lora_name,
        lora_strength=normalized_lora_strength,
        lora_items=normalized_lora_items,
    )
    if isinstance(result_meta, dict):
        final_result_meta.update(result_meta)

    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    display_mode_name = display_mode_name_override or resolve_generation_display_mode_name(
        context,
        public_task_type,
    )
    inputs = _build_wan22_aio_inputs(
        profile=profile,
        prompt=prompt,
        images=images,
        resolution_preset=normalized_resolution_preset,
        duration_seconds=normalized_duration_seconds,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame_value,
        lora_name=normalized_lora_name or None,
        lora_strength=normalized_lora_strength,
        lora_items=normalized_lora_items,
    )

    if _is_legacy_profile(profile):
        duration_text = get_wan22_video_v2_duration_label(
            normalized_duration_seconds,
            lang=getattr(context, "lang", "zh"),
        )
        log_duration_text = f"{normalized_duration_seconds}s"
        resolution_text = get_wan22_video_v2_resolution_display(
            normalized_resolution_preset,
            lang=getattr(context, "lang", "zh"),
        )
        initial_status_text = translate_context_text(
            context,
            "task.status_processing_mode_with_settings",
            mode_name=display_mode_name,
            resolution=resolution_text,
            duration=duration_text,
        )
        submitted_status_key = "task.status_submitted_mode_with_settings"
        submitted_status_kwargs = {
            "mode_name": display_mode_name,
            "resolution": resolution_text,
            "duration": duration_text,
        }
        billing_resolution = normalized_resolution_preset
        allowed_task_types = (MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO)
        entrypoint_name = "process_image_to_video_task"
        flow_prompt = build_log_prompt(
            prompt,
            resolution=normalized_resolution_preset,
            duration=log_duration_text,
            lora_name=normalized_lora_name or None,
            task_type=public_task_type,
            lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
        )
    else:
        initial_status_text = translate_context_text(
            context,
            "task.status_processing_mode",
            mode_name=display_mode_name,
        )
        submitted_status_key = "task.status_submitted_mode"
        submitted_status_kwargs = {"mode_name": display_mode_name}
        billing_resolution = normalized_resolution_preset
        allowed_task_types = profile.public_task_types
        entrypoint_name = "process_wan22_video_v2_task"
        flow_prompt = prompt

    message_spec = build_generation_message_spec(
        context=context,
        notice=notice,
        initial_status_text=initial_status_text,
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=build_generation_completion_caption(
            context,
            public_task_type,
            display_mode_name_override=display_mode_name,
        ),
    )
    billing_args = resolve_generation_billing_args(
        is_video=True,
        resolution=billing_resolution,
        task_type=public_task_type,
        duration=normalized_duration_seconds,
        allowed_task_types=allowed_task_types,
    )

    return await run_bot_task_application(
        flow=build_generation_flow_context(
            context=context,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=public_task_type,
            inputs=inputs,
            prompt=flow_prompt,
            is_video=True,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            message_spec=message_spec,
            submitted_status_builder=build_generation_submitted_status_builder(
                context,
                submitted_status_key,
                notice=notice,
                wait_key="task.status_wait_generating_video",
                **submitted_status_kwargs,
            ),
            send_result=send_result,
            reply_markup=reply_markup,
            result_meta=final_result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            base_priority=base_priority,
            allow_cancel=allow_cancel,
            show_queue_status=show_queue_status,
            user_cancel_allowed=user_cancel_allowed,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=normalized_duration_seconds,
            images=images,
            cleanup=cleanup,
            entrypoint_name=entrypoint_name,
        )
    )


async def process_legacy_image_to_video_generation_task(
    **kwargs: Any,
) -> Tuple[Optional[bytes], Optional[str]]:
    return await process_wan22_aio_video_generation_task(
        profile_name=WAN22_LEGACY_IMAGE_TO_VIDEO_MODEL_PROFILE,
        **kwargs,
    )


async def process_wan22_video_v2_aio_generation_task(
    **kwargs: Any,
) -> Tuple[Optional[bytes], Optional[str]]:
    return await process_wan22_aio_video_generation_task(
        profile_name=WAN22_VIDEO_V2_MODEL_PROFILE,
        **kwargs,
    )
