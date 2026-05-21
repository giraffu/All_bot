from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_FACE_VIDEO_STEP1
from src.core.video_billing import normalize_requested_duration_seconds
from src.services.task_service_entrypoints_common import resolve_internal_user_id


async def process_ltx_video_task(
    *,
    service,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str,
    cleanup: bool = True,
    allow_contribute: bool = True,
    source_post_id: Optional[int] = None,
):
    from src.constants import MODE_LTX_VIDEO

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    internal_user_id = await resolve_internal_user_id(user_id, username)

    mode = MODE_LTX_VIDEO
    resolution = context.user_data.get("ltx_video_resolution", "1280x704")
    duration = context.user_data.get("ltx_video_duration", "5s")

    runtime_state = service._create_runtime_state()
    notice = await service._get_acceleration_notice(user_id)
    message_spec = service._build_message_spec(
        initial_status_text=service._build_status_message(
            f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration})",
            notice=notice,
        ),
        progress_wait_text="⏳ 正在生成高级视频，可能需要数分钟，请耐心等待...",
        completion_caption="✅ 高级图生视频生成完成",
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
        prompt=prompt,
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=service._build_cost_status_builder(
            f"🚀 正在处理高级图生视频任务 (画质:{resolution}, 时长:{duration}, 消耗{{actual_cost}}灵石)",
            notice=notice,
        ),
        source_post_id=source_post_id,
        allow_contribute=allow_contribute,
        billing_resolution=billing_args["billing_resolution"],
        requested_duration=billing_args["requested_duration"],
        unexpected_should_refund=lambda state: state.task_submitted
        and state.actual_cost > 0,
        unexpected_error_log_message=service._build_unexpected_error_log_message(
            "ltx video task"
        ),
        unexpected_error_prefix="出错了",
        cleanup_paths=service._build_cleanup_paths([image_path]),
        cleanup_enabled=cleanup,
    )


async def process_face_video_task(
    *,
    service,
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
    runtime_state = service._create_runtime_state(actual_cost=cost)
    notice = await service._get_acceleration_notice(user_id)
    message_spec = service._build_message_spec(
        initial_status_text=service._build_status_message(
            f"🚀 正在处理视频换脸任务 (画质:{resolution}p)",
            notice=notice,
        ),
        completion_caption="✅ 视频换脸完成",
        missing_output_message="生成失败或超时，已退还灵石。",
    )
    inputs = service._build_task_inputs(
        prompt="Video Face Swap",
        images=[face_image_path, video_path] if face_image_path and video_path else [],
        resolution=resolution,
        duration=duration,
    )
    billing_args = service._resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        include_requested_duration=False,
    )

    return await service._run_bot_task_flow(
        context=context,
        update=None,
        chat_id=chat_id,
        status_msg_id=message_id,
        runtime_state=runtime_state,
        internal_user_id=internal_user_id,
        username=username,
        task_type=mode,
        inputs=inputs,
        prompt="face video",
        is_video=True,
        message_spec=message_spec,
        submitted_status_builder=service._build_cost_status_builder(
            f"🚀 正在处理视频换脸任务 (画质:{resolution}p, 消耗{{actual_cost}}灵石)",
            notice=notice,
        ),
        source_post_id=source_post_id,
        billing_resolution=billing_args["billing_resolution"],
        prefer_edit_status=True,
        unexpected_should_refund=lambda state: state.task_submitted
        and state.actual_cost > 0,
        unexpected_error_log_message=service._build_unexpected_error_log_message(
            "face video task",
            verb="processing",
        ),
        unexpected_error_prefix="系统错误",
        cleanup_paths=service._build_cleanup_paths([face_image_path, video_path]),
        cleanup_enabled=cleanup,
    )
