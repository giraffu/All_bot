#!/usr/bin/env python3
"""History-row-driven, resumable R2 media migration ledger.

The planner addresses only keys referenced by frozen History rows.  It deliberately
has no bucket enumeration or object removal capability.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, BinaryIO, Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlsplit, urlunsplit
import uuid

import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.media_archive_catalog import CATALOG_DDL  # noqa: E402
from shared.r2_retention_contract import (  # noqa: E402
    build_task_input_key,
    build_task_result_key,
)
from src.core.media_archive import (  # noqa: E402
    extract_history_media_assets,
    media_manifest_hash,
)


BUCKET = "user-data-prod"
CHUNK_SIZE = 4 * 1024 * 1024
MAX_DIAGNOSTICS = 100

MIGRATION_DDL = """
create table if not exists analytics_history_media_migration_runs (
    id uuid primary key,
    history_watermark integer not null check (history_watermark >= 0),
    status text not null check (status in ('running','paused','completed','failed')),
    phase text not null,
    cursor_history_id integer not null default 0,
    sha_bytes_read bigint not null default 0,
    error text,
    started_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create table if not exists analytics_history_media_r2_migrations (
    id bigserial primary key,
    run_id uuid not null references analytics_history_media_migration_runs(id),
    catalog_asset_id bigint not null references analytics_media_asset_catalog(id),
    history_id integer not null,
    history_manifest_sha256 char(64) not null,
    role text not null,
    ordinal integer not null,
    original_ref text not null,
    registry_task_id text,
    backend_task_id text,
    target_key text,
    source_name text,
    source_key text,
    byte_size bigint,
    source_sha256 char(64),
    target_sha256 char(64),
    source_last_modified timestamptz,
    status text not null check (status in (
      'pending_probe','copy_required','target_verified','copied_verified',
      'target_conflict','source_missing','source_offline','blocked','unresolved','failed'
    )),
    error_code text,
    error_detail text,
    copy_plan_sha256 char(64),
    switch_plan_sha256 char(64),
    copy_completed_at timestamptz,
    switch_completed_at timestamptz,
    target_checked_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (run_id, history_id, role, ordinal)
);
create index if not exists ix_history_media_migration_status
  on analytics_history_media_r2_migrations(run_id, status, history_id);
create table if not exists analytics_history_media_object_facts (
    source_name text not null,
    object_key text not null,
    byte_size bigint not null,
    last_modified timestamptz not null,
    sha256 char(64) not null,
    verified_at timestamptz not null default now(),
    primary key (source_name, object_key)
);
create table if not exists analytics_history_media_migration_plans (
    plan_sha256 char(64) primary key,
    run_id uuid not null references analytics_history_media_migration_runs(id),
    plan_type text not null check (plan_type in ('copy','switch')),
    rowset_sha256 char(64) not null,
    manifest jsonb not null,
    created_at timestamptz not null default now(),
    unique (run_id, plan_type, rowset_sha256)
);
alter table analytics_history_media_r2_migrations
  add column if not exists target_checked_at timestamptz;
"""

BACKEND_BATCH_SQL = """
select registry_task_id,min(backend_task_id) backend_task_id,
       count(distinct backend_task_id) backend_count
  from private_bot_task_submissions
 where registry_task_id = any($1::text[]) and backend_task_id is not null
 group by registry_task_id
"""

SEED_STAGE_DDL = """
create temp table if not exists history_media_migration_seed_stage (
    run_id uuid not null,
    catalog_asset_id bigint not null,
    history_id integer not null,
    history_manifest_sha256 char(64) not null,
    role text not null,
    ordinal integer not null,
    original_ref text not null,
    registry_task_id text,
    backend_task_id text,
    target_key text,
    status text not null,
    error_code text
) on commit delete rows
"""

SEED_STAGE_INSERT_SQL = """
insert into analytics_history_media_r2_migrations(
    run_id,catalog_asset_id,history_id,history_manifest_sha256,role,ordinal,
    original_ref,registry_task_id,backend_task_id,target_key,status,error_code)
select run_id,catalog_asset_id,history_id,history_manifest_sha256,role,ordinal,
       original_ref,registry_task_id,backend_task_id,target_key,status,error_code
  from history_media_migration_seed_stage
on conflict(run_id,history_id,role,ordinal) do nothing
"""


@dataclass(frozen=True)
class AssetIdentity:
    history_id: int
    role: str
    ordinal: int
    source_ref: str


@dataclass(frozen=True)
class ObjectFact:
    source: str
    key: str
    byte_size: int
    last_modified: datetime
    sha256: str


class SourceFactCache:
    """Process-local full-digest cache keyed by immutable HEAD identity."""

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str, int, datetime], str] = {}

    def remember(
        self,
        *,
        source: str,
        key: str,
        byte_size: int,
        last_modified: datetime,
        sha256: str,
    ) -> None:
        self._facts[(source, key, byte_size, last_modified)] = sha256

    def lookup(
        self,
        *,
        source: str,
        key: str,
        byte_size: int,
        last_modified: datetime,
    ) -> str | None:
        return self._facts.get((source, key, byte_size, last_modified))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=lambda item: item.isoformat()
        if isinstance(item, datetime)
        else str(item),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def classify_reference(reference: str) -> str:
    raw = str(reference or "").strip()
    parsed = urlparse(raw)
    if not raw or parsed.scheme.lower() in {"data", "ftp", "file"}:
        return "blocked"
    if parsed.scheme.lower() in {"http", "https"}:
        return "blocked"
    if parsed.scheme:
        return "blocked"
    return "managed"


def history_assets_from_record(record: Any) -> list[Any]:
    values = dict(record)
    extras = values.get("extra_outputs")
    if isinstance(extras, str):
        try:
            extras = json.loads(extras)
        except json.JSONDecodeError:
            extras = {}
    values["extra_outputs"] = extras if isinstance(extras, dict) else {}
    return extract_history_media_assets(SimpleNamespace(**values))


def _source_name(reference: str) -> str:
    parsed = urlparse(str(reference or ""))
    return PurePosixPath(parsed.path if parsed.scheme else reference).name or "media.bin"


def build_standard_target(
    asset: AssetIdentity,
    *,
    registry_task_id: str | None,
    backend_task_id: str | None,
) -> str | None:
    try:
        if asset.role == "input":
            if not registry_task_id:
                return None
            return build_task_input_key(
                task_id=registry_task_id,
                ordinal=asset.ordinal,
                source_name=_source_name(asset.source_ref),
            )
        if not backend_task_id:
            return None
        role = "primary" if asset.role == "output" else asset.role
        return build_task_result_key(
            task_id=backend_task_id,
            source_name=_source_name(asset.source_ref),
            role=role,
            ordinal=asset.ordinal,
        )
    except ValueError:
        return None


def build_candidate_keys(source_ref: str, registry_task_id: str | None) -> tuple[str, ...]:
    parsed = urlparse(str(source_ref or "").strip())
    raw = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme.lower() in {"http", "https"}
        else str(source_ref or "").strip().lstrip("/")
    )
    basename = PurePosixPath(raw).name
    candidates = [raw]
    if registry_task_id and basename:
        candidates.append(f"history/{registry_task_id}/{basename}")
    candidates.append(basename)
    return tuple(dict.fromkeys(item for item in candidates if item))


def hash_body(body: BinaryIO, *, chunk_size: int = CHUNK_SIZE) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_size = 0
    while chunk := body.read(chunk_size):
        digest.update(chunk)
        byte_size += len(chunk)
    return digest.hexdigest(), byte_size


def evaluate_missing_round(
    *,
    statuses: Iterable[str],
    previous_rounds: int,
    first_missing_at: datetime | None,
    now: datetime,
) -> tuple[str, int, datetime | None]:
    values = tuple(statuses)
    if not values or any(value != "not_found" for value in values):
        state = "source_offline" if "source_offline" in values else "blocked"
        return state, previous_rounds, first_missing_at
    first = first_missing_at or now
    rounds = previous_rounds + 1
    if rounds >= 2 and now - first >= timedelta(hours=24):
        return "confirmed_lost", rounds, first
    return "provisional_missing", rounds, first


def classify_target_status(
    *, source_sha256: str, target_sha256: str | None
) -> tuple[str, str | None]:
    if target_sha256 is None:
        return "copy_required", None
    if target_sha256 == source_sha256:
        return "target_verified", None
    return "target_conflict", "TARGET_SHA256_CONFLICT"


def validate_resume_identity(
    *, stored_watermark: int, requested_watermark: int | None
) -> int:
    if requested_watermark is not None and requested_watermark != stored_watermark:
        raise ValueError("resume identity does not match frozen History watermark")
    return stored_watermark


PLAN_ROW_FIELDS = (
    "history_id",
    "role",
    "ordinal",
    "target_key",
    "source_sha256",
    "target_sha256",
    "source_name",
    "source_key",
    "source_last_modified",
    "byte_size",
    "status",
    "history_manifest_sha256",
    "original_ref",
)


def _plan_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in PLAN_ROW_FIELDS if key in row}


def _plan_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (_plan_row(row) for row in rows),
        key=lambda row: (
            int(row["history_id"]),
            str(row["role"]),
            int(row["ordinal"]),
        ),
    )


class StreamingJsonArraySha256:
    """Hash a canonical JSON array without retaining its rows."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self._digest.update(b"[")
        self._count = 0

    def add(self, row: dict[str, Any]) -> None:
        if self._count:
            self._digest.update(b",")
        self._digest.update(_canonical_json(row))
        self._count += 1

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"]")
        return digest.hexdigest()

    @property
    def count(self) -> int:
        return self._count


async def _stream_plan_rowset(
    conn: asyncpg.Connection,
    query: str,
    *params: Any,
    copy_plan_sha256: str | None = None,
) -> tuple[str, int, Counter[str], Counter[str], list[dict[str, Any]]]:
    digest = StreamingJsonArraySha256()
    counts: Counter[str] = Counter()
    byte_counts: Counter[str] = Counter()
    diagnostics: list[dict[str, Any]] = []
    async with conn.transaction():
        async for record in conn.cursor(query, *params, prefetch=1000):
            raw = dict(record)
            if copy_plan_sha256 and raw.get("copy_plan_sha256") == copy_plan_sha256:
                raw["status"] = "copy_required"
                raw["target_sha256"] = None
            row = _plan_row(raw)
            digest.add(row)
            status = str(row.get("status") or "unknown")
            counts[status] += 1
            byte_counts[status] += int(row.get("byte_size") or 0)
            if (
                len(diagnostics) < MAX_DIAGNOSTICS
                and status
                in {
                    "blocked",
                    "unresolved",
                    "target_conflict",
                    "source_offline",
                    "source_missing",
                    "failed",
                }
            ):
                diagnostics.append(
                    {
                        "asset": hashlib.sha256(
                            f"{row['history_id']}:{row['role']}:{row['ordinal']}".encode()
                        ).hexdigest()[:16],
                        "status": status,
                        "error_code": raw.get("error_code"),
                    }
                )
    return digest.hexdigest(), digest.count, counts, byte_counts, diagnostics


def build_copy_plan(
    *,
    run_id: str,
    history_watermark: int,
    rows: Iterable[dict[str, Any]],
    sha_bytes_read: int,
    diagnostics: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    bound_rows = _plan_rows(rows)
    counts = Counter(str(row["status"]) for row in bound_rows)
    byte_counts: Counter[str] = Counter()
    for row in bound_rows:
        byte_counts[str(row["status"])] += int(row.get("byte_size") or 0)
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-copy-plan/v1",
        "run_id": run_id,
        "history_watermark": history_watermark,
        "counts": dict(sorted(counts.items())),
        "bytes": dict(sorted(byte_counts.items())),
        "sha_bytes_read": int(sha_bytes_read),
        "diagnostics": list(diagnostics)[:MAX_DIAGNOSTICS],
        "rowset_sha256": _sha256_json(bound_rows),
    }
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


def build_switch_plan(
    *, run_id: str, history_watermark: int, rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    eligible = _plan_rows(rows)
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-switch-plan/v1",
        "run_id": run_id,
        "history_watermark": history_watermark,
        "count": len(eligible),
        "bytes": sum(int(row.get("byte_size") or 0) for row in eligible),
        "rowset_sha256": _sha256_json(eligible),
    }
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


def _copy_rowset_sha(rows: Iterable[dict[str, Any]], plan_sha: str) -> str:
    normalized = []
    for original in rows:
        row = dict(original)
        if row.get("copy_plan_sha256") == plan_sha:
            row["status"] = "copy_required"
            row["target_sha256"] = None
        normalized.append(row)
    return _sha256_json(_plan_rows(normalized))


def validate_copy_gate(
    *,
    expected_plan_sha256: str,
    supplied_plan_sha256: str,
    confirmation: str,
) -> None:
    if supplied_plan_sha256 != expected_plan_sha256 or confirmation != (
        f"COPY_HISTORY_MEDIA_{expected_plan_sha256}"
    ):
        raise ValueError("exact copy plan SHA and confirmation are required")


def validate_switch_gate(
    *,
    expected_plan_sha256: str,
    supplied_plan_sha256: str,
    expected_manifest_sha256: str,
    actual_manifest_sha256: str,
    confirmation: str,
) -> None:
    if supplied_plan_sha256 != expected_plan_sha256 or confirmation != (
        f"SWITCH_HISTORY_MEDIA_{expected_plan_sha256}"
    ):
        raise ValueError("exact switch plan SHA and confirmation are required")
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise ValueError("History media manifest changed")


def _dsn(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def normalize_asyncpg_dsn(value: str) -> tuple[str, str | None]:
    parsed = urlsplit(value.replace("postgresql+asyncpg://", "postgresql://", 1))
    query = parse_qsl(parsed.query, keep_blank_values=True)
    ssl_value = next((item for key, item in query if key == "ssl"), None)
    clean_query = urlencode([(key, item) for key, item in query if key != "ssl"])
    clean = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, clean_query, parsed.fragment)
    )
    return clean, "require" if ssl_value else None


