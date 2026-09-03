#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence
from urllib.parse import ParseResult, parse_qs, quote, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT / ".env.cloud-prod-shadow-sync.local"
DEFAULT_BACKUP_ROOT = ROOT / "backups" / "cloud-prod-shadow"
DEFAULT_POSTGRES_IMAGE = "postgres:18"
RCLONE_IMAGE = "rclone/rclone:latest"
REDIS_IMAGE = "redis:7-alpine"
DENIED_TARGET_DATABASES = {"bot_db", "bot_db_prod", "postgres", "template0", "template1"}
SAFE_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
POSTGRES_IDENTIFIER_MAX_LENGTH = 63
PREVIOUS_DB_HASH_CHARS = 10
KEY_TABLES = ("users", "history", "orders", "user_logs", "worker_logs")
LOCAL_ANALYTICS_TABLE_LIKE_PATTERNS = (
    "analytics_prompt_%",
    "analytics_user_profile_%",
    "analytics_media_%",
    "analytics_history_media_%",
    "analytics_snapshot_backup_%",
)
LOCAL_ANALYTICS_TABLE_LIST_FILE = "local_analytics_tables.txt"
LOCAL_ANALYTICS_DUMP_FILE = "local_analytics.dump"


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
    r2_bucket_sync_enabled: bool = True
    r2_shadow_seed_with_copy: bool = False
    complete_media_sync_enabled: bool = False
    local_minio_complete_bucket: str = "user-data-complete-shadow"
    cloud_redis_url: str | None = None
    cloud_worker_redis_url: str | None = None
    cloud_db_tunnel_ssh_host: str | None = None
    cloud_db_tunnel_local_host: str = "127.0.0.1"
    cloud_db_tunnel_local_port: int = 0
    cloud_db_tunnel_connect_timeout_seconds: int = 20
    postgres_image: str = DEFAULT_POSTGRES_IMAGE
    cloud_db_dump_mode: str = "local_tunnel"
    cloud_db_remote_dump_ssh_host: str | None = None
    cloud_db_remote_root: str = "/home/deploy/APP/All_bot"
    cloud_db_remote_env_file: str = "/home/deploy/APP/All_bot/.env.cloud.prod"
    cloud_db_remote_dump_dir: str = "backups/cloud-prod-shadow"
    cloud_db_remote_transfer_prefix: str = "__shadow-transfer"
    r2_http_proxy: str | None = None
    r2_https_proxy: str | None = None
    r2_no_proxy: str | None = None
    local_analytics_preserve_on_shadow_sync: bool = True

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
        return previous_database_name_for(self.shadow_database_name, self.timestamp)

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
        input_text: str | None = None,
        input_label: str | None = None,
    ) -> str:
        rendered = self._render(cmd, env=env)
        if input_text is not None:
            rendered = f"{rendered} < {input_label or 'stdin'}"
        self.commands.append(rendered)
        if not self.execute:
            print(f"[dry-run] {rendered}")
            return ""
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        try:
            completed = subprocess.run(
                list(cmd),
                env=process_env,
                check=True,
                text=True,
                capture_output=capture_output,
                input=input_text,
            )
        except subprocess.CalledProcessError as exc:
            raise ShadowSyncError(
                f"command failed with exit code {exc.returncode}: {rendered}"
            ) from exc
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


def non_negative_int_value(values: dict[str, str], key: str, default: int) -> int:
    raw = values.get(key, str(default))
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ShadowSyncError(f"{key} must be an integer") from exc
    if parsed < 0:
        raise ShadowSyncError(f"{key} must be zero or positive")
    return parsed


def bool_value(values: dict[str, str], key: str, default: bool) -> bool:
    raw = values.get(key)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ShadowSyncError(f"{key} must be a boolean")


def build_config(args: argparse.Namespace) -> ShadowSyncConfig:
    values = merged_env_file_values(args.env_file)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = Path(values.get("SHADOW_SYNC_BACKUP_ROOT", str(DEFAULT_BACKUP_ROOT)))
    seed_r2_shadow_with_copy = bool(
        getattr(args, "seed_r2_shadow_with_copy", False)
    )
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
        r2_transfers=int_value(values, "R2_SYNC_TRANSFERS", 8),
        r2_checkers=int_value(values, "R2_SYNC_CHECKERS", 16),
        retention_days=int_value(values, "SHADOW_SYNC_RETENTION_DAYS", 14),
        r2_bucket_sync_enabled=bool_value(values, "R2_BUCKET_SYNC_ENABLED", True),
        r2_shadow_seed_with_copy=(
            bool_value(values, "R2_SHADOW_SEED_WITH_COPY", False)
            or seed_r2_shadow_with_copy
        ),
        complete_media_sync_enabled=bool_value(
            values,
            "COMPLETE_MEDIA_SYNC_ENABLED",
            False,
        ),
        local_minio_complete_bucket=values.get(
            "LOCAL_MINIO_COMPLETE_BUCKET",
            "user-data-complete-shadow",
        ),
        cloud_redis_url=optional(values, "CLOUD_PROD_REDIS_URL"),
        cloud_worker_redis_url=optional(values, "CLOUD_PROD_WORKER_REDIS_URL"),
        cloud_db_tunnel_ssh_host=optional(values, "CLOUD_PROD_DB_TUNNEL_SSH_HOST"),
        cloud_db_tunnel_local_host=values.get(
            "CLOUD_PROD_DB_TUNNEL_LOCAL_HOST",
            "127.0.0.1",
        ),
        cloud_db_tunnel_local_port=non_negative_int_value(
            values,
            "CLOUD_PROD_DB_TUNNEL_LOCAL_PORT",
            0,
        ),
        cloud_db_tunnel_connect_timeout_seconds=int_value(
            values,
            "CLOUD_PROD_DB_TUNNEL_CONNECT_TIMEOUT_SECONDS",
            20,
        ),
        postgres_image=values.get("SHADOW_SYNC_POSTGRES_IMAGE", DEFAULT_POSTGRES_IMAGE),
        cloud_db_dump_mode=values.get("CLOUD_PROD_DB_DUMP_MODE", "local_tunnel"),
        cloud_db_remote_dump_ssh_host=optional(
            values,
            "CLOUD_PROD_DB_REMOTE_DUMP_SSH_HOST",
        ),
        cloud_db_remote_root=values.get(
            "CLOUD_PROD_DB_REMOTE_ROOT",
            "/home/deploy/APP/All_bot",
        ),
        cloud_db_remote_env_file=values.get(
            "CLOUD_PROD_DB_REMOTE_ENV_FILE",
            "/home/deploy/APP/All_bot/.env.cloud.prod",
        ),
        cloud_db_remote_dump_dir=values.get(
            "CLOUD_PROD_DB_REMOTE_DUMP_DIR",
            "backups/cloud-prod-shadow",
        ),
        cloud_db_remote_transfer_prefix=values.get(
            "CLOUD_PROD_DB_REMOTE_TRANSFER_PREFIX",
            "__shadow-transfer",
        ),
        r2_http_proxy=optional(values, "R2_SYNC_HTTP_PROXY"),
        r2_https_proxy=optional(values, "R2_SYNC_HTTPS_PROXY"),
        r2_no_proxy=optional(values, "R2_SYNC_NO_PROXY"),
        local_analytics_preserve_on_shadow_sync=bool_value(
            values,
            "LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC",
            True,
        ),
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


