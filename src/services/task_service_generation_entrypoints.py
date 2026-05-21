from typing import Optional, Tuple

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMG2IMG_LORA, MODE_NAME_MAP
from src.core.video_billing import normalize_requested_billing_resolution
from src.services.task_service_types import BotTaskRuntimeState


async def process_generation_task_entrypoint(
    *,
    service_cls,
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
) -> Tuple[Optional[bytes], Optional[str]]:
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
    internal_user_id = internal_user.id

    if not task_type:
        task_type = "video" if is_video else "image"

    resolution = 512
    duration = 5

    if is_video and task_type in [MODE_CUSTOM_VIDEO, "video_lora"]:
        _, _, resolution, duration = await service_cls._resolve_custom_video_settings(
            context
        )

    runtime_state = BotTaskRuntimeState()
    notice = await service_cls._get_acceleration_notice(user_id)
    inputs = {
        "prompt": prompt,
        "images": images,
        "resolution": resolution,
        "duration": duration,
        "lora_name": lora_name,
        "lora_strength": lora_strength,
    }
    message_spec = service_cls._build_message_spec(
        initial_status_text=(
            f"🚀 正在处理视频生成任务...{notice}"
            if is_video
            else f"🚀 正在处理 {len(images)} 张图片...{notice}"
        ),
        missing_output_message="生成完成但未获取到文件路径，已退还灵石",
    )

    log_prompt = prompt
    if task_type in ("video_lora", MODE_IMG2IMG_LORA) and lora_name:
        log_prompt = f"[模型: {lora_name}] {prompt}"

    mode_name = MODE_NAME_MAP.get(task_type, task_type)
    display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name
    message_spec = service_cls._with_completion_caption(
        message_spec,
        f"✅ {display_mode_name} 生成完成",
    )

    return await service_cls._run_bot_task_flow(
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
        submitted_status_builder=lambda actual_cost: (
            f"🚀 正在处理视频生成任务 (消耗{actual_cost}灵石)...{notice}"
            if is_video
            else f"🚀 正在处理 {len(images)} 张图片 (消耗{actual_cost}灵石)...{notice}"
        ),
        source_post_id=source_post_id,
        deduct_quota=deduct_quota,
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        allow_contribute=allow_contribute,
        billing_resolution=(
            normalize_requested_billing_resolution(resolution, task_type)
            if is_video
            else None
        ),
        requested_duration=(
            duration if is_video and task_type in (MODE_CUSTOM_VIDEO, "video_lora") else None
        ),
        missing_output_should_refund=deduct_quota,
        unexpected_error_log_message="Error in process_generation_task for user {internal_user_id}: {error}",
        unexpected_error_prefix="出错了",
        cleanup_paths=images,
        cleanup_enabled=cleanup,
    )


async def process_i2i_pro_task_entrypoint(
    *,
    service_cls,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str,
    prompt: str,
    images: list[str],
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    from src.constants import MODE_I2I_PRO
    from src.core.user_core import get_or_create_user_by_telegram
    from src.utils import robust_send_message

    internal_user, _ = await get_or_create_user_by_telegram(user_id, username)
    internal_user_id = internal_user.id

    mode = MODE_I2I_PRO

    if not images or len(images) == 0:
        await robust_send_message(context.bot, chat_id, "❌ 请先发送参考图片。")
        return None, None

    image_path = images[0]

    runtime_state = BotTaskRuntimeState()
    notice = await service_cls._get_acceleration_notice(user_id)
    message_spec = service_cls._build_message_spec(
        initial_status_text=f"🚀 正在处理幻想换脸任务...{notice}",
        completion_caption="🌟 幻想换脸生成完成",
    )
    inputs = {
        "prompt": prompt,
        "images": [image_path],
        "resolution": 512,
        "duration": 5,
    }

    return await service_cls._run_bot_task_flow(
        context=context,
        update=None,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt=prompt,
        is_video=False,
        message_spec=message_spec,
        submitted_status_builder=lambda actual_cost: (
            f"🚀 正在处理幻想换脸任务 (消耗{actual_cost}灵石)...{notice}"
        ),
        source_post_id=source_post_id,
        allow_contribute=allow_contribute,
        refund_suffix_mode="always",
        unexpected_should_refund=lambda state: state.task_submitted,
        unexpected_error_log_message="Error in process_i2i_pro_task for user {internal_user_id}: {error}",
        unexpected_error_prefix="出错了",
        cleanup_paths=images,
    )