async def _connect_env(name: str) -> asyncpg.Connection:
    dsn, ssl_mode = normalize_asyncpg_dsn(_dsn(name))
    return await asyncpg.connect(dsn, ssl=ssl_mode)


def _load_secure_config(path: Path) -> dict[str, Any]:
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise PermissionError("migration config must be a current-user-owned 0600 file")
    return json.loads(path.read_text(encoding="utf-8"))


def _s3_client(config: dict[str, Any]):
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


def _not_found(exc: ClientError) -> bool:
    code = str((exc.response or {}).get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _normalize_modified(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("object HEAD did not return LastModified")
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _head_s3(client, bucket: str, key: str) -> tuple[int, datetime] | None:
    try:
        response = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if _not_found(exc):
            return None
        raise
    return int(response["ContentLength"]), _normalize_modified(response["LastModified"])


def _read_s3_sha(client, bucket: str, key: str) -> tuple[str, int]:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        return hash_body(body)
    finally:
        body.close()


def _filesystem_path(config: dict[str, Any], key: str) -> Path:
    root = Path(config["root"]).resolve(strict=True)
    candidate = (root / key).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise RuntimeError("filesystem source key escapes configured root")
    return candidate


def _head_source(
    config: dict[str, Any], client: Any, key: str
) -> tuple[int, datetime] | None:
    if config.get("type", "s3") == "filesystem":
        path = _filesystem_path(config, key)
        try:
            info = path.stat()
        except FileNotFoundError:
            return None
        if not path.is_file():
            return None
        return int(info.st_size), datetime.fromtimestamp(
            info.st_mtime, tz=timezone.utc
        )
    return _head_s3(client, str(config["bucket"]), key)


def _read_source_sha(
    config: dict[str, Any], client: Any, key: str
) -> tuple[str, int]:
    if config.get("type", "s3") == "filesystem":
        with _filesystem_path(config, key).open("rb") as body:
            return hash_body(body)
    return _read_s3_sha(client, str(config["bucket"]), key)


def _open_source_body(config: dict[str, Any], client: Any, key: str) -> BinaryIO:
    if config.get("type", "s3") == "filesystem":
        return _filesystem_path(config, key).open("rb")
    return client.get_object(Bucket=str(config["bucket"]), Key=key)["Body"]


async def _ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(CATALOG_DDL)
    await conn.execute(MIGRATION_DDL)


async def _seed(args: argparse.Namespace) -> None:
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await _ensure_schema(conn)
        await conn.execute(SEED_STAGE_DDL)
        if args.resume_run_id:
            run_id = uuid.UUID(args.resume_run_id)
            row = await conn.fetchrow(
                "select history_watermark,phase from analytics_history_media_migration_runs where id=$1",
                run_id,
            )
            if not row:
                raise RuntimeError("unknown migration run")
            watermark = validate_resume_identity(
                stored_watermark=int(row["history_watermark"]),
                requested_watermark=args.history_watermark,
            )
            start = int(
                await conn.fetchval(
                    "select cursor_history_id from analytics_history_media_migration_runs where id=$1",
                    run_id,
                )
            ) + 1
        else:
            watermark = int(
                args.history_watermark
                if args.history_watermark is not None
                else await conn.fetchval("select coalesce(max(id),0) from history")
            )
            run_id = uuid.uuid4()
            start = 1
            await conn.execute(
                """insert into analytics_media_runs(id,run_type,status,cursor)
                   values($1,'history-r2-migration','running',
                          jsonb_build_object('history_watermark',$2::integer))""",
                run_id,
                watermark,
            )
            await conn.execute(
                "insert into analytics_history_media_migration_runs(id,history_watermark,status,phase) values($1,$2,'running','seed')",
                run_id,
                watermark,
            )

        for batch_start in range(start, watermark + 1, args.batch_size):
            batch_end = min(watermark, batch_start + args.batch_size - 1)
            histories = await conn.fetch(
                """select id,task_id,user_id,created_at,input_file,output_file,extra_outputs
                     from history where id between $1 and $2 order by id""",
                batch_start,
                batch_end,
            )
            registry_ids = sorted(
                {
                    str(history["task_id"]).strip()
                    for history in histories
                    if str(history["task_id"] or "").strip()
                }
            )
            backend_rows = (
                await conn.fetch(BACKEND_BATCH_SQL, registry_ids)
                if registry_ids
                else []
            )
            backend_map = {
                str(row["registry_task_id"]): (
                    str(row["backend_task_id"]), int(row["backend_count"])
                )
                for row in backend_rows
            }
            catalog_rows = await conn.fetch(
                """select id,history_id,role,ordinal
                     from analytics_media_asset_catalog
                    where history_id between $1 and $2""",
                batch_start,
                batch_end,
            )
            catalog_ids = {
                (int(row["history_id"]), str(row["role"]), int(row["ordinal"])): int(
                    row["id"]
                )
                for row in catalog_rows
            }
            prepared: list[tuple[Any, ...]] = []
            missing_catalog: list[tuple[Any, ...]] = []
            for history in histories:
                assets = history_assets_from_record(history)
                manifest_sha = media_manifest_hash(assets)
                registry_id = str(history["task_id"] or "").strip() or None
                backend = backend_map.get(registry_id or "")
                backend_id = backend[0] if backend and backend[1] == 1 else None
                backend_ambiguous = bool(backend and backend[1] > 1)
                for asset in assets:
                    identity = AssetIdentity(
                        asset.history_id, asset.role, asset.ordinal, asset.source_ref
                    )
                    target = build_standard_target(
                        identity,
                        registry_task_id=registry_id,
                        backend_task_id=backend_id,
                    )
                    ref_class = classify_reference(asset.source_ref)
                    status = "pending_probe"
                    error = None
                    if ref_class == "blocked":
                        status, error = "blocked", "EXTERNAL_OR_UNMANAGED_REFERENCE"
                    elif target is None:
                        status = "unresolved"
                        error = (
                            "AMBIGUOUS_BACKEND_TASK_ID"
                            if backend_ambiguous and asset.role != "input"
                            else "MISSING_EXPLICIT_TASK_ID"
                        )
                    identity_key = (asset.history_id, asset.role, asset.ordinal)
                    if identity_key not in catalog_ids:
                        missing_catalog.append(
                            (
                                asset.history_id,
                                registry_id,
                                history["user_id"],
                                history["created_at"],
                                asset.role,
                                asset.ordinal,
                                asset.source_ref,
                            )
                        )
                    prepared.append(
                        (
                            identity_key,
                            manifest_sha,
                            asset.source_ref,
                            registry_id,
                            backend_id,
                            target,
                            status,
                            error,
                        )
                    )
            async with conn.transaction():
                if missing_catalog:
                    await conn.executemany(
                        """insert into analytics_media_asset_catalog
                             (history_id,task_id,user_id,history_created_at,role,
                              ordinal,original_ref,temperature)
                           values($1,$2,$3,$4,$5,$6,$7,'unknown')
                           on conflict(history_id,role,ordinal) do nothing""",
                        missing_catalog,
                    )
                    refreshed = await conn.fetch(
                        """select id,history_id,role,ordinal
                             from analytics_media_asset_catalog
                            where history_id between $1 and $2""",
                        batch_start,
                        batch_end,
                    )
                    catalog_ids = {
                        (
                            int(row["history_id"]),
                            str(row["role"]),
                            int(row["ordinal"]),
                        ): int(row["id"])
                        for row in refreshed
                    }
                stage_records = [
                    (
                        run_id,
                        catalog_ids[identity_key],
                        identity_key[0],
                        manifest_sha,
                        identity_key[1],
                        identity_key[2],
                        source_ref,
                        registry_id,
                        backend_id,
                        target,
                        status,
                        error,
                    )
                    for (
                        identity_key,
                        manifest_sha,
                        source_ref,
                        registry_id,
                        backend_id,
                        target,
                        status,
                        error,
                    ) in prepared
                ]
                if stage_records:
                    await conn.copy_records_to_table(
                        "history_media_migration_seed_stage",
                        records=stage_records,
                        columns=(
                            "run_id",
                            "catalog_asset_id",
                            "history_id",
                            "history_manifest_sha256",
                            "role",
                            "ordinal",
                            "original_ref",
                            "registry_task_id",
                            "backend_task_id",
                            "target_key",
                            "status",
                            "error_code",
                        ),
                    )
                    await conn.execute(SEED_STAGE_INSERT_SQL)
                await conn.execute(
                    """update analytics_history_media_migration_runs
                          set cursor_history_id=$2,updated_at=now() where id=$1""",
                    run_id,
                    batch_end,
                )
        await conn.execute(
            "update analytics_history_media_migration_runs set status='completed',phase='seed',updated_at=now() where id=$1",
            run_id,
        )
        await conn.execute(
            "update analytics_media_runs set status='completed',completed_at=now() where id=$1",
            run_id,
        )
        print(json.dumps({"run_id": str(run_id), "history_watermark": watermark}))
    except Exception as exc:
        if "run_id" in locals():
            await conn.execute(
                "update analytics_history_media_migration_runs set status='paused',error=$2,updated_at=now() where id=$1",
                run_id,
                str(exc)[:1000],
            )
        raise
    finally:
        await conn.close()


async def _fact_digest(
    conn: asyncpg.Connection,
    cache: SourceFactCache,
    *,
    source: str,
    key: str,
    client: Any,
    source_config: dict[str, Any],
    head: tuple[int, datetime],
) -> tuple[str, int]:
    byte_size, modified = head
    digest = cache.lookup(
        source=source, key=key, byte_size=byte_size, last_modified=modified
    )
    if digest:
        return digest, 0
    digest = await conn.fetchval(
        """select sha256 from analytics_history_media_object_facts
             where source_name=$1 and object_key=$2 and byte_size=$3 and last_modified=$4""",
        source,
        key,
        byte_size,
        modified,
    )
    if digest:
        cache.remember(
            source=source,
            key=key,
            byte_size=byte_size,
            last_modified=modified,
            sha256=str(digest),
        )
        return str(digest), 0
    digest, read_size = await asyncio.to_thread(
        _read_source_sha, source_config, client, key
    )
    if read_size != byte_size:
        raise RuntimeError("OBJECT_CHANGED_DURING_READ")
    await conn.execute(
        """insert into analytics_history_media_object_facts
             (source_name,object_key,byte_size,last_modified,sha256)
           values($1,$2,$3,$4,$5)
           on conflict(source_name,object_key) do update set
             byte_size=excluded.byte_size,last_modified=excluded.last_modified,
             sha256=excluded.sha256,verified_at=now()""",
        source,
        key,
        byte_size,
        modified,
        digest,
    )
    cache.remember(
        source=source,
        key=key,
        byte_size=byte_size,
        last_modified=modified,
        sha256=digest,
    )
    return digest, read_size


async def _probe_target_rows(
    conn: asyncpg.Connection,
    rows: list[asyncpg.Record],
    *,
    target_client: Any,
    concurrency: int,
) -> int:
    """Probe unique standard targets concurrently; persist results serially."""
    if not 1 <= concurrency <= 128:
        raise ValueError("target concurrency must be between 1 and 128")
    grouped: dict[str, list[asyncpg.Record]] = {}
    for row in rows:
        grouped.setdefault(str(row["target_key"]), []).append(row)
    semaphore = asyncio.Semaphore(concurrency)

    async def inspect(key: str) -> tuple[str, tuple[int, datetime] | None, str | None, int]:
        async with semaphore:
            head = await asyncio.to_thread(_head_s3, target_client, BUCKET, key)
            if head is None:
                return key, None, None, 0
            digest, read_size = await asyncio.to_thread(
                _read_s3_sha, target_client, BUCKET, key
            )
            if read_size != int(head[0]):
                raise RuntimeError("TARGET_CHANGED_DURING_READ")
            return key, head, digest, read_size

    results = await asyncio.gather(*(inspect(key) for key in grouped))
    bytes_read = 0
    for key, head, digest, read_size in results:
        linked_rows = grouped[key]
        if head is None or digest is None:
            await conn.executemany(
                """update analytics_history_media_r2_migrations set
                     target_checked_at=now(),error_code='TARGET_MISSING_PENDING_RECOVERY',
                     error_detail=null,updated_at=now() where id=$1""",
                [(row["id"],) for row in linked_rows],
            )
            continue
        bytes_read += read_size
        byte_size, modified = head
        await conn.execute(
            """insert into analytics_history_media_object_facts
                 (source_name,object_key,byte_size,last_modified,sha256)
               values('target:user-data-prod',$1,$2,$3,$4)
               on conflict(source_name,object_key) do update set
                 byte_size=excluded.byte_size,last_modified=excluded.last_modified,
                 sha256=excluded.sha256,verified_at=now()""",
            key,
            byte_size,
            modified,
            digest,
        )
        await conn.executemany(
            """update analytics_history_media_r2_migrations set
                 source_name='target:user-data-prod',source_key=target_key,
                 byte_size=$2,source_sha256=$3,target_sha256=$3,
                 status='target_verified',target_checked_at=now(),
                 error_code=null,error_detail=null,updated_at=now() where id=$1""",
            [(row["id"], byte_size, digest) for row in linked_rows],
        )
        await conn.executemany(
            """update analytics_media_asset_catalog set status='found',
                 found_source='target:user-data-prod',source_key=$2,
                 last_checked_at=now(),missing_rounds=0,first_missing_at=null,
                 last_error=null where id=$1""",
            [(row["catalog_asset_id"], key) for row in linked_rows],
        )
    return bytes_read


async def _probe(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    target_config = config["target"]
    target_client = _s3_client(target_config)
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    cache = SourceFactCache()
    source_query_errors = 0
    try:
        await _ensure_schema(conn)
        registered = await conn.fetch(
            """select source,priority from analytics_media_sources
                 where enabled and retired_at is null order by priority,source"""
        )
        configured = {
            str(item["name"]): item
            for item in config.get("sources", [])
            if item.get("enabled", True)
        }
        missing_configs = [
            str(row["source"])
            for row in registered
            if str(row["source"]) not in configured
        ]
        if missing_configs:
            raise RuntimeError(
                "enabled source missing from secure config: "
                + ",".join(missing_configs)
            )
        sources = [configured[str(row["source"])] for row in registered]
        nas_config = config.get("nas_archive")
        clients = {
            str(item["name"]): (
                None if item.get("type", "s3") == "filesystem" else _s3_client(item)
            )
            for item in sources
        }
        run = await conn.fetchrow(
            "select history_watermark from analytics_history_media_migration_runs where id=$1",
            run_id,
        )
        if not run:
            raise RuntimeError("unknown migration run")
        phase = (
            "probe-target"
            if args.target_only
            else "probe-receipts"
            if args.receipt_only
            else "probe"
        )
        await conn.execute(
            "update analytics_history_media_migration_runs set status='running',phase=$2,error=null,updated_at=now() where id=$1",
            run_id,
            phase,
        )
        if args.target_only:
            rows = await conn.fetch(
                """select m.* from analytics_history_media_r2_migrations m
                     where m.run_id=$1 and m.target_checked_at is null
                       and m.status in ('pending_probe','source_offline','failed')
                     order by m.history_id,m.role,m.ordinal limit $2""",
                run_id,
                args.limit,
            )
        elif args.receipt_only:
            rows = await conn.fetch(
                """select m.* from analytics_history_media_r2_migrations m
                     join analytics_media_asset_catalog a on a.id=m.catalog_asset_id
                     join analytics_media_blobs b on b.sha256=a.sha256
                    where m.run_id=$1 and m.target_checked_at is not null
                      and m.status in ('pending_probe','source_offline','failed')
                      and a.status='archived_verified'
                    order by m.history_id,m.role,m.ordinal limit $2""",
                run_id,
                args.limit,
            )
        else:
            rows = await conn.fetch(
                """select m.* from analytics_history_media_r2_migrations m
                     where m.run_id=$1 and (
                       m.status='pending_probe'
                       or ($3::boolean and m.status in ('source_missing','source_offline','failed')
                           and m.updated_at <= now() - make_interval(hours => $4::integer))
                     )
                     order by m.history_id,m.role,m.ordinal limit $2""",
                run_id,
                args.limit,
                args.recheck_deferred,
                args.deferred_min_age_hours,
            )
        probed_count = len(rows)
        bytes_read = 0
        if args.target_only:
            bytes_read = await _probe_target_rows(
                conn,
                rows,
                target_client=target_client,
                concurrency=args.target_concurrency,
            )
            rows = []
        for row in rows:
            target_key = str(row["target_key"])
            target_head = None
            target_sha = row["target_sha256"]
            if not args.receipt_only:
                target_head = await asyncio.to_thread(
                    _head_s3, target_client, BUCKET, target_key
                )
            if target_head:
                target_sha, consumed = await _fact_digest(
                    conn,
                    cache,
                    source="target:user-data-prod",
                    key=target_key,
                    client=target_client,
                    source_config=target_config,
                    head=target_head,
                )
                bytes_read += consumed
                await conn.execute(
                    """update analytics_history_media_r2_migrations set
                         source_name='target:user-data-prod',source_key=target_key,
                         byte_size=$2,source_sha256=$3,target_sha256=$3,
                         status='target_verified',target_checked_at=now(),
                         error_code=null,error_detail=null,updated_at=now() where id=$1""",
                    row["id"],
                    int(target_head[0]),
                    target_sha,
                )
                continue
            if args.target_only:
                await conn.execute(
                    """update analytics_history_media_r2_migrations set
                         target_checked_at=now(),error_code='TARGET_MISSING_PENDING_RECOVERY',
                         error_detail=null,updated_at=now() where id=$1""",
                    row["id"],
                )
                continue

            attempts: list[str] = []
            found: tuple[str, str, tuple[int, datetime], str] | None = None
            receipt = await conn.fetchrow(
                """select b.nas_key,b.byte_size,b.sha256
                     from analytics_media_asset_catalog a
                     join analytics_media_blobs b on b.sha256=a.sha256
                    where a.id=$1 and a.status='archived_verified'""",
                row["catalog_asset_id"],
            )
            if receipt:
                receipt_source = str(
                    (nas_config or {}).get("name", "verified-nas-receipt")
                )
                if not nas_config:
                    attempts.append("source_offline")
                    await conn.execute(
                        """insert into analytics_media_source_attempts
                             (run_id,asset_id,source,candidate_key,status,error_code)
                           values($1,$2,$3,$4,'source_offline','NAS_CONFIG_UNAVAILABLE')""",
                        run_id,
                        row["catalog_asset_id"],
                        receipt_source,
                        str(receipt["nas_key"]),
                    )
                else:
                    nas_client = (
                        None
                        if nas_config.get("type", "s3") == "filesystem"
                        else _s3_client(nas_config)
                    )
                    try:
                        nas_head = await asyncio.to_thread(
                            _head_source,
                            nas_config,
                            nas_client,
                            str(receipt["nas_key"]),
                        )
                        if nas_head is None:
                            attempts.append("not_found")
                        elif int(nas_head[0]) != int(receipt["byte_size"]):
                            raise RuntimeError("NAS_RECEIPT_SIZE_MISMATCH")
                        else:
                            nas_sha, consumed = await _fact_digest(
                                conn,
                                cache,
                                source=receipt_source,
                                key=str(receipt["nas_key"]),
                                client=nas_client,
                                source_config=nas_config,
                                head=nas_head,
                            )
                            bytes_read += consumed
                            if nas_sha != str(receipt["sha256"]):
                                raise RuntimeError("NAS_RECEIPT_SHA256_MISMATCH")
                            attempts.append("found")
                            found = (
                                receipt_source,
                                str(receipt["nas_key"]),
                                nas_head,
                                nas_sha,
                            )
                        await conn.execute(
                            """insert into analytics_media_source_attempts
                                 (run_id,asset_id,source,candidate_key,status,error_code)
                               values($1,$2,$3,$4,$5,$6)""",
                            run_id,
                            row["catalog_asset_id"],
                            receipt_source,
                            str(receipt["nas_key"]),
                            "found" if found else "not_found",
                            None,
                        )
                    except Exception as exc:
                        if str(exc) in {
                            "NAS_RECEIPT_SIZE_MISMATCH",
                            "NAS_RECEIPT_SHA256_MISMATCH",
                        }:
                            await conn.execute(
                                """insert into analytics_media_source_attempts
                                     (run_id,asset_id,source,candidate_key,status,error_code,detail)
                                   values($1,$2,$3,$4,'checksum_error','NAS_RECEIPT_MISMATCH',$5)""",
                                run_id,
                                row["catalog_asset_id"],
                                receipt_source,
                                str(receipt["nas_key"]),
                                str(exc),
                            )
                            raise
                        attempts.append("source_offline")
                        await conn.execute(
                            """insert into analytics_media_source_attempts
                                 (run_id,asset_id,source,candidate_key,status,error_code,detail)
                               values($1,$2,$3,$4,'source_offline','NAS_RECEIPT_QUERY_FAILED',$5)""",
                            run_id,
                            row["catalog_asset_id"],
                            receipt_source,
                            str(receipt["nas_key"]),
                            str(exc)[:500],
                        )
                        if args.receipt_only:
                            raise RuntimeError(
                                "SYSTEMIC_NAS_RECEIPT_QUERY_FAILURE"
                            ) from exc
            sources_to_probe = [] if args.receipt_only else sources
            for source in sources_to_probe:
                if found:
                    break
                source_name = str(source["name"])
                client = clients[source_name]
                source_status = "not_found"
                for key in build_candidate_keys(
                    str(row["original_ref"]), row["registry_task_id"]
                ):
                    try:
                        head = await asyncio.to_thread(_head_source, source, client, key)
                    except Exception as exc:
                        source_query_errors += 1
                        source_status = "source_offline"
                        await conn.execute(
                            """insert into analytics_media_source_attempts
                                 (run_id,asset_id,source,candidate_key,status,error_code,detail)
                               values($1,$2,$3,$4,'source_offline','SOURCE_QUERY_FAILED',$5)""",
                            run_id,
                            row["catalog_asset_id"],
                            source_name,
                            key,
                            str(exc)[:500],
                        )
                        if source_query_errors >= args.systemic_error_threshold:
                            raise RuntimeError(
                                "SYSTEMIC_SOURCE_QUERY_FAILURE_THRESHOLD_REACHED"
                            ) from exc
                        break
                    if head is None:
                        await conn.execute(
                            """insert into analytics_media_source_attempts
                                 (run_id,asset_id,source,candidate_key,status)
                               values($1,$2,$3,$4,'not_found')""",
                            run_id,
                            row["catalog_asset_id"],
                            source_name,
                            key,
                        )
                        continue
                    digest, consumed = await _fact_digest(
                        conn,
                        cache,
                        source=source_name,
                        key=key,
                        client=client,
                        source_config=source,
                        head=head,
                    )
                    bytes_read += consumed
                    await conn.execute(
                        """insert into analytics_media_source_attempts
                             (run_id,asset_id,source,candidate_key,status)
                           values($1,$2,$3,$4,'found')""",
                        run_id,
                        row["catalog_asset_id"],
                        source_name,
                        key,
                    )
                    source_status = "found"
                    found = (source_name, key, head, digest)
                    break
                attempts.append(source_status)
                if found:
                    break

            if found:
                source_name, source_key, source_head, source_sha = found
                byte_size, modified = source_head
                status, error = classify_target_status(
                    source_sha256=source_sha, target_sha256=target_sha
                )
                await conn.execute(
                    """update analytics_history_media_r2_migrations set
                         source_name=$2,source_key=$3,byte_size=$4,source_last_modified=$5,
                         source_sha256=$6,target_sha256=$7,status=$8,error_code=$9,
                         target_checked_at=now(),error_detail=null,updated_at=now()
                       where id=$1""",
                    row["id"],
                    source_name,
                    source_key,
                    byte_size,
                    modified,
                    source_sha,
                    target_sha,
                    status,
                    error,
                )
                await conn.execute(
                    """update analytics_media_asset_catalog set status='found',
                         found_source=$2,source_key=$3,last_checked_at=now(),
                         missing_rounds=0,first_missing_at=null,last_error=null where id=$1""",
                    row["catalog_asset_id"],
                    source_name,
                    source_key,
                )
            else:
                catalog = await conn.fetchrow(
                    "select missing_rounds,first_missing_at from analytics_media_asset_catalog where id=$1",
                    row["catalog_asset_id"],
                )
                catalog_status, rounds, first = evaluate_missing_round(
                    statuses=attempts,
                    previous_rounds=int(catalog["missing_rounds"]),
                    first_missing_at=catalog["first_missing_at"],
                    now=datetime.now(timezone.utc),
                )
                migration_status = (
                    "source_missing"
                    if catalog_status in {"provisional_missing", "confirmed_lost"}
                    else catalog_status
                )
                await conn.execute(
                    """update analytics_media_asset_catalog set status=$2,
                         missing_rounds=$3,first_missing_at=$4,last_checked_at=now()
                       where id=$1""",
                    row["catalog_asset_id"],
                    catalog_status,
                    rounds,
                    first,
                )
                await conn.execute(
                    """update analytics_history_media_r2_migrations set status=$2,
                         error_code=$3,target_checked_at=now(),updated_at=now()
                       where id=$1""",
                    row["id"],
                    migration_status,
                    catalog_status.upper(),
                )
        if args.target_only:
            remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and target_checked_at is null
                           and status in ('pending_probe','source_offline','failed')""",
                    run_id,
                )
            )
            remaining_receipts = None
        elif args.receipt_only:
            remaining_receipts = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations m
                         join analytics_media_asset_catalog a on a.id=m.catalog_asset_id
                         join analytics_media_blobs b on b.sha256=a.sha256
                        where m.run_id=$1 and m.target_checked_at is not null
                          and m.status in ('pending_probe','source_offline','failed')
                          and a.status='archived_verified'""",
                    run_id,
                )
            )
            remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and status='pending_probe'""",
                    run_id,
                )
            )
        else:
            remaining_receipts = None
            remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and status='pending_probe'""",
                    run_id,
                )
            )
        await conn.execute(
            """update analytics_history_media_migration_runs set status=$3,
                 phase=$4,sha_bytes_read=sha_bytes_read+$2,updated_at=now() where id=$1""",
            run_id,
            bytes_read,
            "completed"
            if remaining == 0 and not args.receipt_only
            else "running",
            phase,
        )
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "probed": probed_count,
                    "remaining_pending": remaining,
                    "target_only": args.target_only,
                    "receipt_only": args.receipt_only,
                    "remaining_receipts": remaining_receipts,
                    "sha_bytes_read": bytes_read,
                }
            )
        )
    except Exception as exc:
        await conn.execute(
            """update analytics_history_media_migration_runs set status='paused',
                 error=$2,updated_at=now() where id=$1""",
            run_id,
            str(exc)[:1000],
        )
        raise
    finally:
        await conn.close()


