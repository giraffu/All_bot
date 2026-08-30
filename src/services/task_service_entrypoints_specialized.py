from typing import Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import (
    MODE_FACE_VIDEO_STEP1,
    MODE_LTX25_VIDEO_UPSCALE,
    MODE_NAME_MAP,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
)
from src.domain_config.ltx25_video_upscale import (
    LTX25_VIDEO_UPSCALE_COST,
    LTX25_VIDEO_UPSCALE_DURATION_SECONDS,
    LTX25_VIDEO_UPSCALE_FACTOR,
    normalize_ltx25_video_upscale_prompt,
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
from src.services.ltx_video_extension_service import normalize_ltx_video_chain_task_ids
from src.services.scail2_face_swap_pipeline_service import (
    process_bot_scail2_face_swap_pipeline,
)


async def process_ltx_video_task_for_actor(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str | None,
    prompt: str,
    image_path: str | None,
    end_image_path: str | None = None,
    video_path: str | None = None,
    resolution: str | int | None = None,
    duration: str | int | None = None,
    ltx_mode: str = "i2v",
    ltx_prev_task_id: str | None = None,
    ltx_chain_task_ids: list[str] | None = None,
    lora_name: str | None = None,
    lora_strength: float | None = None,
    lora_items: list[dict[str, Any]] | None = None,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    negative_prompt: str | None = None,
    display_mode_name_override: str | None = None,
    result_meta: dict[str, Any] | None = None,
    status_msg_id: int | None = None,
    base_priority: int = 0,
    user_cancel_allowed: bool = True,
    allow_cancel: bool = True,
    show_queue_status: bool = True,
    send_result: bool = True,
    delete_status: bool = True,
    record_history: bool = True,
    deduct_quota: bool = True,
    cost_override: int | None = None,
):
    from src.constants import MODE_LTX_VIDEO

    internal_user_id = await resolve_internal_user_id(user_id, username)

    mode = MODE_LTX_VIDEO
    resolution = str(resolution or "1280x704")
    duration = f"{duration}s" if isinstance(duration, int) else str(duration or "5s")
    ltx_mode = ltx_mode or "i2v"
    display_mode_name = display_mode_name_override or translate_context_text(
        context, "task.mode_ltx_video"
    )

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
                mode_name=display_mode_name,
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
            mode_name=display_mode_name,
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
        submit_images = [path for path in [image_path, end_image_path] if path]
    else:
        submit_images = [image_path] if image_path else []

    task_result_meta = dict(result_meta or {})
    task_result_meta.update(
        {
            "ltx_mode": ltx_mode,
            "extract_last_frame": True,
        }
    )
    normalized_ltx_prev_task_id = str(ltx_prev_task_id or "").strip()
    normalized_ltx_chain_task_ids = normalize_ltx_video_chain_task_ids(
        ltx_chain_task_ids
    )
    if normalized_ltx_prev_task_id and not normalized_ltx_chain_task_ids:
        normalized_ltx_chain_task_ids = [normalized_ltx_prev_task_id]
    if normalized_ltx_prev_task_id:
        task_result_meta["ltx_prev_task_id"] = normalized_ltx_prev_task_id
    if normalized_ltx_chain_task_ids:
        task_result_meta["ltx_chain_task_ids"] = normalized_ltx_chain_task_ids
    if lora_items:
        task_result_meta["lora_items"] = lora_items
    elif lora_name:
        task_result_meta["lora_name"] = lora_name
        if lora_strength is not None:
            task_result_meta["lora_strength"] = lora_strength

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
    normalized_negative_prompt = str(negative_prompt or "").strip()
    if normalized_negative_prompt:
        inputs["negative_prompt"] = normalized_negative_prompt
    if normalized_ltx_prev_task_id:
        inputs["ltx_prev_task_id"] = normalized_ltx_prev_task_id
    if normalized_ltx_chain_task_ids:
        inputs["ltx_chain_task_ids"] = normalized_ltx_chain_task_ids
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
            update=None,
            chat_id=chat_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=mode,
            inputs=inputs,
            prompt=prompt,
            is_video=True,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            cost_override=cost_override,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                mode_name=display_mode_name,
                resolution=resolution,
                duration=duration,
            ),
            allow_contribute=allow_contribute,
            result_meta=task_result_meta,
            status_msg_id=status_msg_id,
            base_priority=base_priority,
            user_cancel_allowed=user_cancel_allowed,
            allow_cancel=allow_cancel,
            show_queue_status=show_queue_status,
            send_result=send_result,
            delete_status=delete_status,
            record_history=record_history,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths([image_path, end_image_path, video_path]),
            runtime_state=runtime_state,
            task_label="ltx video task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: (
                    state.task_submitted and state.actual_cost > 0
                ),
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "ltx video task"
                ),
                unexpected_error_prefix="出错了",
            ),
        )
    )


