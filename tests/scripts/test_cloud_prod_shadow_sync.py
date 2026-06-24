import argparse
import hashlib
import json
import subprocess

import pytest

from scripts import sync_cloud_prod_to_local_shadow as sync


TIMESTAMP = "20260624_050000"
CLOUD_DB_URL = (
    "postgresql+asyncpg://cloud_user:cloud_password_123@"
    "cloud-prod-db.example.internal:5432/bot_db_prod?sslmode=require"
)
LOCAL_MAINTENANCE_URL = (
    "postgresql://local_admin:local_password_456@127.0.0.1:5432/postgres"
)
R2_ACCESS_VALUE = "r2_access_value_789"
R2_SECRET_VALUE = "r2_secret_value_789"
MINIO_ACCESS_VALUE = "minio_access_value_789"
MINIO_SECRET_VALUE = "minio_secret_value_789"


def write_env_file(tmp_path, **overrides):
    values = {
        "CLOUD_PROD_DATABASE_URL": CLOUD_DB_URL,
        "LOCAL_POSTGRES_MAINTENANCE_URL": LOCAL_MAINTENANCE_URL,
        "SHADOW_DATABASE_NAME": "bot_db_prod_shadow",
        "SHADOW_SYNC_BACKUP_ROOT": str(tmp_path / "backups" / "cloud-prod-shadow"),
        "SHADOW_SYNC_RETENTION_DAYS": "14",
        "R2_ENDPOINT": "https://account-id.r2.cloudflarestorage.com",
        "R2_ACCESS_KEY": R2_ACCESS_VALUE,
        "R2_SECRET_KEY": R2_SECRET_VALUE,
        "R2_BUCKET": "user-data-prod",
        "R2_SYNC_BWLIMIT": "20M",
        "R2_SYNC_TRANSFERS": "4",
        "R2_SYNC_CHECKERS": "8",
        "LOCAL_MINIO_ENDPOINT": "http://127.0.0.1:9000",
        "LOCAL_MINIO_ACCESS_KEY": MINIO_ACCESS_VALUE,
        "LOCAL_MINIO_SECRET_KEY": MINIO_SECRET_VALUE,
        "LOCAL_MINIO_SHADOW_BUCKET": "user-data-prod-shadow",
        "LOCAL_MINIO_QUARANTINE_BUCKET": "user-data-prod-shadow-quarantine",
        "CLOUD_PROD_REDIS_URL": "",
        "CLOUD_PROD_WORKER_REDIS_URL": "",
    }
    values.update(overrides)
    env_file = tmp_path / ".env.cloud-prod-shadow-sync.local"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return env_file


def build_config(tmp_path, **overrides):
    env_file = write_env_file(tmp_path, **overrides)
    return sync.build_config(argparse.Namespace(env_file=env_file, timestamp=TIMESTAMP))


def test_parser_defaults_to_dry_run_and_requires_execute_for_mutation():
    parser = sync.build_parser()

    assert parser.parse_args([]).execute is False
    assert parser.parse_args(["--execute"]).execute is True


def test_dry_run_plans_commands_without_creating_backup_directory(tmp_path, capsys):
    config = build_config(tmp_path)

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    commands = "\n".join(runner.commands)
    assert "[dry-run]" in output
    assert "pg_dump -Fc --serializable-deferrable" in commands
    assert "pg_restore" in commands
    assert "rclone sync" in commands
    assert "--backup-dir" in commands
    assert "--entrypoint sh rclone/rclone:latest -lc" in commands
    assert "rclone/rclone:latest sh -lc" not in commands
    assert "rclone delete" not in commands
    assert "--delete-excluded" not in commands
    assert not config.backup_dir.exists()


def test_execute_runs_tool_container_commands_and_writes_manifest(tmp_path, monkeypatch):
    config = build_config(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        rendered = " ".join(cmd)
        if "pg_dump" in rendered:
            config.dump_path.write_bytes(b"fake cloud prod dump")
        if "alembic_version.txt" in rendered:
            (config.backup_dir / "alembic_version.txt").write_text(
                "abc123\n",
                encoding="utf-8",
            )
            (config.backup_dir / "table_counts.tsv").write_text(
                "users\t10\nhistory\t20\norders\t3\nuser_logs\t7\nworker_logs\t4\n",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    runner = sync.run_shadow_sync(config, execute=True)

    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    assert calls
    assert "pg_dump" in "\n".join(runner.commands)
    assert "pg_restore" in "\n".join(runner.commands)
    assert "rclone sync" in "\n".join(runner.commands)
    assert manifest["dump_sha256"] == hashlib.sha256(b"fake cloud prod dump").hexdigest()
    assert manifest["shadow_database_name"] == "bot_db_prod_shadow"
    assert manifest["table_counts"]["users"] == 10
    assert manifest["redis_audit"] == {"app": False, "worker": False}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SHADOW_DATABASE_NAME": "bot_db"}, "production or maintenance database"),
        (
            {
                "CLOUD_PROD_DATABASE_URL": (
                    "postgresql://cloud_user:cloud_password_123@127.0.0.1:5432/"
                    "bot_db_prod"
                )
            },
            "host and local Postgres host must be different",
        ),
        (
            {"LOCAL_MINIO_ENDPOINT": "https://account-id.r2.cloudflarestorage.com"},
            "local MinIO endpoint must not point",
        ),
        (
            {"LOCAL_MINIO_SHADOW_BUCKET": "user-data-prod"},
            "must not reuse the R2 production bucket name",
        ),
    ],
)
def test_safety_guards_reject_dangerous_targets(tmp_path, overrides, message):
    config = build_config(tmp_path, **overrides)

    with pytest.raises(sync.ShadowSyncError, match=message):
        sync.validate_config(config)


def test_output_redacts_connection_strings_and_keys(tmp_path, capsys):
    config = build_config(tmp_path)

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    rendered = output + "\n".join(runner.commands)
    for secret in (
        "cloud_password_123",
        "local_password_456",
        R2_ACCESS_VALUE,
        R2_SECRET_VALUE,
        MINIO_ACCESS_VALUE,
        MINIO_SECRET_VALUE,
        CLOUD_DB_URL,
        LOCAL_MAINTENANCE_URL,
    ):
        assert secret not in rendered
    assert "<redacted>" in rendered


def test_postgres_urls_are_normalized_for_tooling():
    assert (
        sync.normalize_postgres_url("postgresql+asyncpg://user:pass@db.example/bot_db_prod")
        == "postgresql://user:pass@db.example/bot_db_prod"
    )
