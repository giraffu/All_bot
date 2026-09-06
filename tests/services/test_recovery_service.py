from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from datetime import datetime, timedelta

import pytest

from src.services import recovery_service
from src.services.private_bot_task_monitor_lease import (
    PrivateBotTaskMonitorAlreadyOwned,
)


@pytest.mark.asyncio
async def test_private_continuation_recovery_injects_runtime_executors(monkeypatch):
    execute_default = AsyncMock(return_value=(None, None))
    resume = AsyncMock()
    monkeypatch.setattr(
        recovery_service,
        "execute_private_qqcc_continuation_stage_default",
        execute_default,
    )
    monkeypatch.setattr(
        recovery_service,
        "resume_private_qqcc_continuation",
        resume,
    )

    application = SimpleNamespace(bot=SimpleNamespace())
    await recovery_service._resume_private_continuation("chain-1", application)

    execute_stage = resume.await_args.kwargs["execute_stage_func"]
    checkpoint = SimpleNamespace()
    stage = {"executor": "generation"}
    ref = SimpleNamespace()
    context = SimpleNamespace()
    await execute_stage(checkpoint, stage, ref, context)

    kwargs = execute_default.await_args.kwargs
    assert kwargs["process_generation_task_func"] is not None
    assert kwargs["process_video_task_template_func"] is not None
    assert kwargs["process_ltx_video_task_func"] is not None
    assert kwargs["download_video_frame_to_fsm_temp_func"] is not None


@pytest.mark.asyncio
async def test_recover_active_tasks_filters_by_client_type(monkeypatch):
    monkeypatch.setattr(
        recovery_service.TaskRegistry,
        "get_all_tasks",
        AsyncMock(
            return_value={
                "main-task": {"client_type": "bot", "backend_task_id": "backend-main"},
                "qqcc-task": {
                    "client_type": "bot:qqcc",
                    "backend_task_id": "backend-qqcc",
                },
                "legacy-task": {"backend_task_id": "backend-legacy"},
            }
        ),
    )
    scheduled = []

    def fake_create_background_task(_application, coroutine):
        scheduled.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(
        recovery_service,
        "create_background_task",
        fake_create_background_task,
    )

    await recovery_service.recover_active_tasks(
        SimpleNamespace(bot=SimpleNamespace()),
        client_type="bot:qqcc",
        include_legacy=False,
    )

    assert len(scheduled) == 1


@pytest.mark.asyncio
async def test_recover_active_tasks_can_include_legacy_main_bot_tasks(monkeypatch):
    monkeypatch.setattr(
        recovery_service.TaskRegistry,
        "get_all_tasks",
        AsyncMock(
            return_value={
                "main-task": {"client_type": "bot", "backend_task_id": "backend-main"},
                "qqcc-task": {
                    "client_type": "bot:qqcc",
                    "backend_task_id": "backend-qqcc",
                },
                "legacy-task": {"backend_task_id": "backend-legacy"},
            }
        ),
    )
    scheduled = []

    def fake_create_background_task(_application, coroutine):
        scheduled.append(coroutine)
        coroutine.close()

    monkeypatch.setattr(
        recovery_service,
        "create_background_task",
        fake_create_background_task,
    )

    await recovery_service.recover_active_tasks(
        SimpleNamespace(bot=SimpleNamespace()),
        client_type="bot",
        include_legacy=True,
    )

    assert len(scheduled) == 2


