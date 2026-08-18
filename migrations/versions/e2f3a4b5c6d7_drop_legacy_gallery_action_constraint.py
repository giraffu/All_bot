"""drop the legacy Gallery action uniqueness constraint

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "ALTER TABLE user_interactions "
                "DROP CONSTRAINT IF EXISTS uix_user_post_action"
            )
        )
        return
    with op.batch_alter_table("user_interactions") as batch_op:
        batch_op.drop_constraint("uix_user_post_action", type_="unique")


def downgrade() -> None:
    columns = ["user_id", "post_id", "action_type"]
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(
            "uix_user_post_action",
            "user_interactions",
            columns,
        )
        return
    with op.batch_alter_table("user_interactions") as batch_op:
        batch_op.create_unique_constraint("uix_user_post_action", columns)
