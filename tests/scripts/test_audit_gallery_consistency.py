from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import audit_gallery_consistency as audit


def _args(**overrides):
    values = {
        "apply": False,
        "backup_confirmed": False,
        "environment": "test",
        "confirm_env": None,
        "confirm_production": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_apply_requires_backup_and_exact_environment_confirmation():
    with pytest.raises(SystemExit, match="backup-confirmed"):
        audit._validate_apply_args(_args(apply=True))
    with pytest.raises(SystemExit, match="confirm-env"):
        audit._validate_apply_args(
            _args(apply=True, backup_confirmed=True, confirm_env="prod")
        )


def test_production_apply_requires_independent_literal_confirmation():
    with pytest.raises(SystemExit, match="confirm-production"):
        audit._validate_apply_args(
            _args(
                apply=True,
                backup_confirmed=True,
                environment="prod",
                confirm_env="prod",
            )
        )


def test_reports_contain_aggregate_evidence_without_database_url(tmp_path):
    counts = {name: 0 for name in audit.AUDIT_SQL}
    payload = {
        "schema_version": 1,
        "environment": "test",
        "applied": False,
        "before": {
            "alembic_revision": "revision-1",
            "gallery_indexes": ["index-1"],
            "counts": counts,
            "consistent": True,
        },
    }

    json_path, md_path = audit._write_reports(tmp_path, payload)

    rendered = json_path.read_text() + md_path.read_text()
    assert "postgresql://" not in rendered
    assert "duplicate_post_groups" in rendered
    assert "user content" in rendered


@pytest.mark.asyncio
async def test_repair_executes_as_separate_postgresql_statements():
    statements = []

    class _Connection:
        async def execute(self, statement):
            statements.append(str(statement))

    await audit._repair(_Connection())

    assert len(statements) >= 10
    assert statements[0].startswith("CREATE TEMP TABLE gallery_post_merge_map")
    assert statements[-1].startswith("UPDATE history histories")


@pytest.mark.asyncio
async def test_audit_transaction_is_read_only_with_statement_timeout(monkeypatch):
    statements = []

    class _Context:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_args):
            return False

    class _Connection:
        dialect = SimpleNamespace(name="postgresql")

        def begin(self):
            return _Context()

        async def execute(self, statement, params=None):
            statements.append((str(statement), params))

    class _Engine:
        def connect(self):
            return _Context()

    connection = _Connection()
    monkeypatch.setattr(audit, "_audit", AsyncMock(return_value={"consistent": True}))

    result = await audit._read_only_audit(
        _Engine(),
        statement_timeout_seconds=45,
    )

    assert result == {"consistent": True}
    assert statements[0][0] == "SET TRANSACTION READ ONLY"
    assert statements[1][1] == {"timeout": "45s"}
