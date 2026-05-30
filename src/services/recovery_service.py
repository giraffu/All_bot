import logging

from src.core.task_core_runtime import cleanup_task_runtime_state
from src.services.task_failure_finalization_service import (
    finalize_recovery_failure_for_task_record,
)
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
    user_id = task_data.get("user_id")
    backend_task_id = task_data.get("backend_task_id")

    if not backend_task_id:
        logger.info(f"Task {registry_task_id} has no backend_task_id. Refunding...")
        await _finalize_recovery_failure(
            registry_task_id,
            task_data,
            application,
            "系统重启，任务未成功提交，已为您退款。",
        )
        return

    try:
        recovered = await run_recovered_task(
            registry_task_id=registry_task_id,
            task_data=task_data,
            application=application,
        )
        if not recovered:
            await _finalize_recovery_failure(
                registry_task_id, task_data, application, "❌ 任务恢复失败，已退还灵石"
            )
            return

        await _cleanup_recovered_task_runtime_state(
            registry_task_id=registry_task_id,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"Error recovering task {registry_task_id}: {e}", exc_info=True)
        await _finalize_recovery_failure(
            registry_task_id,
            task_data,
            application,
            "❌ 任务恢复出现异常，已退还灵石",
        )


async def _cleanup_recovered_task_runtime_state(*, registry_task_id, user_id):
    await cleanup_task_runtime_state(
        internal_user_id=user_id or 0,
        registry_task_id=registry_task_id,
        release_lock=user_id is not None,
    )


async def _finalize_recovery_failure(_registry_task_id, task_data, application, reason):
    await finalize_recovery_failure_for_task_record(
        registry_task_id=_registry_task_id,
        task_data=task_data,
        reason=reason,
        bot=application.bot,
        logger_override=logger,
    )
