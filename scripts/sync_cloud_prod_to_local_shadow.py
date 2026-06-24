#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence
from urllib.parse import ParseResult, quote, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env.cloud-prod-shadow-sync.local"
DEFAULT_BACKUP_ROOT = ROOT / "backups" / "cloud-prod-shadow"
POSTGRES_IMAGE = "postgres:15"
RCLONE_IMAGE = "rclone/rclone:latest"
REDIS_IMAGE = "redis:7-alpine"
DENIED_TARGET_DATABASES = {"bot_db", "bot_db_prod", "postgres", "template0", "template1"}
SAFE_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
KEY_TABLES = ("users", "history", "orders", "user_logs", "worker_logs")


class ShadowSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShadowSyncConfig:
    cloud_database_url: str
    local_postgres_maintenance_url: str
    shadow_database_name: str
    r2_endpoint: str
    r2_access_key: str
    r2_secret_key: str
    r2_bucket: str
    local_minio_endpoint: str
    local_minio_access_key: str
    local_minio_secret_key: str
    local_minio_shadow_bucket: str
    local_minio_quarantine_bucket: str
    backup_root: Path
    timestamp: str
    r2_bwlimit: str
    r2_transfers: int
    r2_checkers: int
    retention_days: int
    cloud_redis_url: str | None = None
    cloud_worker_redis_url: str | None = None

    @property
    def backup_dir(self) -> Path:
        return self.backup_root / self.timestamp

    @property
    def dump_path(self) -> Path:
        return self.backup_dir / "cloud_prod.dump"

    @property
    def manifest_path(self) -> Path:
        return self.backup_dir / "manifest.json"

    @property
    def next_database_name(self) -> str:
        return f"{self.shadow_database_name}_next"

    @property
    def previous_database_name(self) -> str:
        return f"{self.shadow_database_name}_previous_{self.timestamp}"

    @property
    def normalized_cloud_database_url(self) -> str:
        return normalize_postgres_url(self.cloud_database_url)

    @property
    def normalized_local_maintenance_url(self) -> str:
        return normalize_postgres_url(self.local_postgres_maintenance_url)

    @property
    def local_next_database_url(self) -> str:
        return replace_database_name(
            self.normalized_local_maintenance_url,
            self.next_database_name,
        )


