#!/usr/bin/env python3
"""Backup History-referenced R2 objects from a frozen database snapshot to NAS.

This is deliberately independent from the online media-archive worker and from
all R2 migration/retirement jobs.  ``plan`` reads a *restored copy* of a
database backup and writes an immutable manifest.  ``copy`` consumes only that
manifest, never a production database, and writes each object under its exact
R2 key below a dedicated NAS root.

No command in this file mutates R2 or an application database.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any, Iterable
from urllib.parse import unquote, urlparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core.media_archive import extract_history_media_assets


MANIFEST_SCHEMA = "allbot-r2-history-snapshot-backup/v1"
CHUNK_SIZE = 8 * 1024 * 1024


@dataclass(frozen=True)
class LogicalReference:
    history_id: int
    task_id: str | None
    role: str
    ordinal: int
    reference: str


@dataclass(frozen=True)
class CopyErrorDetails:
    error_class: str
    error_code: str
    http_status: int | None
    operation: str | None
    retryable: bool

    @property
    def summary_key(self) -> str:
        if self.error_class == "r2_client":
            disposition = "retryable" if self.retryable else "terminal"
            return f"r2_client:{self.error_code}:{disposition}"
        return self.error_code


@dataclass(frozen=True)
class CopyWorkOutcome:
    result: dict[str, Any] | None
    state_update: dict[str, Any] | None
    error: BaseException | None


_R2_NOT_FOUND_CODES = {"404", "nosuchkey", "notfound", "nosuchobject"}
_R2_RETRYABLE_CODES = {
    "429",
    "500",
    "502",
    "503",
    "504",
    "internalerror",
    "requesttimeout",
    "requesttimeoutexception",
    "serviceunavailable",
    "slowdown",
    "throttling",
    "throttlingexception",
}
_RETRYABLE_EXCEPTION_NAMES = {
    "ConnectionClosedError",
    "ConnectTimeoutError",
    "EndpointConnectionError",
    "IncompleteReadError",
    "ReadTimeoutError",
}


def classify_copy_error(exc: BaseException) -> CopyErrorDetails:
    """Return a low-cardinality, secret-safe error classification."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        metadata = response.get("ResponseMetadata")
        code = str(error.get("Code") if isinstance(error, dict) else "Unknown")
        raw_status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
        try:
            http_status = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            http_status = None
        normalized = code.strip().lower()
        retryable = (
            normalized in _R2_RETRYABLE_CODES
            or http_status == 429
            or (http_status is not None and http_status >= 500)
        )
        if normalized in _R2_NOT_FOUND_CODES or http_status == 404:
            retryable = False
        return CopyErrorDetails(
            error_class="r2_client",
            error_code=code or "Unknown",
            http_status=http_status,
            operation=str(getattr(exc, "operation_name", "") or "") or None,
            retryable=retryable,
        )
    name = type(exc).__name__
    if isinstance(exc, FileNotFoundError):
        retryable = False
    elif name in _RETRYABLE_EXCEPTION_NAMES or isinstance(exc, RuntimeError):
        retryable = True
    else:
        # Unknown local/provider failures remain eligible for bounded retry.
        retryable = True
    return CopyErrorDetails(
        error_class="exception",
        error_code=name,
        http_status=None,
        operation=None,
        retryable=retryable,
    )


