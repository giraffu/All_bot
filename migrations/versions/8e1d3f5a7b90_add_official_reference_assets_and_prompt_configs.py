"""add official reference assets and prompt configs

Revision ID: 8e1d3f5a7b90
Revises: 4d8e2c7a1b90
"""

from alembic import op
import sqlalchemy as sa

revision = "8e1d3f5a7b90"
down_revision = "4d8e2c7a1b90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "character_references",
        sa.Column(
            "moderation_status", sa.String(16), server_default="active", nullable=False
        ),
    )
    op.add_column(
        "character_references",
        sa.Column("moderation_reason", sa.String(255), nullable=True),
    )
    op.create_check_constraint(
        "ck_character_references_moderation_status",
        "character_references",
        "moderation_status in ('active', 'disabled')",
    )
    op.create_table(
        "official_character_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column(
            "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("source_object_key", sa.String(1024)),
        sa.Column("sheet_object_key", sa.String(1024)),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime()),
        sa.CheckConstraint(
            "status in ('draft', 'ready', 'published', 'archived')",
            name="ck_official_character_assets_status",
        ),
    )
    op.create_index(
        "ix_official_character_assets_status_sort",
        "official_character_assets",
        ["status", "sort_order"],
    )
    op.create_table(
        "official_character_asset_views",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "character_id",
            sa.String(36),
            sa.ForeignKey("official_character_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("view_type", sa.String(32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(1024)),
        sa.Column("task_id", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "view_type in ('face_front', 'body_front', 'body_side', 'body_back')",
            name="ck_official_character_asset_views_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'failed')",
            name="ck_official_character_asset_views_status",
        ),
        sa.UniqueConstraint(
            "character_id", "view_type", name="uq_official_character_asset_view"
        ),
    )
    op.create_index(
        "ix_official_character_asset_views_task_id",
        "official_character_asset_views",
        ["task_id"],
        unique=True,
    )
    op.create_table(
        "official_environment_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("category", sa.String(80)),
        sa.Column(
            "tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("object_key", sa.String(1024)),
        sa.Column("task_id", sa.String(64)),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("archived_at", sa.DateTime()),
        sa.CheckConstraint(
            "status in ('draft', 'ready', 'published', 'archived')",
            name="ck_official_environment_assets_status",
        ),
    )
    op.create_index(
        "ix_official_environment_assets_status_sort",
        "official_environment_assets",
        ["status", "sort_order"],
    )
    op.create_table(
        "prompt_optimizer_scene_configs",
        sa.Column("scene_key", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("prompt_optimizer_scene_configs")
    op.drop_index(
        "ix_official_environment_assets_status_sort",
        table_name="official_environment_assets",
    )
    op.drop_table("official_environment_assets")
    op.drop_index(
        "ix_official_character_asset_views_task_id",
        table_name="official_character_asset_views",
    )
    op.drop_table("official_character_asset_views")
    op.drop_index(
        "ix_official_character_assets_status_sort",
        table_name="official_character_assets",
    )
    op.drop_table("official_character_assets")
    op.drop_constraint(
        "ck_character_references_moderation_status",
        "character_references",
        type_="check",
    )
    op.drop_column("character_references", "moderation_reason")
    op.drop_column("character_references", "moderation_status")