def _diagnostic(row: asyncpg.Record) -> dict[str, Any]:
    token = hashlib.sha256(
        f"{row['history_id']}:{row['role']}:{row['ordinal']}".encode()
    ).hexdigest()[:16]
    return {"asset": token, "status": row["status"], "error_code": row["error_code"]}


async def _create_plan(args: argparse.Namespace, *, plan_type: str) -> None:
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    try:
        run = await conn.fetchrow(
            "select history_watermark,sha_bytes_read,status from analytics_history_media_migration_runs where id=$1",
            run_id,
        )
        if not run:
            raise RuntimeError("unknown migration run")
        if plan_type == "copy":
            remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and status='pending_probe'""",
                    run_id,
                )
            )
            if run["status"] == "paused" or (
                remaining and not args.allow_incomplete
            ):
                raise RuntimeError(
                    f"PROBE_NOT_COMPLETE: pending={remaining} run_status={run['status']}"
                )
            query = (
                """select history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256,error_code
                     from analytics_history_media_r2_migrations where run_id=$1
                     order by history_id,role,ordinal"""
            )
            rowset_sha, _count, counts, byte_counts, diagnostics = (
                await _stream_plan_rowset(conn, query, run_id)
            )
            manifest = {
                "schema": "allbot-history-media-r2-copy-plan/v1",
                "run_id": str(run_id),
                "history_watermark": int(run["history_watermark"]),
                "counts": dict(sorted(counts.items())),
                "bytes": dict(sorted(byte_counts.items())),
                "sha_bytes_read": int(run["sha_bytes_read"]),
                "pending_at_freeze": remaining,
                "run_status_at_freeze": str(run["status"]),
                "partial_scope": bool(remaining),
                "diagnostics": diagnostics,
                "rowset_sha256": rowset_sha,
            }
            manifest["plan_sha256"] = _sha256_json(manifest)
        else:
            query = (
                """select history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and status in ('target_verified','copied_verified')
                      and original_ref <> target_key
                    order by history_id,role,ordinal"""
            )
            rowset_sha, count, _counts, byte_counts, _diagnostics = (
                await _stream_plan_rowset(conn, query, run_id)
            )
            manifest = {
                "schema": "allbot-history-media-r2-switch-plan/v1",
                "run_id": str(run_id),
                "history_watermark": int(run["history_watermark"]),
                "count": count,
                "bytes": sum(byte_counts.values()),
                "rowset_sha256": rowset_sha,
            }
            manifest["plan_sha256"] = _sha256_json(manifest)
        plan_sha = manifest["plan_sha256"]
        await conn.execute(
            """insert into analytics_history_media_migration_plans
                 (plan_sha256,run_id,plan_type,rowset_sha256,manifest)
               values($1,$2,$3,$4,$5::jsonb) on conflict(plan_sha256) do nothing""",
            plan_sha,
            run_id,
            plan_type,
            manifest["rowset_sha256"],
            json.dumps(manifest),
        )
        column = "copy_plan_sha256" if plan_type == "copy" else "switch_plan_sha256"
        eligible = "status='copy_required'" if plan_type == "copy" else "status in ('target_verified','copied_verified') and original_ref <> target_key"
        await conn.execute(
            f"update analytics_history_media_r2_migrations set {column}=$2 where run_id=$1 and {eligible}",
            run_id,
            plan_sha,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(json.dumps({"plan_sha256": plan_sha, "manifest": str(output)}))
    finally:
        await conn.close()


async def _load_plan(
    conn: asyncpg.Connection, plan_sha: str, plan_type: str
) -> tuple[uuid.UUID, dict[str, Any]]:
    row = await conn.fetchrow(
        "select run_id,manifest from analytics_history_media_migration_plans where plan_sha256=$1 and plan_type=$2",
        plan_sha,
        plan_type,
    )
    if not row:
        raise RuntimeError("unknown exact plan SHA")
    manifest = (
        json.loads(row["manifest"])
        if isinstance(row["manifest"], str)
        else dict(row["manifest"])
    )
    if _sha256_json({key: value for key, value in manifest.items() if key != "plan_sha256"}) != plan_sha:
        raise RuntimeError("stored plan identity is invalid")
    return row["run_id"], manifest


async def _execute_copy(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    target = config["target"]
    if target.get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    sources = {str(item["name"]): item for item in config.get("sources", [])}
    if config.get("nas_archive"):
        sources[str(config["nas_archive"].get("name", "verified-nas-receipt"))] = config[
            "nas_archive"
        ]
    target_client = _s3_client(target)
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        run_id, manifest = await _load_plan(conn, args.plan_sha256, "copy")
        validate_copy_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        rowset_sha, _count, _counts, _bytes, _diagnostics = (
            await _stream_plan_rowset(
                conn,
                """select history_id,role,ordinal,original_ref,target_key,
                      source_name,source_key,source_last_modified,source_sha256,
                      target_sha256,byte_size,status,history_manifest_sha256,
                      copy_plan_sha256
                 from analytics_history_media_r2_migrations where run_id=$1
                 order by history_id,role,ordinal""",
                run_id,
                copy_plan_sha256=args.plan_sha256,
            )
        )
        if rowset_sha != manifest["rowset_sha256"]:
            raise RuntimeError("copy plan rowset changed")
        rows = await conn.fetch(
            """select * from analytics_history_media_r2_migrations
                 where run_id=$1 and copy_plan_sha256=$2
                   and status in ('copy_required','failed')
                 order by history_id,role,ordinal limit $3""",
            run_id,
            args.plan_sha256,
            args.limit,
        )
        for row in rows:
            try:
                source = sources.get(str(row["source_name"]))
                if not source:
                    raise RuntimeError("planned source is not enabled in this config")
                source_client = (
                    None
                    if source.get("type", "s3") == "filesystem"
                    else _s3_client(source)
                )
                head = await asyncio.to_thread(
                    _head_source, source, source_client, str(row["source_key"])
                )
                if (
                    not head
                    or int(head[0]) != int(row["byte_size"])
                    or head[1] != row["source_last_modified"]
                ):
                    raise RuntimeError("planned source changed before copy")
                existing_target = await asyncio.to_thread(
                    _head_s3, target_client, BUCKET, str(row["target_key"])
                )
                if existing_target:
                    existing_sha, existing_size = await asyncio.to_thread(
                        _read_s3_sha,
                        target_client,
                        BUCKET,
                        str(row["target_key"]),
                    )
                    if (
                        existing_size != int(row["byte_size"])
                        or existing_sha != row["source_sha256"]
                    ):
                        raise RuntimeError("target appeared with conflicting SHA")
                    await conn.execute(
                        """update analytics_history_media_r2_migrations set
                             status='target_verified',target_sha256=$2,
                             copy_completed_at=now(),updated_at=now()
                           where id=$1""",
                        row["id"],
                        existing_sha,
                    )
                    await conn.execute(
                        """update analytics_history_media_migration_runs set
                             sha_bytes_read=sha_bytes_read+$2,updated_at=now() where id=$1""",
                        run_id,
                        existing_size,
                    )
                    continue
                with tempfile.NamedTemporaryFile(prefix="history-media-", suffix=".part") as spool:
                    body = _open_source_body(
                        source, source_client, str(row["source_key"])
                    )
                    digest = hashlib.sha256()
                    size = 0
                    try:
                        while chunk := body.read(CHUNK_SIZE):
                            spool.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    finally:
                        body.close()
                    if size != int(row["byte_size"]) or digest.hexdigest() != row["source_sha256"]:
                        raise RuntimeError("planned source SHA changed before copy")
                    spool.flush()
                    spool.seek(0)
                    target_client.upload_fileobj(spool, BUCKET, str(row["target_key"]))
                target_sha, target_size = await asyncio.to_thread(
                    _read_s3_sha, target_client, BUCKET, str(row["target_key"])
                )
                if target_size != int(row["byte_size"]) or target_sha != row["source_sha256"]:
                    raise RuntimeError("target full SHA verification failed")
                await conn.execute(
                    """update analytics_history_media_r2_migrations set
                         status='copied_verified',target_sha256=$2,
                         copy_completed_at=now(),updated_at=now() where id=$1""",
                    row["id"],
                    target_sha,
                )
                await conn.execute(
                    """update analytics_history_media_migration_runs set
                         sha_bytes_read=sha_bytes_read+$2,updated_at=now() where id=$1""",
                    run_id,
                    int(row["byte_size"]) * 2,
                )
            except Exception as exc:
                await conn.execute(
                    """update analytics_history_media_r2_migrations set status='failed',
                         error_code='COPY_FAILED',error_detail=$2,updated_at=now() where id=$1""",
                    row["id"],
                    str(exc)[:1000],
                )
                raise
        remaining = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and status in ('copy_required','failed')""",
                run_id,
                args.plan_sha256,
            )
        )
        print(
            json.dumps(
                {"run_id": str(run_id), "copied": len(rows), "remaining": remaining}
            )
        )
    finally:
        await conn.close()


