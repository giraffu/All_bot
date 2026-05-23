from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import recovery_service


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

    await recovery_service._recover_single_task(
        "registry-1",
        {
            "user_id": 123,
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        SimpleNamespace(bot=SimpleNamespace()),
    )

    run_recovered.assert_awaited_once()
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id="registry-1",
    )
    finalize_failure.assert_not_awaited()


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

    await recovery_service._recover_single_task(
        "registry-1",
        {
            "backend_task_id": "backend-1",
            "username": "tester",
        },
        SimpleNamespace(bot=SimpleNamespace()),
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

    await recovery_service._recover_single_task(
        "registry-2",
        {
            "user_id": 456,
            "backend_task_id": "backend-2",
            "username": "tester",
            "cost": 5,
            "chat_id": 100,
        },
        SimpleNamespace(bot=SimpleNamespace()),
    )

    finalize_failure.assert_awaited_once()
    cleanup_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_recovery_failure_uses_core_finalize_and_notice(monkeypatch):
    finalize_failure = AsyncMock()
    monkeypatch.setattr(
        recovery_service,
        "finalize_task_failure_for_task_record",
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
    policy = kwargs["policy"]
    assert policy.refund_task_type == "refund_restart"
    assert policy.explicit_user_message == "❌ 任务恢复失败，已退还灵石"
    assert policy.notice_failure_log_message == "Failed to send refund notice to 321"
    assert kwargs["bot"] is application.bot
