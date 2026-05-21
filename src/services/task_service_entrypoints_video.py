from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_CUSTOM_VIDEO
from src.core.video_billing import normalize_requested_duration_seconds
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

    display_mode_name = service._resolve_display_mode_name(mode, context)
    runtime_state = service._create_runtime_state()
    notice = await service._get_acceleration_notice(user_id)
    message_spec = service._build_message_spec(
        initial_status_text=service._build_status_message(
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str})",
            notice=notice,
        ),
        progress_wait_text="⏳ 正在生成视频，请耐心等待...",
        completion_caption=f"✅ {display_mode_name} 生成完成",
        missing_output_message="生成完成但未获取到任务信息，已退还灵石",
    )
    inputs = service._build_task_inputs(
        prompt=base_prompt,
        images=[image_path] if image_path else [],
        resolution=res_val,
        duration=duration,
    )
    billing_args = service._resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
    )

    return await service._run_bot_task_flow(
        context=context,
        update=update,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt=service._build_log_prompt(
            base_prompt,
            resolution=resolution,
            duration=duration_str,
        ),
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=service._build_cost_status_builder(
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str}, 消耗{{actual_cost}}灵石)",
            notice=notice,
        ),
        source_post_id=source_post_id,
        allow_contribute=allow_contribute,
        billing_resolution=billing_args["billing_resolution"],
        requested_duration=billing_args["requested_duration"],
        unexpected_should_refund=lambda state: state.task_submitted
        and state.actual_cost > 0,
        unexpected_error_log_message=service._build_unexpected_error_log_message(
            f"{mode} task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=service._build_cleanup_paths([image_path]),
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
        initial_status_text=service._build_status_message(
            f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration})",
            notice=notice,
        ),
        progress_wait_text="⏳ 正在生成自定义视频，请耐心等待...",
        completion_caption="✅ 自定义图生视频生成完成",
    )
    inputs = service._build_task_inputs(
        prompt=prompt,
        images=[image_path] if image_path else [],
        resolution=resolution,
        duration=duration,
    )
    billing_args = service._resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
        duration_transform=normalize_requested_duration_seconds,
    )

    return await service._run_bot_task_flow(
        context=context,
        update=update,
        chat_id=chat_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt=service._build_log_prompt(
            prompt,
            resolution=resolution,
            duration=duration,
        ),
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=service._build_cost_status_builder(
            f"🚀 正在处理自定义视频生成任务 (画质:{resolution}, 时长:{duration}, 消耗{{actual_cost}}灵石)",
            notice=notice,
            wait_text="⏳ 正在生成自定义视频，请耐心等待...",
        ),
        source_post_id=source_post_id,
        billing_resolution=billing_args["billing_resolution"],
        requested_duration=billing_args["requested_duration"],
        refund_suffix_mode="never",
        unexpected_should_refund=lambda state: state.task_submitted,
        unexpected_error_log_message=service._build_unexpected_error_log_message(
            "custom video task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=service._build_cleanup_paths([image_path]),
        cleanup_enabled=cleanup,
    )
