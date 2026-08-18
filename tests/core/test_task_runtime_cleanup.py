from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import httpx
import pytest

from src.core import task_core
from src.core import task_core_finalization
from src.core import task_core_runtime


@pytest.mark.asyncio
async def test_cleanup_task_runtime_state_releases_lock_and_removes_registry():
    calls = []

    async def fake_release(user_id: int, *, idempotency_key: str):
        calls.append(("release", user_id, idempotency_key))

    async def fake_remove(task_id: str):
        calls.append(("remove", task_id))

    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=123,
        registry_task_id="task-1",
        release_concurrency_lock_func=fake_release,
        remove_task_func=fake_remove,
    )

    assert calls == [
        ("release", 123, "task_concurrency:task-1"),
        ("remove", "task-1"),
    ]


@pytest.mark.asyncio
async def test_cleanup_task_runtime_state_can_skip_lock_release():
    calls = []

    async def fake_release(_user_id: int):
        calls.append("release")

    async def fake_remove(task_id: str):
        calls.append(("remove", task_id))

    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=456,
        registry_task_id="task-2",
        release_lock=False,
        release_concurrency_lock_func=fake_release,
        remove_task_func=fake_remove,
    )

    assert calls == [("remove", "task-2")]


@pytest.mark.asyncio
async def test_cleanup_task_runtime_state_forwards_task_idempotent_release_key():
    release = AsyncMock()
    remove = AsyncMock()

    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=456,
        registry_task_id="task-a",
        release_idempotency_key="task_release:task-a",
        release_concurrency_lock_func=release,
        remove_task_func=remove,
    )

    release.assert_awaited_once_with(
        456,
        idempotency_key="task_release:task-a",
    )
    remove.assert_awaited_once_with("task-a")


@pytest.mark.asyncio
async def test_cleanup_uses_registry_acquisition_mode_during_keyed_rollout():
    release = AsyncMock()
    remove = AsyncMock()
    get_task = AsyncMock(
        side_effect=[
            {"user_id": 456},
            {
                "user_id": 456,
                "concurrency_acquisition_key": "task_concurrency:new-task",
            },
        ]
    )
    runtime_dependencies = SimpleNamespace(get_task_func=get_task)

    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=456,
        registry_task_id="legacy-task",
        release_concurrency_lock_func=release,
        remove_task_func=remove,
        runtime_dependencies=runtime_dependencies,
    )
    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=456,
        registry_task_id="new-task",
        release_concurrency_lock_func=release,
        remove_task_func=remove,
        runtime_dependencies=runtime_dependencies,
    )

    assert release.await_args_list == [
        call(456),
        call(
            456,
            idempotency_key="task_concurrency:new-task",
        ),
    ]


@pytest.mark.asyncio
async def test_refund_cancelled_task_refunds_when_submitted_and_cost_positive(monkeypatch):
    calls = []

    async def fake_refund(user_id: int, amount: int, task_type: str, username: str):
        calls.append((user_id, amount, task_type, username))

    monkeypatch.setattr(task_core_finalization, "refund_credits", fake_refund)

    refunded = await task_core_finalization.refund_cancelled_task(
        internal_user_id=123,
        username="u1",
        cost=20,
        task_submitted=True,
    )

    assert refunded is True
    assert calls == [(123, 20, "refund_user_cancel", "u1")]


@pytest.mark.asyncio
async def test_refund_cancelled_task_skips_when_not_submitted_or_non_positive_cost(monkeypatch):
    calls = []

    async def fake_refund(user_id: int, amount: int, task_type: str, username: str):
        calls.append((user_id, amount, task_type, username))

    monkeypatch.setattr(task_core_finalization, "refund_credits", fake_refund)

    refunded_not_submitted = await task_core_finalization.refund_cancelled_task(
        internal_user_id=123,
        username="u1",
        cost=20,
        task_submitted=False,
    )
    refunded_zero_cost = await task_core_finalization.refund_cancelled_task(
        internal_user_id=123,
        username="u1",
        cost=0,
        task_submitted=True,
    )

    assert refunded_not_submitted is False
    assert refunded_zero_cost is False
    assert calls == []