@pytest.mark.asyncio
async def test_recover_private_bot_tasks_routes_each_tenant_to_its_application(
    monkeypatch,
):
    monkeypatch.setattr(
        recovery_service.TaskRegistry,
        "get_all_tasks_strict",
        AsyncMock(
            return_value={
                "official": {
                    "client_type": "bot:qqcc",
                    "backend_task_id": "backend-official",
                },
                "private-7": {
                    "client_type": "bot:qqcc-private:7",
                    "backend_task_id": "backend-7",
                    "metadata": {
                        "_private_qqcc_continuation": {
                            "version": 1,
                            "chain_id": "chain-7",
                            "stage_index": 0,
                            "submission_sequence": 0,
                            "registry_task_id": "private-7",
                            "executor_token": "executor-7",
                        }
                    },
                },
                "private-9": {
                    "client_type": "bot:qqcc-private:9",
                    "backend_task_id": "backend-9",
                },
                "invalid": {
                    "client_type": "bot:qqcc-private:not-an-id",
                    "backend_task_id": "backend-invalid",
                },
            }
        ),
    )
    monkeypatch.setattr(
        recovery_service,
        "list_private_qqcc_continuations_for_recovery",
        AsyncMock(return_value=[]),
    )
    application_7 = SimpleNamespace(bot=SimpleNamespace(id=7))
    application_9 = SimpleNamespace(bot=SimpleNamespace(id=9))
    resolve_application = AsyncMock(
        side_effect=lambda private_bot_id: {
            7: application_7,
            9: application_9,
        }.get(private_bot_id)
    )
    scheduled = []

    def fake_create_background_task(application, coroutine):
        scheduled.append(application)
        coroutine.close()

    monkeypatch.setattr(
        recovery_service,
        "create_background_task",
        fake_create_background_task,
    )
    orphan_recovery = AsyncMock(return_value=0)
    monkeypatch.setattr(
        recovery_service,
        "recover_private_bot_submission_orphans",
        orphan_recovery,
    )
    prune_ledger = AsyncMock(return_value=0)
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "prune_private_bot_submission_ledger",
        prune_ledger,
    )

    await recovery_service.recover_private_bot_tasks(resolve_application)

    recovery_service.list_private_qqcc_continuations_for_recovery.assert_awaited_once_with(
        active_registry_task_ids={"official", "private-7", "private-9", "invalid"},
        active_chain_ids={"chain-7"},
    )
    assert resolve_application.await_args_list == [call(7), call(9)]
    assert scheduled == [application_7, application_9]
    orphan_recovery.assert_awaited_once()
    prune_ledger.assert_awaited_once_with(
        active_registry_task_ids={"official", "private-7", "private-9", "invalid"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("debit_confirmed", [False, True])
async def test_orphan_reserved_submission_uses_credit_audit_fact_before_refund(
    monkeypatch,
    debit_confirmed,
):
    reserved = SimpleNamespace(
        submission_key="private_bot_update:7:901:0",
        registry_task_id="deterministic-task",
        internal_user_id=123,
        actual_cost=6,
        status="reserved",
        reconcile_not_before_at=(
            datetime(2026, 7, 12, 12, 0, 0) - timedelta(seconds=301)
        ),
    )
    failed = SimpleNamespace(**{**reserved.__dict__, "status": "failed"})
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "list_private_bot_submission_recovery_candidates",
        AsyncMock(return_value=[reserved]),
    )
    mark_failed = AsyncMock(return_value=failed)
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "mark_private_bot_recovery_submission_failed",
        mark_failed,
    )
    finalize = AsyncMock(return_value=SimpleNamespace(completed=True))
    monkeypatch.setattr(
        recovery_service,
        "finalize_private_bot_submission",
        finalize,
    )
    quota = SimpleNamespace(
        has_credit_idempotency_entry=AsyncMock(return_value=debit_confirmed)
    )

    count = await recovery_service.recover_private_bot_submission_orphans(
        active_registry_task_ids=set(),
        quota_manager=quota,
        now_func=lambda: datetime(2026, 7, 12, 12, 0, 0),
    )

    assert count == 1
    quota.has_credit_idempotency_entry.assert_awaited_once_with(
        user_id=123,
        idempotency_key="task_debit:private_bot_update:7:901:0",
        expected_credit_change=-6,
    )
    assert finalize.await_args.kwargs["credits_deducted"] is debit_confirmed
    assert finalize.await_args.kwargs["registry_task_id"] == "deterministic-task"


