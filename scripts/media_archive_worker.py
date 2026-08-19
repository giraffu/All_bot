#!/usr/bin/env python3
"""Lease History media, copy it to NAS MinIO, verify, and post receipts.

The worker has no R2 delete operation by design.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlparse

import boto3
import asyncpg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
import httpx


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.media_archive import (  # noqa: E402
    get_archive_media_type,
    plan_archive_asset_restore_keys,
    plan_archive_thumbnail_restore_keys,
)


ARCHIVE_BUCKET = "allbot-media-archive-v1"
PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def clear_proxy_environment() -> None:
    rejected = [
        key
        for key in PROXY_KEYS
        if "127.0.0.1:7890" in os.environ.get(key, "")
        or "localhost:7890" in os.environ.get(key, "")
    ]
    if rejected:
        raise RuntimeError(
            "archive worker refuses local port 7890 proxy environment: "
            + ",".join(sorted(rejected))
        )
    for key in PROXY_KEYS:
        os.environ.pop(key, None)


def load_secure_config(path: Path) -> dict:
    """Load a worker secret only when it is a current-user owned 0600 file."""
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise PermissionError("archive worker config must be a regular file")
    if info.st_uid != os.geteuid():
        raise PermissionError("archive worker config must be owned by the worker user")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("archive worker config must have mode 0600")
    return json.loads(path.read_text(encoding="utf-8"))


def archive_job_claim_params(
    *,
    worker_id: str,
    limit: int,
    max_priority: int,
    history_ids: list[int] | tuple[int, ...] | None = None,
) -> list[tuple[str, str | int]]:
    exact_history_ids = sorted({int(value) for value in history_ids or ()})
    if len(exact_history_ids) > 100 or any(value < 1 for value in exact_history_ids):
        raise ValueError(
            "history_ids must contain at most 100 positive History IDs"
        )
    params: list[tuple[str, str | int]] = [
        ("worker_id", worker_id),
        ("limit", limit),
        ("max_priority", max_priority),
    ]
    if exact_history_ids:
        params.append(("history_ids", ",".join(map(str, exact_history_ids))))
    return params


def validate_direct_route(
    hostname: str,
    *,
    port: int = 443,
    allowed_interfaces: tuple[str, ...] = (),
    allowed_source_ips: tuple[str, ...] = (),
    allow_tailscale: bool = False,
) -> None:
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    }
    if not addresses:
        raise RuntimeError(f"cannot resolve {hostname}")
    for address in addresses:
        route = subprocess.run(
            ["ip", "route", "get", address], capture_output=True, text=True, check=True
        ).stdout.lower()
        rejected_markers = ["tun0", "wg0", "127.0.0.1"]
        if not allow_tailscale:
            rejected_markers.append("tailscale")
        if any(marker in route for marker in rejected_markers):
            raise RuntimeError(
                f"non-physical route rejected for {hostname}: {route.strip()}"
            )
        if allowed_interfaces and not any(
            f"dev {interface}" in route for interface in allowed_interfaces
        ):
            raise RuntimeError(f"unexpected interface for {hostname}: {route.strip()}")
        if allowed_source_ips and not any(
            f"src {source}" in route for source in allowed_source_ips
        ):
            raise RuntimeError(
                f"unexpected source address for {hostname}: {route.strip()}"
            )


def validate_endpoint_route(config: dict) -> None:
    parsed = urlparse(config["endpoint"])
    validate_direct_route(
        parsed.hostname,
        port=parsed.port or (443 if parsed.scheme == "https" else 80),
        allowed_interfaces=tuple(config.get("allowed_interfaces", ())),
        allowed_source_ips=tuple(config.get("allowed_source_ips", ())),
        allow_tailscale=bool(config.get("allow_tailscale", False)),
    )


def validate_source_routes(sources: list[dict]) -> None:
    for source in sources:
        if source.get("type", "s3") == "filesystem":
            continue
        validate_endpoint_route(source)


def _client(config: dict):
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config.get("region", "auto"),
        verify=config.get("ca_file", True),
        config=Config(
            signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}
        ),
    )


def _candidate_keys(source_ref: str, task_id: str | None) -> list[str]:
    parsed = urlparse(source_ref)
    raw = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    names = []
    if task_id:
        names.append(f"history/{task_id}/{Path(raw).name}")
    names.extend((raw, Path(raw).name))
    seen = set()
    return [name for name in names if name and not (name in seen or seen.add(name))]


def _extension(source_ref: str, content_type: str | None) -> str:
    suffix = Path(urlparse(source_ref).path).suffix.lower().lstrip(".")
    if suffix:
        return "jpg" if suffix == "jpeg" else suffix
    guessed = mimetypes.guess_extension(content_type or "") or ".bin"
    return guessed.lstrip(".")


def _blob_key(digest: str, extension: str) -> str:
    return f"blobs/sha256/{digest[:2]}/{digest[2:4]}/{digest}.{extension}"


class RateLimiter:
    def __init__(self, bytes_per_second: int):
        self.bytes_per_second = max(1, bytes_per_second)
        self.started = time.monotonic()
        self.bytes = 0
        self._lock = threading.Lock()

    def account(self, size: int) -> None:
        with self._lock:
            self.bytes += size
            expected = self.bytes / self.bytes_per_second
            delay = expected - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)


class SpoolBudget:
    """A process-local reservation ledger backed by the actual .part footprint."""

    def __init__(self, path: Path, *, capacity_bytes: int, pause_bytes: int):
        self.path = path
        self.capacity_bytes = capacity_bytes
        self.pause_bytes = min(pause_bytes, capacity_bytes)
        self._reserved = 0
        self._lock = threading.Lock()

    @property
    def used_bytes(self) -> int:
        disk_bytes = sum(
            item.stat().st_size for item in self.path.glob("*.part") if item.is_file()
        )
        return disk_bytes + self._reserved

    def reserve(self, size: int) -> None:
        if size < 0 or size > self.capacity_bytes:
            raise RuntimeError("object exceeds archive spool capacity")
        with self._lock:
            projected = self.used_bytes + size
            if projected > self.pause_bytes:
                raise RuntimeError("archive spool pause threshold reached")
            if shutil.disk_usage(self.path).free < size:
                raise RuntimeError("archive spool has insufficient free space")
            self._reserved += size

    def release(self, size: int) -> None:
        with self._lock:
            self._reserved = max(0, self._reserved - max(0, size))

    def clean_stale_parts(self, *, older_than_seconds: int = 24 * 3600) -> int:
        cutoff = time.time() - older_than_seconds
        removed = 0
        for item in self.path.glob("*.part"):
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                removed += 1
        return removed


class AdaptiveConcurrencyController:
    """Select 8/16/32 without treating an unattainable bandwidth cap as failure."""

    def __init__(
        self, *, bandwidth_limit_bps: int, window_seconds: int = 900, levels=(8, 16, 32)
    ):
        self.bandwidth_limit_bps = bandwidth_limit_bps
        self.window_seconds = window_seconds
        self.levels = levels
        self.current = levels[0]

    def observe(self, *, bytes_transferred: int, errors: int, elapsed: float) -> int:
        if elapsed < self.window_seconds:
            return self.current
        throughput = bytes_transferred / max(1.0, elapsed)
        if errors:
            self.current = self.levels[max(0, self.levels.index(self.current) - 1)]
        elif throughput < self.bandwidth_limit_bps * 0.8:
            self.current = self.levels[
                min(len(self.levels) - 1, self.levels.index(self.current) + 1)
            ]
        return self.current


def capacity_claim_priority(*, archived_bytes: int, capacity_bytes: int) -> int | None:
    if capacity_bytes <= 0:
        raise RuntimeError("nas_capacity_bytes must be configured")
    ratio = archived_bytes / capacity_bytes
    if ratio >= 0.9:
        return None
    if ratio >= 0.8:
        return 0
    return 100


async def read_archived_bytes(database_url: str) -> int:
    conn = await asyncpg.connect(
        database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )
    try:
        return int(
            await conn.fetchval(
                "select coalesce(sum(byte_size),0)::bigint from analytics_media_blobs"
            )
            or 0
        )
    finally:
        await conn.close()


def archive_one_asset(
    asset: dict,
    task_id: str | None,
    sources: list[dict],
    nas: dict,
    spool: Path,
    limiter: RateLimiter,
    spool_budget: SpoolBudget,
    attempt_sink: list[dict] | None = None,
) -> dict:
    nas_client = _client(nas)
    last_error = "not found in any online source"
    attempts = attempt_sink if attempt_sink is not None else []
    with tempfile.NamedTemporaryFile(dir=spool, suffix=".part", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        found = None
        for source in sources:
            if source.get("type", "s3") == "filesystem":
                for root_value in source.get("roots", []):
                    root = Path(root_value).resolve()
                    for key in _candidate_keys(asset["source_ref"], task_id):
                        candidate = (root / key).resolve()
                        if root not in candidate.parents or not candidate.is_file():
                            attempts.append(
                                {
                                    "source": source["name"],
                                    "candidate_key": str(candidate),
                                    "status": "not_found",
                                }
                            )
                            continue
                        expected_size = candidate.stat().st_size
                        spool_budget.reserve(expected_size)
                        digest = hashlib.sha256()
                        size = 0
                        try:
                            with (
                                candidate.open("rb") as incoming,
                                temp_path.open("wb") as handle,
                            ):
                                while chunk := incoming.read(8 * 1024 * 1024):
                                    handle.write(chunk)
                                    digest.update(chunk)
                                    size += len(chunk)
                                    limiter.account(len(chunk))
                        finally:
                            spool_budget.release(expected_size)
                        attempts.append(
                            {
                                "source": source["name"],
                                "candidate_key": str(candidate),
                                "status": "found",
                            }
                        )
                        found = (
                            source,
                            str(candidate),
                            digest.hexdigest(),
                            size,
                            mimetypes.guess_type(candidate.name)[0],
                        )
                        break
                    if found:
                        break
                if not source.get("roots"):
                    attempts.append(
                        {
                            "source": source["name"],
                            "candidate_key": "(no roots configured)",
                            "status": "source_offline",
                            "error_code": "NOT_CONFIGURED",
                        }
                    )
                if found:
                    break
                continue
            source_client = _client(source)
            for key in _candidate_keys(asset["source_ref"], task_id):
                reserved_size = 0
                try:
                    head = source_client.head_object(Bucket=source["bucket"], Key=key)
                    expected_size = int(head.get("ContentLength") or 0)
                    spool_budget.reserve(expected_size)
                    reserved_size = expected_size
                    response = source_client.get_object(
                        Bucket=source["bucket"], Key=key
                    )
                except ClientError as exc:
                    if reserved_size:
                        spool_budget.release(reserved_size)
                    code = str(exc.response.get("Error", {}).get("Code", ""))
                    if code in {"404", "NoSuchKey", "NotFound"}:
                        attempts.append(
                            {
                                "source": source["name"],
                                "candidate_key": key,
                                "status": "not_found",
                                "error_code": code,
                            }
                        )
                        continue
                    attempts.append(
                        {
                            "source": source["name"],
                            "candidate_key": key,
                            "status": "error",
                            "error_code": code or type(exc).__name__,
                            "detail": str(exc)[:500],
                        }
                    )
                    last_error = f"{source['name']}:{code}"
                    break
                except (EndpointConnectionError, BotoCoreError, OSError) as exc:
                    if reserved_size:
                        spool_budget.release(reserved_size)
                    attempts.append(
                        {
                            "source": source["name"],
                            "candidate_key": key,
                            "status": "source_offline",
                            "error_code": type(exc).__name__,
                            "detail": str(exc)[:500],
                        }
                    )
                    last_error = f"{source['name']}:source_offline"
                    break
                digest = hashlib.sha256()
                size = 0
                try:
                    with temp_path.open("wb") as handle:
                        while chunk := response["Body"].read(8 * 1024 * 1024):
                            handle.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                            limiter.account(len(chunk))
                finally:
                    spool_budget.release(reserved_size)
                found = (
                    source,
                    key,
                    digest.hexdigest(),
                    size,
                    response.get("ContentType"),
                )
                attempts.append(
                    {"source": source["name"], "candidate_key": key, "status": "found"}
                )
                break
            if found:
                break
        if not found:
            if any(item["status"] == "source_offline" for item in attempts):
                raise ConnectionError(last_error)
            raise FileNotFoundError(last_error)

        _source, _key, digest, size, content_type = found
        blob_key = _blob_key(digest, _extension(asset["source_ref"], content_type))
        existing_verified = False
        try:
            existing = nas_client.head_object(Bucket=ARCHIVE_BUCKET, Key=blob_key)
            existing_verified = (
                int(existing.get("ContentLength") or -1) == size
                and (existing.get("Metadata") or {}).get("sha256") == digest
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        if not existing_verified:
            nas_client.upload_file(
                str(temp_path),
                ARCHIVE_BUCKET,
                blob_key,
                ExtraArgs={
                    "ContentType": content_type or "application/octet-stream",
                    "Metadata": {"sha256": digest},
                },
            )
        verify = nas_client.get_object(Bucket=ARCHIVE_BUCKET, Key=blob_key)
        verified_hash = hashlib.sha256()
        verified_size = 0
        while chunk := verify["Body"].read(8 * 1024 * 1024):
            verified_hash.update(chunk)
            verified_size += len(chunk)
        if verified_size != size or verified_hash.hexdigest() != digest:
            raise RuntimeError("NAS read-back checksum mismatch")
        return {
            "role": asset["role"],
            "ordinal": asset["ordinal"],
            "source_ref": asset["source_ref"],
            "found_source": _source["name"],
            "source_key": _key,
            "sha256": digest,
            "byte_size": size,
            "mime_type": content_type,
            "nas_bucket": ARCHIVE_BUCKET,
            "nas_key": blob_key,
            "verified_at": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
        }
    finally:
        temp_path.unlink(missing_ok=True)


def _build_restore_thumbnail(source: Path, media_type: str, output: Path) -> None:
    if media_type == "video":
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "1",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=512:-2",
                "-c:v",
                "libwebp",
                str(output),
            ],
            check=True,
        )
        return
    from PIL import Image

    with Image.open(source) as image:
        image.thumbnail((512, 512))
        image.convert("RGB").save(output, "WEBP", quality=82)


def restore_one_asset(
    asset: dict,
    task_id: str,
    history_type: str | None,
    nas: dict,
    restore_target: dict,
    spool: Path,
    limiter: RateLimiter,
    spool_budget: SpoolBudget,
    *,
    client_factory=_client,
    thumbnail_builder=_build_restore_thumbnail,
) -> dict:
    """Rehydrate one verified NAS blob to R2 and rebuild output thumbnails."""
    nas_client = client_factory(nas)
    target_client = client_factory(restore_target)
    expected_size = int(asset["byte_size"])
    expected_sha = str(asset["sha256"])
    head = nas_client.head_object(Bucket=asset["nas_bucket"], Key=asset["nas_key"])
    if (
        int(head.get("ContentLength") or -1) != expected_size
        or (head.get("Metadata") or {}).get("sha256") != expected_sha
    ):
        raise RuntimeError("NAS restore metadata mismatch")
    spool_budget.reserve(expected_size)
    with tempfile.NamedTemporaryFile(
        dir=spool, suffix=".restore.part", delete=False
    ) as temp:
        temp_path = Path(temp.name)
    try:
        response = nas_client.get_object(
            Bucket=asset["nas_bucket"], Key=asset["nas_key"]
        )
        digest = hashlib.sha256()
        size = 0
        with temp_path.open("wb") as handle:
            while chunk := response["Body"].read(8 * 1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                limiter.account(len(chunk))
        if size != expected_size or digest.hexdigest() != expected_sha:
            raise RuntimeError("NAS restore read-back checksum mismatch")
        target_bucket = restore_target["bucket"]
        r2_keys = sorted(
            plan_archive_asset_restore_keys(
                task_id=task_id,
                source_ref=asset["source_ref"],
            )
        )
        if not r2_keys:
            raise RuntimeError("restore produced no R2 media keys")
        for key in r2_keys:
            target_client.upload_file(
                str(temp_path),
                target_bucket,
                key,
                ExtraArgs={
                    "ContentType": asset.get("mime_type") or "application/octet-stream",
                    "Metadata": {"sha256": expected_sha},
                },
            )
            verified = target_client.head_object(Bucket=target_bucket, Key=key)
            if (
                int(verified.get("ContentLength") or -1) != expected_size
                or (verified.get("Metadata") or {}).get("sha256") != expected_sha
            ):
                raise RuntimeError("R2 restore verification failed")

        thumbnail_keys: list[str] = []
        if asset["role"] == "output":
            thumbnail_keys = sorted(
                plan_archive_thumbnail_restore_keys(
                    task_id=task_id,
                    source_ref=asset["source_ref"],
                    history_type=history_type,
                )
            )
            thumbnail_path = temp_path.with_suffix(".thumb.webp")
            try:
                thumbnail_builder(
                    temp_path,
                    get_archive_media_type(history_type),
                    thumbnail_path,
                )
                thumb_sha = hashlib.sha256(thumbnail_path.read_bytes()).hexdigest()
                thumb_size = thumbnail_path.stat().st_size
                for key in thumbnail_keys:
                    target_client.upload_file(
                        str(thumbnail_path),
                        target_bucket,
                        key,
                        ExtraArgs={
                            "ContentType": "image/webp",
                            "Metadata": {"sha256": thumb_sha},
                        },
                    )
                    verified = target_client.head_object(Bucket=target_bucket, Key=key)
                    if int(verified.get("ContentLength") or -1) != thumb_size:
                        raise RuntimeError("R2 thumbnail verification failed")
            finally:
                thumbnail_path.unlink(missing_ok=True)
        return {
            "role": asset["role"],
            "ordinal": asset["ordinal"],
            "r2_keys": r2_keys,
            "thumbnail_keys": thumbnail_keys,
        }
    finally:
        spool_budget.release(expected_size)
        temp_path.unlink(missing_ok=True)


class CatalogRecorder:
    def __init__(self, database_url: str, worker_id: str):
        self.database_url = database_url.replace(
            "postgresql+asyncpg://", "postgresql://", 1
        )
        self.worker_id = worker_id
        self.conn = None
        self.run_id = None
        self.assets = 0
        self.bytes_transferred = 0
        self._operation_lock = asyncio.Lock()

    async def __aenter__(self):
        self.conn = await asyncpg.connect(self.database_url)
        self.run_id = __import__("uuid").uuid4()
        await self.conn.execute(
            "insert into analytics_media_runs(id,run_type,status,cursor,stats) values($1,'archive','running','{}'::jsonb,jsonb_build_object('worker_id',$2::text))",
            self.run_id,
            self.worker_id,
        )
        return self

    async def _asset_id(self, job: dict, asset: dict) -> int:
        assert self.conn is not None and self.run_id is not None
        row = await self.conn.fetchrow(
            "select id from analytics_media_asset_catalog where history_id=$1 and role=$2 and ordinal=$3",
            job["history_id"],
            asset["role"],
            asset["ordinal"],
        )
        if row is None:
            raise RuntimeError("archive asset is absent from local catalog")
        return row["id"]

    async def ensure_job_assets(self, job: dict) -> None:
        async with self._operation_lock:
            assert self.conn is not None
            rows = await self.conn.fetch(
                "select role,ordinal from analytics_media_asset_catalog where history_id=$1",
                job["history_id"],
            )
            expected = [(asset["role"], asset["ordinal"]) for asset in job["assets"]]
            stored = {(row["role"], row["ordinal"]) for row in rows}
            if len(expected) != len(set(expected)) or set(expected) != stored:
                raise RuntimeError("local archive catalog does not cover claimed job")

    async def record_attempts(self, job: dict, asset: dict, attempts: list[dict]):
        if not attempts:
            return
        async with self._operation_lock:
            asset_id = await self._asset_id(job, asset)
            await self._record_attempts(asset_id, attempts)

    async def _record_attempts(self, asset_id: int, attempts: list[dict]) -> None:
        assert self.conn is not None and self.run_id is not None
        await self.conn.executemany(
            """insert into analytics_media_source_attempts
               (run_id,asset_id,source,candidate_key,status,error_code,detail)
               values($1,$2,$3,$4,$5,$6,$7)""",
            [
                (
                    self.run_id,
                    asset_id,
                    item["source"],
                    item["candidate_key"],
                    item["status"],
                    item.get("error_code"),
                    item.get("detail"),
                )
                for item in attempts
            ],
        )
        if any(item["status"] == "source_offline" for item in attempts):
            await self.conn.execute(
                "update analytics_media_asset_catalog set status='source_offline',last_checked_at=now(),last_error='one or more registered sources are offline' where id=$1 and status<>'archived_verified'",
                asset_id,
            )

    async def record(self, job: dict, asset: dict, receipt: dict, attempts: list[dict]):
        async with self._operation_lock:
            assert self.conn is not None and self.run_id is not None
            asset_id = await self._asset_id(job, asset)
            if attempts:
                await self._record_attempts(asset_id, attempts)
            await self.conn.execute(
                """insert into analytics_media_blobs
                   (sha256,byte_size,mime_type,nas_bucket,nas_key,verified_at)
                   values($1,$2,$3,$4,$5,$6)
                   on conflict(sha256) do update set byte_size=excluded.byte_size,
                     mime_type=excluded.mime_type,nas_bucket=excluded.nas_bucket,
                     nas_key=excluded.nas_key,verified_at=excluded.verified_at""",
                receipt["sha256"],
                receipt["byte_size"],
                receipt.get("mime_type"),
                receipt["nas_bucket"],
                receipt["nas_key"],
                __import__("datetime").datetime.fromisoformat(
                    receipt["verified_at"].replace("Z", "+00:00")
                ),
            )
            await self.conn.execute(
                """update analytics_media_asset_catalog set status='archived_verified',
                   found_source=$2,source_key=$3,sha256=$4,last_checked_at=now(),last_error=null
                   where id=$1""",
                asset_id,
                receipt["found_source"],
                receipt["source_key"],
                receipt["sha256"],
            )
            self.assets += 1
            self.bytes_transferred += int(receipt["byte_size"])

    async def __aexit__(self, exc_type, exc, _tb):
        if self.conn is not None and self.run_id is not None:
            await self.conn.execute(
                """update analytics_media_runs set status=$2,error=$3,completed_at=now(),
                   stats=stats || jsonb_build_object('assets',$4::bigint,'bytes',$5::bigint,'bytes_per_second',
                     case when extract(epoch from now()-started_at)>0 then $5::bigint/extract(epoch from now()-started_at) else 0 end)
                   where id=$1""",
                self.run_id,
                "failed" if exc else "completed",
                str(exc)[:2000] if exc else None,
                self.assets,
                self.bytes_transferred,
            )
            await self.conn.close()


async def run_once(args) -> int:
    clear_proxy_environment()
    config = load_secure_config(Path(args.config))
    validate_source_routes(config["sources"])
    validate_endpoint_route(config["nas"])
    if config.get("restore_target"):
        validate_endpoint_route(config["restore_target"])
    spool = Path(config.get("spool_path", "/var/lib/allbot-media-archive/spool"))
    spool.mkdir(parents=True, exist_ok=True)
    max_spool = int(config.get("max_spool_bytes", 100 * 1024**3))
    pause_spool = int(config.get("pause_spool_bytes", 90 * 1024**3))
    spool_budget = SpoolBudget(spool, capacity_bytes=max_spool, pause_bytes=pause_spool)
    spool_budget.clean_stale_parts(
        older_than_seconds=int(config.get("stale_part_seconds", 24 * 3600))
    )
    if shutil.disk_usage(spool).free < min(max_spool, 10 * 1024**3):
        raise RuntimeError("archive spool has insufficient free space")

    catalog_url = config.get("catalog_database_url", "").strip()
    if not catalog_url:
        raise RuntimeError("catalog_database_url is required")
    archived_bytes = await read_archived_bytes(catalog_url)
    max_priority = capacity_claim_priority(
        archived_bytes=archived_bytes,
        capacity_bytes=int(config.get("nas_capacity_bytes", 0)),
    )
    if max_priority is None:
        raise RuntimeError("NAS usage reached 90%; archive job claiming is stopped")
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    async with httpx.AsyncClient(
        base_url=config["central_api"], headers=headers, timeout=60, trust_env=False
    ) as client:
        restore_response = await client.get(
            "/api/internal/media-archive/restore/jobs",
            params={"worker_id": args.worker_id, "limit": args.limit},
        )
        restore_response.raise_for_status()
        restore_jobs = restore_response.json()["jobs"]
        restored = 0
        if restore_jobs:
            if not config.get("restore_target"):
                raise RuntimeError("restore_target is required when restore jobs exist")
            restored = await _process_restore_jobs(
                args, config, client, restore_jobs, spool, spool_budget
            )
        response = await client.get(
            "/api/internal/media-archive/jobs",
            params=archive_job_claim_params(
                worker_id=args.worker_id,
                limit=args.limit,
                max_priority=max_priority,
                history_ids=config.get("history_ids"),
            ),
        )
        response.raise_for_status()
        jobs = response.json()["jobs"]
        if not jobs:
            args._last_bytes = 0
            return restored
        async with CatalogRecorder(catalog_url, args.worker_id) as catalog:
            archived = await _process_jobs(
                args, config, client, catalog, jobs, spool, spool_budget
            )
            return restored + archived


async def _process_restore_jobs(args, config, client, jobs, spool, spool_budget) -> int:
    limiter = RateLimiter(int(config.get("bandwidth_bytes_per_second", 50 * 1024**2)))
    semaphore = asyncio.Semaphore(args.concurrency)

    async def process(job):
        stop_renewal = asyncio.Event()

        async def renew_lease_periodically():
            interval = int(config.get("lease_renew_interval_seconds", 300))
            while True:
                try:
                    await asyncio.wait_for(stop_renewal.wait(), timeout=interval)
                    return
                except asyncio.TimeoutError:
                    renewal = await client.post(
                        "/api/internal/media-archive/restore/leases/renew",
                        json={
                            "history_id": job["history_id"],
                            "worker_id": args.worker_id,
                            "revision": job["revision"],
                        },
                    )
                    renewal.raise_for_status()

        renewal_task = asyncio.create_task(renew_lease_periodically())
        try:
            restored_assets = []
            for asset in job["assets"]:
                async with semaphore:
                    restored_assets.append(
                        await asyncio.to_thread(
                            restore_one_asset,
                            asset,
                            job["task_id"],
                            job.get("history_type"),
                            config["nas"],
                            config["restore_target"],
                            spool,
                            limiter,
                            spool_budget,
                        )
                    )
            receipt = await client.post(
                "/api/internal/media-archive/restore/receipts",
                json={
                    "history_id": job["history_id"],
                    "worker_id": args.worker_id,
                    "revision": job["revision"],
                    "restored_assets": restored_assets,
                },
            )
            receipt.raise_for_status()
        except Exception as exc:
            args._last_errors = int(getattr(args, "_last_errors", 0)) + 1
            failure = await client.post(
                "/api/internal/media-archive/restore/failures",
                json={
                    "history_id": job["history_id"],
                    "worker_id": args.worker_id,
                    "revision": job["revision"],
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:1000],
                    "retryable": True,
                },
            )
            failure.raise_for_status()
        finally:
            stop_renewal.set()
            await renewal_task

    await asyncio.gather(*(process(job) for job in jobs))
    args._last_bytes = limiter.bytes
    return len(jobs)


async def _process_jobs(
    args, config, client, catalog, jobs, spool, spool_budget
) -> int:
    bandwidth_limit = int(config.get("bandwidth_bytes_per_second", 50 * 1024**2))
    limiter = RateLimiter(bandwidth_limit)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def process(job):
        stop_renewal = asyncio.Event()
        renewal_errors: list[Exception] = []

        async def renew_lease_periodically():
            interval = int(config.get("lease_renew_interval_seconds", 300))
            while True:
                try:
                    await asyncio.wait_for(stop_renewal.wait(), timeout=interval)
                    return
                except asyncio.TimeoutError:
                    try:
                        renewal = await client.post(
                            "/api/internal/media-archive/leases/renew",
                            json={
                                "history_id": job["history_id"],
                                "worker_id": args.worker_id,
                                "revision": job["revision"],
                            },
                        )
                        renewal.raise_for_status()
                    except Exception as exc:
                        renewal_errors.append(exc)
                        return

        renewal_task = asyncio.create_task(renew_lease_periodically())
        try:
            await catalog.ensure_job_assets(job)
            receipts = []
            for asset in job["assets"]:
                attempts: list[dict] = []
                async with semaphore:
                    receipt = await asyncio.to_thread(
                        archive_one_asset,
                        asset,
                        job.get("task_id"),
                        config["sources"],
                        config["nas"],
                        spool,
                        limiter,
                        spool_budget,
                        attempts,
                    )
                await catalog.record(job, asset, receipt, attempts)
                attempts = []
                receipts.append(receipt)
            if renewal_errors:
                raise RuntimeError("archive lease renewal failed") from renewal_errors[
                    0
                ]
            result = await client.post(
                "/api/internal/media-archive/receipts",
                json={
                    "history_id": job["history_id"],
                    "worker_id": args.worker_id,
                    "revision": job["revision"],
                    "receipts": receipts,
                },
            )
            result.raise_for_status()
        except Exception as exc:
            args._last_errors = getattr(args, "_last_errors", 0) + 1
            if "asset" in locals() and "attempts" in locals() and attempts:
                try:
                    await catalog.record_attempts(job, asset, attempts)
                except Exception:
                    pass
            failure = await client.post(
                "/api/internal/media-archive/failures",
                json={
                    "history_id": job["history_id"],
                    "worker_id": args.worker_id,
                    "revision": job["revision"],
                    "error_code": type(exc).__name__,
                    "message": str(exc)[:1000],
                    "retryable": not isinstance(exc, FileNotFoundError),
                },
            )
            failure.raise_for_status()
        finally:
            stop_renewal.set()
            await renewal_task

    await asyncio.gather(*(process(job) for job in jobs))
    args._last_bytes = limiter.bytes
    return len(jobs)


async def run(args) -> int:
    if not args.drain:
        return await run_once(args)
    config = load_secure_config(Path(args.config))
    controller = AdaptiveConcurrencyController(
        bandwidth_limit_bps=int(config.get("bandwidth_bytes_per_second", 50 * 1024**2)),
        window_seconds=int(config.get("adaptive_window_seconds", 900)),
    )
    total = 0
    window_started = time.monotonic()
    window_bytes = 0
    window_errors = 0
    while True:
        args.concurrency = controller.current
        args._last_bytes = 0
        args._last_errors = 0
        processed = await run_once(args)
        total += processed
        window_bytes += args._last_bytes
        window_errors += args._last_errors
        elapsed = time.monotonic() - window_started
        if elapsed >= controller.window_seconds:
            controller.observe(
                bytes_transferred=window_bytes,
                errors=window_errors,
                elapsed=elapsed,
            )
            window_started = time.monotonic()
            window_bytes = 0
            window_errors = 0
        if processed == 0:
            await asyncio.sleep(max(5, int(config.get("idle_poll_seconds", 30))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        required=True,
        help="0600 JSON config containing source/NAS credentials",
    )
    parser.add_argument("--worker-id", default=socket.gethostname())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--drain", action="store_true", help="run as a durable polling worker"
    )
    args = parser.parse_args()
    print(f"processed {asyncio.run(run(args))} archive jobs")


if __name__ == "__main__":
    main()
