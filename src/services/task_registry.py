import logging
import uuid
from src.services.permission_service import permission_service

logger = logging.getLogger(__name__)

class TaskRegistry:
    active_tasks = {}

    @classmethod
    def add_task(cls, user_id: int, username: str, cost: int, task_type: str) -> str:
        task_id = str(uuid.uuid4())
        cls.active_tasks[task_id] = {
            "user_id": user_id,
            "username": username,
            "cost": cost,
            "task_type": task_type
        }
        return task_id

    @classmethod
    def remove_task(cls, task_id: str):
        if task_id in cls.active_tasks:
            del cls.active_tasks[task_id]

    @classmethod
    async def refund_all(cls, bot=None):
        if not cls.active_tasks:
            logger.info("No active tasks to refund on shutdown.")
            return
            
        logger.info(f"Refunding {len(cls.active_tasks)} active tasks due to shutdown...")
        for task_id, task in cls.active_tasks.items():
            try:
                if task["cost"] > 0:
                    await permission_service.increment_quota(
                        task["user_id"], 
                        cost=-task["cost"], 
                        username=task["username"], 
                        task_type="refund_restart"
                    )
                    if bot:
                        try:
                            await bot.send_message(
                                chat_id=task["user_id"], 
                                text="⚠️ 系统正在重启/维护，您正在排队或执行中的任务已被中断。消耗的灵石已退回至您的账户，请稍后再试。"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify user {task['user_id']} of refund: {e}")
            except Exception as e:
                logger.error(f"Failed to refund task {task_id} for user {task['user_id']}: {e}")
        cls.active_tasks.clear()
