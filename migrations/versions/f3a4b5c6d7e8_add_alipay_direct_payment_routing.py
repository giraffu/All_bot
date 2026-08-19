"""add Alipay direct allowlist and RMB provider routing

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "alipay_direct_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "orders",
        sa.Column("payment_provider", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_orders_payment_provider",
        "orders",
        ["payment_provider"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_orders_payment_provider",
        "orders",
        "payment_provider is null or payment_provider in ('HUANYUY', 'ALIPAY_DIRECT')",
    )
    op.execute(
        sa.text(
            "UPDATE orders SET payment_provider = 'HUANYUY' "
            "WHERE payment_channel = 'RMB' AND payment_provider IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_orders_payment_provider",
        "orders",
        type_="check",
    )
    op.drop_index("ix_orders_payment_provider", table_name="orders")
    op.drop_column("orders", "payment_provider")
    op.drop_column("users", "alipay_direct_enabled")

