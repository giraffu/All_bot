from sqlalchemy import CheckConstraint

from src.database.models import SupportNotificationRecipient, SupportTicket
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