def test_build_failed_task_user_message_respects_refund_suffix_modes():
    error = RuntimeError("boom")

    default_message = task_core.build_failed_task_user_message(
        error=error,
        generic_error_prefix="出错了",
        refunded=True,
    )
    never_suffix_message = task_core.build_failed_task_user_message(
        error=error,
        generic_error_prefix="出错了",
        refunded=True,
        refund_suffix_mode="never",
    )
    always_suffix_message = task_core.build_failed_task_user_message(
        error=error,
        generic_error_prefix="出错了",
        refunded=False,
        refund_suffix_mode="always",
    )

    assert default_message == "出错了：boom，已退还灵石"
    assert never_suffix_message == "出错了：boom"
    assert always_suffix_message == "出错了：boom，已退还灵石"


def test_build_failed_task_user_message_handles_busy_and_non_refund_cases():
    busy_message = task_core.build_failed_task_user_message(
        error=RuntimeError("Connection refused"),
        generic_error_prefix="出错了",
        refunded=True,
    )
    normal_message = task_core.build_failed_task_user_message(
        error=RuntimeError("boom"),
        generic_error_prefix="系统错误",
        refunded=False,
        refund_suffix_mode="never",
    )

    assert busy_message == "当前服务器繁忙，请稍后再试，已退还灵石"
    assert normal_message == "系统错误：boom"


@pytest.mark.asyncio
async def test_finalize_task_failure_refunds_builds_message_and_cleans_up(monkeypatch):
    refund_calls = []
    cleanup_calls = []

    async def fake_refund(
        user_id: int,
        amount: int,
        task_type: str,
        username: str,
        idempotency_key: str,
    ):
        refund_calls.append((user_id, amount, task_type, username, idempotency_key))

    async def fake_cleanup(*, internal_user_id: int, registry_task_id: str | None, release_lock: bool = True):
        cleanup_calls.append((internal_user_id, registry_task_id, release_lock))

    monkeypatch.setattr(task_core_finalization, "refund_credits", fake_refund)
    monkeypatch.setattr(task_core_finalization, "cleanup_task_runtime_state", fake_cleanup)

    result = await task_core_finalization.finalize_task_failure(
        internal_user_id=10,
        username="u10",
        cost=8,
        should_refund=True,
        registry_task_id="task-10",
        release_lock=True,
        error=RuntimeError("boom"),
        generic_error_prefix="出错了",
    )

    assert result.refunded is True
    assert result.user_message == "出错了：boom，已退还灵石"
    assert refund_calls == [
        (10, 8, "refund", "u10", "task_refund:task:task-10")
    ]
    assert cleanup_calls == [(10, "task-10", True)]


@pytest.mark.asyncio
async def test_finalize_task_failure_with_notice_uses_finalize_result_message(monkeypatch):
    finalize_failure = AsyncMock(
        return_value=SimpleNamespace(
            refunded=True,
            user_message="终态消息",
        )
    )
    send_notice = AsyncMock()

    monkeypatch.setattr(task_core_finalization, "finalize_task_failure", finalize_failure)

    result = await task_core_finalization.finalize_task_failure_with_notice(
        internal_user_id=10,
        username="u10",
        cost=8,
        should_refund=True,
        registry_task_id="task-10",
        send_user_notice_func=send_notice,
    )

    assert result.user_message == "终态消息"
    finalize_failure.assert_awaited_once()
    send_notice.assert_awaited_once_with("终态消息")


@pytest.mark.asyncio
async def test_finalize_task_cancellation_refunds_and_cleans_up(monkeypatch):
    cleanup_calls = []
    refund_cancelled = AsyncMock(return_value=True)

    async def fake_cleanup(*, internal_user_id: int, registry_task_id: str | None, release_lock: bool = True):
        cleanup_calls.append((internal_user_id, registry_task_id, release_lock))

    monkeypatch.setattr(task_core_finalization, "cleanup_task_runtime_state", fake_cleanup)
    monkeypatch.setattr(
        task_core_finalization,
        "refund_cancelled_task",
        refund_cancelled,
    )

    result = await task_core_finalization.finalize_task_cancellation(
        internal_user_id=20,
        username="u20",
        cost=12,
        task_submitted=True,
        registry_task_id="task-20",
        release_lock=True,
    )

    assert result.refunded is True
    assert result.user_message == "任务已撤销，预扣的 12 灵石已全额退回。"
    refund_cancelled.assert_awaited_once_with(
        internal_user_id=20,
        username="u20",
        cost=12,
        task_submitted=True,
        idempotency_key="task_refund:task:task-20",
    )
    assert cleanup_calls == [(20, "task-20", True)]


