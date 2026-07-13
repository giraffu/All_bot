from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import task_failure_finalization_service as service


def test_build_zombie_cleanup_user_message_appends_refund_suffix():
    assert (
        service.build_zombie_cleanup_user_message(5)
        == "您的任务由于等待/执行时间过长，已被系统自动清理。 预扣的 5 灵石已退回。"
    )
    assert service.build_zombie_cleanup_user_message(0) == "您的任务由于等待/执行时间过长，已被系统自动清理。"


def test_build_failure_policies_capture_message_and_log_contract():
    recovery_policy = service.build_recovery_failure_policy(
        reason="恢复失败",
        chat_id=321,
    )
    zombie_policy = service.build_zombie_cleanup_failure_policy(
        cost=5,
        chat_id=456,
    )

    assert recovery_policy.refund_task_type == "refund_restart"
    assert recovery_policy.explicit_user_message == "恢复失败"
    assert recovery_policy.notice_failure_log_message == "Failed to send refund notice to 321"

    assert zombie_policy.refund_task_type == "refund_zombie_cleanup"
    assert (
        zombie_policy.explicit_user_message
        == "您的任务由于等待/执行时间过长，已被系统自动清理。 预扣的 5 灵石已退回。"
    )
    assert (
        zombie_policy.notice_failure_log_message
        == "Failed to send zombie cleanup notice to 456"
    )


@pytest.mark.asyncio
async def test_finalize_task_failure_for_task_record_uses_task_data_and_notice_sender(
    monkeypatch,
):
    finalize = AsyncMock()
    send_message = AsyncMock()
    monkeypatch.setattr(
        service,
        "finalize_task_failure_with_notice",
        finalize,
    )
    monkeypatch.setattr("src.utils.robust_send_message", send_message)

    bot = object()
    await service.finalize_task_failure_for_task_record(
        registry_task_id="task-1",
        task_data={
            "user_id": 123,
            "username": "tester",
            "cost": 5,
            "chat_id": 456,
        },
        policy=service.TaskFailureFinalizationPolicy(
            refund_task_type="refund_test",
            explicit_user_message="message",
            notice_failure_log_message="notice failed",
        ),
        bot=bot,
        logger_override=object(),
        finalize_task_failure_with_notice_func=finalize,
    )

    finalize.assert_awaited_once()
    kwargs = finalize.await_args.kwargs
    assert kwargs["internal_user_id"] == 123
    assert kwargs["username"] == "tester"
    assert kwargs["cost"] == 5
    assert kwargs["should_refund"] is True
    assert kwargs["registry_task_id"] == "task-1"
    assert kwargs["refund_task_type"] == "refund_test"
    assert kwargs["explicit_user_message"] == "message"
    send_notice = kwargs["send_user_notice_func"]
    assert send_notice is not None
    await send_notice("hello")
    send_message.assert_awaited_once_with(bot, 456, "hello")


@pytest.mark.asyncio
async def test_finalize_task_failure_for_task_record_uses_runtime_default_binding(
    monkeypatch,
):
    finalize = AsyncMock()
    monkeypatch.setattr(
        service,
        "finalize_task_failure_with_notice",
        finalize,
    )

    await service.finalize_task_failure_for_task_record(
        registry_task_id="task-runtime",
        task_data={
            "user_id": 123,
            "username": "tester",
            "cost": 0,
        },
        policy=service.TaskFailureFinalizationPolicy(
            refund_task_type="refund_test",
            explicit_user_message="message",
            notice_failure_log_message="notice failed",
        ),
        logger_override=object(),
    )

    finalize.assert_awaited_once()
    kwargs = finalize.await_args.kwargs
    assert kwargs["registry_task_id"] == "task-runtime"
    assert kwargs["explicit_user_message"] == "message"


@pytest.mark.asyncio
async def test_finalize_recovery_failure_for_task_record_builds_policy_and_delegates(
    monkeypatch,
):
    finalize_with_policy = AsyncMock()
    monkeypatch.setattr(
        service,
        "_finalize_task_record_with_policy",
        finalize_with_policy,
    )

    bot = object()
    logger_override = object()
    await service.finalize_recovery_failure_for_task_record(
        registry_task_id="task-2",
        task_data={
            "user_id": 100,
            "username": "tester",
            "cost": 6,
            "chat_id": 999,
        },
        reason="恢复异常",
        bot=bot,
        logger_override=logger_override,
    )

    finalize_with_policy.assert_awaited_once()
    kwargs = finalize_with_policy.await_args.kwargs
    assert kwargs["registry_task_id"] == "task-2"
    assert kwargs["task_data"]["user_id"] == 100
    assert kwargs["bot"] is bot
    assert kwargs["logger_override"] is logger_override
    assert kwargs["finalize_task_failure_for_task_record_func"] is None
    policy = kwargs["policy"]
    assert policy.refund_task_type == "refund_restart"
    assert policy.explicit_user_message == "恢复异常"
    assert policy.notice_failure_log_message == "Failed to send refund notice to 999"


@pytest.mark.asyncio
async def test_finalize_zombie_cleanup_for_task_record_builds_policy_and_cancels_backend(
    monkeypatch,
):
    finalize = AsyncMock(return_value=(SimpleNamespace(refunded=True), True))
    cancel_backend = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service,
        "_finalize_task_record_with_policy",
        finalize,
    )
    monkeypatch.setattr(
        service,
        "cancel_backend_task_best_effort",
        cancel_backend,
    )

    bot = object()
    logger_override = object()
    result, cancelled = await service.finalize_zombie_cleanup_for_task_record(
        registry_task_id="task-3",
        task_data={
            "user_id": 101,
            "username": "tester",
            "cost": 8,
            "chat_id": 888,
            "backend_task_id": "backend-3",
        },
        bot=bot,
        logger_override=logger_override,
    )

    assert result.refunded is True
    assert cancelled is True
    finalize.assert_awaited_once()
    finalize_kwargs = finalize.await_args.kwargs
    assert finalize_kwargs["backend_task_id"] == "backend-3"
    assert finalize_kwargs["cancel_backend_task_best_effort_func"] is None
    policy = finalize_kwargs["policy"]
    assert policy.refund_task_type == "refund_zombie_cleanup"
    assert (
        policy.explicit_user_message
        == "您的任务由于等待/执行时间过长，已被系统自动清理。 预扣的 8 灵石已退回。"
    )
    assert (
        policy.notice_failure_log_message
        == "Failed to send zombie cleanup notice to 888"
    )


@pytest.mark.asyncio
async def test_finalize_task_record_with_policy_uses_runtime_default_cancel_binding(
    monkeypatch,
):
    finalize_task_failure = AsyncMock(return_value=SimpleNamespace(refunded=True))
    cancel_backend = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service,
        "finalize_task_failure_for_task_record",
        finalize_task_failure,
    )
    monkeypatch.setattr(
        service,
        "cancel_backend_task_best_effort",
        cancel_backend,
    )

    result, cancelled = await service._finalize_task_record_with_policy(
        registry_task_id="task-4",
        task_data={"backend_task_id": "backend-4"},
        policy=service.TaskFailureFinalizationPolicy(
            refund_task_type="refund_test",
            explicit_user_message="message",
            notice_failure_log_message="notice failed",
        ),
        logger_override=object(),
        backend_task_id="backend-4",
    )

    assert result.refunded is True
    assert cancelled is True
    finalize_task_failure.assert_awaited_once()
    cancel_backend.assert_awaited_once()
