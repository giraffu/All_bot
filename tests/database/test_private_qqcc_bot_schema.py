import importlib.util
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, JSON, String, Text


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "3e9c7a1b5d24_add_private_qqcc_bots.py"
)


def _server_default(column) -> str | None:
    if column.server_default is None:
        return None
    return str(column.server_default.arg)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "private_qqcc_bot_schema_migration",
        MIGRATION_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_private_qqcc_bot_model_enforces_identity_credentials_and_runtime_state():
    from src.database.models import PrivateQqccBot

    table = PrivateQqccBot.__table__
    columns = table.c

    assert table.name == "private_qqcc_bots"
    assert isinstance(columns.id.type, BigInteger)
    assert columns.id.primary_key is True
    assert columns.id.autoincrement is True

    assert isinstance(columns.owner_user_id.type, BigInteger)
    assert columns.owner_user_id.nullable is False
    assert {fk.target_fullname for fk in columns.owner_user_id.foreign_keys} == {"users.id"}
    assert isinstance(columns.telegram_bot_id.type, BigInteger)
    assert columns.telegram_bot_id.nullable is False

    unique_indexes = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
        if index.unique
    }
    assert ("owner_user_id",) in unique_indexes
    assert ("telegram_bot_id",) in unique_indexes

    assert isinstance(columns.telegram_username.type, String)
    assert columns.telegram_username.type.length == 64
    assert isinstance(columns.telegram_display_name.type, String)
    assert columns.telegram_display_name.type.length == 255
    assert isinstance(columns.token_ciphertext.type, Text)
    assert columns.token_ciphertext.nullable is False
    assert columns.token_fingerprint.unique is True
    assert columns.webhook_public_id.unique is True
    assert columns.webhook_secret_hash.nullable is True

    assert isinstance(columns.token_key_version.type, Integer)
    assert _server_default(columns.token_key_version) == "1"
    assert isinstance(columns.config.type, JSON)
    assert _server_default(columns.config) == "'{}'::json"
    assert _server_default(columns.config_version) == "1"
    assert isinstance(columns.owner_enabled.type, Boolean)
    assert _server_default(columns.owner_enabled) == "true"
    assert _server_default(columns.admin_enabled) == "true"
    assert _server_default(columns.runtime_status) == "'provisioning'"

    runtime_checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "runtime_status in ('provisioning', 'active', 'paused', 'disabled', 'error')" in runtime_checks

    for timestamp in ("last_webhook_at", "last_update_at", "created_at", "updated_at"):
        assert isinstance(columns[timestamp].type, DateTime)


def test_private_qqcc_bot_audit_model_survives_unlink_and_restricts_actor_type():
    from src.database.models import PrivateQqccBotAuditLog

    table = PrivateQqccBotAuditLog.__table__
    columns = table.c

    assert table.name == "private_qqcc_bot_audit_logs"
    assert isinstance(columns.id.type, BigInteger)
    assert columns.private_bot_id.nullable is True
    foreign_key = next(iter(columns.private_bot_id.foreign_keys))
    assert foreign_key.target_fullname == "private_qqcc_bots.id"
    assert foreign_key.ondelete == "SET NULL"
    assert columns.owner_user_id.nullable is False
    assert columns.telegram_bot_id.nullable is False
    assert any(
        tuple(column.name for column in index.columns) == ("private_bot_id",)
        for index in table.indexes
    )

    assert columns.actor_type.nullable is False
    assert columns.actor_identifier.type.length == 128
    assert columns.actor_identifier.nullable is True
    assert columns.action.type.length == 64
    assert columns.action.nullable is False
    assert columns.before_status.nullable is True
    assert columns.after_status.nullable is True
    assert isinstance(columns.details.type, JSON)
    assert columns.details.nullable is False
    assert _server_default(columns.details) == "'{}'::json"

    actor_checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "actor_type in ('owner', 'admin', 'system')" in actor_checks


