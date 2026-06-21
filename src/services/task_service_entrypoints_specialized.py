from typing import Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import (
    MODE_FACE_VIDEO_STEP1,
    MODE_NAME_MAP,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
)
from src.core.video_billing import normalize_requested_duration_seconds
from src.domain_config.scail2_video import (
    SCAIL2_FIXED_HEIGHT,
    SCAIL2_FIXED_WIDTH,
    get_scail2_cost,
    normalize_scail2_duration_seconds,
    normalize_scail2_negative_prompt,
    normalize_scail2_positive_prompt,
)
from src.services.permission_service import permission_service
from src.services.task_service_entrypoint_support import (
    extract_actor_from_update,
    build_bot_task_flow_context,
    build_cleanup_paths,
    build_task_inputs,
    build_unexpected_error_log_message,
    resolve_video_billing_args,
)
from src.services.task_service_message_support import (
    build_translated_cost_status_builder,
    build_message_spec,
    build_status_message,
    translate_context_text,
)
from src.services.task_service_flow import run_bot_task_application
from src.services.task_service_generation_common import resolve_internal_user_id
from src.services.task_service_support import get_acceleration_notice
from src.services.task_service_types import BotTaskFailurePolicy, BotTaskRuntimeState


async def process_ltx_video_task(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str | None,
    end_image_path: str | None = None,
    video_path: str | None = None,
    ltx_mode: str = "i2v",
    lora_name: str | None = None,
    lora_strength: float | None = None,
    lora_items: list[dict[str, Any]] | None = None,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    from src.constants import MODE_LTX_VIDEO

    actor = extract_actor_from_update(update)
    internal_user_id = await resolve_internal_user_id(actor.user_id, actor.username)

    mode = MODE_LTX_VIDEO
    resolution = context.user_data.get("ltx_video_resolution", "1280x704")
    duration = context.user_data.get("ltx_video_duration", "5s")
    ltx_mode = ltx_mode or context.user_data.get("ltx_video_mode") or "i2v"

    runtime_state = BotTaskRuntimeState()
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context,
                "task.status_processing_mode_with_settings",
                mode_name=translate_context_text(context, "task.mode_ltx_video"),
                resolution=resolution,
                duration=duration,
            ),
            notice=notice,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_high_res_video"
        ),
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=translate_context_text(context, "task.mode_ltx_video"),
        ),
        missing_output_message=translate_context_text(
            context, "task.status_missing_output_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )
    submit_images: list[str] = []
    if ltx_mode == "v2v_audio":
        submit_images = [video_path] if video_path else []
    elif ltx_mode == "flf2v":
        submit_images = [
            path for path in [image_path, end_image_path] if path
        ]
    else:
        submit_images = [image_path] if image_path else []

    result_meta = {
        "ltx_mode": ltx_mode,
        "extract_last_frame": True,
    }
    if lora_items:
        result_meta["lora_items"] = lora_items
    elif lora_name:
        result_meta["lora_name"] = lora_name
        if lora_strength is not None:
            result_meta["lora_strength"] = lora_strength

    inputs = build_task_inputs(
        prompt=prompt,
        images=submit_images,
        resolution=resolution,
        duration=duration,
        ltx_mode=ltx_mode,
        use_end_frame=ltx_mode == "flf2v",
        video=video_path if ltx_mode == "v2v_audio" else None,
        extract_last_frame=True,
        lora_name=lora_name,
        lora_strength=lora_strength,
        lora_items=lora_items,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
        duration_transform=normalize_requested_duration_seconds,
    )

    return await run_bot_task_application(
        flow=build_bot_task_flow_context(
            context=context,
            update=update,
            chat_id=actor.chat_id,
            internal_user_id=internal_user_id,
            username=actor.username,
            task_type=mode,
            inputs=inputs,
            prompt=prompt,
            is_video=True,
            source_post_id=source_post_id,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                mode_name=translate_context_text(context, "task.mode_ltx_video"),
                resolution=resolution,
                duration=duration,
            ),
            allow_contribute=allow_contribute,
            result_meta=result_meta,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths([image_path, end_image_path, video_path]),
            runtime_state=runtime_state,
            task_label="ltx video task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "ltx video task"
                ),
                unexpected_error_prefix="出错了",
            ),
        )
    )


