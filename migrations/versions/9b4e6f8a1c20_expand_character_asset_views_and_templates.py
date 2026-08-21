"""expand character asset views and add image templates

Revision ID: 9b4e6f8a1c20
Revises: 7a9c2e4f6b81
"""

from alembic import op
import sqlalchemy as sa


revision = "9b4e6f8a1c20"
down_revision = "7a9c2e4f6b81"
branch_labels = None
depends_on = None


_EXPANDED_TYPES = (
    "view_type in ('face_front', 'face_side', 'face_three_quarter', "
    "'body_front', 'body_side', 'body_back', 'body_front_nude', "
    "'body_front_clothed', 'torso_front', 'genitals_front', 'pelvis_back', "
    "'custom_1', 'custom_2', 'custom_3', 'custom_4')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        type_="check",
    )
    op.create_check_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        _EXPANDED_TYPES,
    )
    op.add_column(
        "character_reference_views",
        sa.Column("display_name", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "character_reference_views",
        sa.Column("description", sa.String(length=500), nullable=True),
    )
    op.execute(
        "UPDATE character_reference_views "
        "SET view_type = 'body_front_nude' WHERE view_type = 'body_front'"
    )
    op.execute(
        "UPDATE character_view_prompt_configs "
        "SET view_type = 'body_front_nude' WHERE view_type = 'body_front'"
    )
    op.execute(
        "DELETE FROM character_view_prompt_configs "
        "WHERE view_type IN ('body_side', 'body_back', 'genitals_front')"
    )

    op.create_table(
        "character_view_image_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("view_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "view_type in ('torso_front', 'genitals_front', 'pelvis_back')",
            name="ck_character_view_image_templates_type",
        ),
        sa.CheckConstraint(
            "gender in ('neutral', 'female', 'male')",
            name="ck_character_view_image_templates_gender",
        ),
        sa.CheckConstraint(
            "status in ('active', 'disabled')",
            name="ck_character_view_image_templates_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_view_image_templates_type_status_sort",
        "character_view_image_templates",
        ["view_type", "status", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_character_view_image_templates_type_status_sort",
        table_name="character_view_image_templates",
    )
    op.drop_table("character_view_image_templates")
    op.execute(
        "DELETE FROM character_reference_views WHERE view_type IN "
        "('body_front_clothed', 'torso_front', 'pelvis_back', "
        "'custom_1', 'custom_2', 'custom_3', 'custom_4')"
    )
    op.execute(
        "UPDATE character_reference_views "
        "SET view_type = 'body_front' WHERE view_type = 'body_front_nude'"
    )
    op.execute(
        "UPDATE character_view_prompt_configs "
        "SET view_type = 'body_front' WHERE view_type = 'body_front_nude'"
    )
    op.drop_column("character_reference_views", "description")
    op.drop_column("character_reference_views", "display_name")
    op.drop_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        type_="check",
    )
    op.create_check_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        "view_type in ('face_front', 'face_side', 'face_three_quarter', "
        "'body_front', 'body_side', 'body_back', 'genitals_front')",
    )
