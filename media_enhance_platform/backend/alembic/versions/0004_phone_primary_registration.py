"""Make verified phone numbers the primary registration identity.

Revision ID: 0004_phone_primary_registration
Revises: 0003_phone_verification
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_phone_primary_registration"
down_revision = "0003_phone_verification"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    users_email = next(
        item for item in sa.inspect(bind).get_columns("users") if item["name"] == "email"
    )
    if not users_email["nullable"]:
        op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)

    challenge_columns = _column_names("sms_verification_challenges")
    user_id = next(
        item
        for item in sa.inspect(bind).get_columns("sms_verification_challenges")
        if item["name"] == "user_id"
    )
    if not user_id["nullable"]:
        op.alter_column(
            "sms_verification_challenges",
            "user_id",
            existing_type=sa.String(36),
            nullable=True,
        )
    if "purpose" not in challenge_columns:
        op.add_column(
            "sms_verification_challenges",
            sa.Column(
                "purpose",
                sa.String(24),
                nullable=False,
                server_default="binding",
            ),
        )
    if "requester_ip_hash" not in challenge_columns:
        op.add_column(
            "sms_verification_challenges",
            sa.Column("requester_ip_hash", sa.String(64), nullable=True),
        )

    challenge_indexes = _index_names("sms_verification_challenges")
    purpose_index = op.f("ix_sms_verification_challenges_purpose")
    if purpose_index not in challenge_indexes:
        op.create_index(
            purpose_index,
            "sms_verification_challenges",
            ["purpose"],
        )
    requester_index = op.f("ix_sms_verification_challenges_requester_ip_hash")
    if requester_index not in challenge_indexes:
        op.create_index(
            requester_index,
            "sms_verification_challenges",
            ["requester_ip_hash"],
        )

    tickets_email = next(
        item for item in sa.inspect(bind).get_columns("tickets") if item["name"] == "email"
    )
    if not tickets_email["nullable"]:
        op.alter_column("tickets", "email", existing_type=sa.String(320), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    phone_only_users = bind.scalar(
        sa.text("SELECT COUNT(*) FROM users WHERE email IS NULL")
    )
    phone_only_tickets = bind.scalar(
        sa.text("SELECT COUNT(*) FROM tickets WHERE email IS NULL")
    )
    if phone_only_users or phone_only_tickets:
        raise RuntimeError(
            "cannot downgrade phone-primary registration while phone-only records exist"
        )

    indexes = _index_names("sms_verification_challenges")
    requester_index = op.f("ix_sms_verification_challenges_requester_ip_hash")
    if requester_index in indexes:
        op.drop_index(requester_index, table_name="sms_verification_challenges")
    purpose_index = op.f("ix_sms_verification_challenges_purpose")
    if purpose_index in indexes:
        op.drop_index(purpose_index, table_name="sms_verification_challenges")

    columns = _column_names("sms_verification_challenges")
    if "requester_ip_hash" in columns:
        op.drop_column("sms_verification_challenges", "requester_ip_hash")
    if "purpose" in columns:
        op.drop_column("sms_verification_challenges", "purpose")
    op.alter_column(
        "sms_verification_challenges",
        "user_id",
        existing_type=sa.String(36),
        nullable=False,
    )
    op.alter_column("tickets", "email", existing_type=sa.String(320), nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
