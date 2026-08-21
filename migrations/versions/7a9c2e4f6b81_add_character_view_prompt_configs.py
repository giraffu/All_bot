"""add character view prompt configs

Revision ID: 7a9c2e4f6b81
Revises: 6d8e2f4a9b31
"""

from alembic import op
import sqlalchemy as sa

revision = "7a9c2e4f6b81"
down_revision = "6d8e2f4a9b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_view_prompt_configs",
        sa.Column("view_type", sa.String(32), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("prompt_templates", sa.JSON(), nullable=False),
        sa.Column(
            "tag_groups", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")
        ),
        sa.Column(
            "tag_options", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("character_view_prompt_configs")
