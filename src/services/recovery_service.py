import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from src.core.task_core_runtime import cleanup_task_runtime_state
from src.services.task_failure_finalization_service import (
    finalize_recovery_failure_for_task_record,
)
from src.services.task_recovery_runtime import run_recovered_task
from src.services.task_registry import TaskRegistry
from src.services.image_service import image_service
from src.services import private_bot_submission_ledger
from src.services.private_bot_task_finalization import (
    finalize_private_bot_submission,
)
from src.quota import QuotaManager
from src.services.private_qqcc_bot_service import parse_private_bot_client_type
from src.services.private_qqcc_continuation_service import (
    PrivateQqccContinuationError,
    list_private_qqcc_continuations_for_recovery,
    normalize_private_qqcc_continuation_task_ref,
    resume_private_qqcc_continuation,
)
from src.services.tg_task_runtime import TelegramBotContextAdapter
from src.services.private_bot_task_monitor_lease import (
    PrivateBotTaskMonitorLeaseError,
    private_bot_task_monitor_lease,
)
from src.utils import create_background_task

logger = logging.getLogger(__name__)


def should_recover_task_record(
    task_data: dict,
    *,
    client_type: str | None = None,
    include_legacy: bool = True,
) -> bool:
    if client_type is None:
        return True

    task_client_type = task_data.get("client_type")
    if task_client_type == client_type:
        return True
    if include_legacy and not task_client_type:
        return True
    return False


async def recover_active_tasks(
    application,
    *,
    client_type: str | None = None,
    include_legacy: bool = True,
):
    tasks = await TaskRegistry.get_all_tasks()
    if not tasks:
        logger.info("No active tasks to recover.")
        return

    filtered_tasks = {
        registry_task_id: task_data
        for registry_task_id, task_data in tasks.items()
        if should_recover_task_record(
            task_data,
            client_type=client_type,
            include_legacy=include_legacy,
        )
    }
    if not filtered_tasks:
        logger.info(
            "Found %s active tasks in Redis, none match recovery client_type=%s.",
            len(tasks),
            client_type,
        )
        return

    logger.info(
        "Found %s active tasks in Redis. Recovering %s for client_type=%s.",
        len(tasks),
        len(filtered_tasks),
        client_type,
    )
    for registry_task_id, task_data in filtered_tasks.items():
        create_background_task(
            application, _recover_single_task(registry_task_id, task_data, application)
        )


async def recover_private_bot_tasks(
    application_resolver: Callable[[int], Awaitable[object | None]],
) -> None:
    """Route each private QQCC task back to its tenant Application exactly once."""

    tasks = await TaskRegistry.get_all_tasks_strict()
    if not tasks:
        logger.info("No active private QQCC tasks to recover.")

    recovered_count = 0
    for registry_task_id, task_data in tasks.items():
        private_bot_id = parse_private_bot_client_type(task_data.get("client_type"))
        if private_bot_id is None:
            continue

        application = await application_resolver(private_bot_id)
        if application is None:
            logger.error(
                "Private QQCC recovery tenant is unavailable private_bot_id=%s",
                private_bot_id,
            )
            continue

        create_background_task(
            application,
            _recover_single_task(registry_task_id, task_data, application),
        )
        recovered_count += 1

    active_registry_task_ids = set(tasks)
    await recover_private_bot_submission_orphans(
        active_registry_task_ids=active_registry_task_ids,
    )
    try:
        await private_bot_submission_ledger.prune_private_bot_submission_ledger(
            active_registry_task_ids=active_registry_task_ids,
        )
    except Exception:
        logger.exception(
            "Private QQCC submission retention cleanup failed; recovery continues."
        )
    active_continuation_chain_ids = {
        ref.chain_id
        for task_data in tasks.values()
        if (
            ref := normalize_private_qqcc_continuation_task_ref(
                task_data.get("metadata") or {}
            )
        )
        is not None
    }
    for checkpoint in await list_private_qqcc_continuations_for_recovery(
        active_registry_task_ids=active_registry_task_ids,
        active_chain_ids=active_continuation_chain_ids,
    ):
        application = await application_resolver(checkpoint.private_bot_id)
        if application is None:
            logger.warning(
                "Skipping private QQCC continuation %s: tenant %s is unavailable.",
                checkpoint.chain_id,
                checkpoint.private_bot_id,
            )
            continue
        create_background_task(
            application,
            _resume_private_continuation(checkpoint.chain_id, application),
        )

    logger.info("Scheduled %s private QQCC tasks for recovery.", recovered_count)


