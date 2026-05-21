from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_CUSTOM_VIDEO, MODE_NAME_MAP
from src.core.video_billing import (
    normalize_requested_billing_resolution,
    normalize_requested_duration_seconds,
)
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.utils import load_prompts


async def process_video_task_template(
    *,
    service,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    mode: str,
    default_prompt_key: str,
    default_prompt_text: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    internal_user_id = await resolve_internal_user_id(user_id, username)

    resolution, duration_str, res_val, duration = await service._resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
    )

    prompts_config = load_prompts()
    base_prompt = prompts_config.get(default_prompt_key, default_prompt_text)

    mode_name = MODE_NAME_MAP.get(mode, mode)
    display_mode_name = context.t(mode_name) if hasattr(context, "t") else mode_name
    runtime_state = service._create_runtime_state()
    notice = await service._get_acceleration_notice(user_id)
    message_spec = service._build_message_spec(
        initial_status_text=(
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str})...{notice}"
        ),
        progress_wait_text="⏳ 正在生成视频，请耐心等待...",
        completion_caption=f"✅ {display_mode_name} 生成完成",
        missing_output_message="生成完成但未获取到任务信息，已退还灵石",
    )
    inputs = {
        "prompt": base_prompt,
        "images": [image_path] if image_path else [],
        "resolution": res_val,
        "duration": duration,
    }

    return await service._run_bot_task_flow(
        context=context,
        update=update,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt=f"[{resolution}|{duration_str}] {base_prompt}",
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=lambda actual_cost: (
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str}, 消耗{actual_cost}灵石)...{notice}"
        ),
        source_post_id=source_post_id,
        allow_contribute=allow_contribute,
        billing_resolution=normalize_requested_billing_resolution(resolution, mode),
        requested_duration=duration,
        unexpected_should_refund=lambda state: state.task_submitted
        and state.actual_cost > 0,
        unexpected_error_log_message="Error in {mode} task for user {internal_user_id}: {error}".replace(
            "{mode}", mode
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=[image_path] if image_path else None,
        cleanup_enabled=cleanup,
    )


async def process_custom_video_task(
    *,
    service,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str,
    cleanup: bool = True,
    source_post_id: Optional[int] = None,
):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    internal_user_id = await resolve_internal_user_id(user_id, username)

    mode = MODE_CUSTOM_VIDEO
    resolution, duration, _res_val, _duration_val = await service._resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
    )

    runtime_state = service._create_runtime_state()
    notice = await service._get_acceleration_notice(user_id)
    message_spec = service._build_message_spec(
        initial_status_text=(
            f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration})...{notice}"
        ),
        progress_wait_text="⏳ 正在生成自定义视频，请耐心等待...",
        completion_caption="✅ 自定义图生视频生成完成",
    )
    inputs = {
        "prompt": prompt,
        "images": [image_path] if image_path else [],
        "resolution": resolution,
        "duration": duration,
    }

    return await service._run_bot_task_flow(
        context=context,
        update=update,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt=f"[{resolution}|{duration}] {prompt}",
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=lambda actual_cost: (
            f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration}, 消耗{actual_cost}灵石)...{notice}\n⏳ 正在生成自定义视频，请耐心等待..."
        ),
        source_post_id=source_post_id,
        billing_resolution=normalize_requested_billing_resolution(resolution, mode),
        requested_duration=normalize_requested_duration_seconds(duration),
        refund_suffix_mode="never",
        unexpected_should_refund=lambda state: state.task_submitted,
        unexpected_error_log_message="Error in custom video task for user {internal_user_id}: {error}",
        unexpected_error_prefix="出错了",
        cleanup_paths=[image_path] if image_path else None,
        cleanup_enabled=cleanup,
    )
