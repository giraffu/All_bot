from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_CUSTOM_VIDEO, MODE_NAME_MAP
from src.services.permission_service import permission_service
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_entrypoints_generation import process_image_to_video_task
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
    build_cost_status_builder,
    build_message_spec,
    build_status_message,
    resolve_display_mode_name,
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
from src.utils import load_prompts


async def process_video_task_template(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    mode: str,
    default_prompt_key: str,
    default_prompt_text: str,
    update: Update | None = None,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    status_msg_id: Optional[int] = None,
) -> Tuple[Optional[bytes], Optional[str]]:
    if update is not None:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        username = update.effective_user.username
    if chat_id is None or user_id is None or username is None:
        raise ValueError("process_video_task_template 缺少用户或聊天上下文")
    internal_user_id = await resolve_internal_user_id(user_id, username)

    resolution, duration_str, res_val, duration = await resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
    )

    prompts_config = load_prompts()
    base_prompt = prompts_config.get(default_prompt_key, default_prompt_text)

    display_mode_name = resolve_display_mode_name(
        mode,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    runtime_state = BotTaskRuntimeState()
    notice = await get_acceleration_notice(
        internal_user_id,
        quota_manager=permission_service.quota_manager,
    )
    message_spec = build_message_spec(
        initial_status_text=build_status_message(
            f"🚀 正在处理{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str})",
            notice=notice,
        ),
        progress_wait_text="⏳ 正在生成视频，请耐心等待...",
        completion_caption=f"✅ {display_mode_name} 生成完成",
        missing_output_message="生成完成但未获取到任务信息，已退还灵石",
    )
    inputs = build_task_inputs(
        prompt=base_prompt,
        images=[image_path] if image_path else [],
        resolution=res_val,
        duration=duration,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
    )

    return await run_bot_task_application(
        flow=BotTaskFlowContext(
            runtime_state=runtime_state,
            request=BotTaskRequestContext(
                context=context,
                update=update,
                chat_id=chat_id,
                status_msg_id=status_msg_id,
                internal_user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                prompt=build_log_prompt(
                    base_prompt,
                    resolution=resolution,
                    duration=duration_str,
                ),
                is_video=True,
                source_post_id=source_post_id,
            ),
            presentation=BotTaskPresentationContext(
                message_spec=message_spec,
                submitted_status_builder=build_cost_status_builder(
                    f"⏳ 任务已提交，正在排队调度{display_mode_name}生成任务 (画质:{resolution}, 时长:{duration_str}, 消耗{{actual_cost}}灵石)",
                    notice=notice,
                ),
                allow_contribute=allow_contribute,
            ),
            billing=BotTaskBillingContext(
                billing_resolution=billing_args["billing_resolution"],
                requested_duration=billing_args["requested_duration"],
            ),
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    f"{mode} task"
                ),
                unexpected_error_prefix="出错了",
            ),
            cleanup_policy=BotTaskCleanupPolicy(
                cleanup_paths=build_cleanup_paths([image_path]),
                cleanup_enabled=cleanup,
                cleanup_files_func=cleanup_task_files,
            ),
        )
    )


async def process_custom_video_task(
    *,
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
    resolution, duration, _res_val, _duration_val = await resolve_custom_video_settings(
        context,
        update=update,
        warn_invalid_combo=True,
    )

    return await process_image_to_video_task(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=[image_path] if image_path else [],
        resolution=resolution,
        duration=duration,
        task_type=MODE_CUSTOM_VIDEO,
        cleanup=cleanup,
        source_post_id=source_post_id,
    )
