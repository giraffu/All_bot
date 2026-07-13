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
    op.add_column("history", sa.Column("billing_resolution", sa.String(length=32), nullable=True))
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
            billing_resolution = CASE
                WHEN h.type = 'ltx_video'
                     AND ranked.width IS NOT NULL
                     AND ranked.height IS NOT NULL
                    THEN ranked.width::text || 'x' || ranked.height::text
                WHEN h.type IN (
                    'doggy_style',
                    'perfect_video_insert',
                    'blowjob',
                    'undress_tongue',
                    'closeup_blowjob',
                    'custom_video',
                    'face_video',
                    'face_video_step1',
                    'face_video_step2',
                    'video_lora',
                    'video_edit',
                    'perfect_video_edit',
                    'txt2video',
                    'video_insert'
                ) AND GREATEST(COALESCE(ranked.width, 0), COALESCE(ranked.height, 0)) >= 960
                    THEN '1024'
                WHEN h.type IN (
                    'doggy_style',
                    'perfect_video_insert',
                    'blowjob',
                    'undress_tongue',
                    'closeup_blowjob',
                    'custom_video',
                    'face_video',
                    'face_video_step1',
                    'face_video_step2',
                    'video_lora',
                    'video_edit',
                    'perfect_video_edit',
                    'txt2video',
                    'video_insert'
                ) AND GREATEST(COALESCE(ranked.width, 0), COALESCE(ranked.height, 0)) >= 700
                    THEN '720'
                WHEN h.type IN (
                    'doggy_style',
                    'perfect_video_insert',
                    'blowjob',
                    'undress_tongue',
                    'closeup_blowjob',
                    'custom_video',
                    'face_video',
                    'face_video_step1',
                    'face_video_step2',
                    'video_lora',
                    'video_edit',
                    'perfect_video_edit',
                    'txt2video',
                    'video_insert'
                ) AND GREATEST(COALESCE(ranked.width, 0), COALESCE(ranked.height, 0)) > 0
                    THEN '512'
                ELSE NULL
            END,
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
    op.drop_column("history", "billing_resolution")
