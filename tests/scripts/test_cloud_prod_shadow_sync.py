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
    assert parser.parse_args([]).seed_r2_shadow_with_copy is False
    assert parser.parse_args(["--seed-r2-shadow-with-copy"]).seed_r2_shadow_with_copy is True


def test_dry_run_plans_commands_without_creating_backup_directory(tmp_path, capsys):
    config = build_config(tmp_path)

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    commands = "\n".join(runner.commands)
    assert "[dry-run]" in output
    assert "pg_dump -Fc --serializable-deferrable" in commands
    assert "postgres:18" in commands
    assert "pg_restore" in commands
    assert '--maintenance-db="$LOCAL_MAINTENANCE_DB"' in commands
    assert "CLOUD_DATABASE_URL" not in commands
    assert "LOCAL_MAINTENANCE_URL" not in commands
    assert "LOCAL_NEXT_DATABASE_URL" not in commands
    assert "rclone sync" in commands
    assert "--backup-dir" in commands
    assert "--entrypoint sh rclone/rclone:latest -lc" in commands
    assert "rclone/rclone:latest sh -lc" not in commands
    assert "rclone delete" not in commands
    assert "--delete-excluded" not in commands
    assert not config.backup_dir.exists()


def test_dry_run_preserves_local_analytics_tables_before_shadow_switch(tmp_path, capsys):
    config = build_config(tmp_path)

    runner = sync.run_shadow_sync(config, execute=False)

    commands = "\n".join(runner.commands)
    assert "local_analytics_tables.txt" in commands
    assert "local_analytics.dump" in commands
    assert "analytics_prompt_%" in commands
    assert "analytics_user_profile_%" in commands
    assert "--table=public.$table_name" in commands
    assert "pg_dump --dbname=\"$SHADOW_DB\"" in commands
    assert "pg_restore --no-owner --no-privileges --dbname=\"$SHADOW_NEXT_DB\"" in commands
    assert commands.index("pg_restore") < commands.index("ALTER DATABASE")