class BandwidthLimiter:
    """A small global limiter shared by concurrent R2 streams."""

    def __init__(self, bytes_per_second: int) -> None:
        self._rate = max(1, bytes_per_second)
        self._lock = threading.Lock()
        self._next_slot = time.monotonic()

    def account(self, byte_count: int) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + byte_count / self._rate
        delay = slot - now
        if delay > 0:
            time.sleep(delay)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _manifest_sha256(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    return hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def normalize_snapshot_key(reference: object, *, source_bucket: str) -> str | None:
    """Convert a DB reference to an R2 key while rejecting unsafe paths."""
    raw = str(reference or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        raw = unquote(parsed.path)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        raw = raw.split("?", 1)[0]
    raw = raw.lstrip("/")
    prefix = f"{source_bucket.strip().strip('/')}/"
    if raw.startswith(prefix):
        raw = raw[len(prefix) :]
    parts = raw.split("/")
    if not raw or any(part in {"", ".", ".."} for part in parts):
        return None
    return raw


def resolve_snapshot_primary_key(
    reference: LogicalReference, *, source_bucket: str
) -> str | None:
    """Match the established archive-worker preference for legacy flat names.

    A flat History value is a filename, not an R2 key.  Its primary managed
    location is ``history/<task_id>/<filename>``.  The flat-key fallback is
    deliberately a later, separately reported pass so a broad root namespace
    is never mistaken for the primary History object.
    """
    key = normalize_snapshot_key(reference.reference, source_bucket=source_bucket)
    if key is None:
        return None
    if "/" not in key and reference.task_id:
        task_id = str(reference.task_id).strip()
        if task_id and all(char not in task_id for char in "/\\\x00\r\n"):
            return f"history/{task_id}/{key}"
    return key


def extract_snapshot_references(rows: Iterable[dict[str, Any]]) -> list[LogicalReference]:
    """Use the same input/output/extra_outputs semantics as the app."""
    references: list[LogicalReference] = []
    for row in rows:
        extras = row.get("extra_outputs")
        if isinstance(extras, str):
            try:
                extras = json.loads(extras)
            except json.JSONDecodeError:
                extras = {}
        history = SimpleNamespace(
            id=row["id"],
            input_file=row.get("input_file"),
            output_file=row.get("output_file"),
            extra_outputs=extras if isinstance(extras, dict) else {},
        )
        for asset in extract_history_media_assets(history):
            references.append(
                LogicalReference(
                    history_id=asset.history_id,
                    task_id=str(row.get("task_id") or "").strip() or None,
                    role=asset.role,
                    ordinal=asset.ordinal,
                    reference=asset.source_ref,
                )
            )
    return references


def build_manifest(
    rows: Iterable[dict[str, Any]], *, source_bucket: str, snapshot_label: str
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    rejected: list[dict[str, Any]] = []
    for reference in extract_snapshot_references(rows):
        key = resolve_snapshot_primary_key(reference, source_bucket=source_bucket)
        payload = asdict(reference)
        if key is None:
            rejected.append(payload)
            continue
        grouped.setdefault(key, []).append(payload)
    objects = [
        {"key": key, "references": sorted(values, key=lambda item: (item["history_id"], item["role"], item["ordinal"]))}
        for key, values in sorted(grouped.items())
    ]
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "snapshot_label": snapshot_label,
        "source_bucket": source_bucket,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "objects": objects,
        "rejected_references": rejected,
    }
    manifest["manifest_sha256"] = _manifest_sha256(manifest)
    return manifest


async def load_history_rows(database_url: str) -> list[dict[str, Any]]:
    import asyncpg

    connection = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        rows = await connection.fetch(
            "select id,task_id,input_file,output_file,extra_outputs from history order by id"
        )
        return [dict(row) for row in rows]
    finally:
        await connection.close()


def _resolve_env(value: str) -> str:
    if value.startswith("env:"):
        name = value[4:]
        resolved = os.getenv(name, "")
        if not resolved:
            raise ValueError(f"required environment variable is not set: {name}")
        return resolved
    return value


def _safe_destination(root: Path, key: str) -> Path:
    path = root.joinpath(*PurePosixPath(key).parts)
    if root not in path.parents and path != root:
        raise ValueError("destination escaped configured root")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_manifest_file(path: Path, expected_sha256: str) -> None:
    if len(expected_sha256) != 64 or _sha256_file(path) != expected_sha256:
        raise ValueError("frozen manifest file SHA-256 is invalid")


def iter_manifest_objects(path: Path) -> Iterable[dict[str, Any]]:
    """Stream the canonical ``objects`` array without retaining the whole plan."""
    marker = '"objects":['
    decoder = json.JSONDecoder()
    buffer = ""
    found = False
    exhausted = False
    with path.open(encoding="utf-8") as stream:
        while True:
            if not exhausted and len(buffer) < 2 * 1024 * 1024:
                chunk = stream.read(1024 * 1024)
                exhausted = not chunk
                buffer += chunk
            if not found:
                marker_index = buffer.find(marker)
                if marker_index < 0:
                    if exhausted:
                        raise ValueError("manifest objects array is missing")
                    buffer = buffer[-len(marker) :]
                    continue
                buffer = buffer[marker_index + len(marker) :]
                found = True
            buffer = buffer.lstrip()
            if buffer.startswith("]"):
                return
            if buffer.startswith(","):
                buffer = buffer[1:].lstrip()
            try:
                item, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                if exhausted:
                    raise ValueError("manifest object is truncated") from None
                chunk = stream.read(1024 * 1024)
                exhausted = not chunk
                buffer += chunk
                continue
            if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                raise ValueError("manifest object is invalid")
            yield item
            buffer = buffer[end:]


def _init_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("pragma busy_timeout=30000")
    conn.execute(
        """create table if not exists snapshot_objects(
             object_key text primary key, byte_size integer, etag text, sha256 text,
             status text not null, attempts integer not null default 0, error text,
             completed_at text, error_class text, error_code text,
             error_http_status integer, error_operation text,
             error_retryable integer, last_error_at text)"""
    )
    existing_columns = {
        str(row[1]) for row in conn.execute("pragma table_info(snapshot_objects)")
    }
    migrations = {
        "error_class": "text",
        "error_code": "text",
        "error_http_status": "integer",
        "error_operation": "text",
        "error_retryable": "integer",
        "last_error_at": "text",
    }
    for column, column_type in migrations.items():
        if column not in existing_columns:
            conn.execute(f"alter table snapshot_objects add column {column} {column_type}")
    conn.execute(
        """create table if not exists snapshot_backup_batches(
             batch_number integer primary key, status text not null,
             started_at text not null, completed_at text,
             object_count integer, byte_size integer,
             local_inventory_sha256 text, remote_inventory_sha256 text,
             error text)"""
    )
    conn.execute(
        """create table if not exists snapshot_backup_batch_objects(
             batch_number integer not null, object_key text not null,
             primary key(batch_number,object_key))"""
    )
    conn.execute(
        """create table if not exists snapshot_manifest_index(
             manifest_sha256 text not null, sequence integer not null,
             object_key text not null,
             primary key(manifest_sha256,sequence),
             unique(manifest_sha256,object_key))"""
    )
    conn.execute(
        """create table if not exists snapshot_manifest_index_meta(
             manifest_sha256 text primary key, imported_count integer not null,
             completed integer not null default 0, updated_at text not null)"""
    )
    conn.execute(
        """create table if not exists snapshot_inventory_filters(
             manifest_sha256 text not null, inventory_file_sha256 text not null,
             inventory_object_count integer not null, inventory_byte_size integer not null,
             matched_count integer not null, absent_count integer not null,
             verified_at text not null,
             primary key(manifest_sha256,inventory_file_sha256))"""
    )
    conn.commit()
    return conn


def _load_credential_environment(config: dict[str, Any]) -> None:
    env_file = config.get("credential_env_file")
    if not env_file:
        return
    path = Path(str(env_file)).expanduser()
    if path.stat().st_mode & 0o077:
        raise PermissionError("credential_env_file must not be group/world accessible")
    required = {
        str(value)[4:]
        for value in config.get("r2", {}).values()
        if str(value).startswith("env:")
    }
    loaded: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in required:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        loaded[name] = value
    missing = sorted(name for name in required if not (os.getenv(name) or loaded.get(name)))
    if missing:
        raise ValueError(f"credential env file does not define required names: {','.join(missing)}")
    for name, value in loaded.items():
        os.environ.setdefault(name, value)


def _build_r2_client(config: dict[str, Any]):
    import boto3
    from botocore.config import Config

    _load_credential_environment(config)
    source = config["r2"]
    return boto3.client(
        "s3",
        endpoint_url=_resolve_env(str(source["endpoint"])),
        aws_access_key_id=_resolve_env(str(source["access_key"])),
        aws_secret_access_key=_resolve_env(str(source["secret_key"])),
        region_name=str(source.get("region", "auto")),
        config=Config(max_pool_connections=max(1, int(config.get("workers", 4))), retries={"max_attempts": 5, "mode": "standard"}),
    )


def _copy_without_state(
    client: Any,
    *,
    bucket: str,
    root: Path,
    key: str,
    limiter: BandwidthLimiter,
    stored: tuple[int | None, str | None, str] | None,
) -> CopyWorkOutcome:
    """Download and verify one key without allowing workers to write SQLite."""
    destination = _safe_destination(root, key)
    try:
        if (
            stored
            and stored[2] == "completed"
            and destination.is_file()
            and destination.stat().st_size == stored[0]
        ):
            if _sha256_file(destination) == stored[1]:
                return CopyWorkOutcome(
                    result={
                        "key": key,
                        "status": "already_verified",
                        "bytes": int(stored[0] or 0),
                    },
                    state_update=None,
                    error=None,
                )
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = client.get_object(Bucket=bucket, Key=key)
        expected_size = int(response["ContentLength"])
        etag = str(response.get("ETag", "")).strip('"')
        with tempfile.NamedTemporaryFile(prefix=".r2-part-", dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            copied = 0
            try:
                body = response["Body"]
                for chunk in iter(lambda: body.read(CHUNK_SIZE), b""):
                    limiter.account(len(chunk))
                    temporary.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        if copied != expected_size:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError("R2 object size changed while being downloaded")
        after = client.head_object(Bucket=bucket, Key=key)
        if int(after["ContentLength"]) != expected_size or str(after.get("ETag", "")).strip('"') != etag:
            temporary_path.unlink(missing_ok=True)
            raise RuntimeError("R2 object identity changed while being downloaded")
        os.replace(temporary_path, destination)
        sha256 = digest.hexdigest()
        completed_at = datetime.now(timezone.utc).isoformat()
        return CopyWorkOutcome(
            result={"key": key, "status": "completed", "bytes": copied},
            state_update={
                "object_key": key,
                "status": "completed",
                "byte_size": copied,
                "etag": etag,
                "sha256": sha256,
                "completed_at": completed_at,
            },
            error=None,
        )
    except Exception as exc:
        details = classify_copy_error(exc)
        return CopyWorkOutcome(
            result=None,
            state_update={
                "object_key": key,
                "status": "failed",
                "error": details.summary_key,
                "error_class": details.error_class,
                "error_code": details.error_code,
                "error_http_status": details.http_status,
                "error_operation": details.operation,
                "error_retryable": int(details.retryable),
                "last_error_at": datetime.now(timezone.utc).isoformat(),
            },
            error=exc,
        )


def _persist_copy_updates(
    state: sqlite3.Connection, updates: Iterable[dict[str, Any]]
) -> None:
    for update in updates:
        if update["status"] == "completed":
            state.execute(
                """insert into snapshot_objects(
                     object_key,byte_size,etag,sha256,status,attempts,error,completed_at,
                     error_class,error_code,error_http_status,error_operation,
                     error_retryable,last_error_at)
                   values(?,?,?,?, 'completed',1,null,?,null,null,null,null,null,null)
                   on conflict(object_key) do update set
                     byte_size=excluded.byte_size,etag=excluded.etag,
                     sha256=excluded.sha256,status='completed',
                     attempts=snapshot_objects.attempts+1,error=null,
                     completed_at=excluded.completed_at,error_class=null,error_code=null,
                     error_http_status=null,error_operation=null,error_retryable=null,
                     last_error_at=null""",
                (
                    update["object_key"],
                    update["byte_size"],
                    update["etag"],
                    update["sha256"],
                    update["completed_at"],
                ),
            )
            continue
        state.execute(
            """insert into snapshot_objects(
                 object_key,status,attempts,error,error_class,error_code,
                 error_http_status,error_operation,error_retryable,last_error_at)
               values(?, 'failed',1,?,?,?,?,?,?,?)
               on conflict(object_key) do update set
                 status='failed',attempts=snapshot_objects.attempts+1,error=excluded.error,
                 error_class=excluded.error_class,error_code=excluded.error_code,
                 error_http_status=excluded.error_http_status,
                 error_operation=excluded.error_operation,
                 error_retryable=excluded.error_retryable,
                 last_error_at=excluded.last_error_at""",
            (
                update["object_key"],
                update["error"],
                update["error_class"],
                update["error_code"],
                update["error_http_status"],
                update["error_operation"],
                update["error_retryable"],
                update["last_error_at"],
            ),
        )
    state.commit()


def copy_one(
    client: Any,
    *,
    bucket: str,
    root: Path,
    key: str,
    state_path: Path,
    limiter: BandwidthLimiter,
) -> dict[str, Any]:
    """Download one key and persist its receipt through the serial state path."""
    state = _init_state(state_path)
    try:
        stored = state.execute(
            "select byte_size,sha256,status from snapshot_objects where object_key=?",
            (key,),
        ).fetchone()
        outcome = _copy_without_state(
            client,
            bucket=bucket,
            root=root,
            key=key,
            limiter=limiter,
            stored=stored,
        )
        if outcome.state_update is not None:
            _persist_copy_updates(state, (outcome.state_update,))
        if outcome.error is not None:
            raise outcome.error
        assert outcome.result is not None
        return outcome.result
    finally:
        state.close()


def copy_many(
    client: Any,
    *,
    bucket: str,
    root: Path,
    keys: list[str],
    state_path: Path,
    limiter: BandwidthLimiter,
    workers: int,
    state_commit_batch_size: int = 100,
) -> dict[str, Any]:
    """Run concurrent R2 I/O while one caller-owned SQLite writer batches receipts."""
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = _init_state(state_path)
    try:
        stored_by_key = {
            key: state.execute(
                "select byte_size,sha256,status from snapshot_objects where object_key=?",
                (key,),
            ).fetchone()
            for key in keys
        }
        completed: list[dict[str, Any]] = []
        failures: Counter[str] = Counter()
        pending_updates: list[dict[str, Any]] = []
        commit_size = max(1, min(10000, int(state_commit_batch_size)))
        with ThreadPoolExecutor(max_workers=max(1, min(64, int(workers)))) as pool:
            futures = [
                pool.submit(
                    _copy_without_state,
                    client,
                    bucket=bucket,
                    root=root,
                    key=key,
                    limiter=limiter,
                    stored=stored_by_key[key],
                )
                for key in keys
            ]
            for future in as_completed(futures):
                outcome = future.result()
                if outcome.state_update is not None:
                    pending_updates.append(outcome.state_update)
                if outcome.result is not None:
                    completed.append(outcome.result)
                if outcome.error is not None:
                    failures[classify_copy_error(outcome.error).summary_key] += 1
                if len(pending_updates) >= commit_size:
                    _persist_copy_updates(state, pending_updates)
                    pending_updates.clear()
        if pending_updates:
            _persist_copy_updates(state, pending_updates)
        return {
            "attempted": len(keys),
            "completed": len(completed),
            "bytes": sum(int(item["bytes"]) for item in completed),
            "failures": dict(sorted(failures.items())),
        }
    finally:
        state.close()


def load_verified_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("manifest_sha256") != _manifest_sha256(manifest):
        raise ValueError("manifest schema or SHA-256 is invalid")
    return manifest


def should_attempt_copy(
    state_row: tuple[str, int, int | None] | None, *, max_attempts: int
) -> bool:
    if state_row is None:
        return True
    status, attempts, retryable = state_row
    if status == "completed":
        return False
    if status != "failed":
        return True
    if retryable == 0:
        return False
    return int(attempts) < max(1, max_attempts)


def reserve_continuous_batch(
    *,
    manifest_path: Path,
    state_path: Path,
    batch_number: int,
    limit: int,
    max_attempts: int,
    manifest_sha256: str,
    priority_prefixes: tuple[str, ...] = (),
    inventory_path: Path | None = None,
    inventory_file_sha256: str | None = None,
) -> list[str]:
    """Freeze one resumable batch before downloading any object bodies."""
    state = _init_state(state_path)
    try:
        existing = [
            str(row[0])
            for row in state.execute(
                "select object_key from snapshot_backup_batch_objects where batch_number=? order by object_key",
                (batch_number,),
            )
        ]
        if existing:
            return existing
        indexed = state.execute(
            "select completed from snapshot_manifest_index_meta where manifest_sha256=?",
            (manifest_sha256,),
        ).fetchone()
        if not indexed or int(indexed[0]) != 1:
            raise RuntimeError("manifest index is not complete")
        if (inventory_path is None) != (inventory_file_sha256 is None):
            raise ValueError("inventory path and SHA-256 must be configured together")
        inventory_join = ""
        if inventory_path is not None and inventory_file_sha256 is not None:
            receipt = state.execute(
                """select 1 from snapshot_inventory_filters
                   where manifest_sha256=? and inventory_file_sha256=?""",
                (manifest_sha256, inventory_file_sha256),
            ).fetchone()
            if not receipt:
                raise RuntimeError("verified inventory filter receipt is missing")
            state.execute(
                "attach database ? as verified_inventory", (str(inventory_path.resolve()),)
            )
            inventory_join = (
                " join verified_inventory.objects inventory"
                " on inventory.key=manifest.object_key"
            )
        normalized_prefixes = tuple(dict.fromkeys(priority_prefixes))
        for prefix in normalized_prefixes:
            if (
                not prefix.endswith("/")
                or prefix.startswith("/")
                or any(part in {"", ".", ".."} for part in prefix[:-1].split("/"))
            ):
                raise ValueError("priority prefixes must be safe R2 directory prefixes")
        selected: list[str] = []
        eligibility = """(
          state.object_key is null or state.status not in ('completed','failed') or
          (state.status='failed' and coalesce(state.error_retryable,1)=1
            and state.attempts < ?)
        )"""
        for prefix in normalized_prefixes:
            remaining = max(1, limit) - len(selected)
            if remaining <= 0:
                break
            upper_bound = prefix + chr(0x10FFFF)
            selected.extend(
                str(row[0])
                for row in state.execute(
                    f"""select manifest.object_key
                        from snapshot_manifest_index manifest
                        {inventory_join}
                        left join snapshot_objects state
                          on state.object_key=manifest.object_key
                        where manifest.manifest_sha256=?
                          and manifest.object_key>=? and manifest.object_key<?
                          and {eligibility}
                        order by manifest.object_key limit ?""",
                    (
                        manifest_sha256,
                        prefix,
                        upper_bound,
                        max(1, max_attempts),
                        remaining,
                    ),
                )
            )
        remaining = max(1, limit) - len(selected)
        if remaining > 0:
            exclusions = "".join(
                " and not (manifest.object_key>=? and manifest.object_key<?)"
                for _prefix in normalized_prefixes
            )
            exclusion_parameters: list[str] = []
            for prefix in normalized_prefixes:
                exclusion_parameters.extend((prefix, prefix + chr(0x10FFFF)))
            selected.extend(
                str(row[0])
                for row in state.execute(
                    f"""select manifest.object_key
                        from snapshot_manifest_index manifest
                        {inventory_join}
                        left join snapshot_objects state
                          on state.object_key=manifest.object_key
                        where manifest.manifest_sha256=? and {eligibility}
                          {exclusions}
                        order by manifest.sequence limit ?""",
                    (
                        manifest_sha256,
                        max(1, max_attempts),
                        *exclusion_parameters,
                        remaining,
                    ),
                )
            )
        if not selected:
            return []
        now = datetime.now(timezone.utc).isoformat()
        state.execute(
            """insert into snapshot_backup_batches(batch_number,status,started_at)
               values(?, 'copying', ?)
               on conflict(batch_number) do nothing""",
            (batch_number, now),
        )
        state.executemany(
            "insert into snapshot_backup_batch_objects(batch_number,object_key) values(?,?)",
            [(batch_number, key) for key in selected],
        )
        state.commit()
        return selected
    finally:
        state.close()


def ensure_manifest_index(
    *, manifest_path: Path, state_path: Path, manifest_sha256: str
) -> int:
    """Build a resumable SQLite key index so each batch does not rescan 2+ GiB."""
    state = _init_state(state_path)
    try:
        row = state.execute(
            """select imported_count,completed from snapshot_manifest_index_meta
               where manifest_sha256=?""",
            (manifest_sha256,),
        ).fetchone()
        imported_count = int(row[0]) if row else 0
        if row and int(row[1]) == 1:
            return imported_count
        if not row:
            state.execute(
                """insert into snapshot_manifest_index_meta(
                     manifest_sha256,imported_count,completed,updated_at)
                   values(?,0,0,?)""",
                (manifest_sha256, datetime.now(timezone.utc).isoformat()),
            )
            state.commit()
        pending: list[tuple[str, int, str]] = []
        sequence = -1
        for sequence, item in enumerate(iter_manifest_objects(manifest_path)):
            if sequence < imported_count:
                continue
            pending.append((manifest_sha256, sequence, str(item["key"])))
            if len(pending) < 10000:
                continue
            state.executemany(
                """insert or ignore into snapshot_manifest_index(
                     manifest_sha256,sequence,object_key) values(?,?,?)""",
                pending,
            )
            imported_count = sequence + 1
            state.execute(
                """update snapshot_manifest_index_meta
                   set imported_count=?,updated_at=? where manifest_sha256=?""",
                (imported_count, datetime.now(timezone.utc).isoformat(), manifest_sha256),
            )
            state.commit()
            pending.clear()
            if imported_count % 100000 == 0:
                print(
                    json.dumps(
                        {"status": "indexing", "objects": imported_count}, sort_keys=True
                    ),
                    flush=True,
                )
        if pending:
            state.executemany(
                """insert or ignore into snapshot_manifest_index(
                     manifest_sha256,sequence,object_key) values(?,?,?)""",
                pending,
            )
            imported_count = sequence + 1
        state.execute(
            """update snapshot_manifest_index_meta
               set imported_count=?,completed=1,updated_at=? where manifest_sha256=?""",
            (imported_count, datetime.now(timezone.utc).isoformat(), manifest_sha256),
        )
        state.commit()
        return imported_count
    finally:
        state.close()


def ensure_inventory_filter(
    *,
    inventory_path: Path,
    inventory_file_sha256: str,
    state_path: Path,
    manifest_sha256: str,
) -> dict[str, Any]:
    """Bind one complete inventory snapshot before excluding absent manifest keys."""
    if len(inventory_file_sha256) != 64 or _sha256_file(inventory_path) != inventory_file_sha256:
        raise ValueError("inventory file SHA-256 is invalid")
    inventory = sqlite3.connect(
        f"file:{inventory_path.resolve()}?mode=ro", uri=True, timeout=30
    )
    try:
        quick_check = inventory.execute("pragma quick_check").fetchone()
        if quick_check != ("ok",):
            raise ValueError("inventory SQLite quick_check failed")
        columns = {
            str(row[1]) for row in inventory.execute("pragma table_info(objects)")
        }
        if not {"key", "size", "etag", "last_modified"}.issubset(columns):
            raise ValueError("inventory objects schema is invalid")
        inventory_count, inventory_bytes = inventory.execute(
            "select count(*),coalesce(sum(size),0) from objects"
        ).fetchone()
    finally:
        inventory.close()
    state = _init_state(state_path)
    try:
        indexed = state.execute(
            """select imported_count,completed from snapshot_manifest_index_meta
               where manifest_sha256=?""",
            (manifest_sha256,),
        ).fetchone()
        if not indexed or int(indexed[1]) != 1:
            raise RuntimeError("manifest index is not complete")
        state.execute(
            "attach database ? as verified_inventory", (str(inventory_path.resolve()),)
        )
        try:
            matched_count = int(
                state.execute(
                    """select count(*)
                       from snapshot_manifest_index manifest
                       join verified_inventory.objects inventory
                         on inventory.key=manifest.object_key
                       where manifest.manifest_sha256=?""",
                    (manifest_sha256,),
                ).fetchone()[0]
            )
        finally:
            state.execute("detach database verified_inventory")
        manifest_count = int(indexed[0])
        if matched_count > manifest_count:
            raise RuntimeError("inventory intersection exceeds manifest size")
        absent_count = manifest_count - matched_count
        verified_at = datetime.now(timezone.utc).isoformat()
        state.execute(
            """insert into snapshot_inventory_filters(
                 manifest_sha256,inventory_file_sha256,inventory_object_count,
                 inventory_byte_size,matched_count,absent_count,verified_at)
               values(?,?,?,?,?,?,?)
               on conflict(manifest_sha256,inventory_file_sha256) do update set
                 inventory_object_count=excluded.inventory_object_count,
                 inventory_byte_size=excluded.inventory_byte_size,
                 matched_count=excluded.matched_count,
                 absent_count=excluded.absent_count,
                 verified_at=excluded.verified_at""",
            (
                manifest_sha256,
                inventory_file_sha256,
                int(inventory_count),
                int(inventory_bytes),
                matched_count,
                absent_count,
                verified_at,
            ),
        )
        state.commit()
        return {
            "manifest_count": manifest_count,
            "inventory_object_count": int(inventory_count),
            "inventory_bytes": int(inventory_bytes),
            "matched_count": matched_count,
            "absent_count": absent_count,
            "inventory_file_sha256": inventory_file_sha256,
        }
    finally:
        state.close()


def directory_inventory(root: Path) -> dict[str, Any]:
    """Hash relative path, size, and full content for a bounded batch directory."""
    rows: list[list[Any]] = []
    byte_size = 0
    if root.exists():
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_symlink():
                raise ValueError("batch directory must not contain symlinks")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            size = path.stat().st_size
            rows.append([relative, size, _sha256_file(path)])
            byte_size += size
    digest = hashlib.sha256(_canonical_json(rows)).hexdigest()
    return {"exists": root.exists(), "objects": len(rows), "bytes": byte_size, "sha256": digest}


_REMOTE_INVENTORY_SCRIPT = """import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
rows=[]
total=0
if root.exists():
  for path in sorted(root.rglob('*'),key=lambda item:item.as_posix()):
    if path.is_symlink(): raise SystemExit('symlink rejected')
    if not path.is_file(): continue
    digest=hashlib.sha256()
    with path.open('rb') as stream:
      for chunk in iter(lambda:stream.read(8*1024*1024),b''): digest.update(chunk)
    size=path.stat().st_size
    rows.append([path.relative_to(root).as_posix(),size,digest.hexdigest()])
    total+=size
payload=json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
print(json.dumps({'exists':root.exists(),'objects':len(rows),'bytes':total,'sha256':hashlib.sha256(payload).hexdigest()},sort_keys=True))
"""


def _validated_remote_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("NAS path must be a safe home-relative path")
    return path.as_posix()


def _remote_inventory(ssh_alias: str, remote_path: str) -> dict[str, Any]:
    command = " ".join(
        ["python3", "-c", shlex.quote(_REMOTE_INVENTORY_SCRIPT), shlex.quote(remote_path)]
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_alias, command],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def transfer_verified_batch(
    *, local_root: Path, ssh_alias: str, nas_batches_root: str, batch_number: int
) -> dict[str, Any]:
    """Transfer through ordinary SSH, verify every file, then atomically publish."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ssh_alias):
        raise ValueError("invalid NAS SSH alias")
    batches_root = _validated_remote_path(nas_batches_root)
    batch_name = f"batch-{batch_number:06d}"
    final_path = _validated_remote_path(f"{batches_root}/{batch_name}")
    incoming_path = _validated_remote_path(f"{batches_root}/.incoming-{batch_name}")
    local = directory_inventory(local_root)
    existing = _remote_inventory(ssh_alias, final_path)
    if existing["exists"]:
        if existing != local:
            raise RuntimeError("existing NAS batch inventory does not match local batch")
        return existing
    prepare = (
        f"mkdir -p {shlex.quote(batches_root)} && "
        f"rm -rf -- {shlex.quote(incoming_path)} && mkdir -p {shlex.quote(incoming_path)}"
    )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_alias, prepare],
        check=True,
    )
    tar_process = subprocess.Popen(
        ["tar", "-C", str(local_root), "-cf", "-", "."], stdout=subprocess.PIPE
    )
    extract = f"tar -C {shlex.quote(incoming_path)} -xf -"
    ssh_process = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_alias, extract],
        stdin=tar_process.stdout,
    )
    assert tar_process.stdout is not None
    tar_process.stdout.close()
    ssh_status = ssh_process.wait()
    tar_status = tar_process.wait()
    if tar_status or ssh_status:
        raise RuntimeError(f"NAS tar transfer failed: tar={tar_status} ssh={ssh_status}")
    remote = _remote_inventory(ssh_alias, incoming_path)
    if remote != local:
        raise RuntimeError("NAS incoming batch inventory verification failed")
    publish = (
        f"test ! -e {shlex.quote(final_path)} && "
        f"mv -- {shlex.quote(incoming_path)} {shlex.quote(final_path)}"
    )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_alias, publish],
        check=True,
    )
    published = _remote_inventory(ssh_alias, final_path)
    if published != local:
        raise RuntimeError("published NAS batch inventory verification failed")
    return published


def _active_batch(state: sqlite3.Connection) -> tuple[int, str] | None:
    row = state.execute(
        """select batch_number,status from snapshot_backup_batches
           where status in ('copying','transferring') order by batch_number limit 1"""
    ).fetchone()
    return (int(row[0]), str(row[1])) if row else None


def _next_batch_number(state: sqlite3.Connection, first_batch_number: int) -> int:
    row = state.execute("select max(batch_number) from snapshot_backup_batches").fetchone()
    return max(first_batch_number, int(row[0] or 0) + 1)


def _run_reserved_copy(
    *,
    config: dict[str, Any],
    state_path: Path,
    root: Path,
    keys: list[str],
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = _build_r2_client(config)
    workers = max(1, min(16, int(config.get("workers", 4))))
    max_attempts = max(1, int(config.get("max_attempts", 5)))
    limiter = BandwidthLimiter(
        int(config.get("bandwidth_bytes_per_second", 30 * 1024 * 1024))
    )
    selected: list[str] = []
    state = _init_state(state_path)
    try:
        for key in keys:
            row = state.execute(
                "select status,attempts,error_retryable from snapshot_objects where object_key=?",
                (key,),
            ).fetchone()
            if row and row[0] == "completed":
                # Re-enter copy_one so a restart verifies that this batch's local file still exists.
                selected.append(key)
            elif should_attempt_copy(row, max_attempts=max_attempts):
                selected.append(key)
    finally:
        state.close()
    return copy_many(
        client,
        bucket=str(config["source_bucket"]),
        root=root,
        keys=selected,
        state_path=state_path,
        limiter=limiter,
        workers=workers,
        state_commit_batch_size=int(config.get("state_commit_batch_size", 100)),
    )


def command_continuous(args: argparse.Namespace) -> None:
    config_path = Path(args.config).expanduser()
    if config_path.stat().st_mode & 0o077:
        raise PermissionError("continuous config must be 0600")
    config = json.loads(config_path.read_text())
    manifest_path = Path(args.manifest).expanduser()
    _verify_manifest_file(manifest_path, str(config["manifest_file_sha256"]))
    state_path = Path(_resolve_env(str(config["state_path"]))).expanduser()
    spool_root = Path(_resolve_env(str(config["spool_root"]))).expanduser()
    spool_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    batch_size = max(1, min(10000, int(config.get("batch_size", 1000))))
    first_batch_number = max(1, int(config.get("first_batch_number", 1)))
    max_attempts = max(1, int(config.get("max_attempts", 5)))
    pause_seconds = max(0.0, min(300.0, float(config.get("batch_pause_seconds", 2))))
    ssh_alias = str(config["nas_ssh_alias"])
    nas_batches_root = str(config["nas_batches_root"])
    manifest_sha256 = str(config["manifest_sha256"])
    raw_priority_prefixes = config.get("priority_prefixes", [])
    if not isinstance(raw_priority_prefixes, list) or not all(
        isinstance(item, str) for item in raw_priority_prefixes
    ):
        raise ValueError("priority_prefixes must be a JSON string list")
    priority_prefixes = tuple(raw_priority_prefixes)
    indexed_count = ensure_manifest_index(
        manifest_path=manifest_path,
        state_path=state_path,
        manifest_sha256=manifest_sha256,
    )
    print(
        json.dumps(
            {"status": "index_ready", "objects": indexed_count}, sort_keys=True
        ),
        flush=True,
    )
    inventory_path: Path | None = None
    inventory_file_sha256: str | None = None
    if config.get("inventory_path") or config.get("inventory_file_sha256"):
        if not config.get("inventory_path") or not config.get("inventory_file_sha256"):
            raise ValueError("inventory_path and inventory_file_sha256 are both required")
        inventory_path = Path(
            _resolve_env(str(config["inventory_path"]))
        ).expanduser()
        inventory_file_sha256 = str(config["inventory_file_sha256"])
        inventory_receipt = ensure_inventory_filter(
            inventory_path=inventory_path,
            inventory_file_sha256=inventory_file_sha256,
            state_path=state_path,
            manifest_sha256=manifest_sha256,
        )
        print(
            json.dumps(
                {"status": "inventory_filter_ready", **inventory_receipt},
                sort_keys=True,
            ),
            flush=True,
        )
    while True:
        state = _init_state(state_path)
        try:
            # A verified batch is safe to remove locally; its NAS inventory is in the ledger.
            verified = [
                int(row[0])
                for row in state.execute(
                    "select batch_number from snapshot_backup_batches where status='verified'"
                )
            ]
            active = _active_batch(state)
            batch_number = (
                active[0]
                if active
                else _next_batch_number(state, first_batch_number)
            )
            phase = active[1] if active else "copying"
        finally:
            state.close()
        for verified_batch in verified:
            verified_root = spool_root / f"batch-{verified_batch:06d}"
            if verified_root.exists():
                shutil.rmtree(verified_root)
        keys = reserve_continuous_batch(
            manifest_path=manifest_path,
            state_path=state_path,
            batch_number=batch_number,
            limit=batch_size,
            max_attempts=max_attempts,
            manifest_sha256=manifest_sha256,
            priority_prefixes=priority_prefixes,
            inventory_path=inventory_path,
            inventory_file_sha256=inventory_file_sha256,
        )
        if not keys:
            print(
                json.dumps(
                    {
                        "status": "completed",
                        "reason": "no_eligible_manifest_objects",
                        "manifest_sha256": config.get("manifest_sha256", ""),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            return
        batch_root = spool_root / f"batch-{batch_number:06d}"
        if phase == "copying":
            summary = _run_reserved_copy(
                config=config,
                state_path=state_path,
                root=batch_root,
                keys=keys,
            )
            state = _init_state(state_path)
            try:
                state.execute(
                    """update snapshot_backup_batches
                       set status='transferring',error=null where batch_number=?""",
                    (batch_number,),
                )
                state.commit()
            finally:
                state.close()
            print(
                json.dumps(
                    {"status": "downloaded", "batch": batch_number, **summary},
                    sort_keys=True,
                ),
                flush=True,
            )
        try:
            remote = transfer_verified_batch(
                local_root=batch_root,
                ssh_alias=ssh_alias,
                nas_batches_root=nas_batches_root,
                batch_number=batch_number,
            )
        except Exception as exc:
            state = _init_state(state_path)
            try:
                state.execute(
                    "update snapshot_backup_batches set error=? where batch_number=?",
                    (type(exc).__name__, batch_number),
                )
                state.commit()
            finally:
                state.close()
            raise
        state = _init_state(state_path)
        try:
            state.execute(
                """update snapshot_backup_batches set status='verified',completed_at=?,
                   object_count=?,byte_size=?,local_inventory_sha256=?,
                   remote_inventory_sha256=?,error=null where batch_number=?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    int(remote["objects"]),
                    int(remote["bytes"]),
                    str(remote["sha256"]),
                    str(remote["sha256"]),
                    batch_number,
                ),
            )
            state.commit()
        finally:
            state.close()
        shutil.rmtree(batch_root)
        print(
            json.dumps(
                {
                    "status": "nas_verified",
                    "batch": batch_number,
                    "objects": remote["objects"],
                    "bytes": remote["bytes"],
                    "inventory_sha256": remote["sha256"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if pause_seconds:
            time.sleep(pause_seconds)


def collect_copy_results(futures: Iterable[Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Allow a frozen batch to finish when individual historical keys are absent."""
    completed: list[dict[str, Any]] = []
    failures: Counter[str] = Counter()
    for future in as_completed(futures):
        try:
            completed.append(future.result())
        except Exception as exc:
            failures[classify_copy_error(exc).summary_key] += 1
    return completed, dict(sorted(failures.items()))


def command_plan(args: argparse.Namespace) -> None:
    import asyncio

    rows = asyncio.run(load_history_rows(_resolve_env(args.database_url)))
    manifest = build_manifest(rows, source_bucket=args.source_bucket, snapshot_label=args.snapshot_label)
    target = Path(args.manifest)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_bytes(_canonical_json(manifest) + b"\n")
    os.chmod(target, 0o600)
    file_sha256 = _sha256_file(target)
    sidecar = target.with_suffix(target.suffix + ".sha256")
    sidecar.write_text(file_sha256 + "\n")
    os.chmod(sidecar, 0o600)
    print(json.dumps({"objects": len(manifest["objects"]), "rejected": len(manifest["rejected_references"]), "manifest_sha256": manifest["manifest_sha256"], "file_sha256": file_sha256}))


def command_copy(args: argparse.Namespace) -> None:
    config = json.loads(Path(args.config).read_text())
    manifest_path = Path(args.manifest)
    _verify_manifest_file(manifest_path, str(config["manifest_file_sha256"]))
    source_bucket = str(config["source_bucket"])
    root = Path(_resolve_env(str(config["destination_root"]))).expanduser()
    state_path = Path(_resolve_env(str(config["state_path"]))).expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = _build_r2_client(config)
    workers = max(1, min(16, int(config.get("workers", 4))))
    limiter = BandwidthLimiter(int(config.get("bandwidth_bytes_per_second", 30 * 1024 * 1024)))
    state = _init_state(state_path)
    max_attempts = max(1, int(config.get("max_attempts", 5)))
    try:
        objects = []
        for item in iter_manifest_objects(manifest_path):
            status_row = state.execute(
                "select status,attempts,error_retryable from snapshot_objects where object_key=?",
                (item["key"],),
            ).fetchone()
            if not should_attempt_copy(status_row, max_attempts=max_attempts):
                continue
            objects.append(item)
            if len(objects) >= max(1, args.limit):
                break
    finally:
        state.close()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                copy_one,
                client,
                bucket=source_bucket,
                root=root,
                key=item["key"],
                state_path=state_path,
                limiter=limiter,
            )
            for item in objects
        ]
        results, failures = collect_copy_results(futures)
    print(json.dumps({"completed": len(results), "bytes": sum(item["bytes"] for item in results), "failures": failures, "manifest_sha256": config.get("manifest_sha256", "")}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="freeze a manifest from a restored DB snapshot")
    plan.add_argument("--database-url", required=True, help="postgres URL or env:NAME for a restored snapshot")
    plan.add_argument("--source-bucket", required=True)
    plan.add_argument("--snapshot-label", required=True)
    plan.add_argument("--manifest", required=True)
    copy = commands.add_parser("copy", help="copy a frozen manifest to NAS")
    copy.add_argument("--config", required=True, help="0600 JSON; R2 credentials may use env:NAME")
    copy.add_argument("--manifest", required=True)
    copy.add_argument("--limit", type=int, default=1000)
    continuous = commands.add_parser(
        "continuous", help="run resumable copy, SSH transfer, and NAS verification batches"
    )
    continuous.add_argument("--config", required=True, help="0600 continuous runtime JSON")
    continuous.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        command_plan(args)
    elif args.command == "copy":
        command_copy(args)
    else:
        command_continuous(args)


if __name__ == "__main__":
    main()