def _replace_extra_path(value: Any, target_ordinal: int, replacement: str) -> tuple[Any, int]:
    counter = 0

    def walk(item: Any) -> Any:
        nonlocal counter
        if isinstance(item, dict):
            result = dict(item)
            if str(result.get("path") or "").strip():
                if counter == target_ordinal:
                    result["path"] = replacement
                counter += 1
            for key, nested in tuple(result.items()):
                if key != "path":
                    result[key] = walk(nested)
            return result
        if isinstance(item, list):
            return [walk(nested) for nested in item]
        return item

    return walk(value), counter


def replace_asset_reference(history: dict[str, Any], role: str, ordinal: int, target: str) -> None:
    if role == "input":
        refs = [item.strip() for item in str(history.get("input_file") or "").split("|") if item.strip()]
        if ordinal >= len(refs):
            raise RuntimeError("History input ordinal changed")
        refs[ordinal] = target
        history["input_file"] = "|".join(refs)
    elif role == "output":
        if ordinal != 0 or not str(history.get("output_file") or "").strip():
            raise RuntimeError("History output ordinal changed")
        history["output_file"] = target
    elif role.startswith("extra:"):
        name = role.split(":", 1)[1]
        extras = dict(history.get("extra_outputs") or {})
        if name not in extras:
            raise RuntimeError("History extra role changed")
        extras[name], count = _replace_extra_path(extras[name], ordinal, target)
        if ordinal >= count:
            raise RuntimeError("History extra ordinal changed")
        history["extra_outputs"] = extras
    else:
        raise RuntimeError("unknown History media role")


