from datetime import datetime
from types import SimpleNamespace

import pytest

from src.database.models import (
    SupportMessage,
    SupportNotificationOutbox,
    SupportNotificationRecipient,
    SupportTicket,
)
from src.services.support_ticket_service import finalize_ticket_submission


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, query):
        entity = query.column_descriptions[0].get("entity")
        if entity is SupportNotificationRecipient:
            recipients = [
                SupportNotificationRecipient(telegram_user_id=111),
                SupportNotificationRecipient(telegram_user_id=222),
            ]
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: recipients)
            )
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, value):
        self.added.append(value)
        if isinstance(value, SupportTicket):
            value.id = 77

    def add_all(self, values):
        self.added.extend(values)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_finalize_submission_creates_one_new_ticket_with_ordered_messages():
    session = FakeSession()
    first_at = datetime(2026, 7, 23, 18, 10)
    second_at = datetime(2026, 7, 23, 18, 11)

    ticket = await finalize_ticket_submission(
        session,
        telegram_user_id=123,
        username="tester",
        full_name="Test User",
        language_code="zh",
        category="bug",
        messages=[
            {
                "telegram_message_id": 501,
                "body": "第一段",
                "attachments": [],
                "created_at": first_at,
            },
            {
                "telegram_message_id": 502,
                "body": "截图",
                "attachments": [
                    {
                        "object_key": "support/123/502/screenshot.jpg",
                        "filename": "screenshot.jpg",
                        "mime_type": "image/jpeg",
                    }
                ],
                "created_at": second_at,
            },
        ],
    )

    assert ticket.id == 77
    assert ticket.category == "bug"
    assert ticket.last_message_at == second_at
    assert session.flushes == 1
    assert session.commits == 1
    persisted_messages = [
        value for value in session.added if isinstance(value, SupportMessage)
    ]
    assert [message.telegram_message_id for message in persisted_messages] == [
        501,
        502,
    ]
    assert [message.created_at for message in persisted_messages] == [
        first_at,
        second_at,
    ]
    assert persisted_messages[1].attachments[0]["object_key"].endswith("screenshot.jpg")
    deliveries = [
        value for value in session.added if isinstance(value, SupportNotificationOutbox)
    ]
    assert [delivery.recipient_telegram_user_id for delivery in deliveries] == [
        111,
        222,
    ]
    assert all(delivery.ticket_id == ticket.id for delivery in deliveries)
    assert all("第一段" in delivery.payload_text for delivery in deliveries)


@pytest.mark.asyncio
async def test_finalize_submission_rejects_empty_draft_without_committing():
    session = FakeSession()

    with pytest.raises(ValueError, match="at least one message"):
        await finalize_ticket_submission(
            session,
            telegram_user_id=123,
            username=None,
            full_name=None,
            language_code=None,
            category="suggestion",
            messages=[],
        )

    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_finalize_submission_normalizes_unknown_category():
    session = FakeSession()

    ticket = await finalize_ticket_submission(
        session,
        telegram_user_id=123,
        username=None,
        full_name=None,
        language_code=None,
        category="unknown",
        messages=[
            {
                "telegram_message_id": 1,
                "body": "hello",
                "attachments": [],
                "created_at": datetime(2026, 7, 23, 18, 12),
            }
        ],
    )

    assert ticket.category == "uncategorized"
