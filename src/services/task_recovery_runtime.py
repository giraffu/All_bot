import logging

from src.constants import MODE_NAME_MAP
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_service_message_support import (
    build_message_spec,
    resolve_display_mode_name,
    translate_context_text,
)
from src.services.task_service_completion import (
    complete_monitored_bot_task,
)
from src.services.task_service_types import (
    BotTaskCompletionContext,
    BotTaskMessageSpec,
    BotTaskRuntimeState,
)
from src.services.tg_task_runtime import (
    TelegramBotContextAdapter,
    TelegramMessageAdapter,
    monitor_task_progress,
)

logger = logging.getLogger(__name__)


def _resolve_recovered_task_language(task_data: dict) -> str:
    metadata = task_data.get("metadata") or {}
    return (
        task_data.get("language_code")
        or task_data.get("lang")
        or metadata.get("language_code")
        or metadata.get("lang")
        or "zh"
    )


def _build_recovered_message_spec(*, context, task_type: str) -> BotTaskMessageSpec:
    display_mode_name = resolve_display_mode_name(
        task_type,
        context=context,
        mode_name_map=MODE_NAME_MAP,
    )
    return build_message_spec(
        initial_status_text="",
        completion_caption=translate_context_text(
            context,
            "task.status_completion_mode",
            mode_name=display_mode_name,
        ),
        missing_output_message=translate_context_text(
            context,
            "task.status_missing_output_refunded",
        ),
        cancellation_message_template=translate_context_text(
            context,
            "task.status_cancelled_refunded",
            cost="{cost}",
        ),
    )


async def _monitor_recovered_task_progress(
    *,
    task_id,
    status_msg,
    is_video,
    identity_str=None,
    user_group=None,
):
    return await monitor_task_progress(
        task_id=task_id,
        status_msg=status_msg,
        is_video=is_video,
        monitor_func=image_service.monitor_progress,
        identity_str=identity_str,
        user_group=user_group,
    )


def _build_recovered_completion_context(
    *,
    context,
    chat_id,
    internal_user_id,
    username,
    prompt,
    task_type,
    registry_task_id,
    backend_task_id,
    saved_input_images,
    is_video,
    send_result,
    reply_markup,
    status_msg,
    delete_status,
    allow_contribute,
    billing_resolution,
    requested_duration,
    caption=None,
    final_info,
):
    task_runtime = BotTaskRuntimeState(
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        task_submitted=True,
    )
    return BotTaskCompletionContext(
        context=context,
        chat_id=chat_id,
        status_msg=status_msg,
        runtime_state=task_runtime,
        internal_user_id=internal_user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        saved_input_images=saved_input_images,
        final_info=final_info,
        is_video=is_video,
        message_spec=_build_recovered_message_spec(
            context=context,
            task_type=task_type,
        ),
        send_result=send_result,
        reply_markup=reply_markup,
        delete_status=delete_status,
        caption=caption,
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
    )


async def _handle_recovered_task_completion(*, completion: BotTaskCompletionContext):
    return await complete_monitored_bot_task(completion=completion)


async def run_recovered_task(*, registry_task_id: str, task_data: dict, application) -> bool:
    bot = application.bot
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    backend_task_id = task_data.get("backend_task_id")
    chat_id = task_data.get("chat_id")
    message_id = task_data.get("message_id")
    task_type = task_data.get("task_type")
    prompt = task_data.get("prompt", "")
    saved_input_images = task_data.get("saved_input_images", [])
    is_video = task_data.get("is_video", False)
    allow_contribute = task_data.get("allow_contribute", True)
    metadata = task_data.get("metadata") or {}
    billing_resolution = task_data.get("billing_resolution") or metadata.get(
        "billing_resolution"
    )
    requested_duration = task_data.get("requested_duration") or metadata.get(
        "requested_duration"
    )

    if not registry_task_id or not backend_task_id:
        return False

    runtime_context = TelegramBotContextAdapter(application)
    runtime_context.lang = _resolve_recovered_task_language(task_data)
    status_msg = (
        TelegramMessageAdapter(bot, chat_id, message_id)
        if chat_id and message_id
        else None
    )

    identity_str = await permission_service.get_user_identity(user_id)
    user_group = await permission_service.get_user_group(user_id)

    final_info = await _monitor_recovered_task_progress(
        task_id=backend_task_id,
        status_msg=status_msg,
        is_video=is_video,
        identity_str=identity_str,
        user_group=user_group,
    )
    if not final_info:
        return False

    completion = _build_recovered_completion_context(
        context=runtime_context,
        chat_id=chat_id,
        internal_user_id=user_id,
        username=username,
        prompt=prompt,
        task_type=task_type,
        registry_task_id=registry_task_id,
        backend_task_id=backend_task_id,
        saved_input_images=saved_input_images,
        is_video=is_video,
        send_result=bool(chat_id),
        reply_markup=None,
        status_msg=status_msg,
        delete_status=bool(status_msg),
        allow_contribute=allow_contribute,
        billing_resolution=billing_resolution,
        requested_duration=requested_duration,
        final_info=final_info,
    )
    await _handle_recovered_task_completion(completion=completion)
    return True