async def recover_private_bot_submission_orphans(
    *,
    active_registry_task_ids: set[str],
    quota_manager: QuotaManager | None = None,
    now_func=datetime.now,
) -> int:
    """Sweep durable submissions that crashed outside the Redis registry seam."""

    quota_manager = quota_manager or QuotaManager()
    recovered_count = 0
    candidates = await (
        private_bot_submission_ledger.list_private_bot_submission_recovery_candidates(
            active_registry_task_ids=active_registry_task_ids,
        )
    )
    for snapshot in candidates:
        try:
            recovered = await _recover_private_bot_submission_orphan_candidate(
                snapshot=snapshot,
                active_registry_task_ids=active_registry_task_ids,
                quota_manager=quota_manager,
                now_func=now_func,
            )
        except Exception:
            logger.exception(
                "Private QQCC orphan recovery failed for %s; continuing the sweep.",
                snapshot.registry_task_id,
            )
            continue
        recovered_count += int(recovered)
    return recovered_count


async def _recover_private_bot_submission_orphan_candidate(
    *,
    snapshot,
    active_registry_task_ids: set[str],
    quota_manager: QuotaManager,
    now_func,
) -> bool:
    is_active = snapshot.registry_task_id in active_registry_task_ids
    if is_active and snapshot.compensation_status not in {"pending", "processing"}:
        return False

    debit_confirmed = getattr(snapshot, "debit_confirmed_at", None) is not None
    if not debit_confirmed:
        debit_confirmed = await quota_manager.has_credit_idempotency_entry(
            user_id=snapshot.internal_user_id,
            idempotency_key=f"task_debit:{snapshot.submission_key}",
            expected_credit_change=-int(snapshot.actual_cost or 0),
        )
    if not debit_confirmed:
        reconcile_not_before_at = snapshot.reconcile_not_before_at
        if reconcile_not_before_at is None:
            return False
        debit_absence_safe_at = reconcile_not_before_at + timedelta(
            seconds=private_bot_submission_ledger.PRIVATE_BOT_DEBIT_AUDIT_GRACE_SECONDS
        )
        if now_func() < debit_absence_safe_at:
            return False
    if snapshot.status == "dispatching":
        async def missing_registry(_registry_task_id: str):
            return None

        reconciliation = await private_bot_submission_ledger.reconcile_private_bot_dispatching_submission(
            snapshot,
            registry_lookup=missing_registry,
            backend_lookup=image_service.get_task_status,
        )
        if reconciliation.confirmed:
            logger.critical(
                "Private QQCC submission %s exists in Central but its registry "
                "record is missing; preserving charge for operator recovery.",
                snapshot.registry_task_id,
            )
            return False
        if not reconciliation.definitively_missing:
            return False

    if snapshot.status != "failed":
        snapshot = await private_bot_submission_ledger.mark_private_bot_recovery_submission_failed(
            snapshot=snapshot,
            error_code="orphaned_before_registry",
            error_message=(
                "Private Bot submission deadline expired without a recoverable registry task."
            ),
        )
        debit_confirmed = bool(
            debit_confirmed
            or getattr(snapshot, "debit_confirmed_at", None) is not None
        )
    result = await finalize_private_bot_submission(
        request=snapshot,
        internal_user_id=snapshot.internal_user_id,
        username=None,
        actual_cost=int(snapshot.actual_cost or 0),
        registry_task_id=snapshot.registry_task_id,
        credits_deducted=debit_confirmed,
        reason_code="orphaned_before_registry",
        reason_message=(
            "Private Bot submission deadline expired outside the task registry."
        ),
    )
    return bool(result.completed)


async def _resume_private_continuation(chain_id: str, application) -> None:
    context = TelegramBotContextAdapter(application)
    await resume_private_qqcc_continuation(
        chain_id=chain_id,
        context=context,
    )


