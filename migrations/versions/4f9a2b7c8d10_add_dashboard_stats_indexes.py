"""add dashboard stats indexes

Revision ID: 4f9a2b7c8d10
Revises: 1b6c8d9e0f24
Create Date: 2026-06-10 10:15:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4f9a2b7c8d10"
down_revision: Union[str, Sequence[str], None] = "1b6c8d9e0f24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_created_at
            ON history (created_at)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_created_at_type
            ON history (created_at, type)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_created_at_user_id
            ON history (created_at, user_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_source_created_at_user_id
            ON history (source, created_at, user_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_checkin_history_checkin_date
            ON checkin_history (checkin_date)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_checkin_history_checkin_date")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_source_created_at_user_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_created_at_user_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_created_at_type")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_created_at")
