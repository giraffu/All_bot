"""add default character view templates

Revision ID: a6d2f8c4e1b9
Revises: 9b4e6f8a1c20
"""

from alembic import op
import sqlalchemy as sa


revision = "a6d2f8c4e1b9"
down_revision = "9b4e6f8a1c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_view_image_templates",
        sa.Column(
            "is_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_character_view_image_templates_default_type",
        "character_view_image_templates",
        ["view_type"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_character_view_image_templates_default_type",
        table_name="character_view_image_templates",
    )
    op.drop_column("character_view_image_templates", "is_default")
