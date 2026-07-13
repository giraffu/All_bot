"""add web gallery hot path indexes

Revision ID: 1b6c8d9e0f24
Revises: 0f4e7b9c1a23
Create Date: 2026-06-07 22:31:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1b6c8d9e0f24"
down_revision: Union[str, Sequence[str], None] = "0f4e7b9c1a23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_gallery_posts_active_created_at_id
            ON gallery_posts (created_at DESC, id DESC)
            WHERE is_active IS TRUE
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_task_id
            ON history (task_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_user_id_id_desc
            ON history (user_id, id DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_user_visible_favorite_id_desc
            ON history (user_id, id DESC)
            WHERE is_favorited IS TRUE AND is_visible IS TRUE
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_history_task_user_id_desc
            ON history (task_id, user_id, id DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_interactions_user_action_post
            ON user_interactions (user_id, action_type, post_id)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_user_interactions_user_action_post"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_task_user_id_desc")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_history_user_visible_favorite_id_desc"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_user_id_id_desc")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_history_task_id")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_gallery_posts_active_created_at_id"
        )
