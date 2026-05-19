"""add affiliate redeems table

Revision ID: f1c9a6d7e2b3
Revises: dc319228d27a
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1c9a6d7e2b3"
down_revision: Union[str, Sequence[str], None] = "dc319228d27a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "affiliate_redeems",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("redeem_type", sa.String(length=50), nullable=False),
        sa.Column("redeem_option_key", sa.String(length=64), nullable=False),
        sa.Column("requested_amount_usdt", sa.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("amount_usdt", sa.DECIMAL(precision=10, scale=4), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("exchange_rate_snapshot", sa.String(length=64), nullable=False),
        sa.Column("rounding_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_affiliate_redeems_user_idempotency_key",
        ),
    )
    op.create_index(
        "ix_affiliate_redeems_user_created_at",
        "affiliate_redeems",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_affiliate_redeems_user_created_at", table_name="affiliate_redeems"
    )
    op.drop_table("affiliate_redeems")
