"""add support tickets

Revision ID: e7f8a9b0c1d2
Revises: 3e9c7a1b5d24, dc319228d27a
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = ("3e9c7a1b5d24", "dc319228d27a")
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("support_tickets", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("telegram_user_id", sa.BigInteger(), nullable=False), sa.Column("internal_user_id", sa.BigInteger(), nullable=True), sa.Column("category", sa.String(32), nullable=False, server_default="uncategorized"), sa.Column("status", sa.String(32), nullable=False, server_default="open"), sa.Column("username", sa.String(100)), sa.Column("full_name", sa.String(200)), sa.Column("language_code", sa.String(20)), sa.Column("assigned_admin", sa.String(100)), sa.Column("closed_at", sa.DateTime()), sa.Column("last_message_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.CheckConstraint("category in ('recharge', 'bug', 'suggestion', 'uncategorized')", name="ck_support_tickets_category"), sa.CheckConstraint("status in ('open', 'processing', 'resolved', 'closed')", name="ck_support_tickets_status"), sa.ForeignKeyConstraint(["internal_user_id"], ["users.id"], ondelete="SET NULL"))
    op.create_index("ix_support_tickets_telegram_user_id", "support_tickets", ["telegram_user_id"])
    op.create_index("ix_support_tickets_status_last_message", "support_tickets", ["status", "last_message_at"])
    op.create_index("ix_support_tickets_telegram_status", "support_tickets", ["telegram_user_id", "status"])
    op.create_table("support_messages", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("ticket_id", sa.BigInteger(), nullable=False), sa.Column("sender_type", sa.String(16), nullable=False), sa.Column("body", sa.Text()), sa.Column("telegram_message_id", sa.BigInteger()), sa.Column("attachments", sa.JSON(), nullable=False, server_default="[]"), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.CheckConstraint("sender_type in ('user', 'admin', 'internal')", name="ck_support_messages_sender_type"), sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"))
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])
    op.create_index("ix_support_messages_ticket_created", "support_messages", ["ticket_id", "created_at", "id"])

def downgrade():
    op.drop_table("support_messages")
    op.drop_table("support_tickets")
