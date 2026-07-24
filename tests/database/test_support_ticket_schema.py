from sqlalchemy import CheckConstraint

from src.database.models import SupportTicket
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