@pytest.mark.asyncio
async def test_orphan_sweep_rechecks_late_debit_before_completing_compensation(
    monkeypatch,
):
    now = datetime(2026, 7, 12, 12, 0, 0)
    reserved = SimpleNamespace(
        submission_key="private_bot_update:7:902:0",
        registry_task_id="late-debit-task",
        internal_user_id=123,
        actual_cost=6,
        status="reserved",
        reconcile_not_before_at=now - timedelta(seconds=30),
    )
    failed = SimpleNamespace(**{**reserved.__dict__, "status": "failed"})
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "list_private_bot_submission_recovery_candidates",
        AsyncMock(return_value=[reserved]),
    )
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "mark_private_bot_recovery_submission_failed",
        AsyncMock(return_value=failed),
    )
    finalize = AsyncMock(return_value=SimpleNamespace(completed=True))
    monkeypatch.setattr(
        recovery_service,
        "finalize_private_bot_submission",
        finalize,
    )
    quota = SimpleNamespace(
        has_credit_idempotency_entry=AsyncMock(side_effect=[False, True])
    )

    first = await recovery_service.recover_private_bot_submission_orphans(
        active_registry_task_ids=set(),
        quota_manager=quota,
        now_func=lambda: now,
    )
    second = await recovery_service.recover_private_bot_submission_orphans(
        active_registry_task_ids=set(),
        quota_manager=quota,
        now_func=lambda: now + timedelta(seconds=30),
    )

    assert first == 0
    assert second == 1
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["credits_deducted"] is True


@pytest.mark.asyncio
async def test_orphan_sweep_finalizes_active_pending_compensation_and_isolates_errors(
    monkeypatch,
):
    failed_first = SimpleNamespace(
        submission_key="private_bot_update:7:903:0",
        registry_task_id="active-failed-1",
        internal_user_id=123,
        actual_cost=6,
        status="failed",
        compensation_status="pending",
        reconcile_not_before_at=None,
    )
    failed_second = SimpleNamespace(
        submission_key="private_bot_update:7:904:0",
        registry_task_id="active-failed-2",
        internal_user_id=124,
        actual_cost=7,
        status="failed",
        compensation_status="pending",
        reconcile_not_before_at=None,
    )
    list_candidates = AsyncMock(return_value=[failed_first, failed_second])
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "list_private_bot_submission_recovery_candidates",
        list_candidates,
    )
    finalize = AsyncMock(return_value=SimpleNamespace(completed=True))
    monkeypatch.setattr(
        recovery_service,
        "finalize_private_bot_submission",
        finalize,
    )
    quota = SimpleNamespace(
        has_credit_idempotency_entry=AsyncMock(
            side_effect=[RuntimeError("audit unavailable"), True]
        )
    )
    active_ids = {"active-failed-1", "active-failed-2"}

    count = await recovery_service.recover_private_bot_submission_orphans(
        active_registry_task_ids=active_ids,
        quota_manager=quota,
    )

    assert count == 1
    list_candidates.assert_awaited_once_with(
        active_registry_task_ids=active_ids,
    )
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["registry_task_id"] == "active-failed-2"


@pytest.mark.asyncio
async def test_recover_private_bot_tasks_scans_ready_checkpoint_with_empty_registry(
    monkeypatch,
):
    monkeypatch.setattr(
        recovery_service.TaskRegistry,
        "get_all_tasks_strict",
        AsyncMock(return_value={}),
    )
    checkpoint = SimpleNamespace(chain_id="chain-ready", private_bot_id=7)
    list_checkpoints = AsyncMock(return_value=[checkpoint])
    monkeypatch.setattr(
        recovery_service,
        "list_private_qqcc_continuations_for_recovery",
        list_checkpoints,
    )
    application = SimpleNamespace(bot=SimpleNamespace(id=7))
    resolve_application = AsyncMock(return_value=application)
    scheduled = []

    def fake_create_background_task(target_application, coroutine):
        scheduled.append(target_application)
        coroutine.close()

    monkeypatch.setattr(
        recovery_service,
        "create_background_task",
        fake_create_background_task,
    )
    orphan_recovery = AsyncMock(return_value=0)
    monkeypatch.setattr(
        recovery_service,
        "recover_private_bot_submission_orphans",
        orphan_recovery,
    )
    prune_ledger = AsyncMock(return_value=0)
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "prune_private_bot_submission_ledger",
        prune_ledger,
    )

    await recovery_service.recover_private_bot_tasks(resolve_application)

    list_checkpoints.assert_awaited_once_with(
        active_registry_task_ids=set(),
        active_chain_ids=set(),
    )
    resolve_application.assert_awaited_once_with(7)
    assert scheduled == [application]
    orphan_recovery.assert_awaited_once_with(active_registry_task_ids=set())
    prune_ledger.assert_awaited_once_with(active_registry_task_ids=set())