def test_private_bot_submission_ledger_has_persistent_unique_outcome_contract():
    from src.database.models import PrivateBotTaskSubmission

    table = PrivateBotTaskSubmission.__table__
    columns = table.c

    assert table.name == "private_bot_task_submissions"
    assert columns.submission_key.type.length == 128
    assert columns.submission_key.nullable is False
    assert columns.registry_task_id.type.length == 64
    assert columns.dispatch_task_id.type.length == 64
    assert columns.dispatch_task_id.nullable is False
    assert columns.dispatch_started_at.nullable is True
    assert columns.submission_owner_token.type.length == 64
    assert columns.submission_owner_deadline_at.nullable is True
    assert columns.reconcile_not_before_at.nullable is True
    assert _server_default(columns.submission_owner_fence) == "0"
    assert columns.request_sha256.type.length == 64
    assert columns.private_bot_id.nullable is False
    assert columns.update_id.nullable is False
    assert columns.submission_sequence.nullable is False
    assert columns.actual_cost.nullable is True
    assert columns.debit_confirmed_at.nullable is True
    assert _server_default(columns.compensation_status) == "'not_required'"
    assert columns.compensation_lease_token.type.length == 64
    assert columns.compensation_attempts.nullable is False
    assert _server_default(columns.compensation_attempts) == "0"
    assert isinstance(columns.saved_inputs.type, JSON)
    assert _server_default(columns.saved_inputs) == "'[]'::json"
    unique_constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if getattr(constraint, "unique", None) is True
        or constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("submission_key",) in unique_constraints
    assert ("registry_task_id",) in unique_constraints
    index_columns = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert (
        "status",
        "reconcile_not_before_at",
        "id",
    ) in index_columns
    assert (
        "compensation_status",
        "compensation_lease_until",
        "id",
    ) in index_columns
    assert (
        "status",
        "compensation_status",
        "updated_at",
        "id",
    ) in index_columns
    status_checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert (
        "status in ('reserved', 'dispatching', 'submitted', 'failed')"
        in status_checks
    )
    assert (
        "compensation_status in ('not_required', 'pending', 'processing', 'completed')"
        in status_checks
    )


def test_private_qqcc_bot_migration_is_single_head_and_has_complete_downgrade(monkeypatch):
    module = _load_migration_module()
    created_tables: list[str] = []
    created_indexes: list[tuple[str, str, tuple[str, ...], bool]] = []
    dropped_indexes: list[tuple[str, str | None]] = []
    dropped_tables: list[str] = []

    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda name, *args, **kwargs: created_tables.append(name),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda name, table_name, columns, unique=False, **kwargs: created_indexes.append(
            (name, table_name, tuple(columns), unique)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "drop_index",
        lambda name, table_name=None, **kwargs: dropped_indexes.append((name, table_name)),
    )
    monkeypatch.setattr(module.op, "drop_table", dropped_tables.append)

    module.upgrade()
    module.downgrade()

    assert module.down_revision == "2d8b6f1a9c03"
    assert created_tables == [
        "private_qqcc_bots",
        "private_qqcc_bot_audit_logs",
        "private_bot_task_submissions",
    ]
    assert {
        (table_name, columns, unique)
        for _, table_name, columns, unique in created_indexes
    } == {
        ("private_qqcc_bots", ("owner_user_id",), True),
        ("private_qqcc_bots", ("telegram_bot_id",), True),
        ("private_qqcc_bot_audit_logs", ("private_bot_id",), False),
        ("private_qqcc_bot_audit_logs", ("owner_user_id",), False),
        ("private_qqcc_bot_audit_logs", ("telegram_bot_id",), False),
        ("private_bot_task_submissions", ("private_bot_id",), False),
        ("private_bot_task_submissions", ("internal_user_id",), False),
        (
            "private_bot_task_submissions",
            ("status", "reconcile_not_before_at", "id"),
            False,
        ),
        (
            "private_bot_task_submissions",
            ("compensation_status", "compensation_lease_until", "id"),
            False,
        ),
        (
            "private_bot_task_submissions",
            ("status", "compensation_status", "updated_at", "id"),
            False,
        ),
    }
    assert {name for name, _ in dropped_indexes} == {
        name for name, _, _, _ in created_indexes
    }
    assert dropped_tables == [
        "private_bot_task_submissions",
        "private_qqcc_bot_audit_logs",
        "private_qqcc_bots",
    ]
