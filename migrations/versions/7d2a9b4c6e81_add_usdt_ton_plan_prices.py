"""add USDT-TON plan prices

Revision ID: 7d2a9b4c6e81
Revises: 5b8d2f4a7c91
"""

from alembic import op
import sqlalchemy as sa


revision = "7d2a9b4c6e81"
down_revision = "5b8d2f4a7c91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "membership_plans",
        sa.Column(
            "price_usdt",
            sa.DECIMAL(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.execute(
        """
        UPDATE membership_plans
        SET price_usdt = CASE id
            WHEN 1 THEN 4.50
            WHEN 2 THEN 10.00
            WHEN 3 THEN 17.00
            WHEN 5 THEN 4.50
            WHEN 6 THEN 10.00
            WHEN 7 THEN 17.00
            ELSE 0
        END
        """
    )
    op.alter_column("membership_plans", "price_usdt", server_default=None)


def downgrade() -> None:
    op.drop_column("membership_plans", "price_usdt")
