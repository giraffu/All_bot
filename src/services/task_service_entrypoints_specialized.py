from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_FACE_VIDEO_STEP1
from src.core.video_billing import normalize_requested_duration_seconds
from src.services.permission_service import permission_service
from src.services.task_service_cleanup import cleanup_task_files
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import (
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
from src.services.task_service_support import get_acceleration_notice
from src.services.task_service_types import (
    BotTaskBillingContext,
    BotTaskCleanupPolicy,
    BotTaskFailurePolicy,
    BotTaskFlowContext,
    BotTaskPresentationContext,
    BotTaskRequestContext,
    BotTaskRuntimeState,
)


async def process_ltx_video_task(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    image_path: str,
    lora_name: str | None = None,
    lora_strength: float | None = None,
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
    inputs = build_task_inputs(
        prompt=prompt,
        images=[image_path] if image_path else [],
        resolution=resolution,
        duration=duration,
        lora_name=lora_name,
        lora_strength=lora_strength,
    )
    billing_args = resolve_video_billing_args(
        is_video=True,
        resolution=resolution,
        task_type=mode,
        duration=duration,
        duration_transform=normalize_requested_duration_seconds,
    )

    return await run_bot_task_application(
        flow=BotTaskFlowContext(
            runtime_state=runtime_state,
            request=BotTaskRequestContext(
                context=context,
                update=update,
                chat_id=chat_id,
                internal_user_id=internal_user_id,
                username=username,
                task_type=mode,
                inputs=inputs,
                prompt=prompt,
                is_video=True,
                source_post_id=source_post_id,
            ),
            presentation=BotTaskPresentationContext(
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
            ),
            billing=BotTaskBillingContext(
                billing_resolution=billing_args["billing_resolution"],
                requested_duration=billing_args["requested_duration"],
            ),
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "ltx video task"
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
        flow=BotTaskFlowContext(
            runtime_state=runtime_state,
            request=BotTaskRequestContext(
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
            ),
            presentation=BotTaskPresentationContext(
                message_spec=message_spec,
                submitted_status_builder=build_translated_cost_status_builder(
                    context,
                    "task.status_submitted_mode_with_resolution",
                    notice=notice,
                    mode_name=translate_context_text(context, "task.mode_face_video_step1"),
                    resolution=f"{resolution}p",
                ),
                prefer_edit_status=True,
            ),
            billing=BotTaskBillingContext(
                billing_resolution=billing_args["billing_resolution"],
            ),
            failure_policy=BotTaskFailurePolicy(
                unexpected_should_refund=lambda state: state.task_submitted
                and state.actual_cost > 0,
                unexpected_error_log_message=build_unexpected_error_log_message(
                    "face video task",
                    verb="processing",
                ),
                unexpected_error_prefix="系统错误",
            ),
            cleanup_policy=BotTaskCleanupPolicy(
                cleanup_paths=build_cleanup_paths([face_image_path, video_path]),
                cleanup_enabled=cleanup,
                cleanup_files_func=cleanup_task_files,
            ),
        )
    )
