"""link gallery posts to their owned history row

Revision ID: 3c7e9a1b5d20
Revises: 2a6c8e1f4b90
Create Date: 2026-09-06 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c7e9a1b5d20"
down_revision: Union[str, Sequence[str], None] = "2a6c8e1f4b90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gallery_posts",
        sa.Column("history_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_gallery_posts_history_id_history",
        "gallery_posts",
        "history",
        ["history_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_gallery_posts_history_id",
        "gallery_posts",
        ["history_id"],
        unique=False,
    )
    # Only deterministic one-to-one owner/task matches are backfilled. Ambiguous
    # legacy rows stay NULL and use the ownership-safe compatibility reader.
    op.execute(
        sa.text(
            """
            WITH unambiguous_history AS (
                SELECT gp.id AS post_id, max(h.id) AS history_id
                FROM gallery_posts AS gp
                JOIN history AS h
                  ON h.task_id = gp.task_id
                 AND h.user_id = gp.user_id
                GROUP BY gp.id
                HAVING count(h.id) = 1
            )
            UPDATE gallery_posts AS gp
               SET history_id = matched.history_id
              FROM unambiguous_history AS matched
             WHERE gp.id = matched.post_id
               AND gp.history_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_gallery_posts_history_id", table_name="gallery_posts")
    op.drop_constraint(
        "fk_gallery_posts_history_id_history",
        "gallery_posts",
        type_="foreignkey",
    )
    op.drop_column("gallery_posts", "history_id")
