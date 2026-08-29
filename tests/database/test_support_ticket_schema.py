from sqlalchemy import CheckConstraint, UniqueConstraint

from src.database.models import (
    SupportNotificationAttempt,
    SupportNotificationOutbox,
    SupportNotificationRecipient,
    SupportTicket,
)
from src.services.support_ticket_service import CATEGORIES


def test_support_ticket_business_category_is_allowed_by_service_and_schema():
    assert "business" in CATEGORIES

    category_constraint = next(
        constraint
        for constraint in SupportTicket.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_support_tickets_category"
    )

    assert "'business'" in str(category_constraint.sqltext)


def test_support_notification_recipient_uses_telegram_user_id_as_identity():
    table = SupportNotificationRecipient.__table__

    assert table.name == "support_notification_recipients"
    assert table.c.telegram_user_id.primary_key is True
    assert table.c.telegram_user_id.nullable is False


def test_support_notification_outbox_is_idempotent_per_ticket_and_recipient():
    table = SupportNotificationOutbox.__table__

    assert table.c.ticket_id.nullable is False
    assert table.c.recipient_telegram_user_id.nullable is False
    assert table.c.payload_text.nullable is False
    assert table.c.next_attempt_at.nullable is False
    assert table.c.attempt_count.nullable is False
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_support_notification_outbox_ticket_recipient"
        for constraint in table.constraints
    )
    assert "ix_support_notification_outbox_claim" in {
        index.name for index in table.indexes
    }


def test_support_notification_attempts_form_a_durable_delivery_record():
    table = SupportNotificationAttempt.__table__

    assert table.c.outbox_id.nullable is False
    assert table.c.attempt_number.nullable is False
    assert table.c.status.nullable is False
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_support_notification_attempt_number"
        for constraint in table.constraints
    )
