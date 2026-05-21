import logging

from src.core.task_core import cleanup_task_runtime_state, finalize_task_failure
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
    runtime_state_finalized = False
    try:
        backend_task_id = task_data.get("backend_task_id")

        if not backend_task_id:
            logger.info(f"Task {registry_task_id} has no backend_task_id. Refunding...")
            await _finalize_recovery_failure(
                registry_task_id,
                task_data,
                application,
                "系统重启，任务未成功提交，已为您退款。",
            )
            runtime_state_finalized = True
            return

        recovered = await run_recovered_task(task_data, application)
        if not recovered:
            await _finalize_recovery_failure(
                registry_task_id, task_data, application, "❌ 任务恢复失败，已退还灵石"
            )
            runtime_state_finalized = True
            return

        if user_id:
            await cleanup_task_runtime_state(
                internal_user_id=user_id,
                registry_task_id=registry_task_id,
            )
            runtime_state_finalized = True

    except Exception as e:
        logger.error(f"Error recovering task {registry_task_id}: {e}", exc_info=True)
        recovery_failed = True

    finally:
        if recovery_failed:
            await _finalize_recovery_failure(
                registry_task_id,
                task_data,
                application,
                "❌ 任务恢复出现异常，已退还灵石",
            )
            runtime_state_finalized = True
        if not runtime_state_finalized:
            await cleanup_task_runtime_state(
                internal_user_id=user_id or 0,
                registry_task_id=registry_task_id,
                release_lock=user_id is not None,
            )


async def _finalize_recovery_failure(_registry_task_id, task_data, application, reason):
    user_id = task_data.get("user_id")
    username = task_data.get("username")
    cost = task_data.get("cost", 0)
    chat_id = task_data.get("chat_id")

    await finalize_task_failure(
        internal_user_id=user_id,
        username=username,
        cost=cost,
        should_refund=cost > 0,
        registry_task_id=_registry_task_id,
        refund_task_type="refund_restart",
        explicit_user_message=reason,
    )

    if chat_id:
        try:
            from src.utils import robust_send_message

            await robust_send_message(application.bot, chat_id, reason)
        except Exception as e:
            logger.error(f"Failed to send refund notice to {chat_id}: {e}")
