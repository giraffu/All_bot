"""expand site notice center

Revision ID: d4e5f6a7b8c9
Revises: c9d2e3f4a5b6
Create Date: 2026-05-28 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c9d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_notices",
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "site_notices",
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("site_notices", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column("site_notices", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE site_notices
        SET
            title = CASE
                WHEN btrim(coalesce(title, '')) = '' THEN '站点通知'
                ELSE title
            END,
            published_at = CASE
                WHEN is_active = true AND published_at IS NULL THEN COALESCE(updated_at, created_at, NOW())
                ELSE published_at
            END
        """
    )


def downgrade() -> None:
    op.drop_column("site_notices", "deleted_at")
    op.drop_column("site_notices", "published_at")
    op.drop_column("site_notices", "is_pinned")
    op.drop_column("site_notices", "title")
