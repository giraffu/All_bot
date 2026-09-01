"""Persist external provider identity for resumable test-worker attempts.

Revision ID: 0002_attempt_provider_binding
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_attempt_provider_binding"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("task_attempts")}
    if "provider" not in columns:
        op.add_column(
            "task_attempts",
            sa.Column("provider", sa.String(length=80), nullable=True),
        )
    if "provider_task_id" not in columns:
        op.add_column(
            "task_attempts",
            sa.Column("provider_task_id", sa.String(length=180), nullable=True),
        )
    indexes = {
        item["name"] for item in sa.inspect(bind).get_indexes("task_attempts")
    }
    index_name = op.f("ix_task_attempts_provider_task_id")
    if index_name not in indexes:
        op.create_index(
            index_name,
            "task_attempts",
            ["provider_task_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_task_attempts_provider_task_id"), table_name="task_attempts"
    )
    op.drop_column("task_attempts", "provider_task_id")
    op.drop_column("task_attempts", "provider")
