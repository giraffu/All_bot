"""Add media metadata to history

Revision ID: 6f4b0d9d8c21
Revises: 9d7f1c2a4b11
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f4b0d9d8c21"
down_revision: Union[str, Sequence[str], None] = "9d7f1c2a4b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("history", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("history", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("history", sa.Column("duration", sa.Integer(), nullable=True))

    op.execute(
        """
        WITH ranked_gallery_posts AS (
            SELECT
                gp.task_id,
                gp.width,
                gp.height,
                gp.duration,
                ROW_NUMBER() OVER (
                    PARTITION BY gp.task_id
                    ORDER BY
                        CASE WHEN gp.is_active THEN 1 ELSE 0 END DESC,
                        CASE WHEN gp.created_at IS NULL THEN 1 ELSE 0 END ASC,
                        gp.created_at DESC,
                        gp.id DESC
                ) AS row_num
            FROM gallery_posts AS gp
        )
        UPDATE history AS h
        SET
            width = ranked.width,
            height = ranked.height,
            duration = ranked.duration
        FROM ranked_gallery_posts AS ranked
        WHERE ranked.task_id = h.task_id
          AND ranked.row_num = 1
          AND (h.width IS NULL OR h.height IS NULL OR h.duration IS NULL)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("history", "duration")
    op.drop_column("history", "height")
    op.drop_column("history", "width")
