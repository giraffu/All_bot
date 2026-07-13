import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from src.core.task_core_runtime import cancel_backend_task_best_effort
from src.services.redis_client import redis_client
from src.services.task_failure_finalization_service import (
    finalize_zombie_cleanup_for_task_record,
)
from src.services.private_qqcc_bot_service import parse_private_bot_client_type
from src.services import private_bot_submission_ledger
from src.services.private_bot_task_finalization import (
    finalize_private_bot_submission,
)
from src.services.private_bot_task_monitor_lease import (
    PrivateBotTaskMonitorLeaseError,
    private_bot_task_monitor_lease,
)

logger = logging.getLogger("bot.zombie_cleaner")


def _task_belongs_to_client(
    task: dict,
    *,
    client_type: str | None,
    include_legacy: bool,
) -> bool:
    # Private QQCC tasks have their own durable submission ledger, monitor
    # lease and tenant-aware delivery path. They must never fall through the
    # generic/manual cleaner, even when that cleaner is invoked unfiltered.
    if parse_private_bot_client_type(task.get("client_type")) is not None:
        return False
    if client_type is None:
        return True
    task_client_type = task.get("client_type")
    return task_client_type == client_type or (include_legacy and not task_client_type)


async def clean_zombies(
    bot=None,
    *,
    client_type: str | None = None,
    include_legacy: bool = True,
):
    """
    扫描并清理驻留过长（超过2小时）的僵尸任务。
    1. 识别卡死的任务。
    2. 为用户退还预扣的灵石。
    3. 解除用户的并发锁。
    4. 调用中控 API 彻底取消该任务，防止算力浪费。
    5. (可选) 通知用户已退款。
    """
    try:
        tasks = await redis_client.get_active_tasks()
        if not tasks:
            logger.debug("No active tasks found during zombie cleanup.")
            tasks = {}

        now = time.time()
        removed_count = 0

        for task_id, task in tasks.items():
            if not _task_belongs_to_client(
                task,
                client_type=client_type,
                include_legacy=include_legacy,
            ):
                continue
            # 如果没有 created_at 时间戳，为了安全起见假设它刚创建
            created_at = task.get("created_at", now)
            age_seconds = now - created_at

            # 如果任务驻留超过 2 小时 (7200秒)，判定为僵尸任务
            if age_seconds > 7200:
                user_id = task.get("user_id")
                cost = task.get("cost", 0)
                backend_task_id = task.get("backend_task_id")

                logger.warning(
                    f"🧟 Detected zombie task {task_id} for user {user_id} (age: {age_seconds:.0f}s). Initiating cleanup."
                )

                # 1. 统一执行退款 + 运行态清理
                if user_id:
                    try:
                        result, cancelled = await finalize_zombie_cleanup_for_task_record(
                            registry_task_id=task_id,
                            task_data=task,
                            bot=bot,
                            logger_override=logger,
                        )
                        if result.refunded:
                            logger.info(
                                f"💰 Refunded {cost} credits to user {user_id} for zombie task {task_id}."
                            )
                        logger.info(
                            f"🔓 Cleaned runtime state for zombie task {task_id} user {user_id}."
                        )
                        if cancelled:
                            logger.info(
                                f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}."
                            )
                    except Exception as e:
                        logger.error(
                            f"Error finalizing zombie task {task_id} for user {user_id}: {e}"
                        )
                elif backend_task_id:
                    logger.warning(
                        "Zombie task %s has no user_id; skipping refund finalization and only cancelling backend task.",
                        task_id,
                    )
                    cancelled = await cancel_backend_task_best_effort(
                        backend_task_id=backend_task_id,
                        registry_task_id=task_id,
                        logger_override=logger,
                    )
                    if cancelled:
                        logger.info(
                            f"🛑 Sent cancellation request to Central API for backend task {backend_task_id}."
                        )

                removed_count += 1

        if removed_count > 0:
            logger.info(
                f"🧹 Zombie cleanup complete. Removed {removed_count} zombie tasks."
            )

        # 6. 检查并非因为僵尸任务而是由于死锁导致并发数 > 0 但没有活跃任务的用户
        try:
            removed_markers = await (
                redis_client.repair_stale_user_concurrency_acquisitions(
                    active_registry_task_ids=set(tasks),
                    stale_before_timestamp=now - 7200,
                )
            )
            if removed_markers:
                logger.info(
                    "Reset %s stale task-keyed concurrency acquisitions.",
                    removed_markers,
                )
        except Exception as e:
            logger.error(f"Error fixing leaked concurrency locks: {e}")

    except Exception as e:
        logger.error(f"Error during zombie task cleanup loop: {e}", exc_info=True)


async def clean_private_qqcc_zombies(
    application_resolver: Callable[[int], Awaitable[object | None]],
    *,
    now: float | None = None,
) -> int:
    """Finalize stale private-Bot tasks through the owning Bot application."""

    tasks = await redis_client.get_active_tasks_strict()
    current_time = time.time() if now is None else float(now)
    removed_count = 0
    for registry_task_id, task_data in tasks.items():
        private_bot_id = parse_private_bot_client_type(task_data.get("client_type"))
        if private_bot_id is None:
            continue
        raw_created_at = task_data.get("created_at")
        created_at = (
            current_time if raw_created_at is None else float(raw_created_at)
        )
        if current_time - created_at <= 7200:
            continue
        application = await application_resolver(private_bot_id)
        if application is None:
            logger.error(
                "Private QQCC zombie cleanup application is unavailable "
                "private_bot_id=%s; preserving this tenant and continuing.",
                private_bot_id,
            )
            continue
        try:
            async with private_bot_task_monitor_lease(registry_task_id):
                snapshot = await private_bot_submission_ledger.get_private_bot_submission_by_registry_task_id(
                    registry_task_id
                )
                if snapshot is None:
                    logger.error(
                        "Private QQCC zombie %s has no submission ledger; preserving it.",
                        registry_task_id,
                    )
                    continue
                result = await finalize_private_bot_submission(
                    request=snapshot,
                    internal_user_id=task_data.get("user_id"),
                    username=task_data.get("username"),
                    actual_cost=int(
                        snapshot.actual_cost or task_data.get("cost") or 0
                    ),
                    registry_task_id=registry_task_id,
                    credits_deducted=bool(
                        task_data.get("credits_deducted", True)
                    ),
                    reason_code="zombie_timeout",
                    reason_message="Private Bot task exceeded the zombie timeout.",
                    backend_task_id=task_data.get("backend_task_id"),
                    cancel_backend=True,
                )
                if result.completed:
                    removed_count += 1
        except PrivateBotTaskMonitorLeaseError:
            logger.info(
                "Private QQCC zombie %s is still owned by a live monitor; preserving it.",
                registry_task_id,
            )
    return removed_count


async def main():
    """
    独立的入口函数，如果需要手动运行此脚本时调用。
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting manual zombie cleanup...")
    await clean_zombies()
    logger.info("Manual zombie cleanup finished.")


if __name__ == "__main__":
    asyncio.run(main())