def previous_database_name_for(shadow_database_name: str, timestamp: str) -> str:
    candidate = f"{shadow_database_name}_previous_{timestamp}"
    if len(candidate) <= POSTGRES_IDENTIFIER_MAX_LENGTH:
        return candidate

    digest = hashlib.sha1(timestamp.encode("utf-8")).hexdigest()[:PREVIOUS_DB_HASH_CHARS]
    prefix = f"{shadow_database_name}_prev_"
    separator = "_"
    available_timestamp_length = (
        POSTGRES_IDENTIFIER_MAX_LENGTH
        - len(prefix)
        - len(separator)
        - len(digest)
    )
    if available_timestamp_length < 1:
        raise ShadowSyncError(
            "SHADOW_DATABASE_NAME is too long to build a safe previous shadow database name"
        )
    return f"{prefix}{timestamp[:available_timestamp_length]}{separator}{digest}"


def normalized_host(url_or_endpoint: str) -> str:
    parsed = urlparse(url_or_endpoint)
    if parsed.hostname:
        return parsed.hostname.lower()
    without_scheme = url_or_endpoint.split("://", 1)[-1]
    return without_scheme.split("/", 1)[0].split(":", 1)[0].lower()


def validate_database_name(name: str, *, label: str) -> None:
    if not SAFE_DB_NAME_RE.match(name):
        raise ShadowSyncError(f"{label} must contain only letters, numbers, and underscores")
    if len(name) > POSTGRES_IDENTIFIER_MAX_LENGTH:
        raise ShadowSyncError(
            f"{label} must be {POSTGRES_IDENTIFIER_MAX_LENGTH} characters or fewer"
        )
    if name in DENIED_TARGET_DATABASES:
        raise ShadowSyncError(f"{label} may not be production or maintenance database: {name}")


def validate_config(config: ShadowSyncConfig) -> None:
    if config.cloud_db_dump_mode not in {"local_tunnel", "remote_r2"}:
        raise ShadowSyncError(
            "CLOUD_PROD_DB_DUMP_MODE must be local_tunnel or remote_r2"
        )
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
    if config.complete_media_sync_enabled:
        if not config.local_minio_complete_bucket:
            raise ShadowSyncError("LOCAL_MINIO_COMPLETE_BUCKET must not be empty")
        if config.local_minio_complete_bucket == config.r2_bucket:
            raise ShadowSyncError(
                "local complete media bucket must not reuse the R2 production bucket name"
            )
        conflicting_buckets = {
            config.local_minio_shadow_bucket,
            config.local_minio_quarantine_bucket,
        }
        if config.local_minio_complete_bucket in conflicting_buckets:
            raise ShadowSyncError(
                "local complete media bucket must be different from shadow and quarantine buckets"
            )
    if config.cloud_db_tunnel_ssh_host:
        parsed_cloud = parsed_url(config.normalized_cloud_database_url)
        if not parsed_cloud.hostname:
            raise ShadowSyncError("cloud database URL must include a host for SSH tunnel")
        if not config.cloud_db_tunnel_local_host:
            raise ShadowSyncError("CLOUD_PROD_DB_TUNNEL_LOCAL_HOST must not be empty")
    if config.cloud_db_dump_mode == "remote_r2":
        if not config.cloud_db_remote_dump_ssh_host:
            raise ShadowSyncError(
                "CLOUD_PROD_DB_REMOTE_DUMP_SSH_HOST is required for remote_r2 dump mode"
            )
        if not config.cloud_db_remote_root:
            raise ShadowSyncError("CLOUD_PROD_DB_REMOTE_ROOT must not be empty")
        if not config.cloud_db_remote_env_file:
            raise ShadowSyncError("CLOUD_PROD_DB_REMOTE_ENV_FILE must not be empty")
        if not config.cloud_db_remote_dump_dir:
            raise ShadowSyncError("CLOUD_PROD_DB_REMOTE_DUMP_DIR must not be empty")
        if not config.cloud_db_remote_transfer_prefix.strip("/"):
            raise ShadowSyncError("CLOUD_PROD_DB_REMOTE_TRANSFER_PREFIX must not be empty")


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


