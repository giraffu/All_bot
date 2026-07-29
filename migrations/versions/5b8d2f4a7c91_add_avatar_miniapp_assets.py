"""add avatar mini app model assets and render jobs

Revision ID: 5b8d2f4a7c91
Revises: 3a7c9e1f2b40
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5b8d2f4a7c91"
down_revision: Union[str, Sequence[str], None] = "3a7c9e1f2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_model_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("model_object_key", sa.String(length=1024), nullable=True),
        sa.Column("render_source_object_key", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_object_key", sa.String(length=1024), nullable=True),
        sa.Column("rig_type", sa.String(length=32), nullable=True),
        sa.Column("animation_ids", sa.JSON(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status in ('queued', 'preparing_views', 'reconstructing', "
            "'rigging', 'ready', 'failed')",
            name="ck_character_model_assets_status",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"], ["character_references.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "version",
            name="uq_character_model_assets_character_version",
        ),
    )
    op.create_index(
        "ix_character_model_assets_user_id",
        "character_model_assets",
        ["user_id"],
    )
    op.create_index(
        "ix_character_model_assets_character_id",
        "character_model_assets",
        ["character_id"],
    )
    op.create_index(
        "ix_character_model_assets_user_status",
        "character_model_assets",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_character_model_assets_character_created",
        "character_model_assets",
        ["character_id", "created_at"],
    )
    op.create_index(
        "uq_character_model_assets_active_build",
        "character_model_assets",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text(
            "status in ('queued', 'preparing_views', 'reconstructing', 'rigging')"
        ),
    )

    op.create_table(
        "character_model_input_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("view_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "view_type in ('model_front', 'model_back', 'model_left', 'model_right')",
            name="ck_character_model_input_views_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'failed')",
            name="ck_character_model_input_views_status",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["character_model_assets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id",
            "view_type",
            name="uq_character_model_input_views_asset_type",
        ),
    )
    op.create_index(
        "ix_character_model_input_views_asset_id",
        "character_model_input_views",
        ["asset_id"],
    )

    op.create_table(
        "character_render_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("render_recipe", sa.JSON(), nullable=False),
        sa.Column("output_object_key", sa.String(length=1024), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status in ('queued', 'rendering', 'ready', 'failed', 'cancelled')",
            name="ck_character_render_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["character_model_assets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_render_jobs_user_id", "character_render_jobs", ["user_id"]
    )
    op.create_index(
        "ix_character_render_jobs_asset_id", "character_render_jobs", ["asset_id"]
    )
    op.create_index(
        "ix_character_render_jobs_user_status",
        "character_render_jobs",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_character_render_jobs_status_created",
        "character_render_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("character_render_jobs")
    op.drop_table("character_model_input_views")
    op.drop_table("character_model_assets")
