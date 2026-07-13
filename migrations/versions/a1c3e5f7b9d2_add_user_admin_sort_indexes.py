"""add user admin sort indexes

Revision ID: a1c3e5f7b9d2
Revises: f2b4c6d8e9f0
Create Date: 2026-05-30 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "f2b4c6d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_users_created_at_id", "users", ["created_at", "id"], unique=False)
    op.create_index("ix_users_credits_id", "users", ["credits", "id"], unique=False)
    op.create_index(
        "ix_users_checkin_count_id",
        "users",
        ["checkin_count", "id"],
        unique=False,
    )
    op.create_index(
        "ix_users_referral_count_id",
        "users",
        ["referral_count", "id"],
        unique=False,
    )
    op.create_index(
        "ix_users_generation_count_id",
        "users",
        ["generation_count", "id"],
        unique=False,
    )
    op.create_index(
        "ix_users_last_activity_id",
        "users",
        ["last_activity", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_last_activity_id", table_name="users")
    op.drop_index("ix_users_generation_count_id", table_name="users")
    op.drop_index("ix_users_referral_count_id", table_name="users")
    op.drop_index("ix_users_checkin_count_id", table_name="users")
    op.drop_index("ix_users_credits_id", table_name="users")
    op.drop_index("ix_users_created_at_id", table_name="users")
