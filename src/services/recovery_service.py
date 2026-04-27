import logging
import asyncio
from src.services.task_registry import TaskRegistry
from src.services.redis_client import redis_client
from src.services.permission_service import permission_service
from src.services.image_service import image_service
from src.services.task_service import TaskService
from src.logger import UserLogger
from src.utils import create_background_task

logger = logging.getLogger(__name__)

class MockMessage:
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
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.debug(f"Recovery edit_text failed: {e}")

    async def delete(self):
        try:
            await self.bot.delete_message(chat_id=self.chat_id, message_id=self.message_id)
        except Exception as e:
            logger.debug(f"Recovery delete failed: {e}")

class MockContext:
    def __init__(self, application):
        self.bot = application.bot
        self.bot_data = getattr(application, 'bot_data', {})

async def recover_active_tasks(application):
    tasks = await TaskRegistry.get_all_tasks()
    if not tasks:
        logger.info("No active tasks to recover.")
        return
    
    logger.info(f"Found {len(tasks)} active tasks in Redis. Attempting recovery...")
    for registry_task_id, task_data in tasks.items():
        create_background_task(application, _recover_single_task(registry_task_id, task_data, application))

async def _recover_single_task(registry_task_id, task_data, application):
    bot = application.bot
    mock_context = None
    try:
        user_id = task_data.get("user_id")
        username = task_data.get("username")
        backend_task_id = task_data.get("backend_task_id")
        chat_id = task_data.get("chat_id")
        message_id = task_data.get("message_id")
        task_type = task_data.get("task_type")
        prompt = task_data.get("prompt", "")
        saved_input_images = task_data.get("saved_input_images", [])
        is_video = task_data.get("is_video", False)

        mock_context = MockContext(application)
        status_msg = MockMessage(bot, chat_id, message_id) if chat_id and message_id else None

        if not backend_task_id:
            logger.info(f"Task {registry_task_id} has no backend_task_id. Refunding...")
            await _refund_and_cleanup(registry_task_id, task_data, mock_context, "系统重启，任务未成功提交，已为您退款。")
            return

        user_logger = UserLogger(user_id, username)
        identity_str = await permission_service.get_user_identity(user_id)
        user_group = await permission_service.get_user_group(user_id)

        # Monitor Progress
        final_info = await TaskService._monitor_task_progress(
            backend_task_id, status_msg, is_video, image_service.monitor_progress, identity_str=identity_str, user_group=user_group
        )

        if final_info:
            await TaskService._handle_task_completion(
                mock_context,
                chat_id,
                user_id,
                prompt,
                task_type,
                backend_task_id,
                saved_input_images,
                user_logger,
                is_video,
                send_result=bool(chat_id),
                reply_markup=None,
                status_msg=status_msg,
                delete_status=bool(status_msg),
            )
        else:
            await _refund_and_cleanup(registry_task_id, task_data, mock_context, "❌ 任务恢复失败，已退还灵石")

    except Exception as e:
        logger.error(f"Error recovering task {registry_task_id}: {e}", exc_info=True)
        if mock_context:
            await _refund_and_cleanup(registry_task_id, task_data, mock_context, "❌ 任务恢复出现异常，已退还灵石")
    finally:
        await TaskRegistry.remove_task(registry_task_id)
        if user_id:
            await redis_client.decrement_user_concurrency(user_id)

async def _refund_and_cleanup(registry_task_id, task_data, mock_context, reason):
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    cost = task_data.get("cost", 0)
    chat_id = task_data.get("chat_id")
    
    if cost > 0:
        await permission_service.increment_quota(user_id, cost=-cost, username=username, task_type="refund_restart")
    
    if chat_id:
        try:
            from src.utils import robust_send_message
            await robust_send_message(mock_context.bot, chat_id, reason)
        except Exception as e:
            logger.error(f"Failed to send refund notice to {chat_id}: {e}")