def query_value(parsed: ParseResult, key: str) -> str | None:
    values = parse_qs(parsed.query).get(key)
    return values[0] if values else None


def postgres_cli_env(url: str, *, database_name: str | None = None) -> dict[str, str]:
    parsed = parsed_url(normalize_postgres_url(url))
    if not parsed.hostname:
        raise ShadowSyncError("PostgreSQL URL must include a host")
    database = database_name or parsed.path.lstrip("/").split("/", 1)[0]
    if not database:
        raise ShadowSyncError("PostgreSQL URL must include a database name")
    env = {
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": database,
        "PGUSER": parsed.username or "",
        "PGPASSWORD": parsed.password or "",
    }
    sslmode = query_value(parsed, "sslmode")
    if sslmode:
        env["PGSSLMODE"] = sslmode
    return env


def local_postgres_env(config: ShadowSyncConfig) -> dict[str, str]:
    env = postgres_cli_env(config.normalized_local_maintenance_url)
    env.update(
        {
            "LOCAL_MAINTENANCE_DB": database_name_from_url(
                config.normalized_local_maintenance_url
            ),
            "SHADOW_DB": config.shadow_database_name,
            "SHADOW_NEXT_DB": config.next_database_name,
            "SHADOW_PREVIOUS_DB": config.previous_database_name,
            "SHADOW_PREVIOUS_PREFIX": f"{config.shadow_database_name}_previous_",
            "SHADOW_COMPACT_PREVIOUS_PREFIX": f"{config.shadow_database_name}_prev_",
        }
    )
    return env


def rclone_env(config: ShadowSyncConfig) -> dict[str, str]:
    env = {
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
    if config.r2_http_proxy:
        env["HTTP_PROXY"] = config.r2_http_proxy
        env["http_proxy"] = config.r2_http_proxy
    if config.r2_https_proxy:
        env["HTTPS_PROXY"] = config.r2_https_proxy
        env["https_proxy"] = config.r2_https_proxy
    if config.r2_no_proxy:
        env["NO_PROXY"] = config.r2_no_proxy
        env["no_proxy"] = config.r2_no_proxy
    return env


def redis_env(url: str) -> dict[str, str]:
    parsed = parsed_url(url)
    if not parsed.hostname:
        raise ShadowSyncError("Redis URL must include a host")
    db = parsed.path.lstrip("/") or "0"
    return {
        "REDIS_HOST": parsed.hostname,
        "REDIS_PORT": str(parsed.port or 6379),
        "REDIS_DB": db,
        "REDISCLI_AUTH": parsed.password or "",
        "REDIS_TLS_FLAG": "--tls" if parsed.scheme == "rediss" else "",
    }


def allocate_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def url_for_host_port(url: str, *, host: str, port: int) -> str:
    parsed = urlparse(url)
    userinfo, sep, _hostport = parsed.netloc.rpartition("@")
    auth = f"{userinfo}@" if sep else ""
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return urlunparse(parsed._replace(netloc=f"{auth}{host_part}:{port}"))


def database_url_for_host_port(url: str, *, host: str, port: int) -> str:
    return url_for_host_port(normalize_postgres_url(url), host=host, port=port)


def remote_endpoint_from_url(url: str, *, default_port: int) -> tuple[str, int]:
    parsed = parsed_url(url)
    if not parsed.hostname:
        raise ShadowSyncError("remote URL must include a host for SSH tunnel")
    return parsed.hostname, parsed.port or default_port


def wait_for_tunnel_ready(
    process: subprocess.Popen[str],
    *,
    local_host: str,
    local_port: int,
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read().strip()
            detail = f": {stderr}" if stderr else ""
            raise ShadowSyncError(f"SSH tunnel process exited before it became ready{detail}")
        try:
            sock = socket.create_connection((local_host, local_port), timeout=1)
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
            continue
        sock.close()
        return
    detail = f": {last_error}" if last_error else ""
    raise ShadowSyncError(f"SSH tunnel did not become ready within {timeout_seconds}s{detail}")


@contextmanager
def tunneled_url_for_remote(
    config: ShadowSyncConfig,
    runner: CommandRunner,
    *,
    remote_url: str,
    default_port: int,
    service_label: str,
    execute: bool,
):
    if not config.cloud_db_tunnel_ssh_host:
        yield remote_url
        return

    local_port = config.cloud_db_tunnel_local_port or allocate_local_port(
        config.cloud_db_tunnel_local_host
    )
    remote_host, remote_port = remote_endpoint_from_url(
        remote_url,
        default_port=default_port,
    )
    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        f"ConnectTimeout={config.cloud_db_tunnel_connect_timeout_seconds}",
        "-N",
        "-L",
        (
            f"{config.cloud_db_tunnel_local_host}:{local_port}:"
            f"{remote_host}:{remote_port}"
        ),
        config.cloud_db_tunnel_ssh_host,
    ]
    rendered = runner._render(ssh_cmd, env=None)
    runner.commands.append(rendered)
    if not execute:
        print(f"[dry-run] {rendered}")
        yield url_for_host_port(
            remote_url,
            host=config.cloud_db_tunnel_local_host,
            port=local_port,
        )
        return

    process = subprocess.Popen(
        ssh_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_tunnel_ready(
            process,
            local_host=config.cloud_db_tunnel_local_host,
            local_port=local_port,
            timeout_seconds=config.cloud_db_tunnel_connect_timeout_seconds,
        )
        print(
            f"Opened {service_label} SSH tunnel via "
            f"{config.cloud_db_tunnel_ssh_host} on "
            f"{config.cloud_db_tunnel_local_host}:{local_port}"
        )
        yield url_for_host_port(remote_url, host=config.cloud_db_tunnel_local_host, port=local_port)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@contextmanager
def cloud_database_url_for_dump(
    config: ShadowSyncConfig,
    runner: CommandRunner,
    *,
    execute: bool,
):
    with tunneled_url_for_remote(
        config,
        runner,
        remote_url=config.normalized_cloud_database_url,
        default_port=5432,
        service_label="cloud DB",
        execute=execute,
    ) as remote_url:
        yield remote_url


def run_db_dump(
    config: ShadowSyncConfig,
    runner: CommandRunner,
    *,
    cloud_database_url: str,
) -> None:
    env = postgres_cli_env(cloud_database_url)
    script = (
        'pg_dump -Fc --serializable-deferrable --lock-wait-timeout=5s '
        "--file=/backup/cloud_prod.dump"
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            backup_dir=config.backup_dir,
            env_keys=tuple(env),
        ),
        env=env,
    )


def remote_transfer_prefix(config: ShadowSyncConfig) -> str:
    return config.cloud_db_remote_transfer_prefix.strip("/")


def remote_transfer_target(config: ShadowSyncConfig) -> str:
    return f"cloudr2:{config.r2_bucket}/{remote_transfer_prefix(config)}/{config.timestamp}"


def remote_ssh_stdin_cmd(config: ShadowSyncConfig) -> list[str]:
    if not config.cloud_db_remote_dump_ssh_host:
        raise ShadowSyncError("remote dump SSH host is not configured")
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={config.cloud_db_tunnel_connect_timeout_seconds}",
        config.cloud_db_remote_dump_ssh_host,
        "bash",
        "-s",
    ]


