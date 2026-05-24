from typing import Any, Optional, Tuple

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_NAME_MAP,
)
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import (
    build_cleanup_paths,
    build_log_prompt,
    build_task_inputs,
    build_unexpected_error_log_message,
    resolve_video_billing_args,
)
from src.services.task_service_support import resolve_custom_video_settings
from src.services.task_service_message_support import (
    build_cost_status_builder,
    build_message_spec,
    build_status_message,
    resolve_display_mode_name,
    with_completion_caption,
)
from src.services.task_service_types import BotTaskRuntimeState
from src.utils import robust_send_message


async def process_image_to_video_task(
    *,
    service,
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

    runtime_state = BotTaskRuntimeState()
    notice = await service._get_acceleration_notice(internal_user_id)
    display_mode_name = resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution_value,
        duration=duration_value,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution_text}, 时长:{duration_text})",
            notice=notice,
        ),
        progress_wait_text="⏳ 正在生成视频，请耐心等待...",
        completion_caption=f"✅ {display_mode_name} 生成完成",
        missing_output_message="生成完成但未获取到文件路径，已退还灵石",
    )
    log_prompt = build_log_prompt(
        prompt,
        resolution=resolution_text,
        duration=duration_text,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=(MODE_IMAGE_TO_VIDEO, "img2img_lora"),
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution_value,
        task_type=task_type,
        duration=duration_value,
        allowed_task_types=(MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO),
    )

    return await service._run_bot_task_flow(
        context=context,
        update=None,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        prompt=log_prompt,
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=build_cost_status_builder(
            f"⏳ 任务已提交，正在排队调度{display_mode_name}生成任务 (画质:{resolution_text}, 时长:{duration_text}, 消耗{{actual_cost}}灵石)",
            notice=notice,
            wait_text="⏳ 正在生成视频，请耐心等待...",
        ),
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        billing_resolution=billing_args["billing_resolution"],
        requested_duration=billing_args["requested_duration"],
        missing_output_should_refund=deduct_quota,
        unexpected_error_log_message=build_unexpected_error_log_message(
            "process_image_to_video_task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=build_cleanup_paths(images),
        cleanup_enabled=cleanup,
    )


async def process_generation_task(
    *,
    service,
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
            service=service,
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

    resolution = 512
    duration = 5

    runtime_state = BotTaskRuntimeState()
    notice = await service._get_acceleration_notice(internal_user_id)
    inputs = build_task_inputs(
        prompt=prompt,
        images=images,
        resolution=resolution,
        duration=duration,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            "🚀 正在处理视频生成任务"
            if is_video
            else f"🚀 正在处理 {len(images)} 张图片",
            notice=notice,
        ),
        missing_output_message="生成完成但未获取到文件路径，已退还灵石",
    )

    log_prompt = build_log_prompt(
        prompt,
        lora_name=lora_name,
        task_type=task_type,
        lora_task_types=("video_lora", "img2img_lora"),
    )

    display_mode_name = resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    message_spec = with_completion_caption(
        message_spec,
        f"✅ {display_mode_name} 生成完成",
    )

    billing_args = resolve_video_billing_args(
        is_video=is_video,
        resolution=resolution,
        task_type=task_type,
        duration=duration,
        allowed_task_types=(MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO),
    )

    return await service._run_bot_task_flow(
        context=context,
        update=None,
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=task_type,
        inputs=inputs,
        prompt=log_prompt,
        is_video=is_video,
        message_spec=message_spec,
        submitted_status_builder=build_cost_status_builder(
            "⏳ 任务已提交，正在排队调度视频生成任务 (消耗{actual_cost}灵石)"
            if is_video
            else f"⏳ 任务已提交，正在排队调度 {len(images)} 张图片 (消耗{{actual_cost}}灵石)",
            notice=notice,
        ),
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        billing_resolution=billing_args["billing_resolution"],
        requested_duration=billing_args["requested_duration"],
        missing_output_should_refund=deduct_quota,
        unexpected_error_log_message=build_unexpected_error_log_message(
            "process_generation_task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=build_cleanup_paths(images),
        cleanup_enabled=cleanup,
    )


async def process_i2i_pro_task(
    *,
    service,
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
    notice = await service._get_acceleration_notice(internal_user_id)
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            "🚀 正在处理幻想换脸任务",
            notice=notice,
        ),
        completion_caption="🌟 幻想换脸生成完成",
    )
    inputs = build_task_inputs(
        prompt=prompt,
        images=[image_path],
        resolution=512,
        duration=5,
    )

    return await service._run_bot_task_flow(
        context=context,
        update=None,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=MODE_I2I_PRO,
        inputs=inputs,
        prompt=prompt,
        is_video=False,
        message_spec=message_spec,
        submitted_status_builder=build_cost_status_builder(
            "⏳ 任务已提交，正在排队调度幻想换脸任务 (消耗{actual_cost}灵石)",
            notice=notice,
        ),
        source_post_id=source_post_id,
        allow_contribute=allow_contribute,
        refund_suffix_mode="always",
        unexpected_should_refund=lambda state: state.task_submitted,
        unexpected_error_log_message=build_unexpected_error_log_message(
            "process_i2i_pro_task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=build_cleanup_paths(images),
    )
