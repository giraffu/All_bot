"""add membership redeem fields to affiliate_redeems

Revision ID: 8a4d2b6c9e10
Revises: 0368ee7bb002
Create Date: 2026-05-20 10:15:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a4d2b6c9e10"
down_revision: Union[str, Sequence[str], None] = "0368ee7bb002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "affiliate_redeems",
        sa.Column("target_plan_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "affiliate_redeems",
        sa.Column("target_identity", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "affiliate_redeems",
        sa.Column("duration_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "affiliate_redeems",
        sa.Column("grant_reward_credits", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "affiliate_redeems",
        sa.Column("settlement_reason", sa.String(length=50), nullable=True),
    )
    op.alter_column(
        "affiliate_redeems",
        "exchange_rate_snapshot",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.alter_column(
        "affiliate_redeems",
        "rounding_mode",
        existing_type=sa.String(length=32),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "affiliate_redeems",
        "rounding_mode",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    op.alter_column(
        "affiliate_redeems",
        "exchange_rate_snapshot",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_column("affiliate_redeems", "settlement_reason")
    op.drop_column("affiliate_redeems", "grant_reward_credits")
    op.drop_column("affiliate_redeems", "duration_days")
    op.drop_column("affiliate_redeems", "target_identity")
    op.drop_column("affiliate_redeems", "target_plan_id")