def build_remote_dump_script(config: ShadowSyncConfig) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"REMOTE_ROOT={shlex.quote(config.cloud_db_remote_root)}",
            f"REMOTE_DUMP_DIR={shlex.quote(config.cloud_db_remote_dump_dir)}",
            f"REMOTE_ENV_FILE={shlex.quote(config.cloud_db_remote_env_file)}",
            f"TIMESTAMP={shlex.quote(config.timestamp)}",
            f"POSTGRES_IMAGE={shlex.quote(config.postgres_image)}",
            f"RCLONE_IMAGE={shlex.quote(RCLONE_IMAGE)}",
            f"R2_BUCKET={shlex.quote(config.r2_bucket)}",
            f"TRANSFER_PREFIX={shlex.quote(remote_transfer_prefix(config))}",
            f"R2_TRANSFERS={config.r2_transfers}",
            f"R2_CHECKERS={config.r2_checkers}",
            'case "$REMOTE_DUMP_DIR" in',
            '  /*) RUN_DIR="$REMOTE_DUMP_DIR/$TIMESTAMP" ;;',
            '  *) RUN_DIR="$REMOTE_ROOT/$REMOTE_DUMP_DIR/$TIMESTAMP" ;;',
            "esac",
            'TRANSFER_TARGET="cloudr2:$R2_BUCKET/$TRANSFER_PREFIX/$TIMESTAMP"',
            'mkdir -p "$RUN_DIR"',
            'chmod 700 "$RUN_DIR"',
            'cleanup_env_files() { rm -f "$RUN_DIR/pg_dump.env" "$RUN_DIR/rclone-transfer.env"; }',
            "trap cleanup_env_files EXIT",
            'python3 - "$REMOTE_ENV_FILE" "$RUN_DIR" <<\'PY\'',
            "import os",
            "import sys",
            "from pathlib import Path",
            "from urllib.parse import parse_qs, unquote, urlparse",
            "",
            "env_file = Path(sys.argv[1])",
            "run_dir = Path(sys.argv[2])",
            "",
            "def parse_env(path):",
            "    values = {}",
            "    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():",
            "        line = raw.strip()",
            "        if not line or line.startswith('#') or '=' not in line:",
            "            continue",
            "        key, value = line.split('=', 1)",
            "        key = key.removeprefix('export ').strip()",
            "        if key:",
            "            values[key] = value.strip().strip('\"').strip(\"'\")",
            "    return values",
            "",
            "def write_env(path, values):",
            "    path.write_text(''.join(f'{key}={value}\\n' for key, value in values.items()), encoding='utf-8')",
            "    os.chmod(path, 0o600)",
            "",
            "env = parse_env(env_file)",
            "db_url = env.get('CLOUD_PROD_DATABASE_URL') or env.get('DATABASE_URL')",
            "if not db_url:",
            "    raise SystemExit('missing CLOUD_PROD_DATABASE_URL or DATABASE_URL in remote env')",
            "parsed = urlparse(db_url)",
            "database = parsed.path.lstrip('/').split('/', 1)[0]",
            "if not parsed.hostname or not database:",
            "    raise SystemExit('remote database URL must include host and database')",
            "pg_env = {",
            "    'PGHOST': parsed.hostname,",
            "    'PGPORT': str(parsed.port or 5432),",
            "    'PGDATABASE': database,",
            "    'PGUSER': unquote(parsed.username or ''),",
            "    'PGPASSWORD': unquote(parsed.password or ''),",
            "}",
            "sslmode = parse_qs(parsed.query).get('sslmode', [''])[0]",
            "if sslmode:",
            "    pg_env['PGSSLMODE'] = sslmode",
            "required_r2 = ('R2_ENDPOINT', 'R2_ACCESS_KEY', 'R2_SECRET_KEY')",
            "missing = [key for key in required_r2 if not env.get(key)]",
            "if missing:",
            "    raise SystemExit('missing remote R2 env keys: ' + ','.join(missing))",
            "rclone_env = {",
            "    'RCLONE_CONFIG_CLOUDR2_TYPE': 's3',",
            "    'RCLONE_CONFIG_CLOUDR2_PROVIDER': 'Cloudflare',",
            "    'RCLONE_CONFIG_CLOUDR2_ACCESS_KEY_ID': env['R2_ACCESS_KEY'],",
            "    'RCLONE_CONFIG_CLOUDR2_SECRET_ACCESS_KEY': env['R2_SECRET_KEY'],",
            "    'RCLONE_CONFIG_CLOUDR2_ENDPOINT': env['R2_ENDPOINT'],",
            "}",
            "write_env(run_dir / 'pg_dump.env', pg_env)",
            "write_env(run_dir / 'rclone-transfer.env', rclone_env)",
            "PY",
            'docker pull "$POSTGRES_IMAGE"',
            'docker run --rm --network host -v "$RUN_DIR:/backup" '
            '--env-file "$RUN_DIR/pg_dump.env" "$POSTGRES_IMAGE" sh -lc '
            '\'pg_dump -Fc --serializable-deferrable --lock-wait-timeout=5s '
            '--file=/backup/cloud_prod.dump\'',
            'sha256sum "$RUN_DIR/cloud_prod.dump" '
            '| awk \'{print $1 "  cloud_prod.dump"}\' > "$RUN_DIR/cloud_prod.dump.sha256"',
            'docker pull "$RCLONE_IMAGE"',
            'docker run --rm --network host -v "$RUN_DIR:/data" '
            '--env-file "$RUN_DIR/rclone-transfer.env" --entrypoint sh "$RCLONE_IMAGE" '
            '-lc "rclone copy /data \\"$TRANSFER_TARGET\\" '
            '--include cloud_prod.dump --include cloud_prod.dump.sha256 '
            '--transfers $R2_TRANSFERS --checkers $R2_CHECKERS '
            '--stats 10s --stats-log-level NOTICE"',
        ]
    )