async def process_scail2_video_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    task_type: str,
    reference_image_path: str,
    motion_video_path: str,
    prompt: str,
    duration: int,
    message_id: int = None,
    cleanup: bool = True,
    source_post_id: Optional[int] = None,
):
    if task_type not in {
        MODE_SCAIL2_ACTION_TRANSFER,
        MODE_SCAIL2_VIDEO_REPLACEMENT,
        MODE_SCAIL2_FACE_SWAP_V2,
    }:
        raise ValueError(f"Unsupported SCAIL-2 task type: {task_type}")

    internal_user_id = await resolve_internal_user_id(user_id, username)

    duration_seconds = normalize_scail2_duration_seconds(duration, strict=True)
    normalized_prompt = normalize_scail2_positive_prompt(task_type, prompt)
    cost = get_scail2_cost(duration_seconds, strict=True)
    resolution = f"{SCAIL2_FIXED_WIDTH}x{SCAIL2_FIXED_HEIGHT}"
    mode_name_key = MODE_NAME_MAP[task_type]
    mode_name = translate_context_text(context, mode_name_key)
    duration_label = f"{duration_seconds}s"
    runtime_state = BotTaskRuntimeState(actual_cost=cost)
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context,
                "task.status_processing_mode_with_settings",
                mode_name=mode_name,
                resolution=resolution,
                duration=duration_label,
            ),
            notice=notice,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=mode_name,
        ),
        missing_output_message=translate_context_text(
            context, "task.status_missing_output_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )
    inputs = build_task_inputs(
        prompt=normalized_prompt,
        images=(
            [reference_image_path, motion_video_path]
            if reference_image_path and motion_video_path
            else []
        ),
        resolution=resolution,
        duration=duration_seconds,
        negative_prompt=normalize_scail2_negative_prompt(None),
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=task_type,
        duration=duration_seconds,
        duration_transform=normalize_requested_duration_seconds,
    )

    return await run_bot_task_application(
        flow=build_bot_task_flow_context(
            context=context,
            chat_id=chat_id,
            status_msg_id=message_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=task_type,
            inputs=inputs,
            prompt=normalized_prompt,
            is_video=True,
            source_post_id=source_post_id,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                mode_name=mode_name,
                resolution=resolution,
                duration=duration_label,
            ),
            prefer_edit_status=True,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths([reference_image_path, motion_video_path]),
            runtime_state=runtime_state,
            task_label="scail2 video task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "scail2 video task",
                    verb="processing",
                ),
                unexpected_error_prefix="系统错误",
            ),
        )
    )


async def process_face_video_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    face_image_path: str,
    video_path: str,
    resolution: int,
    duration: int,
    cost: int,
    message_id: int = None,
    cleanup: bool = True,
    source_post_id: Optional[int] = None,
):
    internal_user_id = await resolve_internal_user_id(user_id, username)

    mode = MODE_FACE_VIDEO_STEP1
    runtime_state = BotTaskRuntimeState(actual_cost=cost)
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context,
                "task.status_processing_mode_with_resolution",
                mode_name=translate_context_text(context, "task.mode_face_video_step1"),
                resolution=f"{resolution}p",
            ),
            notice=notice,
        ),
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=translate_context_text(context, "task.mode_face_video_step1"),
        ),
        missing_output_message=translate_context_text(
            context, "task.status_generation_failed_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )
    inputs = build_task_inputs(
        prompt="Video Face Swap",
        images=[face_image_path, video_path] if face_image_path and video_path else [],
        resolution=resolution,
        duration=duration,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        include_requested_duration=False,
    )

    return await run_bot_task_application(
        flow=build_bot_task_flow_context(
            context=context,
            chat_id=chat_id,
            status_msg_id=message_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt="face video",
            is_video=True,
            source_post_id=source_post_id,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_resolution",
                notice=notice,
                mode_name=translate_context_text(context, "task.mode_face_video_step1"),
                resolution=f"{resolution}p",
            ),
            prefer_edit_status=True,
            billing_resolution=billing_args["billing_resolution"],
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths([face_image_path, video_path]),
            runtime_state=runtime_state,
            task_label="face video task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "face video task",
                    verb="processing",
                ),
                unexpected_error_prefix="系统错误",
            ),
        )
    )