async def _execute_switch(args: argparse.Namespace) -> None:
    ledger = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    production = await _connect_env("PRODUCTION_DATABASE_URL")
    try:
        run_id, manifest = await _load_plan(ledger, args.plan_sha256, "switch")
        validate_switch_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            expected_manifest_sha256="gate",
            actual_manifest_sha256="gate",
            confirmation=args.confirm,
        )
        rowset_sha, _count, _counts, _bytes, _diagnostics = (
            await _stream_plan_rowset(
                ledger,
                """select history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256
                     from analytics_history_media_r2_migrations
                 where run_id=$1 and switch_plan_sha256=$2
                   and status in ('target_verified','copied_verified')
                 order by history_id,role,ordinal""",
                run_id,
                args.plan_sha256,
            )
        )
        if rowset_sha != manifest["rowset_sha256"]:
            raise RuntimeError("switch plan rowset changed")
        switched = 0
        last_history_id = 0
        while True:
            history_id = await ledger.fetchval(
                """select min(history_id) from analytics_history_media_r2_migrations
                     where run_id=$1 and switch_plan_sha256=$2
                       and status in ('target_verified','copied_verified')
                       and history_id > $3""",
                run_id,
                args.plan_sha256,
                last_history_id,
            )
            if history_id is None:
                break
            history_id = int(history_id)
            last_history_id = history_id
            assets = await ledger.fetch(
                """select * from analytics_history_media_r2_migrations
                     where run_id=$1 and switch_plan_sha256=$2 and history_id=$3
                       and status in ('target_verified','copied_verified')
                     order by role,ordinal""",
                run_id,
                args.plan_sha256,
                history_id,
            )
            async with production.transaction():
                history = await production.fetchrow(
                    """select id,input_file,output_file,extra_outputs from history
                         where id=$1 for update""",
                    history_id,
                )
                if not history:
                    raise RuntimeError("History row disappeared")
                current = dict(history)
                extras = current.get("extra_outputs")
                if isinstance(extras, str):
                    try:
                        current["extra_outputs"] = json.loads(extras)
                    except json.JSONDecodeError:
                        current["extra_outputs"] = {}
                specs = history_assets_from_record(current)
                actual_manifest = media_manifest_hash(specs)
                expected_manifest = str(assets[0]["history_manifest_sha256"])
                current_refs = {
                    (asset.role, asset.ordinal): asset.source_ref for asset in specs
                }
                already_switched = all(
                    current_refs.get((str(asset["role"]), int(asset["ordinal"])))
                    == str(asset["target_key"])
                    for asset in assets
                )
                if already_switched:
                    await ledger.execute(
                        """update analytics_history_media_r2_migrations
                              set switch_completed_at=coalesce(switch_completed_at,now()),
                                  updated_at=now()
                            where run_id=$1 and history_id=$2 and switch_plan_sha256=$3""",
                        run_id,
                        history_id,
                        args.plan_sha256,
                    )
                    continue
                validate_switch_gate(
                    expected_plan_sha256=manifest["plan_sha256"],
                    supplied_plan_sha256=args.plan_sha256,
                    expected_manifest_sha256=expected_manifest,
                    actual_manifest_sha256=actual_manifest,
                    confirmation=args.confirm,
                )
                for asset in assets:
                    replace_asset_reference(
                        current,
                        str(asset["role"]),
                        int(asset["ordinal"]),
                        str(asset["target_key"]),
                    )
                await production.execute(
                    """update history set input_file=$2,output_file=$3,extra_outputs=$4::jsonb
                         where id=$1""",
                    history_id,
                    current["input_file"],
                    current["output_file"],
                    json.dumps(current["extra_outputs"]),
                )
                switched += len(assets)
            await ledger.execute(
                """update analytics_history_media_r2_migrations set
                     switch_completed_at=now(),updated_at=now()
                   where run_id=$1 and history_id=$2 and switch_plan_sha256=$3""",
                run_id,
                history_id,
                args.plan_sha256,
            )
        print(json.dumps({"run_id": str(run_id), "switched": switched}))
    finally:
        await production.close()
        await ledger.close()


