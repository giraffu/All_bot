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
from src.services.wan22_video_v2_context import (
    DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
    normalize_wan22_video_v2_chain_task_ids,
    normalize_wan22_video_v2_negative_prompt,
)
from src.services.task_service_message_support import translate_context_text
from src.services.task_service_support import get_acceleration_notice
from src.services.wan22_video_v2_config import (
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_resolution_label,
    normalize_wan22_video_v2_resolution_preset,
)

__all__ = [
    "DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT",
    "WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET",
    "WAN22_VIDEO_V2_RESOLUTION_PRESETS",
    "build_wan22_video_v2_result_meta",
    "get_wan22_video_v2_cost",
    "get_wan22_video_v2_resolution_label",
    "normalize_wan22_video_v2_chain_task_ids",
    "normalize_wan22_video_v2_negative_prompt",
    "normalize_wan22_video_v2_resolution_preset",
    "process_wan22_video_v2_generation_task",
]


def build_wan22_video_v2_result_meta(
    *,
    resolution_preset: str | None,
    negative_prompt: str | None,
    use_end_frame: bool,
    prev_task_id: str | None = None,
    chain_task_ids: Any = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "wan22_resolution_preset": normalize_wan22_video_v2_resolution_preset(
            resolution_preset
        ),
        "wan22_negative_prompt": normalize_wan22_video_v2_negative_prompt(
            negative_prompt
        ),
        "wan22_use_end_frame": bool(use_end_frame),
        "wan22_chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
            chain_task_ids
        ),
    }
    prev_task_id = str(prev_task_id or "").strip()
    if prev_task_id:
        meta["wan22_prev_task_id"] = prev_task_id
    return meta


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
    status_msg_id: int = None,
    delete_status: bool = True,
    task_type: str = MODE_WAN22_VIDEO_V2,
    cleanup: bool = True,
    send_result: bool = True,
    deduct_quota: bool = True,
    reply_markup: Any = None,
    result_meta: dict[str, Any] | None = None,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    resolution_preset: str | None = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)
    normalized_negative_prompt = normalize_wan22_video_v2_negative_prompt(
        negative_prompt
    )
    normalized_resolution_preset = normalize_wan22_video_v2_resolution_preset(
        resolution_preset
    )
    final_result_meta = build_wan22_video_v2_result_meta(
        resolution_preset=normalized_resolution_preset,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame,
    )
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
        resolution=None,
        duration=5,
        negative_prompt=normalized_negative_prompt,
        use_end_frame=use_end_frame,
        resolution_preset=normalized_resolution_preset,
        upscale=False,
        extract_last_frame=True,
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
            result_meta=final_result_meta,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=5,
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_wan22_video_v2_task",
        )
    )
