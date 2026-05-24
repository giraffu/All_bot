"""rename orders telegram_id to internal_user_id

Revision ID: 7c0a4d5e6f71
Revises: 4c6b9e1f2a77
Create Date: 2026-05-25 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c0a4d5e6f71"
down_revision: Union[str, Sequence[str], None] = "4c6b9e1f2a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "telegram_id",
            new_column_name="internal_user_id",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )

    index_names = _get_index_names("orders")
    if "ix_orders_telegram_id" in index_names:
        op.drop_index("ix_orders_telegram_id", table_name="orders")
    if "ix_orders_internal_user_id" not in index_names:
        op.create_index(
            "ix_orders_internal_user_id",
            "orders",
            ["internal_user_id"],
            unique=False,
        )


def downgrade() -> None:
    index_names = _get_index_names("orders")
    if "ix_orders_internal_user_id" in index_names:
        op.drop_index("ix_orders_internal_user_id", table_name="orders")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "internal_user_id",
            new_column_name="telegram_id",
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )

    index_names = _get_index_names("orders")
    if "ix_orders_telegram_id" not in index_names:
        op.create_index("ix_orders_telegram_id", "orders", ["telegram_id"], unique=False)
