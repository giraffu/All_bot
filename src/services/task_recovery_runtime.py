import logging

from src.logger import UserLogger
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_service import TaskService

logger = logging.getLogger(__name__)


class RecoveryMessageAdapter:
    def __init__(self, bot, chat_id, message_id):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            logger.debug("Recovery edit_text failed: %s", exc)

    async def delete(self):
        try:
            await self.bot.delete_message(
                chat_id=self.chat_id, message_id=self.message_id
            )
        except Exception as exc:
            logger.debug("Recovery delete failed: %s", exc)


class RecoveryContextAdapter:
    def __init__(self, application):
        self.bot = application.bot
        self.bot_data = getattr(application, "bot_data", {})


async def run_recovered_task(task_data: dict, application) -> bool:
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

    if not backend_task_id:
        return False

    runtime_context = RecoveryContextAdapter(application)
    status_msg = (
        RecoveryMessageAdapter(bot, chat_id, message_id)
        if chat_id and message_id
        else None
    )

    user_logger = UserLogger(user_id, username)
    identity_str = await permission_service.get_user_identity(user_id)
    user_group = await permission_service.get_user_group(user_id)

    final_info = await TaskService.monitor_task_progress(
        backend_task_id,
        status_msg,
        is_video,
        image_service.monitor_progress,
        identity_str=identity_str,
        user_group=user_group,
    )
    if not final_info:
        return False

    await TaskService.handle_task_completion(
        context=runtime_context,
        chat_id=chat_id,
        internal_user_id=user_id,
        prompt=prompt,
        task_type=task_type,
        task_id=backend_task_id,
        saved_input_images=saved_input_images,
        user_logger=user_logger,
        is_video=is_video,
        send_result=bool(chat_id),
        reply_markup=None,
        status_msg=status_msg,
        delete_status=bool(status_msg),
    )
    return True
