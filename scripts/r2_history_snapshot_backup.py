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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
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
    role: str
    ordinal: int
    reference: str


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
        key = normalize_snapshot_key(reference.reference, source_bucket=source_bucket)
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
            "select id,input_file,output_file,extra_outputs from history order by id"
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


def _init_state(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("pragma busy_timeout=30000")
    conn.execute(
        """create table if not exists snapshot_objects(
             object_key text primary key, byte_size integer, etag text, sha256 text,
             status text not null, attempts integer not null default 0, error text,
             completed_at text)"""
    )
    conn.commit()
    return conn


def _build_r2_client(config: dict[str, Any]):
    import boto3
    from botocore.config import Config

    source = config["r2"]
    return boto3.client(
        "s3",
        endpoint_url=_resolve_env(str(source["endpoint"])),
        aws_access_key_id=_resolve_env(str(source["access_key"])),
        aws_secret_access_key=_resolve_env(str(source["secret_key"])),
        region_name=str(source.get("region", "auto")),
        config=Config(max_pool_connections=max(1, int(config.get("workers", 4))), retries={"max_attempts": 5, "mode": "standard"}),
    )


def copy_one(
    client: Any,
    *,
    bucket: str,
    root: Path,
    key: str,
    state_path: Path,
    limiter: BandwidthLimiter,
) -> dict[str, Any]:
    """Download one key once, stream-hash it, and atomically expose it on NAS."""
    destination = _safe_destination(root, key)
    conn = _init_state(state_path)
    try:
        stored = conn.execute(
            "select byte_size,sha256,status from snapshot_objects where object_key=?", (key,)
        ).fetchone()
        if stored and stored[2] == "completed" and destination.is_file() and destination.stat().st_size == stored[0]:
            if _sha256_file(destination) == stored[1]:
                return {"key": key, "status": "already_verified", "bytes": stored[0]}
        head = client.head_object(Bucket=bucket, Key=key)
        expected_size = int(head["ContentLength"])
        etag = str(head.get("ETag", "")).strip('"')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".r2-part-", dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            copied = 0
            try:
                body = client.get_object(Bucket=bucket, Key=key)["Body"]
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
        conn.execute(
            """insert into snapshot_objects(object_key,byte_size,etag,sha256,status,attempts,error,completed_at)
               values(?,?,?,?, 'completed',1,null,?)
               on conflict(object_key) do update set byte_size=excluded.byte_size,etag=excluded.etag,
                 sha256=excluded.sha256,status='completed',attempts=snapshot_objects.attempts+1,
                 error=null,completed_at=excluded.completed_at""",
            (key, copied, etag, sha256, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return {"key": key, "status": "completed", "bytes": copied}
    except Exception as exc:
        conn.execute(
            """insert into snapshot_objects(object_key,status,attempts,error) values(?, 'failed',1,?)
               on conflict(object_key) do update set status='failed',attempts=snapshot_objects.attempts+1,error=excluded.error""",
            (key, type(exc).__name__),
        )
        conn.commit()
        raise
    finally:
        conn.close()


def load_verified_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("manifest_sha256") != _manifest_sha256(manifest):
        raise ValueError("manifest schema or SHA-256 is invalid")
    return manifest


def command_plan(args: argparse.Namespace) -> None:
    import asyncio

    rows = asyncio.run(load_history_rows(_resolve_env(args.database_url)))
    manifest = build_manifest(rows, source_bucket=args.source_bucket, snapshot_label=args.snapshot_label)
    target = Path(args.manifest)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.write_bytes(_canonical_json(manifest) + b"\n")
    os.chmod(target, 0o600)
    print(json.dumps({"objects": len(manifest["objects"]), "rejected": len(manifest["rejected_references"]), "manifest_sha256": manifest["manifest_sha256"]}))


def command_copy(args: argparse.Namespace) -> None:
    config = json.loads(Path(args.config).read_text())
    manifest = load_verified_manifest(Path(args.manifest))
    root = Path(_resolve_env(str(config["destination_root"]))).expanduser()
    state_path = Path(_resolve_env(str(config["state_path"]))).expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = _build_r2_client(config)
    workers = max(1, min(16, int(config.get("workers", 4))))
    limiter = BandwidthLimiter(int(config.get("bandwidth_bytes_per_second", 30 * 1024 * 1024)))
    objects = manifest["objects"][: max(1, args.limit)]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                copy_one,
                client,
                bucket=manifest["source_bucket"],
                root=root,
                key=item["key"],
                state_path=state_path,
                limiter=limiter,
            )
            for item in objects
        ]
        for future in as_completed(futures):
            results.append(future.result())
    print(json.dumps({"completed": len(results), "bytes": sum(item["bytes"] for item in results), "manifest_sha256": manifest["manifest_sha256"]}))


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
    args = parser.parse_args()
    if args.command == "plan":
        command_plan(args)
    else:
        command_copy(args)


if __name__ == "__main__":
    main()