def build_remote_cleanup_script(config: ShadowSyncConfig) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            f"REMOTE_ROOT={shlex.quote(config.cloud_db_remote_root)}",
            f"REMOTE_DUMP_DIR={shlex.quote(config.cloud_db_remote_dump_dir)}",
            f"TIMESTAMP={shlex.quote(config.timestamp)}",
            'case "$REMOTE_DUMP_DIR" in',
            '  /*) RUN_DIR="$REMOTE_DUMP_DIR/$TIMESTAMP" ;;',
            '  *) RUN_DIR="$REMOTE_ROOT/$REMOTE_DUMP_DIR/$TIMESTAMP" ;;',
            "esac",
            'rm -rf "$RUN_DIR"',
        ]
    )


def run_r2_transfer_download(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    script = "\n".join(
        [
            "set -eu",
            f"rclone copy {shlex.quote(remote_transfer_target(config))} /backup "
            "--include cloud_prod.dump --include cloud_prod.dump.sha256 "
            f"--transfers {config.r2_transfers} "
            f"--checkers {config.r2_checkers} "
            "--stats 10s --stats-log-level NOTICE",
        ]
    )
    runner.run(
        docker_cmd(
            RCLONE_IMAGE,
            script,
            backup_dir=config.backup_dir,
            env_keys=tuple(rclone_env(config).keys()),
            entrypoint="sh",
        ),
        env=rclone_env(config),
    )


def cleanup_remote_dump_and_transfer(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    try:
        runner.run(
            remote_ssh_stdin_cmd(config),
            input_text=build_remote_cleanup_script(config),
            input_label="remote-shadow-cleanup-script",
        )
    except ShadowSyncError as exc:
        print(f"WARNING: remote dump cleanup failed: {exc}", file=sys.stderr)

    script = "\n".join(
        [
            "set +e",
            f"rclone purge {shlex.quote(remote_transfer_target(config))} >/dev/null 2>&1 || true",
        ]
    )
    try:
        runner.run(
            docker_cmd(
                RCLONE_IMAGE,
                script,
                env_keys=tuple(rclone_env(config).keys()),
                entrypoint="sh",
            ),
            env=rclone_env(config),
        )
    except ShadowSyncError as exc:
        print(f"WARNING: R2 transfer cleanup failed: {exc}", file=sys.stderr)


def run_remote_db_dump_via_r2(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    try:
        runner.run(
            remote_ssh_stdin_cmd(config),
            input_text=build_remote_dump_script(config),
            input_label="remote-cloud-dump-script",
        )
        run_r2_transfer_download(config, runner)
    finally:
        cleanup_remote_dump_and_transfer(config, runner)


def run_cloud_db_dump(config: ShadowSyncConfig, runner: CommandRunner, *, execute: bool) -> None:
    if config.cloud_db_dump_mode == "remote_r2":
        run_remote_db_dump_via_r2(config, runner)
        return

    with cloud_database_url_for_dump(config, runner, execute=execute) as cloud_database_url:
        run_db_dump(config, runner, cloud_database_url=cloud_database_url)


def validate_and_write_dump_checksum(config: ShadowSyncConfig) -> str:
    if not config.dump_path.exists():
        raise ShadowSyncError(f"dump file was not created: {config.dump_path}")
    dump_sha = sha256_file(config.dump_path)
    sha_path = config.backup_dir / "cloud_prod.dump.sha256"
    if sha_path.exists():
        expected = sha_path.read_text(encoding="utf-8").split()[0]
        if expected != dump_sha:
            raise ShadowSyncError("downloaded dump checksum does not match sidecar sha256")
        return dump_sha
    sha_path.write_text(
        f"{dump_sha}  {config.dump_path.name}\n",
        encoding="utf-8",
    )
    return dump_sha


def run_db_restore_to_next(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    env = local_postgres_env(config)
    script = "\n".join(
        [
            "set -eu",
            'dropdb --if-exists --force --maintenance-db="$LOCAL_MAINTENANCE_DB" "$SHADOW_NEXT_DB"',
            'createdb --maintenance-db="$LOCAL_MAINTENANCE_DB" "$SHADOW_NEXT_DB"',
            'pg_restore --no-owner --no-privileges --dbname="$SHADOW_NEXT_DB" /backup/cloud_prod.dump',
        ]
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            backup_dir=config.backup_dir,
            env_keys=tuple(env),
        ),
        env=env,
    )


def run_db_validation(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    env = local_postgres_env(config)
    table_sql = " UNION ALL ".join(
        f"SELECT '{table}' AS table_name, count(*)::text AS row_count FROM {table}"
        for table in KEY_TABLES
    )
    script = "\n".join(
        [
            "set -eu",
            'psql --dbname="$SHADOW_NEXT_DB" -v ON_ERROR_STOP=1 -At '
            "-c 'select version_num from alembic_version order by version_num limit 1' "
            "> /backup/alembic_version.txt",
            "test -s /backup/alembic_version.txt",
            'psql --dbname="$SHADOW_NEXT_DB" -v ON_ERROR_STOP=1 -At -F "$(printf \'\\t\')" '
            f"-c {shlex.quote(table_sql)} > /backup/table_counts.tsv",
        ]
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            backup_dir=config.backup_dir,
            env_keys=tuple(env),
        ),
        env=env,
    )


def run_local_analytics_table_preservation(
    config: ShadowSyncConfig,
    runner: CommandRunner,
) -> None:
    if not config.local_analytics_preserve_on_shadow_sync:
        print("Local analytics table preservation skipped: LOCAL_ANALYTICS_PRESERVE_ON_SHADOW_SYNC=false")
        return

    env = local_postgres_env(config)
    table_predicate = " or ".join(
        f"tablename like '{pattern}'" for pattern in LOCAL_ANALYTICS_TABLE_LIKE_PATTERNS
    )
    table_list_sql = (
        "select tablename from pg_tables "
        "where schemaname = 'public' "
        f"and ({table_predicate}) "
        "order by tablename"
    )
    script = "\n".join(
        [
            "set -eu",
            "db_exists() {",
            '  psql --dbname="$LOCAL_MAINTENANCE_DB" -At -c "SELECT 1 FROM pg_database WHERE datname = \'$1\'" | grep -qx 1',
            "}",
            'if ! db_exists "$SHADOW_DB"; then',
            f"  : > /backup/{LOCAL_ANALYTICS_TABLE_LIST_FILE}",
            '  echo "Local analytics table preservation skipped: source shadow database is missing"',
            "  exit 0",
            "fi",
            'psql --dbname="$SHADOW_DB" -v ON_ERROR_STOP=1 -At '
            f"-c {shlex.quote(table_list_sql)} "
            f"> /backup/{LOCAL_ANALYTICS_TABLE_LIST_FILE}",
            f"if [ ! -s /backup/{LOCAL_ANALYTICS_TABLE_LIST_FILE} ]; then",
            '  echo "Local analytics table preservation skipped: no local analytics tables found"',
            "  exit 0",
            "fi",
            f"rm -f /backup/{LOCAL_ANALYTICS_DUMP_FILE}",
            "dump_table_args=\"\"",
            "while IFS= read -r table_name; do",
            "  dump_table_args=\"$dump_table_args --table=public.$table_name\"",
            f"done < /backup/{LOCAL_ANALYTICS_TABLE_LIST_FILE}",
            "pg_dump "
            '--dbname="$SHADOW_DB" '
            "--format=custom "
            "--schema=public "
            "$dump_table_args "
            f"--file=/backup/{LOCAL_ANALYTICS_DUMP_FILE}",
            'psql --dbname="$SHADOW_NEXT_DB" -v ON_ERROR_STOP=1 <<\'SQL\'',
            "do $$",
            "declare row record;",
            "begin",
            "  for row in",
            "    select schemaname, tablename",
            "    from pg_tables",
            "    where schemaname = 'public'",
            f"      and ({table_predicate})",
            "  loop",
            "    execute format('drop table if exists %I.%I cascade', row.schemaname, row.tablename);",
            "  end loop;",
            "end $$;",
            "SQL",
            "pg_restore "
            "--no-owner "
            "--no-privileges "
            '--dbname="$SHADOW_NEXT_DB" '
            f"/backup/{LOCAL_ANALYTICS_DUMP_FILE}",
            'echo "Local analytics tables preserved into $SHADOW_NEXT_DB"',
        ]
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            backup_dir=config.backup_dir,
            env_keys=tuple(env),
        ),
        env=env,
    )


def run_db_atomic_switch(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    env = local_postgres_env(config)
    terminate_sql = (
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname IN ('$SHADOW_DB', '$SHADOW_NEXT_DB') AND pid <> pg_backend_pid();"
    )
    script = "\n".join(
        [
            "set -eu",
            "RENAMED_CURRENT=0",
            "db_exists() {",
            '  psql --dbname="$LOCAL_MAINTENANCE_DB" -At -c "SELECT 1 FROM pg_database WHERE datname = \'$1\'" | grep -qx 1',
            "}",
            f'psql --dbname="$LOCAL_MAINTENANCE_DB" -v ON_ERROR_STOP=1 -c "{terminate_sql}" >/dev/null',
            'if db_exists "$SHADOW_PREVIOUS_DB"; then',
            '  dropdb --force --maintenance-db="$LOCAL_MAINTENANCE_DB" "$SHADOW_PREVIOUS_DB"',
            "fi",
            'if db_exists "$SHADOW_DB"; then',
            '  psql --dbname="$LOCAL_MAINTENANCE_DB" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_DB\\" RENAME TO \\"$SHADOW_PREVIOUS_DB\\""',
            "  RENAMED_CURRENT=1",
            "fi",
            'if ! psql --dbname="$LOCAL_MAINTENANCE_DB" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_NEXT_DB\\" RENAME TO \\"$SHADOW_DB\\""; then',
            '  if [ "$RENAMED_CURRENT" = "1" ] && ! db_exists "$SHADOW_DB" && db_exists "$SHADOW_PREVIOUS_DB"; then',
            '    psql --dbname="$LOCAL_MAINTENANCE_DB" -v ON_ERROR_STOP=1 '
            '-c "ALTER DATABASE \\"$SHADOW_PREVIOUS_DB\\" RENAME TO \\"$SHADOW_DB\\"" || true',
            "  fi",
            "  exit 1",
            "fi",
        ]
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            env_keys=tuple(env),
        ),
        env=env,
    )


def prune_old_previous_databases(
    config: ShadowSyncConfig,
    runner: CommandRunner,
) -> None:
    env = local_postgres_env(config)
    list_sql = (
        "SELECT datname FROM pg_database "
        "WHERE ("
        "left(datname, char_length('$SHADOW_PREVIOUS_PREFIX')) = "
        "'$SHADOW_PREVIOUS_PREFIX' OR "
        "left(datname, char_length('$SHADOW_COMPACT_PREVIOUS_PREFIX')) = "
        "'$SHADOW_COMPACT_PREVIOUS_PREFIX'"
        ") AND datname <> '$SHADOW_PREVIOUS_DB' "
        "ORDER BY datname;"
    )
    script = "\n".join(
        [
            "set -eu",
            "psql --dbname=\"$LOCAL_MAINTENANCE_DB\" -v ON_ERROR_STOP=1 -At "
            f'-c "{list_sql}" |',
            "while IFS= read -r old_previous_db; do",
            '  [ -n "$old_previous_db" ] || continue',
            '  case "$old_previous_db" in',
            '    "$SHADOW_PREVIOUS_PREFIX"*|"$SHADOW_COMPACT_PREVIOUS_PREFIX"*) ;;',
            '    *) echo "Refusing unexpected previous database: $old_previous_db" >&2; exit 1 ;;',
            "  esac",
            '  [ "$old_previous_db" != "$SHADOW_DB" ]',
            '  [ "$old_previous_db" != "$SHADOW_NEXT_DB" ]',
            '  [ "$old_previous_db" != "$SHADOW_PREVIOUS_DB" ]',
            '  [ "$old_previous_db" != "$LOCAL_MAINTENANCE_DB" ]',
            '  dropdb --force --maintenance-db="$LOCAL_MAINTENANCE_DB" "$old_previous_db"',
            '  echo "Pruned old shadow previous database: $old_previous_db"',
            "done",
        ]
    )
    runner.run(
        docker_cmd(
            config.postgres_image,
            script,
            env_keys=tuple(env),
        ),
        env=env,
    )


def run_r2_sync(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    if not config.r2_bucket_sync_enabled:
        print("R2 bucket sync skipped: R2_BUCKET_SYNC_ENABLED=false")
        return

    lines = [
        "set -eu",
        f"rclone mkdir localminio:{shlex.quote(config.local_minio_shadow_bucket)}",
        f"rclone mkdir localminio:{shlex.quote(config.local_minio_quarantine_bucket)}",
    ]
    if config.r2_shadow_seed_with_copy:
        lines.append(
            "rclone copy "
            f"cloudr2:{shlex.quote(config.r2_bucket)} "
            f"localminio:{shlex.quote(config.local_minio_shadow_bucket)} "
            "--no-traverse "
            f"--transfers {config.r2_transfers} "
            f"--checkers {config.r2_checkers} "
            f"--bwlimit {shlex.quote(config.r2_bwlimit)} "
            "--stats 60s --stats-log-level NOTICE"
        )
    else:
        lines.append(
            "rclone sync "
            f"cloudr2:{shlex.quote(config.r2_bucket)} "
            f"localminio:{shlex.quote(config.local_minio_shadow_bucket)} "
            f"--backup-dir localminio:{shlex.quote(config.local_minio_quarantine_bucket)}/{shlex.quote(config.timestamp)} "
            f"--transfers {config.r2_transfers} "
            f"--checkers {config.r2_checkers} "
            f"--bwlimit {shlex.quote(config.r2_bwlimit)} "
            "--fast-list --stats 60s --stats-log-level NOTICE"
        )
    script = "\n".join(lines)
    runner.run(
        docker_cmd(
            RCLONE_IMAGE,
            script,
            env_keys=tuple(rclone_env(config).keys()),
            entrypoint="sh",
        ),
        env=rclone_env(config),
    )


def rclone_copy_common_flags(config: ShadowSyncConfig) -> str:
    return (
        "--no-traverse "
        f"--transfers {config.r2_transfers} "
        f"--checkers {config.r2_checkers} "
        f"--bwlimit {shlex.quote(config.r2_bwlimit)} "
        "--stats 60s --stats-log-level NOTICE"
    )


def run_complete_media_sync(config: ShadowSyncConfig, runner: CommandRunner) -> None:
    if not config.complete_media_sync_enabled:
        print("Complete media bucket sync skipped: COMPLETE_MEDIA_SYNC_ENABLED=false")
        return

    complete_bucket = shlex.quote(config.local_minio_complete_bucket)
    shadow_bucket = shlex.quote(config.local_minio_shadow_bucket)
    lines = [
        "set -eu",
        f"rclone mkdir localminio:{complete_bucket}",
        "rclone copy "
        f"localminio:{shadow_bucket} "
        f"localminio:{complete_bucket} "
        f"{rclone_copy_common_flags(config)}",
    ]
    runner.run(
        docker_cmd(
            RCLONE_IMAGE,
            "\n".join(lines),
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
            'TLS_FLAG="${REDIS_TLS_FLAG:-}"',
            f'redis-cli $TLS_FLAG -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" '
            f'--no-auth-warning INFO memory > "/backup/redis_{safe_label}_memory.txt"',
            f'redis-cli $TLS_FLAG -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" '
            f'--no-auth-warning DBSIZE > "/backup/redis_{safe_label}_dbsize.txt"',
        ]
    )
    with tunneled_url_for_remote(
        config,
        runner,
        remote_url=url,
        default_port=6379,
        service_label=f"Redis audit {label}",
        execute=runner.execute,
    ) as audit_url:
        runner.run(
            docker_cmd(
                REDIS_IMAGE,
                script,
                backup_dir=config.backup_dir,
                env_keys=tuple(redis_env(audit_url)),
            ),
            env=redis_env(audit_url),
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


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def local_analytics_preservation_manifest(config: ShadowSyncConfig) -> dict[str, object]:
    tables = read_lines(config.backup_dir / LOCAL_ANALYTICS_TABLE_LIST_FILE)
    return {
        "enabled": config.local_analytics_preserve_on_shadow_sync,
        "source_database": config.shadow_database_name,
        "target_database": config.next_database_name,
        "preserved": bool(tables),
        "table_count": len(tables),
        "tables": tables,
    }


def write_manifest(config: ShadowSyncConfig, *, dump_sha256: str) -> None:
    manifest = {
        "timestamp": config.timestamp,
        "cloud_database_host": normalized_host(config.normalized_cloud_database_url),
        "cloud_database_name": database_name_from_url(config.normalized_cloud_database_url),
        "cloud_database_dump_mode": config.cloud_db_dump_mode,
        "cloud_database_remote_dump_host": config.cloud_db_remote_dump_ssh_host,
        "cloud_database_remote_transfer_prefix": (
            f"{remote_transfer_prefix(config)}/{config.timestamp}"
            if config.cloud_db_dump_mode == "remote_r2"
            else None
        ),
        "shadow_database_name": config.shadow_database_name,
        "previous_database_name": config.previous_database_name,
        "r2_bucket": config.r2_bucket,
        "local_minio_shadow_bucket": config.local_minio_shadow_bucket,
        "local_minio_quarantine_bucket": config.local_minio_quarantine_bucket,
        "r2_bucket_sync_enabled": config.r2_bucket_sync_enabled,
        "r2_shadow_seed_with_copy": config.r2_shadow_seed_with_copy,
        "complete_media_sync": {
            "enabled": config.complete_media_sync_enabled,
            "source_shadow_bucket": (
                config.local_minio_shadow_bucket
                if config.complete_media_sync_enabled
                else None
            ),
            "complete_bucket": (
                config.local_minio_complete_bucket
                if config.complete_media_sync_enabled
                else None
            ),
            "daily_mode": "shadow_copy_without_delete",
        },
        "dump_sha256": dump_sha256,
        "dump_file": str(config.dump_path),
        "alembic_version": (
            (config.backup_dir / "alembic_version.txt").read_text(encoding="utf-8").strip()
            if (config.backup_dir / "alembic_version.txt").exists()
            else None
        ),
        "table_counts": read_table_counts(config.backup_dir / "table_counts.tsv"),
        "local_analytics_preservation": local_analytics_preservation_manifest(config),
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


@contextmanager
def sync_run_lock(config: ShadowSyncConfig, *, execute: bool):
    lock_path = config.backup_root / ".shadow-sync.lock"
    if not execute:
        print(f"[dry-run] Would acquire sync lock: {lock_path}")
        yield
        return

    config.backup_root.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ShadowSyncError(
                f"another cloud-prod shadow sync is already running: {lock_path}"
            ) from exc
        handle.write(f"pid={os.getpid()} timestamp={config.timestamp}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
                "cloud_db_dump_mode": config.cloud_db_dump_mode,
                "cloud_db_tunnel": bool(config.cloud_db_tunnel_ssh_host),
                "cloud_db_remote_dump_host": config.cloud_db_remote_dump_ssh_host,
                "shadow_db": config.shadow_database_name,
                "r2_bucket": config.r2_bucket,
                "local_shadow_bucket": config.local_minio_shadow_bucket,
                "local_quarantine_bucket": config.local_minio_quarantine_bucket,
                "r2_bucket_sync_enabled": config.r2_bucket_sync_enabled,
                "r2_shadow_seed_with_copy": config.r2_shadow_seed_with_copy,
                "complete_media_sync_enabled": config.complete_media_sync_enabled,
                "local_complete_bucket": (
                    config.local_minio_complete_bucket
                    if config.complete_media_sync_enabled
                    else None
                ),
                "local_analytics_preserve_on_shadow_sync": (
                    config.local_analytics_preserve_on_shadow_sync
                ),
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
    with sync_run_lock(config, execute=execute):
        maybe_prepare_backup_dir(config, execute=execute)

        run_cloud_db_dump(config, runner, execute=execute)
        dump_sha = "<dry-run>"
        if execute:
            dump_sha = validate_and_write_dump_checksum(config)

        run_db_restore_to_next(config, runner)
        run_db_validation(config, runner)
        run_local_analytics_table_preservation(config, runner)
        run_db_atomic_switch(config, runner)
        run_r2_sync(config, runner)
        run_complete_media_sync(config, runner)
        run_redis_audit(config, runner, url=config.cloud_redis_url, label="app")
        run_redis_audit(config, runner, url=config.cloud_worker_redis_url, label="worker")

        if execute:
            write_manifest(config, dump_sha256=dump_sha)
            print(f"Manifest written: {config.manifest_path}")
        else:
            print("[dry-run] Would write manifest with dump sha256 and validation counts")
        prune_old_previous_databases(config, runner)
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
    parser.add_argument(
        "--seed-r2-shadow-with-copy",
        action="store_true",
        help=(
            "one-off initial R2 shadow bucket seed using rclone copy --no-traverse; "
            "daily timer should normally use sync/quarantine instead"
        ),
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