@pytest.mark.asyncio
async def test_recover_single_task_success_uses_cleanup_runtime(monkeypatch):
    run_recovered = AsyncMock(return_value=True)
    cleanup_runtime = AsyncMock()
    finalize_failure = AsyncMock()

    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    application = SimpleNamespace(bot=SimpleNamespace())

    await recovery_service._recover_single_task(
        "registry-1",
        {
            "user_id": 123,
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        application,
    )

    run_recovered.assert_awaited_once_with(
        registry_task_id="registry-1",
        task_data={
            "user_id": 123,
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        application=application,
    )
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="registry-1",
        release_lock=True,
    )
    finalize_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_recovery_does_not_finalize_task_owned_by_live_monitor(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def already_owned(_registry_task_id):
        raise PrivateBotTaskMonitorAlreadyOwned("owned")
        yield

    run_recovered = AsyncMock()
    finalize_failure = AsyncMock()
    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "private_bot_task_monitor_lease",
        already_owned,
    )
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )

    await recovery_service._recover_single_task(
        "registry-private",
        {
            "user_id": 123,
            "backend_task_id": "backend-private",
            "client_type": "bot:qqcc-private:7",
        },
        SimpleNamespace(bot=SimpleNamespace()),
    )

    run_recovered.assert_not_awaited()
    finalize_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_recovery_binds_accepted_timeout_without_refund_or_remove(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def monitor_lease(_registry_task_id):
        yield

    task_data = {
        "user_id": 123,
        "backend_task_id": None,
        "username": "tester",
        "cost": 6,
        "client_type": "bot:qqcc-private:7",
    }
    snapshot = SimpleNamespace(status="submitted")
    reconcile = AsyncMock(
        return_value=SimpleNamespace(
            snapshot=snapshot,
            confirmed=True,
            definitively_missing=False,
            backend_task_id="deterministic-task",
        )
    )
    run_recovered = AsyncMock(return_value=True)
    cleanup = AsyncMock()
    finalize_failure = AsyncMock()
    compensate = AsyncMock()
    monkeypatch.setattr(
        recovery_service,
        "private_bot_task_monitor_lease",
        monitor_lease,
    )
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "reconcile_private_bot_recovery_submission",
        reconcile,
    )
    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(recovery_service, "cleanup_task_runtime_state", cleanup)
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    monkeypatch.setattr(
        recovery_service,
        "_compensate_private_recovery_submission",
        compensate,
    )
    application = SimpleNamespace(bot=SimpleNamespace())

    await recovery_service._recover_single_task(
        "deterministic-task",
        task_data,
        application,
    )

    run_recovered.assert_awaited_once_with(
        registry_task_id="deterministic-task",
        task_data={**task_data, "backend_task_id": "deterministic-task"},
        application=application,
    )
    finalize_failure.assert_not_awaited()
    compensate.assert_not_awaited()
    cleanup.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="deterministic-task",
        release_lock=True,
    )


