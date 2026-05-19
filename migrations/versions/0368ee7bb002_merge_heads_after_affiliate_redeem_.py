"""merge heads after affiliate redeem credits

Revision ID: 0368ee7bb002
Revises: 5a8d9f3c1b2e, f1c9a6d7e2b3
Create Date: 2026-05-19 17:53:57.600458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0368ee7bb002'
down_revision: Union[str, Sequence[str], None] = ('5a8d9f3c1b2e', 'f1c9a6d7e2b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
