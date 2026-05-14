"""Add history billing_resolution hotfix

Revision ID: bfd287d977f3
Revises: 6f4b0d9d8c21
Create Date: 2026-05-14 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "bfd287d977f3"
down_revision: Union[str, Sequence[str], None] = "6f4b0d9d8c21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE history
        ADD COLUMN IF NOT EXISTS billing_resolution VARCHAR(32)
        """
    )

    op.execute(
        """
        WITH ranked_gallery_posts AS (
            SELECT
                gp.task_id,
                gp.width,
                gp.height,
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
        SET billing_resolution = CASE
            WHEN h.type = 'ltx_video'
                 AND COALESCE(h.width, ranked.width) IS NOT NULL
                 AND COALESCE(h.height, ranked.height) IS NOT NULL
                THEN COALESCE(h.width, ranked.width)::text || 'x' || COALESCE(h.height, ranked.height)::text
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
            ) AND GREATEST(COALESCE(h.width, ranked.width, 0), COALESCE(h.height, ranked.height, 0)) >= 960
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
            ) AND GREATEST(COALESCE(h.width, ranked.width, 0), COALESCE(h.height, ranked.height, 0)) >= 700
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
            ) AND GREATEST(COALESCE(h.width, ranked.width, 0), COALESCE(h.height, ranked.height, 0)) > 0
                THEN '512'
            ELSE NULL
        END
        FROM ranked_gallery_posts AS ranked
        WHERE ranked.task_id = h.task_id
          AND ranked.row_num = 1
          AND h.billing_resolution IS NULL
        """
    )

    op.execute(
        """
        UPDATE history AS h
        SET billing_resolution = CASE
            WHEN h.type = 'ltx_video'
                 AND h.width IS NOT NULL
                 AND h.height IS NOT NULL
                THEN h.width::text || 'x' || h.height::text
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
            ) AND GREATEST(COALESCE(h.width, 0), COALESCE(h.height, 0)) >= 960
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
            ) AND GREATEST(COALESCE(h.width, 0), COALESCE(h.height, 0)) >= 700
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
            ) AND GREATEST(COALESCE(h.width, 0), COALESCE(h.height, 0)) > 0
                THEN '512'
            ELSE billing_resolution
        END
        WHERE h.billing_resolution IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Hotfix migration: keep downgrade as a no-op to avoid dropping a column
    # that may also exist in databases initialized from the newer base revision.
    pass