async def process_ltx_video_task(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    **kwargs: Any,
):
    actor = extract_actor_from_update(update)
    return await process_ltx_video_task_for_actor(
        context=context,
        chat_id=actor.chat_id,
        user_id=actor.user_id,
        username=actor.username,
        **kwargs,
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
    reference_preprocessed: bool = False,
    history_reference_image_path: str | None = None,
    deduct_quota: bool = True,
    cost_override: int | None = None,
    base_priority: int = 0,
    allow_cancel: bool = True,
    user_cancel_allowed: bool = True,
    send_result: bool = True,
    record_history: bool = True,
    task_id_override: str | None = None,
):
    if task_type not in {
        MODE_SCAIL2_ACTION_TRANSFER,
        MODE_SCAIL2_ACTION_TRANSFER_LONG,
        MODE_SCAIL2_VIDEO_REPLACEMENT,
        MODE_SCAIL2_FACE_SWAP_V2,
    }:
        raise ValueError(f"Unsupported SCAIL-2 task type: {task_type}")

    public_task_type = (
        MODE_SCAIL2_ACTION_TRANSFER
        if task_type == MODE_SCAIL2_ACTION_TRANSFER_LONG
        else task_type
    )
    internal_user_id = await resolve_internal_user_id(user_id, username)

    duration_seconds = normalize_scail2_duration_seconds(
        duration,
        strict=True,
        task_type=public_task_type,
    )
    normalized_prompt = normalize_scail2_positive_prompt(public_task_type, prompt)
    cost = get_scail2_cost(duration_seconds, strict=True, task_type=public_task_type)
    if (
        public_task_type == MODE_SCAIL2_FACE_SWAP_V2
        and not reference_preprocessed
    ):
        return await process_bot_scail2_face_swap_pipeline(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            internal_user_id=internal_user_id,
            username=username,
            reference_image_path=reference_image_path,
            motion_video_path=motion_video_path,
            prompt=normalized_prompt,
            duration=duration_seconds,
            message_id=message_id,
            cleanup=cleanup,
            source_post_id=source_post_id,
            normal_priority=base_priority,
            cost=cost,
            process_scail2_stage_func=process_scail2_video_task,
        )
    resolution = f"{SCAIL2_FIXED_WIDTH}x{SCAIL2_FIXED_HEIGHT}"
    mode_name_key = MODE_NAME_MAP[public_task_type]
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
    submit_images = [reference_image_path, motion_video_path]
    if history_reference_image_path:
        submit_images.append(history_reference_image_path)
    inputs = build_task_inputs(
        prompt=normalized_prompt,
        images=submit_images if reference_image_path and motion_video_path else [],
        resolution=resolution,
        duration=duration_seconds,
        negative_prompt=normalize_scail2_negative_prompt(None),
        reference_preprocessed=reference_preprocessed,
        history_reference_image=history_reference_image_path,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=public_task_type,
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
            task_type=public_task_type,
            inputs=inputs,
            prompt=normalized_prompt,
            is_video=True,
            source_post_id=source_post_id,
            deduct_quota=deduct_quota,
            cost_override=cost_override,
            base_priority=base_priority,
            user_cancel_allowed=user_cancel_allowed,
            allow_cancel=allow_cancel,
            send_result=send_result,
            record_history=record_history,
            result_input_image_indices=(
                [2, 1] if history_reference_image_path else None
            ),
            task_id_override=task_id_override,
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
            cleanup_paths=build_cleanup_paths(
                [
                    reference_image_path,
                    motion_video_path,
                    history_reference_image_path,
                ]
            ),
            runtime_state=runtime_state,
            task_label="scail2 video task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: (
                    state.task_submitted and state.actual_cost > 0
                ),
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "scail2 video task",
                    verb="processing",
                ),
                unexpected_error_prefix="系统错误",
            ),
        )
    )


async def process_ltx25_video_upscale_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str | None,
    video_path: str,
    prompt: str = "",
    message_id: int | None = None,
    cleanup: bool = True,
):
    internal_user_id = await resolve_internal_user_id(user_id, username)
    normalized_prompt = normalize_ltx25_video_upscale_prompt(prompt)
    mode_name = translate_context_text(
        context, MODE_NAME_MAP[MODE_LTX25_VIDEO_UPSCALE]
    )
    runtime_state = BotTaskRuntimeState(actual_cost=LTX25_VIDEO_UPSCALE_COST)
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    duration_label = f"{LTX25_VIDEO_UPSCALE_DURATION_SECONDS}s"
    resolution_label = f"{LTX25_VIDEO_UPSCALE_FACTOR}x"
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context,
                "task.status_processing_mode_with_settings",
                mode_name=mode_name,
                resolution=resolution_label,
                duration=duration_label,
            ),
            notice=notice,
        ),
        progress_wait_text=translate_context_text(
            context, "task.status_wait_generating_video"
        ),
        completion_caption=translate_context_text(
            context, "task.status_completion_mode", mode_name=mode_name
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
        images=[video_path],
        duration=LTX25_VIDEO_UPSCALE_DURATION_SECONDS,
    )
    return await run_bot_task_application(
        flow=build_bot_task_flow_context(
            context=context,
            chat_id=chat_id,
            status_msg_id=message_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=MODE_LTX25_VIDEO_UPSCALE,
            inputs=inputs,
            prompt=normalized_prompt,
            is_video=True,
            deduct_quota=True,
            cost_override=LTX25_VIDEO_UPSCALE_COST,
            user_cancel_allowed=True,
            allow_cancel=True,
            send_result=True,
            record_history=True,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode_with_settings",
                notice=notice,
                mode_name=mode_name,
                resolution=resolution_label,
                duration=duration_label,
            ),
            prefer_edit_status=True,
            billing_resolution=resolution_label,
            requested_duration=LTX25_VIDEO_UPSCALE_DURATION_SECONDS,
            cleanup=cleanup,
            cleanup_paths=build_cleanup_paths([video_path]),
            runtime_state=runtime_state,
            task_label="ltx25 video upscale task",
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: (
                    state.task_submitted and state.actual_cost > 0
                ),
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "ltx25 video upscale task", verb="processing"
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
                unexpected_should_refund=lambda state: (
                    state.task_submitted and state.actual_cost > 0
                ),
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "face video task",
                    verb="processing",
                ),
                unexpected_error_prefix="系统错误",
            ),
        )
    )