@pytest.mark.asyncio
async def test_finalize_task_cancellation_skips_duplicate_refund_message(monkeypatch):
    monkeypatch.setattr(
        task_core_finalization,
        "cleanup_task_runtime_state",
        AsyncMock(),
    )
    monkeypatch.setattr(
        task_core_finalization,
        "refund_cancelled_task",
        AsyncMock(return_value=False),
    )

    result = await task_core_finalization.finalize_task_cancellation(
        internal_user_id=20,
        username="u20",
        cost=12,
        task_submitted=True,
        registry_task_id="task-20",
        release_lock=True,
    )

    assert result.refunded is False
    assert result.user_message is None


@pytest.mark.asyncio
async def test_finalize_terminated_task_terminates_before_refund(monkeypatch):
    call_order = []

    async def fake_force_terminate(registry_task_id: str, user_id: int | None = None):
        call_order.append(("terminate", registry_task_id, user_id))

    async def fake_refund(
        user_id: int,
        amount: int,
        task_type: str,
        username: str,
        idempotency_key: str,
    ):
        call_order.append(
            ("refund", user_id, amount, task_type, username, idempotency_key)
        )

    monkeypatch.setattr(task_core_finalization, "force_terminate_task", fake_force_terminate)
    monkeypatch.setattr(task_core_finalization, "refund_credits", fake_refund)

    result = await task_core_finalization.finalize_terminated_task(
        registry_task_id="task-30",
        user_id=30,
        username="u30",
        cost=6,
        should_refund=True,
        refund_task_type="refund_admin_force",
    )

    assert result.terminated is True
    assert result.refunded is True
    assert call_order == [
        ("terminate", "task-30", 30),
        (
            "refund",
            30,
            6,
            "refund_admin_force",
            "u30",
            "task_refund:task:task-30",
        ),
    ]


@pytest.mark.asyncio
async def test_force_terminate_task_reuses_cleanup_runtime_state_without_user_lock(
    monkeypatch,
):
    cancel_task = AsyncMock()
    cleanup_runtime = AsyncMock()
    submission_outbox = SimpleNamespace(
        get_active_tasks=AsyncMock(
            return_value={
                "registry-task-9": {
                    "backend_task_id": "backend-task-9",
                }
            }
        )
    )

    async def cancel_backend(*, backend_task_id: str, registry_task_id: str, raise_on_error: bool):
        assert registry_task_id == "registry-task-9"
        assert raise_on_error is True
        await cancel_task(backend_task_id)
        return True

    await task_core_runtime.force_terminate_task(
        "registry-task-9",
        submission_outbox=submission_outbox,
        cleanup_task_runtime_state_func=cleanup_runtime,
        cancel_backend_task_best_effort_func=cancel_backend,
    )

    cancel_task.assert_awaited_once_with("backend-task-9")
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=0,
        registry_task_id="registry-task-9",
        release_lock=False,
    )


@pytest.mark.asyncio
async def test_cancel_backend_task_best_effort_treats_missing_backend_as_cleaned():
    request = SimpleNamespace()
    response = SimpleNamespace(status_code=404)
    cancel_task = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "missing",
            request=request,
            response=response,
        )
    )

    cancelled = await task_core_runtime.cancel_backend_task_best_effort(
        backend_task_id="backend-task-404",
        registry_task_id="registry-task-404",
        cancel_task_func=cancel_task,
    )

    assert cancelled is False
    cancel_task.assert_awaited_once_with("backend-task-404")


@pytest.mark.asyncio
async def test_cleanup_task_runtime_state_uses_runtime_default_bindings():
    release_lock = AsyncMock()
    remove_task = AsyncMock()

    await task_core_runtime.cleanup_task_runtime_state(
        internal_user_id=9,
        registry_task_id="registry-9",
        release_concurrency_lock_func=release_lock,
        remove_task_func=remove_task,
    )

    release_lock.assert_awaited_once_with(
        9,
        idempotency_key="task_concurrency:registry-9",
    )
    remove_task.assert_awaited_once_with("registry-9")


