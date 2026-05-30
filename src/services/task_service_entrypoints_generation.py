from typing import Optional

from telegram.ext import ContextTypes

from src.constants import MODE_I2I_PRO
from src.services.permission_service import permission_service
from src.services.task_service_entrypoints_common import resolve_internal_user_id
from src.services.task_service_entrypoint_support import build_task_inputs
from src.services.task_service_flow import run_bot_task_application
from src.services.task_service_message_support import (
    build_message_spec,
    build_status_message,
    build_translated_cost_status_builder,
    translate_context_text,
)
from src.services.task_service_support import get_acceleration_notice
from src.services.task_service_types import (
    BotTaskFailurePolicy,
)
from src.utils import robust_send_message
from src.services.task_service_entrypoint_support import (
    build_bot_task_flow_context,
    build_unexpected_error_log_message,
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