def test_local_analytics_preservation_can_be_disabled(tmp_path, capsys):
    config = build_config(
        tmp_path,
        LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC="false",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    commands = "\n".join(runner.commands)
    assert "local_analytics.dump" not in commands
    assert "analytics_prompt_%" not in commands
    assert "analytics_user_profile_%" not in commands


def test_manifest_records_local_analytics_preservation(tmp_path):
    config = build_config(tmp_path)
    config.backup_dir.mkdir(parents=True)
    (config.backup_dir / "alembic_version.txt").write_text("abc123\n", encoding="utf-8")
    (config.backup_dir / "table_counts.tsv").write_text("users\t10\n", encoding="utf-8")
    (config.backup_dir / "local_analytics_tables.txt").write_text(
        "analytics_prompt_embeddings\nanalytics_prompt_slim_candidates\nanalytics_user_profile_daily_snapshots\n",
        encoding="utf-8",
    )

    sync.write_manifest(config, dump_sha256="fake-sha")

    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    assert manifest["local_analytics_preservation"] == {
        "enabled": True,
        "source_database": "bot_db_prod_shadow",
        "target_database": "bot_db_prod_shadow_next",
        "preserved": True,
        "table_count": 3,
        "tables": [
            "analytics_prompt_embeddings",
            "analytics_prompt_slim_candidates",
            "analytics_user_profile_daily_snapshots",
        ],
    }


def test_initial_r2_shadow_seed_uses_copy_without_quarantine_sync(tmp_path, capsys):
    config = build_config(
        tmp_path,
        R2_SHADOW_SEED_WITH_COPY="true",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    commands = "\n".join(runner.commands)
    assert (
        "rclone copy cloudr2:user-data-prod localminio:user-data-prod-shadow "
        "--no-traverse"
    ) in commands
    assert "rclone sync cloudr2:user-data-prod localminio:user-data-prod-shadow" not in commands
    seed_lines = [
        line
        for line in commands.splitlines()
        if "cloudr2:user-data-prod localminio:user-data-prod-shadow" in line
    ]
    assert seed_lines
    assert all("--backup-dir" not in line for line in seed_lines)


def test_complete_media_sync_copies_shadow_to_complete_without_destructive_sync(
    tmp_path,
    capsys,
):
    config = build_config(
        tmp_path,
        COMPLETE_MEDIA_SYNC_ENABLED="true",
        LOCAL_MINIO_COMPLETE_BUCKET="user-data-complete-shadow",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    commands = "\n".join(runner.commands)
    assert "rclone mkdir localminio:user-data-complete-shadow" in commands
    assert (
        "rclone copy localminio:user-data-prod-shadow "
        "localminio:user-data-complete-shadow"
    ) in commands
    assert (
        "rclone copy cloudr2:user-data-prod localminio:user-data-complete-shadow"
        not in commands
    )
    complete_lines = [
        line for line in commands.splitlines() if "user-data-complete-shadow" in line
    ]
    assert complete_lines
    assert all("rclone sync" not in line for line in complete_lines)
    assert all("--backup-dir" not in line for line in complete_lines)
    assert "--ignore-existing" not in "\n".join(complete_lines)
    assert not config.backup_dir.exists()


def test_long_manual_timestamp_uses_compact_previous_database_name(tmp_path):
    env_file = write_env_file(tmp_path)
    timestamp = "manual_complete_seed_20260625_032920"
    config = sync.build_config(argparse.Namespace(env_file=env_file, timestamp=timestamp))

    expected_digest = hashlib.sha1(timestamp.encode("utf-8")).hexdigest()[:10]
    assert len(config.previous_database_name) <= sync.POSTGRES_IDENTIFIER_MAX_LENGTH
    assert config.previous_database_name.startswith(
        "bot_db_prod_shadow_prev_manual_complete_seed_"
    )
    assert config.previous_database_name.endswith(f"_{expected_digest}")


def test_postgres_tool_image_defaults_to_cloud_prod_major_version(tmp_path):
    config = build_config(tmp_path)

    assert config.postgres_image == "postgres:18"


def test_postgres_tool_image_can_be_overridden_for_tests(tmp_path, capsys):
    config = build_config(tmp_path, SHADOW_SYNC_POSTGRES_IMAGE="postgres:18-alpine")

    runner = sync.run_shadow_sync(config, execute=False)

    assert "postgres:18-alpine" in "\n".join(runner.commands)


def test_dry_run_remote_r2_dump_mode_plans_cloud_dump_transfer_and_cleanup(
    tmp_path,
    capsys,
):
    config = build_config(
        tmp_path,
        CLOUD_PROD_DB_DUMP_MODE="remote_r2",
        CLOUD_PROD_DB_REMOTE_DUMP_SSH_HOST="allbot-do-sgp1-control",
        CLOUD_PROD_DB_REMOTE_ROOT="/home/deploy/APP/All_bot",
        CLOUD_PROD_DB_REMOTE_ENV_FILE="/home/deploy/APP/All_bot/.env.cloud.prod",
        CLOUD_PROD_DB_REMOTE_DUMP_DIR="backups/cloud-prod-shadow",
        CLOUD_PROD_DB_REMOTE_TRANSFER_PREFIX="__shadow-transfer",
        R2_SYNC_HTTP_PROXY="http://127.0.0.1:7890",
        R2_SYNC_HTTPS_PROXY="http://127.0.0.1:7890",
        R2_SYNC_NO_PROXY="127.0.0.1,localhost",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    commands = "\n".join(runner.commands)
    assert "cloud_db_dump_mode" in output
    assert "remote_r2" in output
    assert (
        "ssh -o BatchMode=yes -o ConnectTimeout=20 "
        "allbot-do-sgp1-control bash -s < remote-cloud-dump-script"
    ) in commands
    assert (
        "ssh -o BatchMode=yes -o ConnectTimeout=20 "
        "allbot-do-sgp1-control bash -s < remote-shadow-cleanup-script"
    ) in commands
    assert "cloudr2:user-data-prod/__shadow-transfer/20260624_050000" in commands
    assert "rclone copy cloudr2:user-data-prod/__shadow-transfer/20260624_050000 /backup" in commands
    assert "rclone purge cloudr2:user-data-prod/__shadow-transfer/20260624_050000" in commands
    assert "HTTPS_PROXY=<redacted>" in commands
    assert "HTTP_PROXY=<redacted>" in commands
    assert "NO_PROXY=<redacted>" in commands
    assert "pg_dump -Fc --serializable-deferrable" not in commands
    assert "cloud_password_123" not in output + commands
    assert not config.backup_dir.exists()


def test_database_only_sync_skips_media_buckets_but_keeps_remote_dump_transfer(
    tmp_path,
    capsys,
):
    config = build_config(
        tmp_path,
        CLOUD_PROD_DB_DUMP_MODE="remote_r2",
        CLOUD_PROD_DB_REMOTE_DUMP_SSH_HOST="allbot-do-sgp1-control",
        CLOUD_PROD_DB_REMOTE_ROOT="/home/deploy/APP/All_bot",
        CLOUD_PROD_DB_REMOTE_ENV_FILE="/home/deploy/APP/All_bot/.env.cloud.prod",
        CLOUD_PROD_DB_REMOTE_DUMP_DIR="backups/cloud-prod-shadow",
        CLOUD_PROD_DB_REMOTE_TRANSFER_PREFIX="__shadow-transfer",
        R2_BUCKET_SYNC_ENABLED="false",
        COMPLETE_MEDIA_SYNC_ENABLED="false",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    commands = "\n".join(runner.commands)
    assert "R2 bucket sync skipped: R2_BUCKET_SYNC_ENABLED=false" in output
    assert "Complete media bucket sync skipped: COMPLETE_MEDIA_SYNC_ENABLED=false" in output
    assert "cloudr2:user-data-prod/__shadow-transfer/20260624_050000" in commands
    assert (
        "rclone copy cloudr2:user-data-prod/__shadow-transfer/20260624_050000 /backup"
        in commands
    )
    assert "rclone purge cloudr2:user-data-prod/__shadow-transfer/20260624_050000" in commands
    assert (
        "rclone sync cloudr2:user-data-prod localminio:user-data-prod-shadow"
        not in commands
    )
    assert (
        "rclone copy cloudr2:user-data-prod localminio:user-data-prod-shadow"
        not in commands
    )
    assert "localminio:user-data-complete-shadow" not in commands
    assert not config.backup_dir.exists()


def test_execute_runs_tool_container_commands_and_writes_manifest(tmp_path, monkeypatch):
    config = build_config(tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        rendered = " ".join(cmd)
        if "pg_dump" in rendered and "cloud_prod.dump" in rendered:
            assert "CLOUD_DATABASE_URL" not in kwargs["env"]
            assert kwargs["env"]["PGDATABASE"] == "bot_db_prod"
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


def test_execute_remote_r2_dump_mode_downloads_dump_and_writes_manifest(
    tmp_path,
    monkeypatch,
):
    config = build_config(
        tmp_path,
        CLOUD_PROD_DB_DUMP_MODE="remote_r2",
        CLOUD_PROD_DB_REMOTE_DUMP_SSH_HOST="allbot-do-sgp1-control",
        R2_SYNC_HTTP_PROXY="http://127.0.0.1:7890",
        R2_SYNC_HTTPS_PROXY="http://127.0.0.1:7890",
        R2_SYNC_NO_PROXY="127.0.0.1,localhost",
    )
    calls = []
    ssh_inputs = []
    download_envs = []
    dump_bytes = b"fake remote r2 dump"
    dump_sha = hashlib.sha256(dump_bytes).hexdigest()

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        rendered = " ".join(cmd)
        if cmd[:1] == ["ssh"]:
            ssh_inputs.append(kwargs.get("input", ""))
        if (
            "rclone copy cloudr2:user-data-prod/__shadow-transfer/20260624_050000 /backup"
            in rendered
        ):
            download_envs.append(kwargs["env"])
            config.dump_path.write_bytes(dump_bytes)
            (config.backup_dir / "cloud_prod.dump.sha256").write_text(
                f"{dump_sha}  cloud_prod.dump\n",
                encoding="utf-8",
            )
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

    rendered_commands = "\n".join(runner.commands)
    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    assert calls
    assert len(ssh_inputs) == 2
    assert "pg_dump -Fc --serializable-deferrable" in ssh_inputs[0]
    assert "pg_dump -Fc --serializable-deferrable" not in rendered_commands
    assert "remote-cloud-dump-script" in rendered_commands
    assert "remote-shadow-cleanup-script" in rendered_commands
    assert download_envs[0]["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert manifest["cloud_database_dump_mode"] == "remote_r2"
    assert manifest["cloud_database_remote_dump_host"] == "allbot-do-sgp1-control"
    assert (
        manifest["cloud_database_remote_transfer_prefix"]
        == "__shadow-transfer/20260624_050000"
    )
    assert manifest["dump_sha256"] == dump_sha
    assert manifest["table_counts"]["users"] == 10


def test_existing_matching_checksum_sidecar_is_not_rewritten(tmp_path):
    config = build_config(tmp_path)
    config.backup_dir.mkdir(parents=True)
    dump_bytes = b"fake remote r2 dump"
    dump_sha = hashlib.sha256(dump_bytes).hexdigest()
    config.dump_path.write_bytes(dump_bytes)
    sha_path = config.backup_dir / "cloud_prod.dump.sha256"
    sha_path.write_text(f"{dump_sha}  cloud_prod.dump\n", encoding="utf-8")
    sha_path.chmod(0o444)

    try:
        assert sync.validate_and_write_dump_checksum(config) == dump_sha
        assert sha_path.read_text(encoding="utf-8") == f"{dump_sha}  cloud_prod.dump\n"
    finally:
        sha_path.chmod(0o644)


def test_execute_can_dump_cloud_db_through_ssh_tunnel(tmp_path, monkeypatch):
    config = build_config(
        tmp_path,
        CLOUD_PROD_DB_TUNNEL_SSH_HOST="allbot-do-sgp1-control",
        CLOUD_PROD_DB_TUNNEL_LOCAL_PORT="15432",
    )
    calls = []
    popen_calls = []

    class FakeTunnelProcess:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return self.returncode

        def kill(self):
            self.returncode = -9

    class FakeSocket:
        def close(self):
            pass

    def fake_popen(cmd, **kwargs):
        popen_calls.append((cmd, kwargs))
        return FakeTunnelProcess()

    def fake_create_connection(address, timeout=None):
        assert address == ("127.0.0.1", 15432)
        return FakeSocket()

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        rendered = " ".join(cmd)
        if "pg_dump" in rendered and "cloud_prod.dump" in rendered:
            assert "CLOUD_DATABASE_URL" not in kwargs["env"]
            assert kwargs["env"]["PGHOST"] == "127.0.0.1"
            assert kwargs["env"]["PGPORT"] == "15432"
            assert kwargs["env"]["PGDATABASE"] == "bot_db_prod"
            assert kwargs["env"]["PGSSLMODE"] == "require"
            config.dump_path.write_bytes(b"fake cloud prod dump")
        if "alembic_version.txt" in rendered:
            (config.backup_dir / "alembic_version.txt").write_text("abc123\n", encoding="utf-8")
            (config.backup_dir / "table_counts.tsv").write_text(
                "users\t10\nhistory\t20\norders\t3\nuser_logs\t7\nworker_logs\t4\n",
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(sync.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    monkeypatch.setattr(sync.socket, "create_connection", fake_create_connection)

    runner = sync.run_shadow_sync(config, execute=True)

    assert popen_calls
    ssh_cmd = " ".join(popen_calls[0][0])
    assert "-L 127.0.0.1:15432:cloud-prod-db.example.internal:5432" in ssh_cmd
    assert "allbot-do-sgp1-control" in ssh_cmd
    assert any("ssh -o BatchMode=yes" in command for command in runner.commands)
    assert config.manifest_path.exists()


def test_execute_tunnels_redis_audit_when_ssh_tunnel_is_enabled(tmp_path, monkeypatch):
    config = build_config(
        tmp_path,
        CLOUD_PROD_DB_TUNNEL_SSH_HOST="allbot-do-sgp1-control",
        CLOUD_PROD_DB_TUNNEL_LOCAL_PORT="15432",
        CLOUD_PROD_REDIS_URL="redis://:redis_password_123@redis.example.internal:25061/0",
    )
    redis_urls = []

    class FakeTunnelProcess:
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return self.returncode

        def kill(self):
            self.returncode = -9

    class FakeSocket:
        def close(self):
            pass

    def fake_run(cmd, **kwargs):
        rendered = " ".join(cmd)
        if "pg_dump" in rendered:
            config.dump_path.write_bytes(b"fake cloud prod dump")
        if "alembic_version.txt" in rendered:
            (config.backup_dir / "alembic_version.txt").write_text("abc123\n", encoding="utf-8")
            (config.backup_dir / "table_counts.tsv").write_text(
                "users\t10\nhistory\t20\norders\t3\nuser_logs\t7\nworker_logs\t4\n",
                encoding="utf-8",
            )
        if "redis-cli" in rendered:
            assert "CLOUD_REDIS_URL" not in kwargs["env"]
            redis_urls.append(kwargs["env"])
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(sync.subprocess, "Popen", lambda *args, **kwargs: FakeTunnelProcess())
    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sync.socket,
        "create_connection",
        lambda address, timeout=None: FakeSocket(),
    )

    sync.run_shadow_sync(config, execute=True)

    assert redis_urls
    assert redis_urls[0]["REDIS_HOST"] == "127.0.0.1"
    assert redis_urls[0]["REDIS_PORT"] == "15432"
    assert redis_urls[0]["REDIS_DB"] == "0"
    assert redis_urls[0]["REDISCLI_AUTH"] == "redis_password_123"


def test_postgres_and_redis_passwords_are_not_passed_as_process_arguments(tmp_path, capsys):
    config = build_config(
        tmp_path,
        CLOUD_PROD_REDIS_URL="redis://:redis_password_123@redis.example.internal:25061/0",
    )

    runner = sync.run_shadow_sync(config, execute=False)

    output = capsys.readouterr().out
    rendered = output + "\n".join(runner.commands)
    assert "cloud_password_123" not in rendered
    assert "local_password_456" not in rendered
    assert "redis_password_123" not in rendered
    assert "postgresql://cloud_user" not in rendered
    assert "redis://:" not in rendered
    assert 'pg_dump -Fc --serializable-deferrable --lock-wait-timeout=5s --file=/backup/cloud_prod.dump' in rendered
    assert 'redis-cli $TLS_FLAG -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB"' in rendered


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
        (
            {"CLOUD_PROD_DB_DUMP_MODE": "remote_r2"},
            "REMOTE_DUMP_SSH_HOST is required",
        ),
        (
            {
                "COMPLETE_MEDIA_SYNC_ENABLED": "true",
                "LOCAL_MINIO_COMPLETE_BUCKET": "user-data-prod-shadow",
            },
            "complete media bucket must be different",
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