class Redactor:
    def __init__(self, values: Sequence[str]) -> None:
        self.values = sorted({value for value in values if value}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        redacted = text
        for value in self.values:
            redacted = redacted.replace(value, "<redacted>")
        redacted = re.sub(
            r"(postgres(?:ql)?(?:\+\w+)?://)([^:@/\s]+):([^@/\s]+)@",
            r"\1<user>:<redacted>@",
            redacted,
        )
        redacted = re.sub(
            r"(redis://:)([^@/\s]+)@",
            r"\1<redacted>@",
            redacted,
        )
        return redacted


class CommandRunner:
    def __init__(self, *, execute: bool, redactor: Redactor) -> None:
        self.execute = execute
        self.redactor = redactor
        self.commands: list[str] = []

    def run(
        self,
        cmd: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        capture_output: bool = False,
    ) -> str:
        rendered = self._render(cmd, env=env)
        self.commands.append(rendered)
        if not self.execute:
            print(f"[dry-run] {rendered}")
            return ""
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        completed = subprocess.run(
            list(cmd),
            env=process_env,
            check=True,
            text=True,
            capture_output=capture_output,
        )
        return completed.stdout if capture_output else ""

    def _render(self, cmd: Sequence[str], *, env: dict[str, str] | None) -> str:
        env_prefix = ""
        if env:
            env_prefix = " ".join(f"{key}=<redacted>" for key in sorted(env)) + " "
        rendered = env_prefix + " ".join(shlex.quote(part) for part in cmd)
        return self.redactor.redact(rendered)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def merged_env_file_values(path: Path) -> dict[str, str]:
    values = load_env_file(path)
    for key, value in os.environ.items():
        values.setdefault(key, value)
    return values


def require(values: dict[str, str], key: str) -> str:
    value = values.get(key)
    if value is None or value == "":
        raise ShadowSyncError(f"missing required env key: {key}")
    return value


def optional(values: dict[str, str], key: str) -> str | None:
    value = values.get(key)
    return value if value else None


def int_value(values: dict[str, str], key: str, default: int) -> int:
    raw = values.get(key, str(default))
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ShadowSyncError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise ShadowSyncError(f"{key} must be positive")
    return parsed


def build_config(args: argparse.Namespace) -> ShadowSyncConfig:
    values = merged_env_file_values(args.env_file)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = Path(values.get("SHADOW_SYNC_BACKUP_ROOT", str(DEFAULT_BACKUP_ROOT)))
    return ShadowSyncConfig(
        cloud_database_url=require(values, "CLOUD_PROD_DATABASE_URL"),
        local_postgres_maintenance_url=require(values, "LOCAL_POSTGRES_MAINTENANCE_URL"),
        shadow_database_name=values.get("SHADOW_DATABASE_NAME", "bot_db_prod_shadow"),
        r2_endpoint=require(values, "R2_ENDPOINT"),
        r2_access_key=require(values, "R2_ACCESS_KEY"),
        r2_secret_key=require(values, "R2_SECRET_KEY"),
        r2_bucket=values.get("R2_BUCKET", "user-data-prod"),
        local_minio_endpoint=require(values, "LOCAL_MINIO_ENDPOINT"),
        local_minio_access_key=require(values, "LOCAL_MINIO_ACCESS_KEY"),
        local_minio_secret_key=require(values, "LOCAL_MINIO_SECRET_KEY"),
        local_minio_shadow_bucket=values.get(
            "LOCAL_MINIO_SHADOW_BUCKET",
            "user-data-prod-shadow",
        ),
        local_minio_quarantine_bucket=values.get(
            "LOCAL_MINIO_QUARANTINE_BUCKET",
            "user-data-prod-shadow-quarantine",
        ),
        backup_root=backup_root,
        timestamp=timestamp,
        r2_bwlimit=values.get("R2_SYNC_BWLIMIT", "20M"),
        r2_transfers=int_value(values, "R2_SYNC_TRANSFERS", 4),
        r2_checkers=int_value(values, "R2_SYNC_CHECKERS", 8),
        retention_days=int_value(values, "SHADOW_SYNC_RETENTION_DAYS", 14),
        cloud_redis_url=optional(values, "CLOUD_PROD_REDIS_URL"),
        cloud_worker_redis_url=optional(values, "CLOUD_PROD_WORKER_REDIS_URL"),
    )


def normalize_postgres_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme
    if scheme.startswith("postgresql+"):
        scheme = "postgresql"
    elif scheme == "postgres":
        scheme = "postgresql"
    return urlunparse(parsed._replace(scheme=scheme))


def replace_database_name(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/" + quote(database_name)))


def parsed_url(url: str) -> ParseResult:
    parsed = urlparse(url)
    if not parsed.scheme:
        raise ShadowSyncError(f"invalid URL: {url}")
    return parsed


def database_name_from_url(url: str) -> str:
    parsed = parsed_url(url)
    return parsed.path.lstrip("/").split("/", 1)[0]


def normalized_host(url_or_endpoint: str) -> str:
    parsed = urlparse(url_or_endpoint)
    if parsed.hostname:
        return parsed.hostname.lower()
    without_scheme = url_or_endpoint.split("://", 1)[-1]
    return without_scheme.split("/", 1)[0].split(":", 1)[0].lower()


def validate_database_name(name: str, *, label: str) -> None:
    if not SAFE_DB_NAME_RE.match(name):
        raise ShadowSyncError(f"{label} must contain only letters, numbers, and underscores")
    if name in DENIED_TARGET_DATABASES:
        raise ShadowSyncError(f"{label} may not be production or maintenance database: {name}")


def validate_config(config: ShadowSyncConfig) -> None:
    validate_database_name(config.shadow_database_name, label="SHADOW_DATABASE_NAME")
    validate_database_name(config.next_database_name, label="shadow next database")
    validate_database_name(config.previous_database_name, label="shadow previous database")

    cloud_db = database_name_from_url(config.normalized_cloud_database_url)
    local_maintenance_db = database_name_from_url(config.normalized_local_maintenance_url)
    if config.shadow_database_name in {cloud_db, local_maintenance_db}:
        raise ShadowSyncError("shadow database must not equal cloud or maintenance database")
    if config.next_database_name in {cloud_db, local_maintenance_db}:
        raise ShadowSyncError("shadow next database must not equal cloud or maintenance database")
    if normalized_host(config.normalized_cloud_database_url) == normalized_host(
        config.normalized_local_maintenance_url
    ):
        raise ShadowSyncError("cloud DB host and local Postgres host must be different")

    r2_host = normalized_host(config.r2_endpoint)
    local_minio_host = normalized_host(config.local_minio_endpoint)
    if r2_host == local_minio_host or "cloudflarestorage.com" in local_minio_host:
        raise ShadowSyncError("local MinIO endpoint must not point to the cloud R2 endpoint")
    if config.r2_bucket == config.local_minio_shadow_bucket:
        raise ShadowSyncError("local shadow bucket must not reuse the R2 production bucket name")
    if config.local_minio_shadow_bucket == config.local_minio_quarantine_bucket:
        raise ShadowSyncError("shadow and quarantine buckets must be different")


def redactor_for_config(config: ShadowSyncConfig) -> Redactor:
    sensitive_values = [
        config.cloud_database_url,
        config.normalized_cloud_database_url,
        config.local_postgres_maintenance_url,
        config.normalized_local_maintenance_url,
        config.local_next_database_url,
        config.r2_access_key,
        config.r2_secret_key,
        config.local_minio_access_key,
        config.local_minio_secret_key,
        config.cloud_redis_url or "",
        config.cloud_worker_redis_url or "",
    ]
    return Redactor(sensitive_values)


def docker_cmd(
    image: str,
    script: str,
    *,
    backup_dir: Path | None = None,
    env_keys: Sequence[str] = (),
    entrypoint: str | None = None,
) -> list[str]:
    cmd = ["docker", "run", "--rm", "--network", "host"]
    if backup_dir is not None:
        cmd.extend(["-v", f"{backup_dir.resolve()}:/backup"])
    for key in env_keys:
        cmd.extend(["-e", key])
    if entrypoint:
        cmd.extend(["--entrypoint", entrypoint])
        cmd.extend([image, "-lc", script])
    else:
        cmd.extend([image, "sh", "-lc", script])
    return cmd


def postgres_env(config: ShadowSyncConfig) -> dict[str, str]:
    return {
        "CLOUD_DATABASE_URL": config.normalized_cloud_database_url,
        "LOCAL_MAINTENANCE_URL": config.normalized_local_maintenance_url,
        "LOCAL_NEXT_DATABASE_URL": config.local_next_database_url,
        "SHADOW_DB": config.shadow_database_name,
        "SHADOW_NEXT_DB": config.next_database_name,
        "SHADOW_PREVIOUS_DB": config.previous_database_name,
    }


def rclone_env(config: ShadowSyncConfig) -> dict[str, str]:
    return {
        "RCLONE_CONFIG_CLOUDR2_TYPE": "s3",
        "RCLONE_CONFIG_CLOUDR2_PROVIDER": "Cloudflare",
        "RCLONE_CONFIG_CLOUDR2_ACCESS_KEY_ID": config.r2_access_key,
        "RCLONE_CONFIG_CLOUDR2_SECRET_ACCESS_KEY": config.r2_secret_key,
        "RCLONE_CONFIG_CLOUDR2_ENDPOINT": config.r2_endpoint,
        "RCLONE_CONFIG_LOCALMINIO_TYPE": "s3",
        "RCLONE_CONFIG_LOCALMINIO_PROVIDER": "Minio",
        "RCLONE_CONFIG_LOCALMINIO_ACCESS_KEY_ID": config.local_minio_access_key,
        "RCLONE_CONFIG_LOCALMINIO_SECRET_ACCESS_KEY": config.local_minio_secret_key,
        "RCLONE_CONFIG_LOCALMINIO_ENDPOINT": config.local_minio_endpoint,
        "RCLONE_CONFIG_LOCALMINIO_FORCE_PATH_STYLE": "true",
    }


def redis_env(url: str) -> dict[str, str]:
    return {"CLOUD_REDIS_URL": url}


def run_db_dump(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    script = (
        'pg_dump -Fc --serializable-deferrable --lock-wait-timeout=5s '
        '--file=/backup/cloud_prod.dump "$CLOUD_DATABASE_URL"'
    )
    runner.run(
        docker_cmd(
            POSTGRES_IMAGE,
            script,
            backup_dir=config.backup_dir,
            env_keys=("CLOUD_DATABASE_URL",),
        ),
        env={"CLOUD_DATABASE_URL": config.normalized_cloud_database_url},
    )


def run_db_restore_to_next(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    script = "\n".join(
        [
            "set -eu",
            'dropdb --if-exists --force --dbname="$LOCAL_MAINTENANCE_URL" "$SHADOW_NEXT_DB"',
            'createdb --dbname="$LOCAL_MAINTENANCE_URL" "$SHADOW_NEXT_DB"',
            'pg_restore --no-owner --no-privileges --dbname="$LOCAL_NEXT_DATABASE_URL" /backup/cloud_prod.dump',
        ]
    )
    runner.run(
        docker_cmd(
            POSTGRES_IMAGE,
            script,
            backup_dir=config.backup_dir,
            env_keys=(
                "LOCAL_MAINTENANCE_URL",
                "LOCAL_NEXT_DATABASE_URL",
                "SHADOW_NEXT_DB",
            ),
        ),
        env=postgres_env(config),
    )


def run_db_validation(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    table_sql = " UNION ALL ".join(
        f"SELECT '{table}' AS table_name, count(*)::text AS row_count FROM {table}"
        for table in KEY_TABLES
    )
    script = "\n".join(
        [
            "set -eu",
            'psql "$LOCAL_NEXT_DATABASE_URL" -v ON_ERROR_STOP=1 -At '
            "-c 'select version_num from alembic_version order by version_num limit 1' "
            "> /backup/alembic_version.txt",
            "test -s /backup/alembic_version.txt",
            'psql "$LOCAL_NEXT_DATABASE_URL" -v ON_ERROR_STOP=1 -At -F "$(printf \'\\t\')" '
            f"-c {shlex.quote(table_sql)} > /backup/table_counts.tsv",
        ]
    )
    runner.run(
        docker_cmd(
            POSTGRES_IMAGE,
            script,
            backup_dir=config.backup_dir,
            env_keys=("LOCAL_NEXT_DATABASE_URL",),
        ),
        env=postgres_env(config),
    )


def run_db_atomic_switch(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    terminate_sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname IN ('$SHADOW_DB', '$SHADOW_NEXT_DB') AND pid <> pg_backend_pid();"
    )
    script = "\n".join(
        [
            "set -eu",
            "RENAMED_CURRENT=0",
            "db_exists() {",
            '  psql "$LOCAL_MAINTENANCE_URL" -At -c "SELECT 1 FROM pg_database WHERE datname = \'$1\'" | grep -qx 1',
            "}",
            f'psql "$LOCAL_MAINTENANCE_URL" -v ON_ERROR_STOP=1 -c "{terminate_sql}" >/dev/null',
            'if db_exists "$SHADOW_PREVIOUS_DB"; then',
            '  dropdb --force --dbname="$LOCAL_MAINTENANCE_URL" "$SHADOW_PREVIOUS_DB"',
            "fi",
            'if db_exists "$SHADOW_DB"; then',
            '  psql "$LOCAL_MAINTENANCE_URL" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_DB\\" RENAME TO \\"$SHADOW_PREVIOUS_DB\\""',
            "  RENAMED_CURRENT=1",
            "fi",
            'if ! psql "$LOCAL_MAINTENANCE_URL" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_NEXT_DB\\" RENAME TO \\"$SHADOW_DB\\""; then',
            '  if [ "$RENAMED_CURRENT" = "1" ] && ! db_exists "$SHADOW_DB" && db_exists "$SHADOW_PREVIOUS_DB"; then',
            '    psql "$LOCAL_MAINTENANCE_URL" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_PREVIOUS_DB\\" RENAME TO \\"$SHADOW_DB\\"" || true',
            "  fi",
            "  exit 1",
            "fi",
        ]
    )
    runner.run(
        docker_cmd(
            POSTGRES_IMAGE,
            script,
            env_keys=(
                "LOCAL_MAINTENANCE_URL",
                "SHADOW_DB",
                "SHADOW_NEXT_DB",
                "SHADOW_PREVIOUS_DB",
            ),
        ),
        env=postgres_env(config),
    )


def run_r2_sync(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    script = "\n".join(
        [
            "set -eu",
            f"rclone mkdir localminio:{shlex.quote(config.local_minio_shadow_bucket)}",
            f"rclone mkdir localminio:{shlex.quote(config.local_minio_quarantine_bucket)}",
            "rclone sync "
            f"cloudr2:{shlex.quote(config.r2_bucket)} "
            f"localminio:{shlex.quote(config.local_minio_shadow_bucket)} "
            f"--backup-dir localminio:{shlex.quote(config.local_minio_quarantine_bucket)}/{shlex.quote(config.timestamp)} "
            f"--transfers {config.r2_transfers} "
            f"--checkers {config.r2_checkers} "
            f"--bwlimit {shlex.quote(config.r2_bwlimit)} "
            "--fast-list --stats 60s",
        ]
    )
    runner.run(
        docker_cmd(
            RCLONE_IMAGE,
            script,
            env_keys=tuple(rclone_env(config).keys()),
            entrypoint="sh",
        ),
        env=rclone_env(config),
    )


def run_redis_audit(
    config: ShadowSyncConfig,
    runner: CommandRunner,
    *,
    url: str | None,
    label: str,
) -> None:
    if not url:
        print(f"Redis audit skipped for {label}: URL not configured")
        return
    safe_label = re.sub(r"[^A-Za-z0-9_]", "_", label)
    script = "\n".join(
        [
            "set -eu",
            f'redis-cli -u "$CLOUD_REDIS_URL" INFO memory > "/backup/redis_{safe_label}_memory.txt"',
            f'redis-cli -u "$CLOUD_REDIS_URL" DBSIZE > "/backup/redis_{safe_label}_dbsize.txt"',
        ]
    )
    runner.run(
        docker_cmd(
            REDIS_IMAGE,
            script,
            backup_dir=config.backup_dir,
            env_keys=("CLOUD_REDIS_URL",),
        ),
        env=redis_env(url),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_table_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        table, count = line.split("\t", 1)
        counts[table] = int(count)
    return counts


def write_manifest(config: ShadowSyncConfig, *, dump_sha256: str) -> None:
    manifest = {
        "timestamp": config.timestamp,
        "cloud_database_host": normalized_host(config.normalized_cloud_database_url),
        "cloud_database_name": database_name_from_url(config.normalized_cloud_database_url),
        "shadow_database_name": config.shadow_database_name,
        "previous_database_name": config.previous_database_name,
        "r2_bucket": config.r2_bucket,
        "local_minio_shadow_bucket": config.local_minio_shadow_bucket,
        "local_minio_quarantine_bucket": config.local_minio_quarantine_bucket,
        "dump_sha256": dump_sha256,
        "dump_file": str(config.dump_path),
        "alembic_version": (
            (config.backup_dir / "alembic_version.txt").read_text(encoding="utf-8").strip()
            if (config.backup_dir / "alembic_version.txt").exists()
            else None
        ),
        "table_counts": read_table_counts(config.backup_dir / "table_counts.tsv"),
        "retention_days": config.retention_days,
        "redis_audit": {
            "app": bool(config.cloud_redis_url),
            "worker": bool(config.cloud_worker_redis_url),
        },
    }
    config.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def maybe_prepare_backup_dir(config: ShadowSyncConfig, *, execute: bool) -> None:
    if not execute:
        print(f"[dry-run] Would create backup directory: {config.backup_dir}")
        return
    config.backup_dir.mkdir(parents=True, exist_ok=False)


def prune_old_backups(config: ShadowSyncConfig, *, execute: bool) -> None:
    if not config.backup_root.exists():
        return
    cutoff = time.time() - config.retention_days * 24 * 60 * 60
    for child in sorted(config.backup_root.iterdir()):
        if child == config.backup_dir or not child.is_dir() or child.is_symlink():
            continue
        if child.stat().st_mtime >= cutoff:
            continue
        if execute:
            shutil.rmtree(child)
            print(f"Pruned old backup directory: {child}")
        else:
            print(f"[dry-run] Would prune old backup directory: {child}")


def log_preflight(config: ShadowSyncConfig, *, execute: bool) -> None:
    free_bytes = shutil.disk_usage(config.backup_root.parent if config.backup_root.parent.exists() else ROOT).free
    print(
        json.dumps(
            {
                "mode": "execute" if execute else "dry-run",
                "timestamp": config.timestamp,
                "backup_dir": str(config.backup_dir),
                "cloud_db_host": normalized_host(config.normalized_cloud_database_url),
                "cloud_db_name": database_name_from_url(config.normalized_cloud_database_url),
                "shadow_db": config.shadow_database_name,
                "r2_bucket": config.r2_bucket,
                "local_shadow_bucket": config.local_minio_shadow_bucket,
                "local_quarantine_bucket": config.local_minio_quarantine_bucket,
                "backup_parent_free_gib": round(free_bytes / 1024 / 1024 / 1024, 2),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_shadow_sync(config: ShadowSyncConfig, *, execute: bool) -> CommandRunner:
    validate_config(config)
    runner = CommandRunner(execute=execute, redactor=redactor_for_config(config))
    log_preflight(config, execute=execute)
    maybe_prepare_backup_dir(config, execute=execute)

    run_db_dump(config, runner)
    dump_sha = "<dry-run>"
    if execute:
        dump_sha = sha256_file(config.dump_path)
        (config.backup_dir / "cloud_prod.dump.sha256").write_text(
            f"{dump_sha}  {config.dump_path.name}\n",
            encoding="utf-8",
        )

    run_db_restore_to_next(config, runner)
    run_db_validation(config, runner)
    run_db_atomic_switch(config, runner)
    run_r2_sync(config, runner)
    run_redis_audit(config, runner, url=config.cloud_redis_url, label="app")
    run_redis_audit(config, runner, url=config.cloud_worker_redis_url, label="worker")

    if execute:
        write_manifest(config, dump_sha256=dump_sha)
        print(f"Manifest written: {config.manifest_path}")
    else:
        print("[dry-run] Would write manifest with dump sha256 and validation counts")
    prune_old_backups(config, execute=execute)
    return runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync cloud production PostgreSQL/R2 into local shadow copies.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"ignored env file with sync credentials (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform real Docker/database/object-storage operations; default is dry-run",
    )
    parser.add_argument(
        "--timestamp",
        help="override timestamp for tests or one-off recovery runs",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = build_config(args)
        run_shadow_sync(config, execute=args.execute)
    except ShadowSyncError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
