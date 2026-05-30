from typing import Any, Optional, Tuple

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_NAME_MAP,
    MODE_WAN22_VIDEO_V2,
)
from src.services.permission_service import permission_service
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import (
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
from src.services.task_service_types import (
    BotTaskBillingContext,
    BotTaskCleanupPolicy,
    BotTaskFailurePolicy,
    BotTaskFlowContext,
    BotTaskPresentationContext,
    BotTaskRequestContext,
    BotTaskRuntimeState,
)
from src.utils import robust_send_message


def _build_default_failure_policy(entrypoint_name: str) -> BotTaskFailurePolicy:
    return BotTaskFailurePolicy(
        unexpected_error_log_message=build_unexpected_error_log_message(
            entrypoint_name
        ),
        unexpected_error_prefix="出错了",
    )


def _build_default_cleanup_policy(
    images: list[str],
    *,
    cleanup: bool,
) -> BotTaskCleanupPolicy:
    return BotTaskCleanupPolicy(
        cleanup_paths=build_cleanup_paths(images),
        cleanup_enabled=cleanup,
        cleanup_files_func=cleanup_task_files,
    )


def _build_generation_message_spec(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    notice: str | None,
    initial_status_text: str,
    progress_wait_text: str | None = None,
    completion_caption: str | None = None,
) -> Any:
    return build_message_spec(
        initial_status_text=build_status_message(
            initial_status_text,
            notice=notice,
        ),
        progress_wait_text=progress_wait_text,
        completion_caption=completion_caption,
        missing_output_message=translate_context_text(
            context, "task.status_missing_output_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )


def _build_generation_submitted_status_builder(
    context: ContextTypes.DEFAULT_TYPE,
    status_key: str,
    *,
    notice: str | None,
    **kwargs: Any,
) -> Any:
    return build_translated_cost_status_builder(
        context,
        status_key,
        notice=notice,
        **kwargs,
    )


def _resolve_generation_display_mode_name(
    context: ContextTypes.DEFAULT_TYPE,
    task_type: str,
) -> str:
    return resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )


def _build_generation_completion_caption(
    context: ContextTypes.DEFAULT_TYPE,
    task_type: str,
) -> str:
    return translate_context_text(
        context,
        "task.status_completion_mode",
        mode_name=_resolve_generation_display_mode_name(context, task_type),
    )


def _resolve_generation_billing_args(
    *,
    is_video: bool,
    resolution: Any,
    task_type: str,
    duration: Any,
    allowed_task_types: tuple[str, ...],
) -> dict[str, Any]:
    return resolve_video_billing_args(
        is_video=is_video,
        resolution=resolution,
        task_type=task_type,
        duration=duration,
        allowed_task_types=allowed_task_types,
    )


def _build_generation_flow_context(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    status_msg_id: int | None,
    internal_user_id: int,
    username: str,
    task_type: str,
    inputs: dict[str, Any],
    prompt: str,
    is_video: bool,
    source_post_id: Optional[int],
    deduct_quota: bool,
    message_spec: Any,
    submitted_status_builder: Any,
    send_result: bool,
    reply_markup: InlineKeyboardMarkup | None,
    delete_status: bool,
    allow_contribute: bool,
    billing_resolution: Optional[str],
    requested_duration: Optional[int],
    images: list[str],
    cleanup: bool,
    entrypoint_name: str,
) -> BotTaskFlowContext:
    return BotTaskFlowContext(
        runtime_state=BotTaskRuntimeState(),
        request=BotTaskRequestContext(
            context=context,
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
        ),
        presentation=BotTaskPresentationContext(
            message_spec=message_spec,
            submitted_status_builder=submitted_status_builder,
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
        ),
        billing=BotTaskBillingContext(
            billing_resolution=billing_resolution,
            requested_duration=requested_duration,
            missing_output_should_refund=deduct_quota,
        ),
        failure_policy=_build_default_failure_policy(entrypoint_name),
        cleanup_policy=_build_default_cleanup_policy(images, cleanup=cleanup),
    )


async def process_image_to_video_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
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
    reply_markup: InlineKeyboardMarkup = None,
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
    display_mode_name = _resolve_generation_display_mode_name(context, task_type)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution_value,
        duration=duration_value,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    message_spec = _build_generation_message_spec(
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
        completion_caption=_build_generation_completion_caption(
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
    billing_args = _resolve_generation_billing_args(
        is_video=True,
        resolution=resolution_value,
        task_type=task_type,
        duration=duration_value,
        allowed_task_types=(MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO),
    )

    return await run_bot_task_application(
        flow=_build_generation_flow_context(
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
            submitted_status_builder=_build_generation_submitted_status_builder(
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


async def process_wan22_video_v2_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
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
    reply_markup: InlineKeyboardMarkup = None,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    display_mode_name = _resolve_generation_display_mode_name(context, task_type)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=None,
        duration=5,
        negative_prompt=negative_prompt,
        use_end_frame=use_end_frame,
        color_match=color_match,
        perfect_loop=perfect_loop,
        upscale=upscale,
        extract_last_frame=extract_last_frame,
    )
    message_spec = _build_generation_message_spec(
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
        completion_caption=_build_generation_completion_caption(
            context,
            task_type,
        ),
    )
    billing_args = _resolve_generation_billing_args(
        is_video=True,
        resolution=None,
        task_type=task_type,
        duration=5,
        allowed_task_types=(),
    )

    return await run_bot_task_application(
        flow=_build_generation_flow_context(
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
            submitted_status_builder=_build_generation_submitted_status_builder(
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


async def process_generation_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
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
    reply_markup: InlineKeyboardMarkup = None,
    lora_name: str = None,
    lora_strength: float = 1.0,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    resolution: Any = None,
    duration: Any = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    internal_user_id = await resolve_internal_user_id(user_id, username)

    if not task_type:
        task_type = "video" if is_video else "image"

    if is_video and task_type in [MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO]:
        return await process_image_to_video_task(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            images=images,
            resolution=resolution,
            duration=duration,
            status_msg_id=status_msg_id,
            delete_status=delete_status,
            task_type=task_type,
            cleanup=cleanup,
            send_result=send_result,
            deduct_quota=deduct_quota,
            reply_markup=reply_markup,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )
    if is_video and task_type == MODE_WAN22_VIDEO_V2:
        return await process_wan22_video_v2_task(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            prompt=prompt,
            negative_prompt="",
            images=images,
            use_end_frame=len(images) > 1,
            color_match=False,
            perfect_loop=False,
            upscale=False,
            extract_last_frame=True,
            status_msg_id=status_msg_id,
            delete_status=delete_status,
            task_type=task_type,
            cleanup=cleanup,
            send_result=send_result,
            deduct_quota=deduct_quota,
            reply_markup=reply_markup,
            allow_contribute=allow_contribute,
            source_post_id=source_post_id,
        )

    resolution = 512
    duration = 5

    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution,
        duration=duration,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    log_prompt = build_log_prompt(
        prompt,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
    )

    message_spec = _build_generation_message_spec(
        context=context,
        notice=notice,
        initial_status_text=(
            translate_context_text(context, "task.status_processing_video")
            if is_video
            else translate_context_text(
                context, "task.status_processing_images", image_count=len(images)
            )
        ),
        completion_caption=_build_generation_completion_caption(
            context,
            task_type,
        ),
    )

    billing_args = _resolve_generation_billing_args(
        is_video=is_video,
        resolution=resolution,
        task_type=task_type,
        duration=duration,
        allowed_task_types=(MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO),
    )

    return await run_bot_task_application(
        flow=_build_generation_flow_context(
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
            submitted_status_builder=_build_generation_submitted_status_builder(
                context,
                "task.status_submitted_video"
                if is_video
                else "task.status_submitted_images",
                notice=notice,
                image_count=len(images),
            ),
            send_result=send_result,
            reply_markup=reply_markup,
            delete_status=delete_status,
            allow_contribute=allow_contribute,
            billing_resolution=billing_args["billing_resolution"],
            requested_duration=billing_args["requested_duration"],
            images=images,
            cleanup=cleanup,
            entrypoint_name="process_generation_task",
        )
    )


async def process_i2i_pro_task(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    internal_user_id = await resolve_internal_user_id(user_id, username)

    if not images or len(images) == 0:
        await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
        return None, None

    image_path = images[0]
    runtime_state = BotTaskRuntimeState()
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            translate_context_text(
                context, "task.status_processing_mode", mode_name=translate_context_text(context, "task.mode_i2i_pro")
            ),
            notice=notice,
        ),
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=translate_context_text(context, "task.mode_i2i_pro"),
        ),
        missing_output_message=translate_context_text(
            context, "task.status_missing_output_refunded"
        ),
        cancellation_message_template=translate_context_text(
            context, "task.status_cancelled_refunded", cost="{cost}"
        ),
    )
    inputs = build_task_inputs(
        prompt=prompt,
        images=[image_path],
        resolution=512,
        duration=5,
    )

    return await run_bot_task_application(
        flow=BotTaskFlowContext(
            runtime_state=runtime_state,
            request=BotTaskRequestContext(
                context=context,
                chat_id=chat_id,
                internal_user_id=internal_user_id,
                username=username,
                task_type=MODE_I2I_PRO,
                inputs=inputs,
                prompt=prompt,
                is_video=False,
                source_post_id=source_post_id,
            ),
            presentation=BotTaskPresentationContext(
                message_spec=message_spec,
                submitted_status_builder=build_translated_cost_status_builder(
                    context,
                    "task.status_submitted_mode",
                    notice=notice,
                    mode_name=translate_context_text(context, "task.mode_i2i_pro"),
                ),
                allow_contribute=allow_contribute,
            ),
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "process_i2i_pro_task"
                ),
                unexpected_error_prefix="出错了",
                refund_suffix_mode="always",
            ),
            cleanup_policy=BotTaskCleanupPolicy(
                cleanup_paths=build_cleanup_paths(images),
                cleanup_files_func=cleanup_task_files,
            ),
        )
    )
