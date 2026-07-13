"""reconcile gallery comment indexes

Revision ID: 24b7c9d1e3f5
Revises: f6e7d8c9b0a1
Create Date: 2026-06-04 17:10:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "24b7c9d1e3f5"
down_revision: Union[str, Sequence[str], None] = "f6e7d8c9b0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE gallery_comments
        SET is_active = true
        WHERE is_active IS NULL
        """
    )
    op.execute(
        """
        UPDATE gallery_comments
        SET created_at = now()
        WHERE created_at IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE gallery_comments
            ALTER COLUMN is_active SET DEFAULT true,
            ALTER COLUMN is_active SET NOT NULL,
            ALTER COLUMN created_at SET DEFAULT now(),
            ALTER COLUMN created_at SET NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_gallery_comments_created_at")
    op.execute("DROP INDEX IF EXISTS ix_gallery_comments_post_id")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gallery_comments_post_created_at
        ON gallery_comments (post_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gallery_comments_active_post_created_at
        ON gallery_comments (post_id, created_at)
        WHERE is_active = true
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_user_logs_user_id")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gallery_comments_active_post_created_at")
    op.execute("DROP INDEX IF EXISTS ix_gallery_comments_post_created_at")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gallery_comments_post_id
        ON gallery_comments (post_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_gallery_comments_created_at
        ON gallery_comments (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_logs_user_id
        ON user_logs (user_id)
        """
    )
    op.execute(
        """
        ALTER TABLE gallery_comments
            ALTER COLUMN is_active DROP NOT NULL,
            ALTER COLUMN is_active DROP DEFAULT,
            ALTER COLUMN created_at DROP NOT NULL,
            ALTER COLUMN created_at DROP DEFAULT
        """
    )