async def _report(args: argparse.Namespace) -> None:
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    try:
        run = await conn.fetchrow(
            "select * from analytics_history_media_migration_runs where id=$1", run_id
        )
        if not run:
            raise RuntimeError("unknown migration run")
        summary = await conn.fetch(
            """select status,count(*) object_count,coalesce(sum(byte_size),0) byte_size
                 from analytics_history_media_r2_migrations where run_id=$1
                 group by status order by status""",
            run_id,
        )
        diagnostic_rows = await conn.fetch(
            """select history_id,role,ordinal,status,error_code
                 from analytics_history_media_r2_migrations
                where run_id=$1 and status in
                  ('blocked','unresolved','target_conflict','source_offline','source_missing','failed')
                order by history_id,role,ordinal limit $2""",
            run_id,
            MAX_DIAGNOSTICS,
        )
        rowset_sha, row_count, _counts, _bytes, _diagnostics = (
            await _stream_plan_rowset(
                conn,
                """select history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256,error_code
                     from analytics_history_media_r2_migrations where run_id=$1
                     order by history_id,role,ordinal""",
                run_id,
            )
        )
        plans = await conn.fetch(
            """select plan_type,plan_sha256,rowset_sha256
                 from analytics_history_media_migration_plans
                where run_id=$1 order by plan_type,created_at""",
            run_id,
        )
        report = {
            "schema": "allbot-history-media-r2-report/v1",
            "run_id": str(run_id),
            "history_watermark": int(run["history_watermark"]),
            "scope": "History logical media rows only; no bucket enumeration",
            "statuses": [dict(row) for row in summary],
            "sha_bytes_read": int(run["sha_bytes_read"]),
            "row_count": row_count,
            "rowset_sha256": rowset_sha,
            "plans": [dict(row) for row in plans],
            "diagnostics": [_diagnostic(row) for row in diagnostic_rows],
        }
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(report) + b"\n")
        os.chmod(output, 0o600)
        print(json.dumps({"report": str(output), "rowset_sha256": report["rowset_sha256"]}))
    finally:
        await conn.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed")
    seed.add_argument("--history-watermark", type=int)
    seed.add_argument("--resume-run-id")
    seed.add_argument("--batch-size", type=int, default=1000)
    probe = commands.add_parser("probe")
    probe.add_argument("--run-id", required=True)
    probe.add_argument("--config", required=True)
    probe.add_argument("--limit", type=int, default=1000)
    probe.add_argument("--systemic-error-threshold", type=int, default=5)
    probe_mode = probe.add_mutually_exclusive_group()
    probe_mode.add_argument("--target-only", action="store_true")
    probe_mode.add_argument("--receipt-only", action="store_true")
    probe.add_argument("--target-concurrency", type=int, default=32)
    probe.add_argument("--recheck-deferred", action="store_true")
    probe.add_argument("--deferred-min-age-hours", type=int, default=24)
    plan_copy = commands.add_parser("plan-copy")
    plan_copy.add_argument("--run-id", required=True)
    plan_copy.add_argument("--output", required=True)
    plan_copy.add_argument("--allow-incomplete", action="store_true")
    plan_switch = commands.add_parser("plan-switch")
    plan_switch.add_argument("--run-id", required=True)
    plan_switch.add_argument("--output", required=True)
    copy = commands.add_parser("execute-copy")
    copy.add_argument("--plan-sha256", required=True)
    copy.add_argument("--confirm", required=True)
    copy.add_argument("--config", required=True)
    copy.add_argument("--limit", type=int, default=1000)
    switch = commands.add_parser("execute-switch")
    switch.add_argument("--plan-sha256", required=True)
    switch.add_argument("--confirm", required=True)
    report = commands.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--output", required=True)
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "seed":
        await _seed(args)
    elif args.command == "probe":
        await _probe(args)
    elif args.command == "plan-copy":
        await _create_plan(args, plan_type="copy")
    elif args.command == "execute-copy":
        await _execute_copy(args)
    elif args.command == "plan-switch":
        await _create_plan(args, plan_type="switch")
    elif args.command == "execute-switch":
        await _execute_switch(args)
    elif args.command == "report":
        await _report(args)


def main() -> None:
    asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    main()
