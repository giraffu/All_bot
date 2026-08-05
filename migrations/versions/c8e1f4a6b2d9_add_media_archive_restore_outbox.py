"""add media archive restore outbox

Revision ID: c8e1f4a6b2d9
Revises: b7d9e1f3a5c2
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e1f4a6b2d9"
down_revision = "b7d9e1f3a5c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_archive_restore_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "history_id",
            sa.Integer(),
            sa.ForeignKey("history.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime()),
        sa.Column("available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_message", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("restored_at", sa.DateTime()),
        sa.UniqueConstraint("history_id", name="uq_media_archive_restore_outbox_history"),
        sa.CheckConstraint(
            "status in ('pending', 'leased', 'retry', 'restored', 'manual_review')",
            name="ck_media_archive_restore_outbox_status",
        ),
    )
    op.create_index(
        "ix_media_archive_restore_outbox_claim",
        "media_archive_restore_outbox",
        ["status", "priority", "available_at", "id"],
    )


def downgrade():
    op.drop_index(
        "ix_media_archive_restore_outbox_claim",
        table_name="media_archive_restore_outbox",
    )
    op.drop_table("media_archive_restore_outbox")