@pytest.mark.asyncio
async def test_force_terminate_task_uses_runtime_default_bindings(monkeypatch):
    cancel_backend = AsyncMock()
    cleanup_runtime = AsyncMock()
    redis_client = SimpleNamespace(
        get_active_tasks=AsyncMock(
            return_value={
                "registry-task-10": {
                    "user_id": 10,
                    "backend_task_id": "backend-task-10",
                }
            }
        )
    )
    monkeypatch.setattr(
        task_core_runtime,
        "cancel_backend_task_best_effort",
        cancel_backend,
    )
    monkeypatch.setattr(
        task_core_runtime,
        "cleanup_task_runtime_state",
        cleanup_runtime,
    )

    await task_core_runtime.force_terminate_task(
        "registry-task-10",
        submission_outbox=redis_client,
    )

    cancel_backend.assert_awaited_once_with(
        backend_task_id="backend-task-10",
        registry_task_id="registry-task-10",
        raise_on_error=True,
    )
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=10,
        registry_task_id="registry-task-10",
        release_lock=True,
    )


@pytest.mark.asyncio
async def test_finalize_task_failure_with_notice_uses_runtime_default_binding(
    monkeypatch,
):
    finalize_failure = AsyncMock(return_value=SimpleNamespace(user_message="hello"))
    monkeypatch.setattr(
        task_core_finalization,
        "finalize_task_failure",
        finalize_failure,
    )

    result = await task_core_finalization.finalize_task_failure_with_notice(
        internal_user_id=1,
        username="tester",
        cost=2,
        should_refund=True,
        registry_task_id="reg-1",
    )

    assert result.user_message == "hello"
    finalize_failure.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_task_cancellation_uses_runtime_default_bindings(monkeypatch):
    refund_cancelled = AsyncMock(return_value=True)
    cleanup_runtime = AsyncMock()
    monkeypatch.setattr(
        task_core_finalization,
        "refund_cancelled_task",
        refund_cancelled,
    )
    monkeypatch.setattr(
        task_core_finalization,
        "cleanup_task_runtime_state",
        cleanup_runtime,
    )

    result = await task_core_finalization.finalize_task_cancellation(
        internal_user_id=2,
        username="tester",
        cost=3,
        task_submitted=True,
        registry_task_id="reg-2",
    )

    assert result.refunded is True
    refund_cancelled.assert_awaited_once()
    cleanup_runtime.assert_awaited_once_with(
        internal_user_id=2,
        registry_task_id="reg-2",
        release_lock=True,
    )


@pytest.mark.asyncio
async def test_get_system_task_stats_uses_runtime_redis_provider():
    active_tasks = {"task-1": {"user_id": 1}}
    user_concurrencies = {1: 1}
    redis_client = SimpleNamespace(
        get_active_tasks=AsyncMock(return_value=active_tasks),
        get_all_user_concurrencies=AsyncMock(return_value=user_concurrencies),
    )

    result = await task_core.get_system_task_stats(submission_outbox=redis_client)

    assert result == (active_tasks, user_concurrencies)
    redis_client.get_active_tasks.assert_awaited_once()
    redis_client.get_all_user_concurrencies.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_user_concurrency_uses_runtime_redis_provider():
    sync_concurrency = AsyncMock()
    redis_client = SimpleNamespace(sync_user_concurrency=sync_concurrency)

    await task_core.sync_user_concurrency(123, 2, submission_outbox=redis_client)
    await task_core.sync_user_concurrency(123, 0, submission_outbox=redis_client)

    assert sync_concurrency.await_args_list == [call(123, 2), call(123, 0)]


