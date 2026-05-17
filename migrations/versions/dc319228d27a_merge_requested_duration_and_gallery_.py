"""merge requested_duration and gallery_comments heads

Revision ID: dc319228d27a
Revises: 86a36381fa4c, c4a5f9b2d1e7
Create Date: 2026-05-17 15:00:38.401373

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'dc319228d27a'
down_revision: Union[str, Sequence[str], None] = ('86a36381fa4c', 'c4a5f9b2d1e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
