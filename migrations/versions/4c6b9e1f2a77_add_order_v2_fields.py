"""add order v2 fields

Revision ID: 4c6b9e1f2a77
Revises: 8a4d2b6c9e10
Create Date: 2026-05-20 16:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c6b9e1f2a77"
down_revision: Union[str, Sequence[str], None] = "8a4d2b6c9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("business_order_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("settlement_schema_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("settlement_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_orders_business_order_id",
        "orders",
        ["business_order_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_business_order_id", table_name="orders")
    op.drop_column("orders", "settlement_snapshot")
    op.drop_column("orders", "settlement_schema_version")
    op.drop_column("orders", "business_order_id")
