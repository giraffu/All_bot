from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest, RetryAfter, TimedOut

from src.database.models import SupportNotificationRecipient
from src.services.support_ticket_notification_service import (
    ClaimedSupportNotification,
    MAX_DELIVERY_ATTEMPTS,
    MAX_NOTIFICATION_RECIPIENTS,
    TELEGRAM_MESSAGE_LIMIT,
    SupportNotificationDispatcher,
    build_support_ticket_notification,
    enqueue_support_ticket_notifications,
    fail_support_notification,
    notification_retry_delay_seconds,
    replace_support_notification_recipient_ids,
)


@pytest.mark.asyncio
async def test_replacing_notification_recipients_deduplicates_and_commits():
    db = SimpleNamespace(execute=AsyncMock(), add_all=Mock(), commit=AsyncMock())

    result = await replace_support_notification_recipient_ids(
        db,
        [987654321, 123456789, 987654321],
    )

    assert result == [123456789, 987654321]
    recipients = db.add_all.call_args.args[0]
    assert all(isinstance(item, SupportNotificationRecipient) for item in recipients)
    assert [item.telegram_user_id for item in recipients] == result
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recipient_ids",
    ([0], [-1], [True], list(range(1, MAX_NOTIFICATION_RECIPIENTS + 2))),
)
async def test_replacing_notification_recipients_rejects_invalid_input(
    recipient_ids,
):
    db = SimpleNamespace(execute=AsyncMock(), add_all=Mock(), commit=AsyncMock())

    with pytest.raises(ValueError):
        await replace_support_notification_recipient_ids(db, recipient_ids)

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ticket_notification_enqueues_one_durable_delivery_per_recipient():
    recipients = [
        SupportNotificationRecipient(telegram_user_id=123456789),
        SupportNotificationRecipient(telegram_user_id=987654321),
    ]
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: recipients),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    db.add_all = Mock()
    ticket = SimpleNamespace(
        id=42,
        category="bug",
        telegram_user_id=556677,
        username="reporter",
        full_name="Report User",
    )

    deliveries = await enqueue_support_ticket_notifications(
        db,
        ticket=ticket,
        messages=[
            {"body": "第一段问题描述", "attachments": []},
            {
                "body": "第二段补充",
                "attachments": [{"filename": "error.png"}],
            },
        ],
    )

    assert [item.recipient_telegram_user_id for item in deliveries] == [
        123456789,
        987654321,
    ]
    notification = deliveries[0].payload_text
    assert "工单 #42" in notification
    assert "第一段问题描述" in notification
    assert "第二段补充" in notification
    assert "error.png" in notification


@pytest.mark.parametrize(
    ("attempt_count", "expected"),
    [(1, 5), (2, 30), (3, 120), (8, 10800), (99, 10800)],
)
def test_notification_retry_delay_is_bounded(attempt_count, expected):
    assert notification_retry_delay_seconds(attempt_count) == expected


def _job(outbox_id: int, recipient_id: int, attempt_number: int = 1):
    return ClaimedSupportNotification(
        outbox_id=outbox_id,
        ticket_id=40 + outbox_id,
        recipient_telegram_user_id=recipient_id,
        payload_text=f"notification-{outbox_id}",
        attempt_number=attempt_number,
        lease_token=f"lease-{outbox_id}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt_count", "retryable", "expected_status"),
    [
        (1, True, "retry"),
        (MAX_DELIVERY_ATTEMPTS, True, "failed"),
        (1, False, "failed"),
    ],
)
async def test_failure_record_uses_finite_retry_budget(
    monkeypatch, attempt_count, retryable, expected_status
):
    from src.services import support_ticket_notification_service as service

    delivery = SimpleNamespace(
        id=1,
        status="processing",
        attempt_count=attempt_count,
        lease_token="lease-1",
        lease_owner="worker",
        lease_until=None,
        next_attempt_at=None,
        failed_at=None,
        last_error_type=None,
        last_error_message=None,
        updated_at=None,
    )

    class FakeSession:
        def __init__(self):
            self.execute_count = 0
            self.commit = AsyncMock()

        async def execute(self, _statement):
            self.execute_count += 1
            if self.execute_count == 1:
                return SimpleNamespace(scalar_one_or_none=lambda: delivery)
            return SimpleNamespace()

    session = FakeSession()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(service, "AsyncSessionLocal", SessionContext)

    await fail_support_notification(
        _job(1, 123, attempt_number=attempt_count),
        error_type="TimedOut",
        error_message="temporary",
        retryable=retryable,
        retry_after_seconds=30,
    )

    assert delivery.status == expected_status
    assert (delivery.next_attempt_at is not None) is (expected_status == "retry")
    assert (delivery.failed_at is not None) is (expected_status == "failed")
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_delivers_with_notification_bot_and_records_success():
    job = _job(1, 123456789)
    claim = AsyncMock(return_value=[job])
    send_message = AsyncMock(return_value=SimpleNamespace(message_id=9001))
    complete = AsyncMock()
    fail = AsyncMock()
    dispatcher = SupportNotificationDispatcher(
        send_message=send_message,
        claim_func=claim,
        complete_func=complete,
        fail_func=fail,
        worker_id="support-1",
    )

    assert await dispatcher.run_once() == 1

    send_message.assert_awaited_once_with(
        chat_id=job.recipient_telegram_user_id,
        text=job.payload_text,
    )
    complete.assert_awaited_once_with(job, telegram_message_id=9001)
    fail.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "retryable", "retry_after"),
    [
        (TimedOut(), True, 5),
        (RetryAfter(17), True, 17),
        (BadRequest("chat not found"), False, 5),
    ],
)
async def test_dispatcher_classifies_retryable_and_permanent_failures(
    error, retryable, retry_after
):
    job = _job(2, 987654321)
    fail = AsyncMock()
    dispatcher = SupportNotificationDispatcher(
        send_message=AsyncMock(side_effect=error),
        claim_func=AsyncMock(return_value=[job]),
        complete_func=AsyncMock(),
        fail_func=fail,
        worker_id="support-1",
    )

    assert await dispatcher.run_once() == 1

    assert fail.await_args.args[0] == job
    assert fail.await_args.kwargs["error_type"] == type(error).__name__
    assert fail.await_args.kwargs["retryable"] is retryable
    assert fail.await_args.kwargs["retry_after_seconds"] == retry_after


@pytest.mark.asyncio
async def test_one_delivery_failure_does_not_block_another_recipient():
    first = _job(3, 111)
    second = _job(4, 222)
    complete = AsyncMock()
    fail = AsyncMock()

    async def send_message(*, chat_id, text):
        if chat_id == 111:
            raise BadRequest("chat not found")
        return SimpleNamespace(message_id=44)

    dispatcher = SupportNotificationDispatcher(
        send_message=send_message,
        claim_func=AsyncMock(return_value=[first, second]),
        complete_func=complete,
        fail_func=fail,
        worker_id="support-1",
        concurrency=2,
    )

    assert await dispatcher.run_once() == 2
    fail.assert_awaited_once()
    complete.assert_awaited_once_with(second, telegram_message_id=44)


def test_ticket_notification_stays_within_telegram_message_limit():
    notification = build_support_ticket_notification(
        ticket=SimpleNamespace(
            id=44,
            category="bug",
            telegram_user_id=556677,
            username=None,
            full_name=None,
        ),
        messages=[{"body": "很长的内容" * 1000, "attachments": []}],
    )

    assert len(notification) <= TELEGRAM_MESSAGE_LIMIT
    assert "管理后台查看完整工单" in notification
