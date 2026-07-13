"""add extra_outputs to history

Revision ID: f2b4c6d8e9f0
Revises: e6f7a8b9c0d1
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2b4c6d8e9f0"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("history", sa.Column("extra_outputs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("history", "extra_outputs")