@pytest.mark.asyncio
async def test_private_recovery_preserves_backendless_task_during_dispatch_grace(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def monitor_lease(_registry_task_id):
        yield

    monkeypatch.setattr(
        recovery_service,
        "private_bot_task_monitor_lease",
        monitor_lease,
    )
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "reconcile_private_bot_recovery_submission",
        AsyncMock(
            return_value=SimpleNamespace(
                snapshot=SimpleNamespace(status="dispatching"),
                confirmed=False,
                definitively_missing=False,
                backend_task_id=None,
            )
        ),
    )
    run_recovered = AsyncMock()
    finalize_failure = AsyncMock()
    compensate = AsyncMock()
    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    monkeypatch.setattr(
        recovery_service,
        "_compensate_private_recovery_submission",
        compensate,
    )

    await recovery_service._recover_single_task(
        "deterministic-task",
        {
            "user_id": 123,
            "backend_task_id": None,
            "client_type": "bot:qqcc-private:7",
        },
        SimpleNamespace(bot=SimpleNamespace()),
    )

    run_recovered.assert_not_awaited()
    finalize_failure.assert_not_awaited()
    compensate.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_recovery_repository_outage_fails_closed_without_refund_or_remove(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def monitor_lease(_registry_task_id):
        yield

    monkeypatch.setattr(
        recovery_service,
        "private_bot_task_monitor_lease",
        monitor_lease,
    )
    monkeypatch.setattr(
        recovery_service.private_bot_submission_ledger,
        "reconcile_private_bot_recovery_submission",
        AsyncMock(side_effect=RuntimeError("postgres unavailable")),
    )
    run_recovered = AsyncMock()
    finalize_failure = AsyncMock()
    cleanup = AsyncMock()
    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    monkeypatch.setattr(recovery_service, "cleanup_task_runtime_state", cleanup)

    await recovery_service._recover_single_task(
        "deterministic-task",
        {
            "user_id": 123,
            "backend_task_id": None,
            "client_type": "bot:qqcc-private:7",
        },
        SimpleNamespace(bot=SimpleNamespace()),
    )

    run_recovered.assert_not_awaited()
    finalize_failure.assert_not_awaited()
    cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_single_task_fallback_cleanup_uses_core_helper(monkeypatch):
    run_recovered = AsyncMock(return_value=True)
    cleanup_runtime = AsyncMock()
    finalize_failure = AsyncMock()

    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    application = SimpleNamespace(bot=SimpleNamespace())

    await recovery_service._recover_single_task(
        "registry-1",
        {
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        application,
    )

    run_recovered.assert_awaited_once_with(
        registry_task_id="registry-1",
        task_data={
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        application=application,
    )
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=0,
        registry_task_id="registry-1",
        release_lock=False,
    )
    finalize_failure.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_single_task_failed_recovery_uses_finalize_helper(monkeypatch):
    run_recovered = AsyncMock(return_value=False)
    cleanup_runtime = AsyncMock()
    finalize_failure = AsyncMock()

    monkeypatch.setattr(recovery_service, "run_recovered_task", run_recovered)
    monkeypatch.setattr(
        recovery_service,
        "cleanup_task_runtime_state",
        cleanup_runtime,
    )
    monkeypatch.setattr(
        recovery_service,
        "_finalize_recovery_failure",
        finalize_failure,
    )
    application = SimpleNamespace(bot=SimpleNamespace())

    await recovery_service._recover_single_task(
        "registry-2",
        {
            "user_id": 456,
            "backend_task_id": "backend-2",
            "username": "tester",
            "cost": 5,
            "chat_id": 100,
        },
        application,
    )

    run_recovered.assert_awaited_once_with(
        registry_task_id="registry-2",
        task_data={
            "user_id": 456,
            "backend_task_id": "backend-2",
            "username": "tester",
            "cost": 5,
            "chat_id": 100,
        },
        application=application,
    )
    finalize_failure.assert_awaited_once()
    cleanup_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_recovery_failure_uses_core_finalize_and_notice(monkeypatch):
    finalize_failure = AsyncMock()
    monkeypatch.setattr(
        recovery_service,
        "finalize_recovery_failure_for_task_record",
        finalize_failure,
    )

    application = SimpleNamespace(bot=SimpleNamespace())
    await recovery_service._finalize_recovery_failure(
        "registry-3",
        {
            "user_id": 789,
            "username": "tester",
            "cost": 9,
            "chat_id": 321,
        },
        application,
        "❌ 任务恢复失败，已退还灵石",
    )

    finalize_failure.assert_awaited_once()
    kwargs = finalize_failure.await_args.kwargs
    assert kwargs["registry_task_id"] == "registry-3"
    assert kwargs["task_data"] == {
        "user_id": 789,
        "username": "tester",
        "cost": 9,
        "chat_id": 321,
    }
    assert kwargs["reason"] == "❌ 任务恢复失败，已退还灵石"
    assert kwargs["bot"] is application.bot
