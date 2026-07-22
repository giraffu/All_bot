"""add support business category

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from alembic import op


revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "ck_support_tickets_category",
        "support_tickets",
        type_="check",
    )
    op.create_check_constraint(
        "ck_support_tickets_category",
        "support_tickets",
        "category in ('recharge', 'bug', 'suggestion', 'business', 'uncategorized')",
    )


def downgrade():
    op.execute(
        "UPDATE support_tickets SET category = 'uncategorized' "
        "WHERE category = 'business'"
    )
    op.drop_constraint(
        "ck_support_tickets_category",
        "support_tickets",
        type_="check",
    )
    op.create_check_constraint(
        "ck_support_tickets_category",
        "support_tickets",
        "category in ('recharge', 'bug', 'suggestion', 'uncategorized')",
    )