async def _recover_single_task(registry_task_id, task_data, application):
    user_id = task_data.get("user_id")
    backend_task_id = task_data.get("backend_task_id")
    is_private_task = (
        parse_private_bot_client_type(task_data.get("client_type")) is not None
    )

    try:
        async def recover_owned():
            resolved_task_data = task_data
            resolved_backend_task_id = backend_task_id
            if not resolved_backend_task_id and is_private_task:
                reconciliation = await private_bot_submission_ledger.reconcile_private_bot_recovery_submission(
                    registry_task_id=registry_task_id,
                    registry_task=task_data,
                    backend_lookup=image_service.get_task_status,
                    update_registry_backend=TaskRegistry.update_backend_task_id,
                )
                if reconciliation.confirmed:
                    resolved_backend_task_id = reconciliation.backend_task_id
                    resolved_task_data = {
                        **task_data,
                        "backend_task_id": resolved_backend_task_id,
                    }
                elif not reconciliation.definitively_missing:
                    logger.info(
                        "Private QQCC task %s dispatch remains uncertain; "
                        "preserving charge, registry and concurrency for retry.",
                        registry_task_id,
                    )
                    return
                else:
                    await _compensate_private_recovery_submission(
                        registry_task_id=registry_task_id,
                        task_data=task_data,
                        snapshot=reconciliation.snapshot,
                    )
                    return

            if not resolved_backend_task_id:
                logger.info(
                    "Task %s has no backend_task_id. Refunding...",
                    registry_task_id,
                )
                await _finalize_recovery_failure(
                    registry_task_id,
                    task_data,
                    application,
                    "系统重启，任务未成功提交，已为您退款。",
                )
                return

            recovered = await run_recovered_task(
                registry_task_id=registry_task_id,
                task_data=resolved_task_data,
                application=application,
            )
            if not recovered:
                if is_private_task:
                    snapshot = await private_bot_submission_ledger.get_private_bot_submission_by_registry_task_id(
                        registry_task_id
                    )
                    if snapshot is None:
                        logger.error(
                            "Private QQCC recovery task %s has no ledger; preserving it.",
                            registry_task_id,
                        )
                        return
                    await finalize_private_bot_submission(
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
                        reason_code="recovery_failed",
                        reason_message="Private Bot task recovery reached a terminal failure.",
                        backend_task_id=resolved_backend_task_id,
                    )
                    return
                await _finalize_recovery_failure(
                    registry_task_id,
                    task_data,
                    application,
                    "❌ 任务恢复失败，已退还灵石",
                )
                return

            await _cleanup_recovered_task_runtime_state(
                registry_task_id=registry_task_id,
                user_id=user_id,
            )
            continuation_ref = normalize_private_qqcc_continuation_task_ref(
                task_data.get("metadata") or {}
            )
            if continuation_ref is not None:
                await _resume_private_continuation(
                    continuation_ref.chain_id,
                    application,
                )

        if not is_private_task:
            await recover_owned()
        else:
            async with private_bot_task_monitor_lease(registry_task_id):
                await recover_owned()
    except PrivateQqccContinuationError:
        # Keep the active registry record and user lock. Removing them before
        # the checkpoint advances would recreate the exact cleanup/register
        # crash gap the durable continuation is meant to close.
        logger.exception(
            "Private QQCC continuation checkpoint failed for task %s; "
            "runtime state is preserved for retry.",
            registry_task_id,
        )
    except PrivateBotTaskMonitorLeaseError:
        logger.info(
            "Private QQCC recovery monitor ownership is held elsewhere for task %s.",
            registry_task_id,
        )
    except Exception as e:
        logger.error(f"Error recovering task {registry_task_id}: {e}", exc_info=True)
        if is_private_task:
            logger.error(
                "Private QQCC recovery failed closed for task %s; "
                "preserving charge, registry and concurrency.",
                registry_task_id,
            )
            return
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


async def _compensate_private_recovery_submission(
    *,
    registry_task_id: str,
    task_data: dict,
    snapshot,
) -> bool:
    if snapshot is None:
        logger.error(
            "Private QQCC task %s has no durable submission ledger; preserving it.",
            registry_task_id,
        )
        return False
    if snapshot.status != "failed":
        snapshot = await private_bot_submission_ledger.mark_private_bot_recovery_submission_failed(
            snapshot=snapshot,
            error_code="dispatch_not_found",
            error_message=(
                "Central confirmed that the deterministic recovery dispatch is absent."
            ),
        )
    result = await finalize_private_bot_submission(
        request=snapshot,
        internal_user_id=task_data.get("user_id"),
        username=task_data.get("username"),
        actual_cost=int(snapshot.actual_cost or task_data.get("cost") or 0),
        registry_task_id=registry_task_id,
        credits_deducted=bool(task_data.get("credits_deducted", True)),
        reason_code="dispatch_not_found",
        reason_message=(
            "Central confirmed that the deterministic recovery dispatch is absent."
        ),
    )
    return result.completed


async def _finalize_recovery_failure(_registry_task_id, task_data, application, reason):
    await finalize_recovery_failure_for_task_record(
        registry_task_id=_registry_task_id,
        task_data=task_data,
        reason=reason,
        bot=application.bot,
        logger_override=logger,
    )
