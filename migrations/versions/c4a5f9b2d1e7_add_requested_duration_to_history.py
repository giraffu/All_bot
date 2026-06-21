"""Add requested_duration to history

Revision ID: c4a5f9b2d1e7
Revises: bfd287d977f3
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4a5f9b2d1e7"
down_revision: Union[str, Sequence[str], None] = "bfd287d977f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE history
        ADD COLUMN IF NOT EXISTS requested_duration INTEGER
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("history", "requested_duration")
