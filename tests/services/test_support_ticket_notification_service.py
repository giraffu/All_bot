from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.database.models import SupportNotificationRecipient
from src.services.support_ticket_notification_service import (
    MAX_NOTIFICATION_RECIPIENTS,
    TELEGRAM_MESSAGE_LIMIT,
    build_support_ticket_notification,
    notify_support_ticket_submission,
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
async def test_ticket_notification_delivers_submitted_content_to_every_recipient():
    recipients = [
        SupportNotificationRecipient(telegram_user_id=123456789),
        SupportNotificationRecipient(telegram_user_id=987654321),
    ]
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: recipients),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    send_message = AsyncMock()
    ticket = SimpleNamespace(
        id=42,
        category="bug",
        telegram_user_id=556677,
        username="reporter",
        full_name="Report User",
    )

    await notify_support_ticket_submission(
        db,
        ticket=ticket,
        messages=[
            {"body": "第一段问题描述", "attachments": []},
            {
                "body": "第二段补充",
                "attachments": [{"filename": "error.png"}],
            },
        ],
        send_message=send_message,
    )

    assert [call.kwargs["chat_id"] for call in send_message.await_args_list] == [
        123456789,
        987654321,
    ]
    notification = send_message.await_args_list[0].kwargs["text"]
    assert "工单 #42" in notification
    assert "第一段问题描述" in notification
    assert "第二段补充" in notification
    assert "error.png" in notification


@pytest.mark.asyncio
async def test_one_notification_failure_does_not_block_other_recipients():
    recipients = [
        SupportNotificationRecipient(telegram_user_id=123456789),
        SupportNotificationRecipient(telegram_user_id=987654321),
    ]
    result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: recipients),
    )
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    send_message = AsyncMock(side_effect=[RuntimeError("blocked"), None])

    await notify_support_ticket_submission(
        db,
        ticket=SimpleNamespace(
            id=43,
            category="suggestion",
            telegram_user_id=556677,
            username=None,
            full_name=None,
        ),
        messages=[{"body": "建议内容", "attachments": []}],
        send_message=send_message,
    )

    assert send_message.await_count == 2


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