@pytest.mark.asyncio
async def test_cancel_user_task_finalizes_confirmed_pending_cancellation():
    finalize_cancellation = AsyncMock(
        return_value=SimpleNamespace(
            refunded=True,
            user_message="任务已撤销，预扣的 12 灵石已全额退回。",
        )
    )
    runtime_dependencies = SimpleNamespace(
        get_task_func=AsyncMock(
            return_value={
                "user_id": 42,
                "username": "daoist",
                "cost": 12,
                "credits_deducted": True,
                "backend_task_id": "backend-42",
            }
        ),
        find_task_by_backend_task_id_func=AsyncMock(),
        cancel_task_func=AsyncMock(
            return_value={
                "state": "cancelled",
                "task_id": "backend-42",
                "message": "任务已从排队队列移除",
            }
        ),
    )

    result = await task_core_runtime.cancel_user_task(
        "registry-42",
        42,
        runtime_dependencies=runtime_dependencies,
        finalize_task_cancellation_func=finalize_cancellation,
    )

    runtime_dependencies.cancel_task_func.assert_awaited_once_with("backend-42")
    finalize_cancellation.assert_awaited_once_with(
        internal_user_id=42,
        username="daoist",
        cost=12,
        task_submitted=True,
        registry_task_id="registry-42",
        release_lock=True,
    )
    assert result["message"] == "任务已撤销，预扣的 12 灵石已全额退回。"


@pytest.mark.asyncio
async def test_cancel_user_task_does_not_finalize_running_cancel_request():
    finalize_cancellation = AsyncMock()
    runtime_dependencies = SimpleNamespace(
        get_task_func=AsyncMock(
            return_value={
                "user_id": 42,
                "username": "daoist",
                "cost": 12,
                "credits_deducted": True,
                "backend_task_id": "backend-43",
            }
        ),
        find_task_by_backend_task_id_func=AsyncMock(),
        cancel_task_func=AsyncMock(
            return_value={
                "state": "cancellation_requested",
                "task_id": "backend-43",
                "message": "任务已请求取消，等待执行端确认",
            }
        ),
    )

    result = await task_core_runtime.cancel_user_task(
        "registry-43",
        42,
        runtime_dependencies=runtime_dependencies,
        finalize_task_cancellation_func=finalize_cancellation,
    )

    runtime_dependencies.cancel_task_func.assert_awaited_once_with("backend-43")
    finalize_cancellation.assert_not_awaited()
    assert result["state"] == "cancellation_requested"


@pytest.mark.asyncio
async def test_cancel_user_task_rejects_user_locked_task_without_backend_cancel():
    finalize_cancellation = AsyncMock()
    runtime_dependencies = SimpleNamespace(
        get_task_func=AsyncMock(
            return_value={
                "user_id": 42,
                "username": "daoist",
                "cost": 12,
                "credits_deducted": True,
                "backend_task_id": "backend-locked",
                "user_cancel_allowed": False,
            }
        ),
        find_task_by_backend_task_id_func=AsyncMock(),
        cancel_task_func=AsyncMock(),
    )

    result = await task_core_runtime.cancel_user_task(
        "registry-locked",
        42,
        runtime_dependencies=runtime_dependencies,
        finalize_task_cancellation_func=finalize_cancellation,
    )

    assert result == {
        "state": "not_cancellable",
        "task_id": "registry-locked",
        "message": "任务已进入连续生成阶段，无法再取消",
        "reason": "user_cancel_locked",
    }
    runtime_dependencies.cancel_task_func.assert_not_awaited()
    finalize_cancellation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_user_task_skips_refund_for_non_deducted_pending_task():
    finalize_cancellation = AsyncMock(return_value=SimpleNamespace(user_message=None))
    runtime_dependencies = SimpleNamespace(
        get_task_func=AsyncMock(
            return_value={
                "user_id": 42,
                "username": "daoist",
                "cost": 12,
                "credits_deducted": False,
                "backend_task_id": "backend-free",
            }
        ),
        find_task_by_backend_task_id_func=AsyncMock(),
        cancel_task_func=AsyncMock(
            return_value={
                "state": "cancelled",
                "task_id": "backend-free",
                "message": "任务已从排队队列移除",
            }
        ),
    )

    await task_core_runtime.cancel_user_task(
        "registry-free",
        42,
        runtime_dependencies=runtime_dependencies,
        finalize_task_cancellation_func=finalize_cancellation,
    )

    finalize_cancellation.assert_awaited_once_with(
        internal_user_id=42,
        username="daoist",
        cost=12,
        task_submitted=False,
        registry_task_id="registry-free",
        release_lock=True,
    )
