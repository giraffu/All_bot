"""harden media archive priority, source receipts, and claim index

Revision ID: b7d9e1f3a5c2
Revises: a4c8e2f6b901
"""

from alembic import op
import sqlalchemy as sa


revision = "b7d9e1f3a5c2"
down_revision = "a4c8e2f6b901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "media_archive_outbox",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="20"),
    )
    op.add_column(
        "media_archive_receipts", sa.Column("found_source", sa.String(128))
    )
    op.add_column("media_archive_receipts", sa.Column("source_key", sa.Text()))
    op.execute(
        "update media_archive_receipts set found_source='legacy-receipt', "
        "source_key=source_ref where found_source is null or source_key is null"
    )
    op.alter_column("media_archive_receipts", "found_source", nullable=False)
    op.alter_column("media_archive_receipts", "source_key", nullable=False)
    op.drop_index("ix_media_archive_outbox_claim", table_name="media_archive_outbox")
    op.create_index(
        "ix_media_archive_outbox_claim",
        "media_archive_outbox",
        ["status", "priority", "available_at", "id"],
    )


def downgrade():
    op.drop_index("ix_media_archive_outbox_claim", table_name="media_archive_outbox")
    op.create_index(
        "ix_media_archive_outbox_claim",
        "media_archive_outbox",
        ["status", "available_at", "id"],
    )
    op.drop_column("media_archive_receipts", "source_key")
    op.drop_column("media_archive_receipts", "found_source")
    op.drop_column("media_archive_outbox", "priority")
