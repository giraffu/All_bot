import logging

from src.services.permission_service import permission_service
from src.services.redis_client import redis_client
from src.services.task_recovery_runtime import run_recovered_task
from src.services.task_registry import TaskRegistry
from src.utils import create_background_task

logger = logging.getLogger(__name__)


async def recover_active_tasks(application):
    tasks = await TaskRegistry.get_all_tasks()
    if not tasks:
        logger.info("No active tasks to recover.")
        return

    logger.info(f"Found {len(tasks)} active tasks in Redis. Attempting recovery...")
    for registry_task_id, task_data in tasks.items():
        create_background_task(
            application, _recover_single_task(registry_task_id, task_data, application)
        )


async def _recover_single_task(registry_task_id, task_data, application):
    recovery_failed = False
    user_id = task_data.get("user_id")
    try:
        backend_task_id = task_data.get("backend_task_id")

        if not backend_task_id:
            logger.info(f"Task {registry_task_id} has no backend_task_id. Refunding...")
            await _refund_and_cleanup(
                registry_task_id,
                task_data,
                application,
                "系统重启，任务未成功提交，已为您退款。",
            )
            return

        recovered = await run_recovered_task(task_data, application)
        if not recovered:
            await _refund_and_cleanup(
                registry_task_id, task_data, application, "❌ 任务恢复失败，已退还灵石"
            )

    except Exception as e:
        logger.error(f"Error recovering task {registry_task_id}: {e}", exc_info=True)
        recovery_failed = True

    finally:
        await TaskRegistry.remove_task(registry_task_id)
        if recovery_failed:
            await _refund_and_cleanup(
                registry_task_id,
                task_data,
                application,
                "❌ 任务恢复出现异常，已退还灵石",
            )
        if user_id:
            await redis_client.decrement_user_concurrency(user_id)


async def _refund_and_cleanup(_registry_task_id, task_data, application, reason):
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    cost = task_data.get("cost", 0)
    chat_id = task_data.get("chat_id")


    if cost > 0:
        await permission_service.refund_quota(
            user_id, credits=cost, username=username, task_type="refund_restart"
        )

    if chat_id:
        try:
            from src.utils import robust_send_message

            await robust_send_message(application.bot, chat_id, reason)
        except Exception as e:
            logger.error(f"Failed to send refund notice to {chat_id}: {e}")
