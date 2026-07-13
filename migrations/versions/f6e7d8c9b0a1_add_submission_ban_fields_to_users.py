"""add submission ban fields to users

Revision ID: f6e7d8c9b0a1
Revises: a1c3e5f7b9d2
Create Date: 2026-06-01 11:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6e7d8c9b0a1"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_submission_banned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("users", sa.Column("submission_banned_at", sa.DateTime(), nullable=True))
    op.add_column(
        "users", sa.Column("submission_ban_reason", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "submission_ban_reason")
    op.drop_column("users", "submission_banned_at")
    op.drop_column("users", "is_submission_banned")
