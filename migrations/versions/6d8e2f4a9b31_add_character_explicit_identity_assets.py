"""add explicit character identity assets

Revision ID: 6d8e2f4a9b31
Revises: f3a4b5c6d7e8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6d8e2f4a9b31"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_references",
        sa.Column("adult_confirmed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "character_references",
        sa.Column("usage_rights_confirmed_at", sa.DateTime(), nullable=True),
    )
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


def downgrade() -> None:
    op.drop_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        type_="check",
    )
    op.create_check_constraint(
        "ck_character_reference_views_type",
        "character_reference_views",
        "view_type in ('face_front', 'face_side', 'face_three_quarter', "
        "'body_front', 'body_side', 'body_back')",
    )
    op.drop_column("character_references", "usage_rights_confirmed_at")
    op.drop_column("character_references", "adult_confirmed_at")
