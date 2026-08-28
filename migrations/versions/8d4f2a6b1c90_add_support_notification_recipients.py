"""add support notification recipients

Revision ID: 8d4f2a6b1c90
Revises: 5c2a7e9d1b40
Create Date: 2026-08-28 19:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8d4f2a6b1c90"
down_revision: Union[str, Sequence[str], None] = "5c2a7e9d1b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_notification_recipients",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )


def downgrade() -> None:
    op.drop_table("support_notification_recipients")
