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
