"""add editable character reference views

Revision ID: 3a7c9e1f2b40
Revises: 1d6f4a8b9c20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3a7c9e1f2b40"
down_revision: Union[str, Sequence[str], None] = "1d6f4a8b9c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_character_references_status",
        "character_references",
        type_="check",
    )
    op.create_check_constraint(
        "ck_character_references_status",
        "character_references",
        "status in ('draft', 'pending', 'ready', 'failed', 'deleted')",
    )
    op.create_table(
        "character_reference_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("character_id", sa.String(length=36), nullable=False),
        sa.Column("view_type", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "view_type in ('face_front', 'face_side', 'face_three_quarter', "
            "'body_front', 'body_side', 'body_back')",
            name="ck_character_reference_views_type",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'ready', 'failed')",
            name="ck_character_reference_views_status",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["character_references.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "character_id",
            "view_type",
            name="uq_character_reference_views_character_type",
        ),
    )
    op.create_index(
        "ix_character_reference_views_character_id",
        "character_reference_views",
        ["character_id"],
    )
    op.create_index(
        "ix_character_reference_views_task_id",
        "character_reference_views",
        ["task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_character_reference_views_task_id",
        table_name="character_reference_views",
    )
    op.drop_index(
        "ix_character_reference_views_character_id",
        table_name="character_reference_views",
    )
    op.drop_table("character_reference_views")
    op.drop_constraint(
        "ck_character_references_status",
        "character_references",
        type_="check",
    )
    op.create_check_constraint(
        "ck_character_references_status",
        "character_references",
        "status in ('pending', 'ready', 'failed', 'deleted')",
    )
