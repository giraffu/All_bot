from typing import Any, Optional, Tuple

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.constants import MODE_I2I_PRO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.services.permission_service import permission_service
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import build_task_inputs
from src.services.task_service_flow import run_bot_task_application
from src.services.task_service_generation_image import process_standard_generation_task
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task,
)
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task,
)
from src.services.task_service_message_support import (
    build_message_spec,
    build_status_message,
    build_translated_cost_status_builder,
    translate_context_text,
)
from src.services.task_service_support import get_acceleration_notice
from src.services.task_service_types import (
    BotTaskFailurePolicy,
    BotTaskRuntimeState,
)
from src.utils import robust_send_message
from src.services.task_service_entrypoint_support import (
    build_bot_task_flow_context,
    build_unexpected_error_log_message,
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
    return await process_image_to_video_generation_task(
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
    return await process_wan22_video_v2_generation_task(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        negative_prompt=negative_prompt,
        images=images,
        use_end_frame=use_end_frame,
        color_match=color_match,
        perfect_loop=perfect_loop,
        upscale=upscale,
        extract_last_frame=extract_last_frame,
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
    return await process_standard_generation_task(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=images,
        is_video=is_video,
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
        resolution=resolution,
        duration=duration,
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
        flow=build_bot_task_flow_context(
            context=context,
            chat_id=chat_id,
            internal_user_id=internal_user_id,
            username=username,
            task_type=MODE_I2I_PRO,
            inputs=inputs,
            prompt=prompt,
            is_video=False,
            source_post_id=source_post_id,
            message_spec=message_spec,
            submitted_status_builder=build_translated_cost_status_builder(
                context,
                "task.status_submitted_mode",
                notice=notice,
                mode_name=translate_context_text(context, "task.mode_i2i_pro"),
            ),
            allow_contribute=allow_contribute,
            cleanup=True,
            cleanup_paths=images,
            task_label="process_i2i_pro_task",
            runtime_state=runtime_state,
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "process_i2i_pro_task"
                ),
                unexpected_error_prefix="出错了",
                refund_suffix_mode="always",
            ),
        )
    )
