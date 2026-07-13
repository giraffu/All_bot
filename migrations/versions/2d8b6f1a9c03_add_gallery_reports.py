"""add gallery reports

Revision ID: 2d8b6f1a9c03
Revises: 9b2f7c4d1a88
Create Date: 2026-07-04 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d8b6f1a9c03"
down_revision: Union[str, Sequence[str], None] = "9b2f7c4d1a88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gallery_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("reporter_user_id", sa.BigInteger(), nullable=True),
        sa.Column("post_author_user_id", sa.BigInteger(), nullable=True),
        sa.Column("post_task_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_action", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "reason in ('children', 'gore', 'gross', 'other')",
            name="ck_gallery_reports_reason",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'resolved')",
            name="ck_gallery_reports_status",
        ),
        sa.ForeignKeyConstraint(
            ["post_author_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["gallery_posts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reporter_user_id",
            "post_id",
            name="uq_gallery_reports_reporter_post",
        ),
    )
    op.create_index(
        "ix_gallery_reports_post_author_user_id",
        "gallery_reports",
        ["post_author_user_id"],
    )
    op.create_index(
        "ix_gallery_reports_post_created_at",
        "gallery_reports",
        ["post_id", "created_at"],
    )
    op.create_index(
        "ix_gallery_reports_post_id",
        "gallery_reports",
        ["post_id"],
    )
    op.create_index(
        "ix_gallery_reports_post_task_id",
        "gallery_reports",
        ["post_task_id"],
    )
    op.create_index(
        "ix_gallery_reports_reason_created_at",
        "gallery_reports",
        ["reason", "created_at"],
    )
    op.create_index(
        "ix_gallery_reports_reporter_user_id",
        "gallery_reports",
        ["reporter_user_id"],
    )
    op.create_index(
        "ix_gallery_reports_status_created_at",
        "gallery_reports",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_gallery_reports_status_created_at", table_name="gallery_reports")
    op.drop_index("ix_gallery_reports_reporter_user_id", table_name="gallery_reports")
    op.drop_index("ix_gallery_reports_reason_created_at", table_name="gallery_reports")
    op.drop_index("ix_gallery_reports_post_task_id", table_name="gallery_reports")
    op.drop_index("ix_gallery_reports_post_id", table_name="gallery_reports")
    op.drop_index("ix_gallery_reports_post_created_at", table_name="gallery_reports")
    op.drop_index(
        "ix_gallery_reports_post_author_user_id",
        table_name="gallery_reports",
    )
    op.drop_table("gallery_reports")
