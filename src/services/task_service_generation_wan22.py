from typing import Any, Optional, Tuple

from src.constants import MODE_WAN22_VIDEO_V2
from src.services.permission_service import permission_service
from src.services.task_service_entrypoint_support import build_task_inputs
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
from src.services.task_service_message_support import translate_context_text
from src.services.task_service_support import get_acceleration_notice


DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT = (
    "censored, mosaic censoring, bar censor, pixelated, glowing, bloom, blurry, "
    "out of focus, low detail, bad anatomy, ugly, overexposed, underexposed, "
    "distorted face, extra limbs, cartoonish, 3d render artifacts, duplicate "
    "people, unnatural lighting, bad composition, missing shadows, low "
    "resolution, poorly textured, glitch, noise, grain, static, motionless, "
    "still frame, stylized, artwork, painting, illustration, many people in "
    "background, three legs, walking backward, unnatural skin tone, discolored "
    "eyelid, red eyelids, closed eyes, poorly drawn hands, extra fingers, fused "
    "fingers, poorly drawn face, deformed, disfigured, malformed limbs, fog, "
    "mist, voluminous eyelashes,"
)


def normalize_wan22_video_v2_negative_prompt(negative_prompt: str | None) -> str:
    normalized = (negative_prompt or "").strip()
    return normalized or DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT


async def process_wan22_video_v2_generation_task(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    negative_prompt: str,
    images: list[str],
    use_end_frame: bool,
    color_match: bool,
    perfect_loop: bool,
    upscale: bool,
    extract_last_frame: bool,
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = MODE_WAN22_VIDEO_V2,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: Any = None,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)
    normalized_negative_prompt = normalize_wan22_video_v2_negative_prompt(
        negative_prompt
    )
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    display_mode_name = resolve_generation_display_mode_name(context, task_type)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=None,
        duration=5,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame,
        color_match=color_match,
        perfect_loop=perfect_loop,
        upscale=upscale,
        extract_last_frame=extract_last_frame,
    )
    message_spec = build_generation_message_spec(
        context=context,
        notice=notice,
        initial_status_text=translate_context_text(
            context,
            "task.status_processing_mode",
            mode_name=display_mode_name,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=build_generation_completion_caption(
            context,
            task_type,
        ),
    )
    billing_args = resolve_generation_billing_args(
        is_video=True,
        resolution=None,
        task_type=task_type,
        duration=5,
        allowed_task_types=(),
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
            prompt=prompt,
            is_video=True,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            message_spec=message_spec,
            submitted_status_builder=build_generation_submitted_status_builder(
                context,
                "task.status_submitted_mode",
                notice=notice,
                wait_key="task.status_wait_generating_video",
                mode_name=display_mode_name,
            ),
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=5,
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_wan22_video_v2_task",
        )
    )
