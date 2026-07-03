"""add user log credit ledger index

Revision ID: 9b2f7c4d1a88
Revises: 7f3a9c1d2e4b
Create Date: 2026-07-03 14:20:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9b2f7c4d1a88"
down_revision: Union[str, Sequence[str], None] = "7f3a9c1d2e4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_user_logs_user_created_at_id",
        "user_logs",
        ["user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_logs_user_created_at_id", table_name="user_logs")
