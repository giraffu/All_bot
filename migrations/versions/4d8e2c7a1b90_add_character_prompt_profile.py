"""add character prompt profile

Revision ID: 4d8e2c7a1b90
Revises: c2e4f6a8b0d1
"""

import sqlalchemy as sa
from alembic import op

revision = "4d8e2c7a1b90"
down_revision = "c2e4f6a8b0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_references",
        sa.Column("prompt_profile", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("character_references", "prompt_profile")
