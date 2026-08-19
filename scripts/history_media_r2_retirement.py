#!/usr/bin/env python3
"""Freeze and execute deletion of fully archived, unreferenced History R2 old sources."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
import time
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.history_media_r2_migration import (
    _canonical_json,
    _load_secure_config,
    _runtime_identity,
    normalize_asyncpg_dsn,
)
from scripts.media_archive_worker import (
    clear_proxy_environment,
    validate_endpoint_route,
)

RETIREMENT_BATCH_SIZE = 1000
MAX_DELETE_CONCURRENCY = 8
DURABILITY_NAS_ARCHIVE = "nas-archive"
DURABILITY_R2_PERSISTENT_TARGET = "r2-persistent-target"
DURABILITY_BASES = (DURABILITY_NAS_ARCHIVE, DURABILITY_R2_PERSISTENT_TARGET)
BULK_SOURCE_IDENTITY_POLICY = "etag-or-size-last-modified"
RETIREMENT_DDL = """
create table if not exists analytics_history_media_r2_retirement_plans (
    plan_sha256 char(64) primary key,
    run_id uuid not null references analytics_history_media_migration_runs(id),
    parent_copy_plan_sha256 char(64) not null,
    rowset_sha256 char(64) not null,
    manifest jsonb not null,
    status text not null default 'frozen'
      check (status in ('frozen','running','completed','paused')),
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);
create table if not exists analytics_history_media_r2_retirement_batches (
    plan_sha256 char(64) not null references analytics_history_media_r2_retirement_plans(plan_sha256),
    batch_no integer not null check (batch_no >= 0),
    object_count integer not null check (object_count between 1 and 1000),
    total_bytes bigint not null check (total_bytes >= 0),
    rowset_sha256 char(64) not null,
    status text not null default 'pending'
      check (status in ('pending','running','completed','paused')),
    outcome_counts jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (plan_sha256,batch_no)
);
create table if not exists analytics_history_media_r2_retirement_objects (
    plan_sha256 char(64) not null references analytics_history_media_r2_retirement_plans(plan_sha256),
    batch_no integer not null,
    object_no integer not null,
    source_name text not null,
    source_key text not null,
    source_key_sha256 char(64) not null,
    byte_size bigint not null check (byte_size >= 0),
    source_etag text not null,
    source_last_modified timestamptz not null,
    asset_count integer not null check (asset_count > 0),
    archive_sha256 char(64) not null,
    nas_bucket text not null,
    nas_key text not null,
    target_facts jsonb not null,
    status text not null default 'planned'
      check (status in ('planned','deleted','blocked')),
    error_code text,
    deleted_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (plan_sha256,object_no),
    unique (plan_sha256,source_name,source_key),
    foreign key (plan_sha256,batch_no)
      references analytics_history_media_r2_retirement_batches(plan_sha256,batch_no)
);
create index if not exists ix_history_media_r2_retirement_objects_status
  on analytics_history_media_r2_retirement_objects(plan_sha256,status,batch_no,object_no);
alter table analytics_history_media_r2_retirement_plans
  alter column parent_copy_plan_sha256 drop not null;
alter table analytics_history_media_r2_retirement_plans
  add column if not exists execution_mode text not null default 'single';
alter table analytics_history_media_r2_retirement_plans
  add column if not exists asset_coordinate_count bigint not null default 0;
alter table analytics_history_media_r2_retirement_batches
  add column if not exists is_canary boolean not null default false;
alter table analytics_history_media_r2_retirement_batches
  add column if not exists asset_coordinate_count bigint not null default 0;
alter table analytics_history_media_r2_retirement_objects
  add column if not exists scope_asset_count integer not null default 0;
alter table analytics_history_media_r2_retirement_objects
  add column if not exists scope_facts jsonb not null default '{}'::jsonb;
"""
RETIREMENT_BLOCKER_TIMEOUT_SECONDS = 60.0
RETIREMENT_BLOCKER_SQL = """with selected as materialized (
  select * from unnest($1::text[],$2::text[]) as x(source_name,source_key)
), blockers as (
  select 1 blocker from selected s
    join analytics_history_media_r2_migrations m
      using(source_name,source_key)
   where m.status in ('copy_required','failed')
  union all
  select 1 blocker from selected s
    join analytics_history_media_r2_migrations m
      using(source_name,source_key)
   where m.original_ref<>m.target_key and m.switch_completed_at is null
  union all
  select 1 blocker from selected s
    join analytics_history_media_r2_migrations m
      on m.target_key=s.source_key
)
select exists(select 1 from blockers limit 1)
"""
RETIREMENT_BLOCKER_INDEX_DDL = (
    (
        "ix_history_media_r2_retirement_source_pending",
        """create index concurrently if not exists
             ix_history_media_r2_retirement_source_pending
             on analytics_history_media_r2_migrations(source_name,source_key)
             where status in ('copy_required','failed')
               and source_name is not null and source_key is not null""",
    ),
    (
        "ix_history_media_r2_retirement_source_unswitched",
        """create index concurrently if not exists
             ix_history_media_r2_retirement_source_unswitched
             on analytics_history_media_r2_migrations(source_name,source_key)
             where original_ref<>target_key and switch_completed_at is null
               and source_name is not null and source_key is not null""",
    ),
    (
        "ix_history_media_r2_retirement_target_key",
        """create index concurrently if not exists
             ix_history_media_r2_retirement_target_key
             on analytics_history_media_r2_migrations(target_key)
             where target_key is not null""",
    ),
)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _strip_etag(value: Any) -> str:
    return str(value or "").strip().strip('"')


def _key_sha(source_name: str, source_key: str) -> str:
    return hashlib.sha256(f"{source_name}\0{source_key}".encode()).hexdigest()


def classify_retirement_candidate(candidate: dict[str, Any]) -> str:
    if int(candidate.get("pending_copy_refs") or 0):
        return "pending_copy_source"
    if int(candidate.get("unswitched_refs") or 0):
        return "unswitched_reference"
    if int(candidate.get("target_collisions") or 0):
        return "source_is_target"
    if int(candidate.get("live_history_refs") or 0):
        return "live_history_reference"
    durability_basis = str(
        candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
    )
    if durability_basis not in DURABILITY_BASES:
        return "unknown_durability_basis"
    if (
        durability_basis == DURABILITY_R2_PERSISTENT_TARGET
        and not candidate.get("targets")
    ):
        return "persistent_target_missing"
    if durability_basis == DURABILITY_NAS_ARCHIVE:
        if int(candidate.get("archive_verified_asset_count") or 0) != int(
            candidate.get("asset_count") or 0
        ):
            return "archive_incomplete"
        if not str(candidate.get("archive_sha256") or "") or not str(
            candidate.get("nas_key") or ""
        ):
            return "archive_incomplete"
    return "eligible"


def _retirement_object_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    target_identities = [
        {
            "target_key_sha256": hashlib.sha256(
                str(target["target_key"]).encode()
            ).hexdigest(),
            "copy_plan_sha256": str(target["copy_plan_sha256"]),
            "target_etag": str(target.get("target_etag") or ""),
        }
        for target in sorted(
            candidate["targets"], key=lambda item: str(item["target_key"])
        )
    ]
    identity = {
        "durability_basis": str(
            candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
        ),
        "source_name": str(candidate["source_name"]),
        "source_key_sha256": _key_sha(
            str(candidate["source_name"]), str(candidate["source_key"])
        ),
        "byte_size": int(candidate["byte_size"]),
        "source_etag": str(candidate["source_etag"]),
        "source_last_modified": _iso(candidate["source_last_modified"]),
        "asset_count": int(candidate["asset_count"]),
        # PostgreSQL bpchar pads the empty R2-only archive sentinel to 64 spaces.
        # Normalize that storage round-trip so the frozen and execution rowsets
        # have the same identity without weakening any non-empty SHA check.
        "archive_sha256": str(candidate["archive_sha256"]).strip(),
        "nas_object_sha256": _key_sha(
            str(candidate["nas_bucket"]), str(candidate["nas_key"])
        ),
        "target_facts_sha256": _sha256_json(target_identities),
        "target_count": len(target_identities),
    }
    if "scope_switch_counts" in candidate:
        scope_switch_counts = {
            str(key): int(value)
            for key, value in sorted(
                dict(candidate.get("scope_switch_counts") or {}).items()
            )
        }
        identity.update(
            {
                "scope_asset_count": int(candidate.get("scope_asset_count") or 0),
                "scope_switch_counts_sha256": _sha256_json(scope_switch_counts),
            }
        )
    return identity


def build_retirement_plan(
    *,
    run_id: str,
    parent_copy_plan_sha256: str,
    parent_switch_plan_sha256s: Iterable[str],
    objects: Iterable[dict[str, Any]],
    report_sha256: str,
    runtime_identity: dict[str, Any],
    durability_basis: str = DURABILITY_NAS_ARCHIVE,
    batch_size: int = RETIREMENT_BATCH_SIZE,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if durability_basis not in DURABILITY_BASES:
        raise ValueError("unknown retirement durability basis")
    if not 1 <= batch_size <= RETIREMENT_BATCH_SIZE:
        raise ValueError("retirement batch size must be between 1 and 1000")
    frozen = sorted(
        (dict(item) for item in objects),
        key=lambda item: (
            -int(item["byte_size"]),
            _key_sha(str(item["source_name"]), str(item["source_key"])),
        ),
    )
    keys = [(str(item["source_name"]), str(item["source_key"])) for item in frozen]
    if len(keys) != len(set(keys)):
        raise RuntimeError("retirement plan contains a duplicate old source")
    if not frozen:
        raise RuntimeError("retirement plan has no eligible old sources")
    for candidate in frozen:
        candidate_basis = str(
            candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
        )
        if candidate_basis != durability_basis:
            raise RuntimeError("retirement object durability basis changed")
        candidate["durability_basis"] = candidate_basis
        classification = classify_retirement_candidate(candidate)
        if classification != "eligible":
            raise RuntimeError(
                f"retirement plan contains ineligible source: {classification}"
            )
        candidate["source_key_sha256"] = _key_sha(
            str(candidate["source_name"]), str(candidate["source_key"])
        )
    identities = [_retirement_object_identity(item) for item in frozen]
    batches: list[dict[str, Any]] = []
    for batch_no, offset in enumerate(range(0, len(frozen), batch_size)):
        subset = frozen[offset : offset + batch_size]
        subset_identities = identities[offset : offset + batch_size]
        batches.append(
            {
                "batch_no": batch_no,
                "object_count": len(subset),
                "total_bytes": sum(int(item["byte_size"]) for item in subset),
                "rowset_sha256": _sha256_json(subset_identities),
            }
        )
        for item in subset:
            item["batch_no"] = batch_no
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-retirement-plan/v2",
        "durability_basis": durability_basis,
        "run_id": str(run_id),
        "parent_copy_plan_sha256": str(parent_copy_plan_sha256),
        "parent_switch_plan_sha256s": sorted(
            str(value) for value in parent_switch_plan_sha256s
        ),
        "report_sha256": str(report_sha256),
        "object_count": len(frozen),
        "total_bytes": sum(int(item["byte_size"]) for item in frozen),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "rowset_sha256": _sha256_json(identities),
        "batches_sha256": _sha256_json(batches),
        "object_keys_redacted": True,
        "runtime_identity": dict(runtime_identity),
    }
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, frozen, batches


def build_bulk_retirement_plan(
    *,
    run_id: str,
    parent_copy_plan_sha256s: Iterable[str],
    switch_scope_counts: dict[str, int],
    switch_scope_rowset_sha256s: dict[str, str],
    asset_scope_sha256: str,
    objects: Iterable[dict[str, Any]],
    runtime_identity: dict[str, Any],
    switch_plan_sha256s: Iterable[str] | None = None,
    canary_size: int = 100,
    batch_size: int = RETIREMENT_BATCH_SIZE,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    supplied_switches = list(switch_plan_sha256s or switch_scope_counts)
    if len(supplied_switches) != len(set(supplied_switches)):
        raise ValueError("bulk retirement requires unique Switch plans")
    switches = sorted(str(value) for value in supplied_switches)
    if not switches or set(switches) != set(switch_scope_counts):
        raise ValueError("bulk retirement Switch scope is incomplete")
    if set(switches) != set(switch_scope_rowset_sha256s):
        raise ValueError("bulk retirement Switch rowsets are incomplete")
    copy_plans = sorted(set(str(value) for value in parent_copy_plan_sha256s))
    if not copy_plans:
        raise ValueError("bulk retirement requires at least one Copy parent")
    if not 1 <= canary_size <= batch_size <= RETIREMENT_BATCH_SIZE:
        raise ValueError("bulk retirement batch sizes must satisfy 1 <= canary <= batch <= 1000")

    frozen = sorted(
        (dict(item) for item in objects),
        key=lambda item: (
            -int(item["byte_size"]),
            _key_sha(str(item["source_name"]), str(item["source_key"])),
        ),
    )
    keys = [(str(item["source_name"]), str(item["source_key"])) for item in frozen]
    if not frozen:
        raise RuntimeError("bulk retirement plan has no old sources")
    if len(keys) != len(set(keys)):
        raise RuntimeError("bulk retirement plan contains a duplicate old source")
    for candidate in frozen:
        candidate["durability_basis"] = DURABILITY_R2_PERSISTENT_TARGET
        if classify_retirement_candidate(candidate) != "eligible":
            raise RuntimeError("bulk retirement plan contains an ineligible source")
        candidate["source_key_sha256"] = _key_sha(
            str(candidate["source_name"]), str(candidate["source_key"])
        )
        counts = {
            str(key): int(value)
            for key, value in dict(candidate.get("scope_switch_counts") or {}).items()
        }
        if set(counts) - set(switches) or sum(counts.values()) != int(
            candidate.get("scope_asset_count") or 0
        ):
            raise RuntimeError("bulk retirement object Switch scope changed")

    expected_assets = sum(int(value) for value in switch_scope_counts.values())
    actual_assets = sum(int(item.get("scope_asset_count") or 0) for item in frozen)
    if actual_assets != expected_assets:
        raise RuntimeError("bulk retirement asset coordinate count changed")

    identities = [_retirement_object_identity(item) for item in frozen]
    batches: list[dict[str, Any]] = []
    offset = 0
    batch_no = 0
    while offset < len(frozen):
        size = canary_size if batch_no == 0 else batch_size
        subset = frozen[offset : offset + size]
        subset_identities = identities[offset : offset + size]
        batches.append(
            {
                "batch_no": batch_no,
                "is_canary": batch_no == 0,
                "object_count": len(subset),
                "asset_coordinate_count": sum(
                    int(item["scope_asset_count"]) for item in subset
                ),
                "total_bytes": sum(int(item["byte_size"]) for item in subset),
                "rowset_sha256": _sha256_json(subset_identities),
            }
        )
        for item in subset:
            item["batch_no"] = batch_no
        offset += len(subset)
        batch_no += 1

    switch_scopes = [
        {
            "switch_plan_sha256": plan_sha,
            "asset_coordinate_count": int(switch_scope_counts[plan_sha]),
            "rowset_sha256": str(switch_scope_rowset_sha256s[plan_sha]),
        }
        for plan_sha in switches
    ]
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-bulk-retirement-plan/v1",
        "execution_mode": "bulk",
        "durability_basis": DURABILITY_R2_PERSISTENT_TARGET,
        "run_id": str(run_id),
        "parent_copy_plan_sha256s": copy_plans,
        "parent_switch_plan_sha256s": switches,
        "switch_scopes": switch_scopes,
        "asset_coordinate_count": expected_assets,
        "asset_scope_sha256": str(asset_scope_sha256),
        "asset_scope_algorithm": "history-r2-bulk-scope-merkle-v1",
        "source_identity_policy": BULK_SOURCE_IDENTITY_POLICY,
        "object_count": len(frozen),
        "total_bytes": sum(int(item["byte_size"]) for item in frozen),
        "canary_object_count": min(canary_size, len(frozen)),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "rowset_sha256": _sha256_json(identities),
        "batches_sha256": _sha256_json(batches),
        "one_confirmation_covers_all_batches": True,
        "object_keys_redacted": True,
        "runtime_identity": dict(runtime_identity),
    }
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, frozen, batches


def validate_delete_gate(
    *, expected_plan_sha256: str, supplied_plan_sha256: str, confirmation: str
) -> None:
    if supplied_plan_sha256 != expected_plan_sha256 or confirmation != (
        f"DELETE_HISTORY_MEDIA_{expected_plan_sha256}"
    ):
        raise ValueError("exact retirement plan SHA and confirmation are required")


def validate_retirement_object_heads(
    candidate: dict[str, Any],
    *,
    source_head: dict[str, Any] | None,
    target_heads: dict[str, dict[str, Any] | None],
    nas_head: dict[str, Any] | None,
) -> None:
    if source_head is None:
        raise RuntimeError("old source is missing before retirement")
    if int(source_head.get("ContentLength") or -1) != int(candidate["byte_size"]):
        raise RuntimeError("old source size changed")
    expected_etag = _strip_etag(candidate["source_etag"])
    if expected_etag:
        if _strip_etag(source_head.get("ETag")) != expected_etag:
            raise RuntimeError("old source identity changed")
    elif candidate.get("source_identity_policy") != BULK_SOURCE_IDENTITY_POLICY:
        raise RuntimeError("old source ETag evidence is missing")
    expected_modified = candidate.get("source_last_modified")
    actual_modified = source_head.get("LastModified")
    if not expected_etag and (
        not isinstance(expected_modified, datetime)
        or not isinstance(actual_modified, datetime)
    ):
        raise RuntimeError("old source Last-Modified evidence is missing")
    if (
        isinstance(expected_modified, datetime)
        and isinstance(actual_modified, datetime)
        and expected_modified.astimezone(timezone.utc)
        != actual_modified.astimezone(timezone.utc)
    ):
        raise RuntimeError("old source last-modified changed")
    validate_retirement_survivor_heads(
        candidate, target_heads=target_heads, nas_head=nas_head
    )


def validate_retirement_survivor_heads(
    candidate: dict[str, Any],
    *,
    target_heads: dict[str, dict[str, Any] | None],
    nas_head: dict[str, Any] | None,
) -> None:
    for target in candidate["targets"]:
        key = str(target["target_key"])
        if key == str(candidate["source_key"]):
            raise RuntimeError("old source is also a standard target")
        head = target_heads.get(key)
        if head is None:
            raise RuntimeError("verified target is missing")
        if int(head.get("ContentLength") or -1) != int(candidate["byte_size"]):
            raise RuntimeError("verified target size changed")
        marker = str((head.get("Metadata") or {}).get("allbot-copy-plan-sha256") or "")
        if marker != str(target["copy_plan_sha256"]):
            raise RuntimeError("verified target marker changed")
        expected_target_etag = str(target.get("target_etag") or "")
        if expected_target_etag and _strip_etag(head.get("ETag")) != _strip_etag(
            expected_target_etag
        ):
            raise RuntimeError("verified target identity changed")
    durability_basis = str(
        candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
    )
    if durability_basis == DURABILITY_R2_PERSISTENT_TARGET:
        return
    if durability_basis != DURABILITY_NAS_ARCHIVE:
        raise RuntimeError("unknown retirement durability basis")
    if nas_head is None:
        raise RuntimeError("NAS archive object is missing")
    if int(nas_head.get("ContentLength") or -1) != int(candidate["byte_size"]):
        raise RuntimeError("NAS archive size changed")
    if str((nas_head.get("Metadata") or {}).get("sha256") or "") != str(
        candidate["archive_sha256"]
    ):
        raise RuntimeError("NAS archive SHA-256 changed")


def _secure_json(path: Path) -> dict[str, Any]:
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise PermissionError("archive config must be a current-user owned 0600 file")
    return json.loads(path.read_text(encoding="utf-8"))


def _durability_archive_config(
    durability_basis: str, archive_config_path: str | None
) -> dict[str, Any] | None:
    if durability_basis == DURABILITY_R2_PERSISTENT_TARGET:
        if archive_config_path:
            raise ValueError(
                "archive config is not accepted for r2-persistent-target durability"
            )
        return None
    if durability_basis != DURABILITY_NAS_ARCHIVE:
        raise ValueError("unknown retirement durability basis")
    if not archive_config_path:
        raise ValueError("archive config is required for nas-archive durability")
    return _secure_json(Path(archive_config_path))


def _load_history_ids(path: Path) -> tuple[int, ...]:
    values = tuple(
        sorted(
            {
                int(raw.strip())
                for raw in path.read_text(encoding="utf-8").splitlines()
                if raw.strip() and not raw.lstrip().startswith("#")
            }
        )
    )
    if not values or len(values) > 1000 or any(value < 1 for value in values):
        raise ValueError("retirement History scope must contain 1-1000 positive IDs")
    return values


async def _connect(name: str) -> asyncpg.Connection:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    dsn, ssl_value = normalize_asyncpg_dsn(value)
    return await asyncpg.connect(dsn, ssl=ssl_value)


async def _retirement_has_blockers(
    ledger: asyncpg.Connection,
    objects: list[dict[str, Any]],
) -> bool:
    started = time.monotonic()
    try:
        blocked = bool(
            await ledger.fetchval(
                RETIREMENT_BLOCKER_SQL,
                [str(item["source_name"]) for item in objects],
                [str(item["source_key"]) for item in objects],
                timeout=RETIREMENT_BLOCKER_TIMEOUT_SECONDS,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "retirement_blocker_gate_failed",
                    "source_count": len(objects),
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise
    print(
        json.dumps(
            {
                "event": "retirement_blocker_gate",
                "source_count": len(objects),
                "blocked": blocked,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
            sort_keys=True,
        )
    )
    return blocked


async def _mark_retirement_plan_paused(
    plan_sha256: str,
    *,
    connect_func: Any = None,
    sleep_func: Any = asyncio.sleep,
    attempts: int = 3,
) -> None:
    connector = connect_func or _connect
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        connection = None
        try:
            connection = await connector("LOCAL_ANALYTICS_DATABASE_URL")
            await connection.execute(
                """update analytics_history_media_r2_retirement_plans
                     set status='paused',updated_at=now() where plan_sha256=$1""",
                plan_sha256,
            )
            await connection.execute(
                """update analytics_history_media_r2_retirement_batches
                     set status='paused',updated_at=now()
                   where plan_sha256=$1 and status='running'""",
                plan_sha256,
            )
            print(
                json.dumps(
                    {
                        "event": "retirement_plan_paused",
                        "reconnect_attempt": attempt,
                    },
                    sort_keys=True,
                )
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                await sleep_func(attempt)
        finally:
            if connection is not None:
                await connection.close()
    raise RuntimeError("could not mark retirement plan paused via a fresh connection") from last_error


async def _ensure_retirement_blocker_indexes(
    ledger: asyncpg.Connection,
    *,
    timeout_seconds: float,
) -> None:
    for name, statement in RETIREMENT_BLOCKER_INDEX_DDL:
        started = time.monotonic()
        await ledger.execute(statement, timeout=timeout_seconds)
        print(
            json.dumps(
                {
                    "event": "retirement_blocker_index_ready",
                    "index": name,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                },
                sort_keys=True,
            )
        )


async def _missing_retirement_blocker_indexes(
    ledger: asyncpg.Connection,
) -> tuple[str, ...]:
    required = tuple(name for name, _statement in RETIREMENT_BLOCKER_INDEX_DDL)
    rows = await ledger.fetch(
        """select index_rel.relname as indexname
             from pg_class table_rel
             join pg_namespace ns on ns.oid=table_rel.relnamespace
             join pg_index idx on idx.indrelid=table_rel.oid and idx.indisvalid
             join pg_class index_rel on index_rel.oid=idx.indexrelid
            where ns.nspname=current_schema()
              and table_rel.relname='analytics_history_media_r2_migrations'
              and index_rel.relname=any($1::text[])""",
        list(required),
    )
    present = {str(row["indexname"]) for row in rows}
    return tuple(name for name in required if name not in present)


async def _prepare_delete_indexes(args: argparse.Namespace) -> None:
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await _ensure_retirement_blocker_indexes(
            ledger, timeout_seconds=float(args.timeout_seconds)
        )
        missing = await _missing_retirement_blocker_indexes(ledger)
        if missing:
            raise RuntimeError("retirement blocker indexes are incomplete")
        print(
            json.dumps(
                {
                    "event": "retirement_blocker_indexes_verified",
                    "index_count": len(RETIREMENT_BLOCKER_INDEX_DDL),
                },
                sort_keys=True,
            )
        )
    finally:
        await ledger.close()


def _s3_client(config: dict[str, Any], *, max_connections: int) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config.get("region") or "auto",
        verify=config.get("ca_file", True),
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 5, "mode": "adaptive"},
            max_pool_connections=max_connections,
        ),
    )


def _retirement_runtime_identity(
    *,
    artifact_digest: str,
    r2_config: dict[str, Any],
    durability_basis: str,
    archive_config: dict[str, Any] | None,
) -> dict[str, Any]:
    target = r2_config["target"]
    identity = _runtime_identity(artifact_digest=artifact_digest, config=r2_config)
    identity.update(
        {
            "retirement_protocol": "history-r2-old-source-retirement/v2",
            "durability_basis": durability_basis,
            "retirement_script_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "delete_bucket": str(target["bucket"]),
        }
    )
    if durability_basis == DURABILITY_NAS_ARCHIVE:
        if archive_config is None:
            raise ValueError("archive config is required for nas-archive durability")
        nas = archive_config["nas"]
        identity.update(
            {
                "nas_bucket": str(nas["bucket"]),
                "nas_endpoint_sha256": hashlib.sha256(
                    str(nas["endpoint"]).encode()
                ).hexdigest(),
            }
        )
    elif durability_basis != DURABILITY_R2_PERSISTENT_TARGET:
        raise ValueError("unknown retirement durability basis")
    return identity


REPORT_SQL = """
with cohort as (
  select * from analytics_history_media_r2_migrations where copy_plan_sha256=$1
), object_rows as (
  select source_name,source_key,max(byte_size) byte_size,min(source_etag) source_etag,
         min(source_last_modified) source_last_modified,count(*) asset_count,
         count(*) filter(where switch_completed_at is not null) switched_asset_count
    from cohort group by source_name,source_key
), archive_rows as (
  select c.source_name,c.source_key,count(*) verified_assets
    from cohort c join media_archive_receipts r
      on r.history_id=c.history_id and r.role=c.role and r.ordinal=c.ordinal
     and r.status='archived_verified' and length(r.sha256)=64
     and r.byte_size=c.byte_size and r.source_ref in (c.original_ref,c.target_key)
    join media_archive_outbox o on o.history_id=c.history_id and o.status='archived'
   group by c.source_name,c.source_key
), pending as (
  select source_name,source_key,count(*) refs
    from analytics_history_media_r2_migrations
   where status in ('copy_required','failed')
   group by source_name,source_key
), unswitched as (
  select source_name,source_key,count(*) refs
    from analytics_history_media_r2_migrations
   where original_ref<>target_key and switch_completed_at is null
   group by source_name,source_key
), collisions as (
  select o.source_name,o.source_key,count(*) refs from object_rows o
    join analytics_history_media_r2_migrations m on m.target_key=o.source_key
   group by o.source_name,o.source_key
), classified as (
  select o.*,
         coalesce(a.verified_assets,0) archive_verified_asset_count,
         coalesce(p.refs,0) pending_copy_refs,
         coalesce(u.refs,0) unswitched_refs,
         coalesce(c.refs,0) target_collisions
    from object_rows o left join archive_rows a using(source_name,source_key)
    left join pending p using(source_name,source_key)
    left join unswitched u using(source_name,source_key)
    left join collisions c using(source_name,source_key)
)
select count(*) object_count,coalesce(sum(byte_size),0) total_bytes,
       coalesce(sum(asset_count),0) asset_count,
       count(*) filter(where switched_asset_count=asset_count) fully_switched_objects,
       count(*) filter(where pending_copy_refs>0) pending_copy_source_objects,
       count(*) filter(where unswitched_refs>0) unswitched_source_objects,
       count(*) filter(where target_collisions>0) source_is_target_objects,
       count(*) filter(where archive_verified_asset_count=asset_count) archive_ready_objects,
       coalesce(sum(byte_size) filter(where archive_verified_asset_count=asset_count),0) archive_ready_bytes
  from classified
"""


ARCHIVE_CANDIDATE_HISTORY_SQL = """
with cohort as (
  select * from analytics_history_media_r2_migrations where copy_plan_sha256=$1
), missing as (
  select c.history_id,max(c.byte_size) largest_asset,coalesce(sum(c.byte_size),0) bytes
    from cohort c left join media_archive_receipts r
      on r.history_id=c.history_id and r.role=c.role and r.ordinal=c.ordinal
     and r.status='archived_verified' and length(r.sha256)=64
     and r.byte_size=c.byte_size and r.source_ref in (c.original_ref,c.target_key)
   where c.switch_completed_at is not null and r.id is null
   group by c.history_id
)
select history_id,largest_asset,bytes from missing
 order by largest_asset desc,bytes desc,history_id limit $2
"""


async def _report(args: argparse.Namespace) -> None:
    conn = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        parent = await conn.fetchrow(
            """select run_id,manifest from analytics_history_media_migration_plans
                 where plan_sha256=$1 and plan_type='copy'""",
            args.parent_copy_plan_sha256,
        )
        if parent is None:
            raise RuntimeError("unknown parent Copy plan")
        aggregate = dict(await conn.fetchrow(REPORT_SQL, args.parent_copy_plan_sha256))
        candidates = [
            dict(row)
            for row in await conn.fetch(
                ARCHIVE_CANDIDATE_HISTORY_SQL,
                args.parent_copy_plan_sha256,
                args.archive_candidate_limit,
            )
        ]
        candidate_ids = [int(item["history_id"]) for item in candidates]
        candidate_identity = [
            {
                "history_id": int(item["history_id"]),
                "largest_asset": int(item["largest_asset"] or 0),
                "bytes": int(item["bytes"] or 0),
            }
            for item in candidates
        ]
        report: dict[str, Any] = {
            "schema": "allbot-history-media-r2-retirement-report/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parent_copy_plan_sha256": args.parent_copy_plan_sha256,
            "run_id": str(parent["run_id"]),
            **{key: int(value or 0) for key, value in aggregate.items()},
            "archive_candidate_history_count": len(candidate_ids),
            "archive_candidates_sha256": _sha256_json(candidate_identity),
            "production_live_reference_scope": "not_yet_frozen; required by plan-delete",
            "object_keys_redacted": True,
        }
        report["report_sha256"] = _sha256_json(report)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(report) + b"\n")
        os.chmod(output, 0o600)
        if args.archive_candidates_output:
            candidate_output = Path(args.archive_candidates_output)
            candidate_output.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": "allbot-history-media-r2-archive-candidates/v1",
                "parent_copy_plan_sha256": args.parent_copy_plan_sha256,
                "report_sha256": report["report_sha256"],
                "history_ids": candidate_ids,
                "waves": [
                    candidate_ids[offset : offset + 100]
                    for offset in range(0, len(candidate_ids), 100)
                ],
                "rowset_sha256": _sha256_json(candidate_identity),
            }
            candidate_output.write_bytes(_canonical_json(payload) + b"\n")
            os.chmod(candidate_output, 0o600)
        print(
            json.dumps(
                {
                    "report_sha256": report["report_sha256"],
                    "object_count": report["object_count"],
                    "total_bytes": report["total_bytes"],
                    "archive_ready_objects": report["archive_ready_objects"],
                    "archive_ready_bytes": report["archive_ready_bytes"],
                    "archive_candidate_history_count": len(candidate_ids),
                    "report": str(output),
                }
            )
        )
    finally:
        await conn.close()


SCOPED_COHORT_SQL = """with selected as (
  select * from unnest($2::text[],$3::text[]) as x(source_name,source_key)
)
select m.id,m.history_id,m.role,m.ordinal,m.original_ref,m.target_key,
       m.source_name,m.source_key,m.byte_size,m.source_etag,m.target_etag,
       m.source_last_modified,m.copy_plan_sha256,m.switch_plan_sha256,
       m.switch_completed_at
  from analytics_history_media_r2_migrations m join selected s
    on s.source_name=m.source_name and s.source_key=m.source_key
 where m.copy_plan_sha256=$1 order by m.source_name,m.source_key,m.history_id,m.role,m.ordinal
"""

PRODUCTION_ARCHIVE_EVIDENCE_SQL = """select r.history_id,r.role,r.ordinal,
       r.source_ref,r.sha256,r.byte_size,r.nas_bucket,r.nas_key,r.status,
       o.status outbox_status
  from media_archive_receipts r join media_archive_outbox o on o.history_id=r.history_id
 where r.history_id=any($1::integer[])
"""


async def _live_reference_counts(
    production: asyncpg.Connection, keys: list[str]
) -> dict[str, int]:
    if not keys:
        return {}
    rows = await production.fetch(
        """with refs as (
             select btrim(x.ref) ref from history h
              cross join lateral unnest(string_to_array(coalesce(h.input_file,''),'|')) x(ref)
             union all select btrim(output_file) from history
              where btrim(coalesce(output_file,''))<>''
             union all select trim(both '"' from p.path::text) from history h
              cross join lateral jsonb_path_query(
                coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path') p(path)
           ) select ref,count(*) refs from refs where ref=any($1::text[]) group by ref""",
        keys,
    )
    return {str(row["ref"]): int(row["refs"]) for row in rows}


async def _head_candidates(
    candidates: list[dict[str, Any]],
    *,
    r2_client: Any,
    r2_bucket: str,
    nas_client: Any | None,
    concurrency: int,
    allow_source_missing: bool = False,
) -> int:
    loop = asyncio.get_running_loop()

    def check(candidate: dict[str, Any]) -> bool:
        source = None
        try:
            source = r2_client.head_object(
                Bucket=r2_bucket, Key=str(candidate["source_key"])
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            status = int(
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
            )
            if not allow_source_missing or (
                code not in {"404", "NoSuchKey", "NotFound"} and status != 404
            ):
                raise
        targets = {
            str(item["target_key"]): r2_client.head_object(
                Bucket=r2_bucket, Key=str(item["target_key"])
            )
            for item in candidate["targets"]
        }
        nas = None
        durability_basis = str(
            candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
        )
        if durability_basis == DURABILITY_NAS_ARCHIVE:
            if nas_client is None:
                raise RuntimeError("NAS client is required for nas-archive durability")
            nas = nas_client.head_object(
                Bucket=str(candidate["nas_bucket"]), Key=str(candidate["nas_key"])
            )
        elif durability_basis != DURABILITY_R2_PERSISTENT_TARGET:
            raise RuntimeError("unknown retirement durability basis")
        if source is None:
            validate_retirement_survivor_heads(
                candidate, target_heads=targets, nas_head=nas
            )
            candidate["_source_already_missing"] = True
            return True
        validate_retirement_object_heads(
            candidate, source_head=source, target_heads=targets, nas_head=nas
        )
        return False

    executor = ThreadPoolExecutor(
        max_workers=concurrency, thread_name_prefix="history-r2-retirement-head"
    )
    try:
        outcomes = await asyncio.gather(
            *(loop.run_in_executor(executor, check, item) for item in candidates)
        )
        return sum(bool(value) for value in outcomes)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


async def _plan_delete(args: argparse.Namespace) -> None:
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_sha = _sha256_json(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    if report_sha != report.get("report_sha256"):
        raise RuntimeError("retirement report identity changed")
    if report.get("parent_copy_plan_sha256") != args.parent_copy_plan_sha256:
        raise RuntimeError("retirement report Copy parent changed")
    r2_config = _load_secure_config(Path(args.config))
    archive_config = _durability_archive_config(
        args.durability_basis, args.archive_config
    )
    clear_proxy_environment()
    validate_endpoint_route(r2_config["target"])
    if archive_config is not None:
        validate_endpoint_route(archive_config["nas"])
    runtime_identity = _retirement_runtime_identity(
        artifact_digest=args.artifact_digest,
        r2_config=r2_config,
        durability_basis=args.durability_basis,
        archive_config=archive_config,
    )
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    production = await _connect("PRODUCTION_DATABASE_URL")
    r2_client = _s3_client(r2_config["target"], max_connections=16)
    nas_client = (
        _s3_client(archive_config["nas"], max_connections=16)
        if archive_config is not None
        else None
    )
    try:
        await ledger.execute(RETIREMENT_DDL)
        parent = await ledger.fetchrow(
            """select run_id from analytics_history_media_migration_plans
                 where plan_sha256=$1 and plan_type='copy'""",
            args.parent_copy_plan_sha256,
        )
        if parent is None:
            raise RuntimeError("unknown parent Copy plan")
        history_ids = _load_history_ids(Path(args.history_id_file))
        scoped_rows = [
            dict(row)
            for row in await ledger.fetch(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,byte_size,source_etag,target_etag,
                          source_last_modified,copy_plan_sha256,switch_plan_sha256,
                          switch_completed_at
                     from analytics_history_media_r2_migrations
                    where copy_plan_sha256=$1 and history_id=any($2::integer[])
                      and source_name is not null and source_key is not null
                    order by source_name,source_key,history_id,role,ordinal""",
                args.parent_copy_plan_sha256,
                list(history_ids),
            )
        ]
        selected_sources = sorted(
            {(str(row["source_name"]), str(row["source_key"])) for row in scoped_rows}
        )
        if not selected_sources:
            raise RuntimeError("retirement History scope has no migrated old sources")
        all_rows = [
            dict(row)
            for row in await ledger.fetch(
                SCOPED_COHORT_SQL,
                args.parent_copy_plan_sha256,
                [item[0] for item in selected_sources],
                [item[1] for item in selected_sources],
            )
        ]
        all_history_ids = sorted({int(row["history_id"]) for row in all_rows})
        if len(all_history_ids) > 10000:
            raise RuntimeError("retirement source fanout exceeds 10000 Histories")
        evidence_rows = (
            await production.fetch(PRODUCTION_ARCHIVE_EVIDENCE_SQL, all_history_ids)
            if args.durability_basis == DURABILITY_NAS_ARCHIVE
            else []
        )
        evidence = {
            (int(row["history_id"]), str(row["role"]), int(row["ordinal"])): dict(row)
            for row in evidence_rows
            if str(row["status"]) == "archived_verified"
            and str(row["outbox_status"]) == "archived"
        }
        pending_sources = {
            (str(row["source_name"]), str(row["source_key"]))
            for row in await ledger.fetch(
                """with selected as (
                     select * from unnest($1::text[],$2::text[])
                       as x(source_name,source_key))
                   select distinct m.source_name,m.source_key
                     from analytics_history_media_r2_migrations m join selected s
                       using(source_name,source_key)
                    where m.status in ('copy_required','failed')""",
                [item[0] for item in selected_sources],
                [item[1] for item in selected_sources],
            )
        }
        unswitched_sources = {
            (str(row["source_name"]), str(row["source_key"]))
            for row in await ledger.fetch(
                """with selected as (
                     select * from unnest($1::text[],$2::text[])
                       as x(source_name,source_key))
                   select distinct m.source_name,m.source_key
                     from analytics_history_media_r2_migrations m join selected s
                       using(source_name,source_key)
                    where m.original_ref<>m.target_key
                      and m.switch_completed_at is null""",
                [item[0] for item in selected_sources],
                [item[1] for item in selected_sources],
            )
        }
        collision_keys = {
            str(row["source_key"])
            for row in await ledger.fetch(
                """select distinct s.source_key
                     from unnest($1::text[]) s(source_key)
                     join analytics_history_media_r2_migrations m
                       on m.target_key=s.source_key""",
                [item[1] for item in selected_sources],
            )
        }
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in all_rows:
            grouped.setdefault(
                (str(row["source_name"]), str(row["source_key"])), []
            ).append(row)
        candidates: list[dict[str, Any]] = []
        for source, rows in grouped.items():
            receipts = [
                evidence.get(
                    (int(row["history_id"]), str(row["role"]), int(row["ordinal"]))
                )
                for row in rows
            ]
            verified = [
                receipt
                for row, receipt in zip(rows, receipts)
                if receipt is not None
                and int(receipt["byte_size"] or -1) == int(row["byte_size"])
                and str(receipt["source_ref"])
                in {str(row["original_ref"]), str(row["target_key"])}
            ]
            archive_shas = {str(item["sha256"]) for item in verified}
            archive_locations = sorted(
                {(str(item["nas_bucket"]), str(item["nas_key"])) for item in verified}
            )
            location = archive_locations[0] if archive_locations else ("", "")
            targets = [
                {
                    "target_key": target_key,
                    "copy_plan_sha256": copy_plan_sha,
                    "target_etag": target_etag,
                }
                for target_key, copy_plan_sha, target_etag in sorted(
                    {
                        (
                            str(row["target_key"]),
                            str(row["copy_plan_sha256"]),
                            str(row.get("target_etag") or ""),
                        )
                        for row in rows
                    }
                )
            ]
            candidates.append(
                {
                    "durability_basis": args.durability_basis,
                    "source_name": source[0],
                    "source_key": source[1],
                    "byte_size": int(rows[0]["byte_size"]),
                    "source_etag": str(rows[0]["source_etag"]),
                    "source_last_modified": rows[0]["source_last_modified"],
                    "asset_count": len(rows),
                    "switched_asset_count": sum(
                        row["switch_completed_at"] is not None for row in rows
                    ),
                    "pending_copy_refs": int(source in pending_sources),
                    "unswitched_refs": int(source in unswitched_sources),
                    "target_collisions": int(source[1] in collision_keys),
                    "live_history_refs": 0,
                    "archive_verified_asset_count": (
                        len(verified) if len(archive_shas) == 1 else 0
                    ),
                    "archive_sha256": (
                        next(iter(archive_shas)) if len(archive_shas) == 1 else ""
                    ),
                    "nas_bucket": location[0],
                    "nas_key": location[1],
                    "targets": targets,
                }
            )
        live_refs = await _live_reference_counts(
            production, [str(item["source_key"]) for item in candidates]
        )
        for item in candidates:
            item["live_history_refs"] = live_refs.get(str(item["source_key"]), 0)
        candidates = sorted(
            (
                item
                for item in candidates
                if classify_retirement_candidate(item) == "eligible"
            ),
            key=lambda item: (
                -int(item["byte_size"]),
                _key_sha(item["source_name"], item["source_key"]),
            ),
        )[: args.limit]
        if not candidates:
            raise RuntimeError("no durable zero-reference old sources are eligible")
        await _head_candidates(
            candidates,
            r2_client=r2_client,
            r2_bucket=str(r2_config["target"]["bucket"]),
            nas_client=nas_client,
            concurrency=min(8, args.head_concurrency),
        )
        switch_plans = [
            str(row["switch_plan_sha256"])
            for row in await ledger.fetch(
                """select distinct switch_plan_sha256
                     from analytics_history_media_r2_migrations
                    where copy_plan_sha256=$1 and switch_completed_at is not null
                    order by switch_plan_sha256""",
                args.parent_copy_plan_sha256,
            )
        ]
        manifest, frozen, batches = build_retirement_plan(
            run_id=str(parent["run_id"]),
            parent_copy_plan_sha256=args.parent_copy_plan_sha256,
            parent_switch_plan_sha256s=switch_plans,
            objects=candidates,
            report_sha256=report_sha,
            runtime_identity=runtime_identity,
            durability_basis=args.durability_basis,
            batch_size=args.batch_size,
        )
        async with ledger.transaction():
            await ledger.execute(
                """insert into analytics_history_media_r2_retirement_plans(
                     plan_sha256,run_id,parent_copy_plan_sha256,rowset_sha256,manifest)
                   values($1,$2,$3,$4,$5::jsonb)""",
                manifest["plan_sha256"],
                uuid.UUID(manifest["run_id"]),
                args.parent_copy_plan_sha256,
                manifest["rowset_sha256"],
                json.dumps(manifest),
            )
            await ledger.executemany(
                """insert into analytics_history_media_r2_retirement_batches(
                     plan_sha256,batch_no,object_count,total_bytes,rowset_sha256)
                   values($1,$2,$3,$4,$5)""",
                [
                    (
                        manifest["plan_sha256"],
                        item["batch_no"],
                        item["object_count"],
                        item["total_bytes"],
                        item["rowset_sha256"],
                    )
                    for item in batches
                ],
            )
            await ledger.executemany(
                """insert into analytics_history_media_r2_retirement_objects(
                     plan_sha256,batch_no,object_no,source_name,source_key,
                     source_key_sha256,byte_size,source_etag,source_last_modified,
                     asset_count,archive_sha256,nas_bucket,nas_key,target_facts)
                   values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)""",
                [
                    (
                        manifest["plan_sha256"],
                        int(item["batch_no"]),
                        index,
                        item["source_name"],
                        item["source_key"],
                        item["source_key_sha256"],
                        int(item["byte_size"]),
                        item["source_etag"],
                        item["source_last_modified"],
                        int(item["asset_count"]),
                        item["archive_sha256"],
                        item["nas_bucket"],
                        item["nas_key"],
                        json.dumps(item["targets"]),
                    )
                    for index, item in enumerate(frozen)
                ],
            )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "object_count": manifest["object_count"],
                    "total_bytes": manifest["total_bytes"],
                    "batch_count": manifest["batch_count"],
                    "rowset_sha256": manifest["rowset_sha256"],
                    "manifest": str(output),
                }
            )
        )
    finally:
        await production.close()
        await ledger.close()
        r2_client.close()
        if nas_client is not None:
            nas_client.close()


def _expected_switch_counts(values: Iterable[str]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for raw in values:
        plan_sha, separator, count_raw = str(raw).partition("=")
        if (
            separator != "="
            or len(plan_sha) != 64
            or any(char not in "0123456789abcdef" for char in plan_sha)
        ):
            raise ValueError("expected Switch count must be <64-lower-hex-sha>=<count>")
        count = int(count_raw)
        if count < 1 or plan_sha in parsed:
            raise ValueError("expected Switch counts must be unique and positive")
        parsed[plan_sha] = count
    return parsed


def _stream_json_identity(
    hasher: Any, identity: dict[str, Any], *, first: bool
) -> bool:
    if first:
        hasher.update(b"[")
    else:
        hasher.update(b",")
    hasher.update(_canonical_json(identity))
    return False


async def _bulk_scope_fingerprint(
    ledger: asyncpg.Connection,
    switch_plan_sha256s: list[str],
) -> tuple[str, dict[str, int], set[str]]:
    row = await ledger.fetchrow(
        """with scope as materialized (
             select * from analytics_history_media_r2_migrations
              where switch_plan_sha256=any($1::text[])
           ), ordered as (
             select *,((row_number() over(
                        order by switch_plan_sha256,id)-1)/10000)::bigint chunk_no,
                    encode(sha256(convert_to(jsonb_build_array(
                      id,history_id,role,ordinal,original_ref,target_key,
                      source_name,source_key,byte_size,source_etag,
                      source_last_modified,copy_plan_sha256,switch_plan_sha256,
                      switch_completed_at)::text,'UTF8')),'hex') row_sha
               from scope
           ), chunks as (
             select chunk_no,encode(sha256(convert_to(
                      string_agg(row_sha,'' order by switch_plan_sha256,id),
                      'UTF8')),'hex') chunk_sha
               from ordered group by chunk_no
           ), fingerprint as (
             select encode(sha256(convert_to(
                      string_agg(chunk_sha,'' order by chunk_no),'UTF8')),'hex') value
               from chunks
           ), counts as (
             select jsonb_object_agg(switch_plan_sha256,asset_count
                                      order by switch_plan_sha256) value
               from (select switch_plan_sha256,count(*) asset_count
                       from scope group by switch_plan_sha256) c
           )
           select (select value from fingerprint) asset_scope_sha256,
                  (select value from counts) scope_counts,
                  array(select distinct copy_plan_sha256 from scope order by 1)
                    copy_plan_sha256s,
                  count(*) scope_count,
                  bool_and(switch_completed_at is not null
                           and original_ref<>target_key
                           and source_name is not null and source_key is not null)
                    fully_completed
             from scope""",
        switch_plan_sha256s,
        timeout=3600,
    )
    if row is None or not int(row["scope_count"] or 0):
        raise RuntimeError("bulk retirement Switch scope is empty")
    if not bool(row["fully_completed"]):
        raise RuntimeError("bulk retirement Switch scope is not fully completed")
    raw_counts = row["scope_counts"]
    counts = {
        str(key): int(value)
        for key, value in (
            json.loads(raw_counts) if isinstance(raw_counts, str) else dict(raw_counts)
        ).items()
    }
    copy_plans = {str(value) for value in row["copy_plan_sha256s"]}
    return str(row["asset_scope_sha256"]), counts, copy_plans


BULK_RETIREMENT_STAGE_SQL = """
create temporary table bulk_retirement_candidates on commit preserve rows as
with scope as materialized (
  select * from analytics_history_media_r2_migrations
   where switch_plan_sha256=any($1::text[])
), selected_sources as materialized (
  select distinct source_name,source_key from scope
), all_rows as materialized (
  select m.* from analytics_history_media_r2_migrations m
    join selected_sources s using(source_name,source_key)
), source_stats as (
  select source_name,source_key,min(byte_size) byte_size,
         min(nullif(trim(both '"' from source_etag),'')) source_etag,
         min(source_last_modified) source_last_modified,
         count(*)::integer asset_count,
         count(distinct byte_size) byte_size_variants,
         count(distinct nullif(trim(both '"' from source_etag),''))
           source_etag_variants,
         count(distinct source_last_modified) source_time_variants
    from all_rows group by source_name,source_key
), target_rows as (
  select source_name,source_key,
         jsonb_agg(jsonb_build_object(
           'target_key',target_key,
           'copy_plan_sha256',copy_plan_sha256,
           'target_etag',target_etag
         ) order by target_key,copy_plan_sha256,target_etag) target_facts
    from (
      select distinct source_name,source_key,target_key,copy_plan_sha256,
             coalesce(target_etag,'') target_etag
        from all_rows
    ) t group by source_name,source_key
), scope_counts as (
  select source_name,source_key,sum(coordinate_count)::integer scope_asset_count,
         jsonb_object_agg(switch_plan_sha256,coordinate_count
                          order by switch_plan_sha256) scope_facts
    from (
      select source_name,source_key,switch_plan_sha256,
             count(*)::integer coordinate_count
        from scope group by source_name,source_key,switch_plan_sha256
    ) c group by source_name,source_key
)
select s.source_name,s.source_key,s.byte_size,s.source_etag,s.source_last_modified,
       s.asset_count,c.scope_asset_count,c.scope_facts,t.target_facts,
       s.byte_size_variants,s.source_etag_variants,s.source_time_variants
  from source_stats s join scope_counts c using(source_name,source_key)
  join target_rows t using(source_name,source_key)
"""


async def _prepare_bulk_retirement_stage(
    ledger: asyncpg.Connection,
    switch_plan_sha256s: list[str],
    *,
    canary_size: int,
    batch_size: int,
) -> None:
    await ledger.execute(BULK_RETIREMENT_STAGE_SQL, switch_plan_sha256s, timeout=3600)
    invalid = int(
        await ledger.fetchval(
            """select count(*) from bulk_retirement_candidates
                where byte_size_variants<>1 or source_etag_variants>1
                   or source_time_variants<>1 or jsonb_array_length(target_facts)=0
                   or exists(
                     select 1 from jsonb_array_elements(target_facts) f
                      group by f->>'target_key' having count(*)>1)"""
        )
    )
    if invalid:
        raise RuntimeError("bulk retirement source or target facts are inconsistent")
    blocked = bool(
        await ledger.fetchval(
            """with blockers as (
                 select 1 from bulk_retirement_candidates s
                   join analytics_history_media_r2_migrations m
                     using(source_name,source_key)
                  where m.status in ('copy_required','failed')
                 union all
                 select 1 from bulk_retirement_candidates s
                   join analytics_history_media_r2_migrations m
                     using(source_name,source_key)
                  where m.original_ref<>m.target_key
                    and m.switch_completed_at is null
                 union all
                 select 1 from bulk_retirement_candidates s
                   join analytics_history_media_r2_migrations m
                     on m.target_key=s.source_key
               ) select exists(select 1 from blockers limit 1)""",
            timeout=RETIREMENT_BLOCKER_TIMEOUT_SECONDS,
        )
    )
    if blocked:
        raise RuntimeError("bulk retirement scope has a Copy or Switch blocker")
    await ledger.execute(
        """create temporary table bulk_retirement_ordered on commit preserve rows as
             select c.*,
                    (row_number() over(
                       order by byte_size desc,
                                encode(sha256(
                                  convert_to(source_name,'UTF8')||decode('00','hex')||
                                  convert_to(source_key,'UTF8')),'hex')
                     )-1)::integer object_no
               from bulk_retirement_candidates c"""
    )
    await ledger.execute(
        "alter table bulk_retirement_ordered add column batch_no integer"
    )
    await ledger.execute(
        """update bulk_retirement_ordered
              set batch_no=case when object_no<$1 then 0
                                else 1+((object_no-$1)/$2) end""",
        canary_size,
        batch_size,
    )


async def _bulk_production_has_live_refs(
    ledger: asyncpg.Connection,
    production: asyncpg.Connection,
) -> bool:
    await production.execute(
        """create temporary table bulk_retirement_source_keys(
             source_key text not null) on commit preserve rows"""
    )
    async with ledger.transaction():
        statement = await ledger.prepare(
            """select distinct source_key from bulk_retirement_ordered
                order by source_key"""
        )
        pending: list[tuple[str]] = []
        async for row in statement.cursor(prefetch=10000):
            pending.append((str(row["source_key"]),))
            if len(pending) == 10000:
                await production.copy_records_to_table(
                    "bulk_retirement_source_keys",
                    records=pending,
                    columns=["source_key"],
                )
                pending.clear()
        if pending:
            await production.copy_records_to_table(
                "bulk_retirement_source_keys",
                records=pending,
                columns=["source_key"],
            )
    return bool(
        await production.fetchval(
            """with refs as (
                 select btrim(x.ref) ref from history h
                  cross join lateral unnest(
                    string_to_array(coalesce(h.input_file,''),'|')) x(ref)
                 union all select btrim(output_file) from history
                  where btrim(coalesce(output_file,''))<>''
                 union all select trim(both '"' from p.path::text) from history h
                  cross join lateral jsonb_path_query(
                    coalesce(h.extra_outputs::jsonb,'{}'::jsonb),
                    'strict $.**.path') p(path)
               ) select exists(
                   select 1 from refs r join bulk_retirement_source_keys s
                     on s.source_key=r.ref limit 1)""",
            timeout=600,
        )
    )


def _candidate_from_bulk_stage(row: Any) -> dict[str, Any]:
    targets = row["target_facts"]
    scope_facts = row["scope_facts"]
    return {
        "durability_basis": DURABILITY_R2_PERSISTENT_TARGET,
        "source_name": str(row["source_name"]),
        "source_key": str(row["source_key"]),
        "byte_size": int(row["byte_size"]),
        "source_etag": str(row["source_etag"] or ""),
        "source_last_modified": row["source_last_modified"],
        "asset_count": int(row["asset_count"]),
        "scope_asset_count": int(row["scope_asset_count"]),
        "scope_switch_counts": (
            json.loads(scope_facts) if isinstance(scope_facts, str) else dict(scope_facts)
        ),
        "archive_sha256": "",
        "nas_bucket": "",
        "nas_key": "",
        "targets": json.loads(targets) if isinstance(targets, str) else list(targets),
    }


async def _bulk_staged_identity(
    ledger: asyncpg.Connection,
) -> tuple[str, list[dict[str, Any]], int, int]:
    global_hasher = hashlib.sha256()
    global_first = True
    batch_hasher = hashlib.sha256()
    batch_first = True
    current_batch: int | None = None
    batch_count = 0
    batch_assets = 0
    batch_bytes = 0
    batches: list[dict[str, Any]] = []
    object_count = 0
    total_bytes = 0

    def finish_batch() -> None:
        nonlocal batch_first
        if current_batch is None:
            return
        batch_hasher.update(b"]")
        batches.append(
            {
                "batch_no": current_batch,
                "is_canary": current_batch == 0,
                "object_count": batch_count,
                "asset_coordinate_count": batch_assets,
                "total_bytes": batch_bytes,
                "rowset_sha256": batch_hasher.hexdigest(),
            }
        )
        batch_first = True

    async with ledger.transaction():
        statement = await ledger.prepare(
            """select * from bulk_retirement_ordered order by object_no"""
        )
        async for row in statement.cursor(prefetch=5000):
            candidate = _candidate_from_bulk_stage(row)
            identity = _retirement_object_identity(candidate)
            row_batch = int(row["batch_no"])
            if current_batch != row_batch:
                finish_batch()
                current_batch = row_batch
                batch_hasher = hashlib.sha256()
                batch_count = 0
                batch_assets = 0
                batch_bytes = 0
            global_first = _stream_json_identity(
                global_hasher, identity, first=global_first
            )
            batch_first = _stream_json_identity(
                batch_hasher, identity, first=batch_first
            )
            batch_count += 1
            batch_assets += int(candidate["scope_asset_count"])
            batch_bytes += int(candidate["byte_size"])
            object_count += 1
            total_bytes += int(candidate["byte_size"])
    finish_batch()
    if global_first:
        raise RuntimeError("bulk retirement candidate rowset is empty")
    global_hasher.update(b"]")
    return global_hasher.hexdigest(), batches, object_count, total_bytes


async def _plan_bulk_delete(args: argparse.Namespace) -> None:
    switch_plans = [str(value) for value in args.switch_plan_sha256]
    if len(switch_plans) != len(set(switch_plans)):
        raise ValueError("bulk retirement requires unique Switch plans")
    expected_counts = _expected_switch_counts(args.expected_switch_asset_count)
    if set(expected_counts) != set(switch_plans):
        raise ValueError("every bulk Switch plan requires one exact expected count")
    r2_config = _load_secure_config(Path(args.config))
    clear_proxy_environment()
    validate_endpoint_route(r2_config["target"])
    runtime_identity = _retirement_runtime_identity(
        artifact_digest=args.artifact_digest,
        r2_config=r2_config,
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_config=None,
    )
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    production = await _connect("PRODUCTION_DATABASE_URL")
    try:
        await ledger.execute(RETIREMENT_DDL)
        plan_rows = await ledger.fetch(
            """select plan_sha256,run_id,rowset_sha256,manifest from
                 analytics_history_media_migration_plans
                where plan_type='switch' and plan_sha256=any($1::text[])
                order by plan_sha256""",
            switch_plans,
        )
        if len(plan_rows) != len(switch_plans):
            raise RuntimeError("unknown bulk retirement Switch plan")
        for row in plan_rows:
            switch_manifest = (
                json.loads(row["manifest"])
                if isinstance(row["manifest"], str)
                else dict(row["manifest"])
            )
            if (
                str(switch_manifest.get("plan_sha256") or "")
                != str(row["plan_sha256"])
                or _sha256_json(
                    {
                        key: value
                        for key, value in switch_manifest.items()
                        if key != "plan_sha256"
                    }
                )
                != str(row["plan_sha256"])
            ):
                raise RuntimeError("bulk retirement parent Switch identity changed")
        run_ids = {str(row["run_id"]) for row in plan_rows}
        if len(run_ids) != 1:
            raise RuntimeError("bulk retirement Switch plans belong to different runs")
        switch_rowsets = {
            str(row["plan_sha256"]): str(row["rowset_sha256"]) for row in plan_rows
        }
        batch_proofs = await ledger.fetch(
            """select plan_sha256,count(*) batch_count,
                      count(*) filter(where status<>'completed') incomplete_batches,
                      coalesce(sum(asset_count),0) asset_count
                 from analytics_history_media_migration_plan_batches
                where plan_sha256=any($1::text[]) group by plan_sha256""",
            switch_plans,
        )
        for proof in batch_proofs:
            plan_sha = str(proof["plan_sha256"])
            if int(proof["incomplete_batches"]) or int(
                proof["asset_count"]
            ) != expected_counts[plan_sha]:
                raise RuntimeError("bulk retirement parent Switch is incomplete")
        asset_scope_sha, actual_counts, copy_plans = await _bulk_scope_fingerprint(
            ledger, sorted(switch_plans)
        )
        if actual_counts != expected_counts:
            raise RuntimeError("bulk retirement Switch asset counts changed")
        await _prepare_bulk_retirement_stage(
            ledger,
            sorted(switch_plans),
            canary_size=args.canary_size,
            batch_size=args.batch_size,
        )
        if await _bulk_production_has_live_refs(ledger, production):
            raise RuntimeError("bulk retirement scope still has a live History reference")
        rowset_sha, batches, object_count, total_bytes = await _bulk_staged_identity(
            ledger
        )
        asset_count = int(
            await ledger.fetchval(
                "select coalesce(sum(scope_asset_count),0) from bulk_retirement_ordered"
            )
        )
        if asset_count != sum(expected_counts.values()):
            raise RuntimeError("bulk retirement asset coordinate count changed")
        switch_scopes = [
            {
                "switch_plan_sha256": plan_sha,
                "asset_coordinate_count": expected_counts[plan_sha],
                "rowset_sha256": switch_rowsets[plan_sha],
            }
            for plan_sha in sorted(switch_plans)
        ]
        manifest: dict[str, Any] = {
            "schema": "allbot-history-media-r2-bulk-retirement-plan/v1",
            "execution_mode": "bulk",
            "durability_basis": DURABILITY_R2_PERSISTENT_TARGET,
            "run_id": next(iter(run_ids)),
            "parent_copy_plan_sha256s": sorted(copy_plans),
            "parent_switch_plan_sha256s": sorted(switch_plans),
            "switch_scopes": switch_scopes,
            "asset_coordinate_count": asset_count,
            "asset_scope_sha256": asset_scope_sha,
            "asset_scope_algorithm": "history-r2-bulk-scope-merkle-v1",
            "source_identity_policy": BULK_SOURCE_IDENTITY_POLICY,
            "object_count": object_count,
            "total_bytes": total_bytes,
            "canary_object_count": min(args.canary_size, object_count),
            "batch_count": len(batches),
            "batch_size": args.batch_size,
            "rowset_sha256": rowset_sha,
            "batches_sha256": _sha256_json(batches),
            "one_confirmation_covers_all_batches": True,
            "object_keys_redacted": True,
            "runtime_identity": runtime_identity,
        }
        manifest["plan_sha256"] = _sha256_json(manifest)
        async with ledger.transaction():
            await ledger.execute(
                """insert into analytics_history_media_r2_retirement_plans(
                     plan_sha256,run_id,parent_copy_plan_sha256,rowset_sha256,
                     manifest,execution_mode,asset_coordinate_count)
                   values($1,$2,null,$3,$4::jsonb,'bulk',$5)""",
                manifest["plan_sha256"],
                uuid.UUID(manifest["run_id"]),
                manifest["rowset_sha256"],
                json.dumps(manifest),
                asset_count,
            )
            await ledger.executemany(
                """insert into analytics_history_media_r2_retirement_batches(
                     plan_sha256,batch_no,object_count,total_bytes,rowset_sha256,
                     is_canary,asset_coordinate_count)
                   values($1,$2,$3,$4,$5,$6,$7)""",
                [
                    (
                        manifest["plan_sha256"],
                        item["batch_no"],
                        item["object_count"],
                        item["total_bytes"],
                        item["rowset_sha256"],
                        item["is_canary"],
                        item["asset_coordinate_count"],
                    )
                    for item in batches
                ],
            )
            await ledger.execute(
                """insert into analytics_history_media_r2_retirement_objects(
                     plan_sha256,batch_no,object_no,source_name,source_key,
                     source_key_sha256,byte_size,source_etag,source_last_modified,
                     asset_count,archive_sha256,nas_bucket,nas_key,target_facts,
                     scope_asset_count,scope_facts)
                   select $1,batch_no,object_no,source_name,source_key,
                          encode(sha256(
                            convert_to(source_name,'UTF8')||decode('00','hex')||
                            convert_to(source_key,'UTF8')),'hex'),
                          byte_size,source_etag,source_last_modified,asset_count,
                          '', '', '',target_facts,scope_asset_count,scope_facts
                     from bulk_retirement_ordered order by object_no""",
                manifest["plan_sha256"],
                timeout=3600,
            )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "switch_plan_count": len(switch_plans),
                    "copy_plan_count": len(copy_plans),
                    "asset_coordinate_count": asset_count,
                    "object_count": object_count,
                    "total_bytes": total_bytes,
                    "canary_object_count": manifest["canary_object_count"],
                    "batch_count": len(batches),
                    "rowset_sha256": rowset_sha,
                    "batches_sha256": manifest["batches_sha256"],
                    "asset_scope_sha256": asset_scope_sha,
                    "manifest": str(output),
                },
                sort_keys=True,
            )
        )
    finally:
        await production.close()
        await ledger.close()


async def _source_missing(client: Any, bucket: str, key: str) -> bool:
    try:
        await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
        return False
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        status = int(
            exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
        )
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return True
        raise


async def _execute_delete(args: argparse.Namespace) -> None:
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    production = await _connect("PRODUCTION_DATABASE_URL")
    r2_config = _load_secure_config(Path(args.config))
    archive_config = _durability_archive_config(
        args.durability_basis, args.archive_config
    )
    clear_proxy_environment()
    validate_endpoint_route(r2_config["target"])
    if archive_config is not None:
        validate_endpoint_route(archive_config["nas"])
    r2_client = _s3_client(r2_config["target"], max_connections=args.delete_concurrency)
    nas_client = (
        _s3_client(archive_config["nas"], max_connections=args.delete_concurrency)
        if archive_config is not None
        else None
    )
    try:
        await ledger.execute(RETIREMENT_DDL)
        missing_indexes = await _missing_retirement_blocker_indexes(ledger)
        if missing_indexes:
            raise RuntimeError(
                "retirement blocker indexes are not prepared; run prepare-delete-indexes"
            )
        plan = await ledger.fetchrow(
            """select run_id,manifest,status
                 from analytics_history_media_r2_retirement_plans
                where plan_sha256=$1""",
            args.plan_sha256,
        )
        if plan is None:
            raise RuntimeError("unknown exact retirement plan SHA")
        manifest = (
            json.loads(plan["manifest"])
            if isinstance(plan["manifest"], str)
            else dict(plan["manifest"])
        )
        if (
            _sha256_json(
                {key: value for key, value in manifest.items() if key != "plan_sha256"}
            )
            != args.plan_sha256
        ):
            raise RuntimeError("stored retirement plan identity changed")
        is_bulk = manifest.get("execution_mode") == "bulk"
        if is_bulk and not bool(getattr(args, "_bulk_preflight_done", False)):
            raise RuntimeError("bulk retirement requires global preflight")
        validate_delete_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        manifest_durability_basis = str(
            manifest.get("durability_basis") or DURABILITY_NAS_ARCHIVE
        )
        if args.durability_basis != manifest_durability_basis:
            raise RuntimeError("retirement durability basis changed")
        actual_runtime = _retirement_runtime_identity(
            artifact_digest=args.artifact_digest,
            r2_config=r2_config,
            durability_basis=manifest_durability_basis,
            archive_config=archive_config,
        )
        if actual_runtime != manifest["runtime_identity"]:
            raise RuntimeError("retirement runtime identity changed")
        await ledger.execute(
            """update analytics_history_media_r2_retirement_plans
                 set status='running',updated_at=now()
               where plan_sha256=$1 and status in ('frozen','paused')""",
            args.plan_sha256,
        )
        batch = await ledger.fetchrow(
            """select * from analytics_history_media_r2_retirement_batches
                 where plan_sha256=$1 and status<>'completed'
                 order by batch_no limit 1""",
            args.plan_sha256,
        )
        if batch is None:
            print(json.dumps({"deleted": 0, "remaining_batches": 0}))
            return
        objects = [
            dict(row)
            for row in await ledger.fetch(
                """select * from analytics_history_media_r2_retirement_objects
                     where plan_sha256=$1 and batch_no=$2 and status='planned'
                     order by object_no""",
                args.plan_sha256,
                int(batch["batch_no"]),
            )
        ]
        for item in objects:
            item["durability_basis"] = manifest_durability_basis
            item["targets"] = (
                json.loads(item["target_facts"])
                if isinstance(item["target_facts"], str)
                else list(item["target_facts"])
            )
            if is_bulk:
                scope_facts = item.get("scope_facts") or {}
                item["scope_switch_counts"] = (
                    json.loads(scope_facts)
                    if isinstance(scope_facts, str)
                    else dict(scope_facts)
                )
                item["source_identity_policy"] = str(
                    manifest.get("source_identity_policy") or ""
                )
            item["archive_verified_asset_count"] = int(item["asset_count"])
        if not is_bulk:
            all_objects = [
                dict(row)
                for row in await ledger.fetch(
                    """select source_name,source_key,source_key_sha256,byte_size,
                              source_etag,source_last_modified,asset_count,archive_sha256,
                              nas_bucket,nas_key,target_facts
                         from analytics_history_media_r2_retirement_objects
                        where plan_sha256=$1 order by object_no""",
                    args.plan_sha256,
                )
            ]
            for item in all_objects:
                item["durability_basis"] = manifest_durability_basis
                item["targets"] = (
                    json.loads(item["target_facts"])
                    if isinstance(item["target_facts"], str)
                    else list(item["target_facts"])
                )
            if (
                len(all_objects) != int(manifest["object_count"])
                or _sha256_json(
                    [_retirement_object_identity(item) for item in all_objects]
                )
                != manifest["rowset_sha256"]
            ):
                raise RuntimeError("retirement global rowset changed")
        identities = [_retirement_object_identity(item) for item in objects]
        if len(objects) != int(batch["object_count"]) or _sha256_json(
            identities
        ) != str(batch["rowset_sha256"]):
            raise RuntimeError("retirement batch rowset changed")
        await ledger.execute(
            """update analytics_history_media_r2_retirement_batches
                 set status='running',started_at=coalesce(started_at,now()),
                     updated_at=now()
               where plan_sha256=$1 and batch_no=$2 and status<>'completed'""",
            args.plan_sha256,
            int(batch["batch_no"]),
        )
        live_refs = await _live_reference_counts(
            production, [str(item["source_key"]) for item in objects]
        )
        if live_refs:
            raise RuntimeError("retirement batch gained a live History reference")
        if await _retirement_has_blockers(ledger, objects):
            raise RuntimeError("retirement batch gained a Copy or Switch blocker")
        recovered_missing = await _head_candidates(
            objects,
            r2_client=r2_client,
            r2_bucket=str(r2_config["target"]["bucket"]),
            nas_client=nas_client,
            concurrency=args.delete_concurrency,
            allow_source_missing=True,
        )
        semaphore = asyncio.Semaphore(args.delete_concurrency)

        async def delete_one(item: dict[str, Any]) -> None:
            async with semaphore:
                if not item.get("_source_already_missing"):
                    await asyncio.to_thread(
                        r2_client.delete_object,
                        Bucket=str(r2_config["target"]["bucket"]),
                        Key=str(item["source_key"]),
                    )
                if not await _source_missing(
                    r2_client,
                    str(r2_config["target"]["bucket"]),
                    str(item["source_key"]),
                ):
                    raise RuntimeError("old source still exists after delete")
                target_heads = {
                    str(target["target_key"]): await asyncio.to_thread(
                        r2_client.head_object,
                        Bucket=str(r2_config["target"]["bucket"]),
                        Key=str(target["target_key"]),
                    )
                    for target in item["targets"]
                }
                nas_head = None
                if manifest_durability_basis == DURABILITY_NAS_ARCHIVE:
                    if nas_client is None:
                        raise RuntimeError(
                            "NAS client is required for nas-archive durability"
                        )
                    nas_head = await asyncio.to_thread(
                        nas_client.head_object,
                        Bucket=str(item["nas_bucket"]),
                        Key=str(item["nas_key"]),
                    )
                for target in item["targets"]:
                    head = target_heads[str(target["target_key"])]
                    if str(
                        (head.get("Metadata") or {}).get("allbot-copy-plan-sha256")
                        or ""
                    ) != str(target["copy_plan_sha256"]):
                        raise RuntimeError(
                            "verified target marker changed after delete"
                        )
                validate_retirement_survivor_heads(
                    item, target_heads=target_heads, nas_head=nas_head
                )

        await asyncio.gather(*(delete_one(item) for item in objects))
        async with ledger.transaction():
            await ledger.execute(
                """update analytics_history_media_r2_retirement_objects
                     set status='deleted',deleted_at=now(),updated_at=now()
                   where plan_sha256=$1 and batch_no=$2 and status='planned'""",
                args.plan_sha256,
                int(batch["batch_no"]),
            )
            await ledger.execute(
                """update analytics_history_media_r2_retirement_batches
                     set status='completed',started_at=coalesce(started_at,now()),
                         completed_at=now(),outcome_counts=$3::jsonb,updated_at=now()
                   where plan_sha256=$1 and batch_no=$2""",
                args.plan_sha256,
                int(batch["batch_no"]),
                json.dumps(
                    {
                        "deleted": len(objects),
                        "already_missing_recovered": recovered_missing,
                    }
                ),
            )
        remaining = int(
            await ledger.fetchval(
                """select count(*) from analytics_history_media_r2_retirement_batches
                     where plan_sha256=$1 and status<>'completed'""",
                args.plan_sha256,
            )
        )
        if remaining == 0 and not is_bulk:
            await ledger.execute(
                """update analytics_history_media_r2_retirement_plans
                     set status='completed',completed_at=now(),updated_at=now()
                   where plan_sha256=$1""",
                args.plan_sha256,
            )
        print(
            json.dumps(
                {
                    "deleted": len(objects),
                    "already_missing_recovered": recovered_missing,
                    "remaining_batches": remaining,
                }
            )
        )
    except Exception:
        try:
            await _mark_retirement_plan_paused(args.plan_sha256)
        except Exception as pause_error:
            print(
                json.dumps(
                    {
                        "event": "retirement_plan_pause_failed",
                        "error_type": type(pause_error).__name__,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        raise
    finally:
        await production.close()
        await ledger.close()
        r2_client.close()
        if nas_client is not None:
            nas_client.close()


async def _bulk_plan_coverage_counts(
    ledger: asyncpg.Connection,
    plan_sha256: str,
) -> tuple[int, int]:
    row = await ledger.fetchrow(
        """select count(*) object_count,
                  coalesce(sum(scope_asset_count),0) asset_coordinate_count
             from analytics_history_media_r2_retirement_objects
            where plan_sha256=$1""",
        plan_sha256,
    )
    return int(row["object_count"]), int(row["asset_coordinate_count"])


async def _bulk_global_preflight(args: argparse.Namespace) -> dict[str, Any]:
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        row = await ledger.fetchrow(
            """select manifest,status from analytics_history_media_r2_retirement_plans
                 where plan_sha256=$1""",
            args.plan_sha256,
        )
        if row is None:
            raise RuntimeError("unknown exact bulk retirement plan SHA")
        manifest = (
            json.loads(row["manifest"])
            if isinstance(row["manifest"], str)
            else dict(row["manifest"])
        )
        if manifest.get("execution_mode") != "bulk":
            raise RuntimeError("retirement plan is not a bulk plan")
        if (
            _sha256_json(
                {key: value for key, value in manifest.items() if key != "plan_sha256"}
            )
            != args.plan_sha256
        ):
            raise RuntimeError("stored bulk retirement plan identity changed")
        validate_delete_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        r2_config = _load_secure_config(Path(args.config))
        clear_proxy_environment()
        validate_endpoint_route(r2_config["target"])
        actual_runtime = _retirement_runtime_identity(
            artifact_digest=args.artifact_digest,
            r2_config=r2_config,
            durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
            archive_config=None,
        )
        if actual_runtime != manifest["runtime_identity"]:
            raise RuntimeError("bulk retirement runtime identity changed")
        switch_plans = [str(value) for value in manifest["parent_switch_plan_sha256s"]]
        scope_sha, counts, copy_plans = await _bulk_scope_fingerprint(
            ledger, switch_plans
        )
        expected_counts = {
            str(item["switch_plan_sha256"]): int(item["asset_coordinate_count"])
            for item in manifest["switch_scopes"]
        }
        if (
            scope_sha != manifest["asset_scope_sha256"]
            or counts != expected_counts
            or sorted(copy_plans) != manifest["parent_copy_plan_sha256s"]
        ):
            raise RuntimeError("bulk retirement global Switch scope changed")
        object_count, asset_count = await _bulk_plan_coverage_counts(
            ledger, args.plan_sha256
        )
        if (
            object_count != int(manifest["object_count"])
            or asset_count != int(manifest["asset_coordinate_count"])
        ):
            raise RuntimeError("bulk retirement stored coverage changed")
        batch_rows = await ledger.fetch(
            """select batch_no,is_canary,object_count,asset_coordinate_count,
                      total_bytes,rowset_sha256
                 from analytics_history_media_r2_retirement_batches
                where plan_sha256=$1 order by batch_no""",
            args.plan_sha256,
        )
        batches = [
            {
                "batch_no": int(item["batch_no"]),
                "is_canary": bool(item["is_canary"]),
                "object_count": int(item["object_count"]),
                "asset_coordinate_count": int(item["asset_coordinate_count"]),
                "total_bytes": int(item["total_bytes"]),
                "rowset_sha256": str(item["rowset_sha256"]),
            }
            for item in batch_rows
        ]
        if (
            len(batches) != int(manifest["batch_count"])
            or _sha256_json(batches) != manifest["batches_sha256"]
            or not batches
            or not batches[0]["is_canary"]
            or any(item["is_canary"] for item in batches[1:])
        ):
            raise RuntimeError("bulk retirement batch identities changed")
        await ledger.execute(
            """update analytics_history_media_r2_retirement_plans
                 set status='running',updated_at=now()
               where plan_sha256=$1 and status in ('frozen','paused')""",
            args.plan_sha256,
        )
        print(
            json.dumps(
                {
                    "event": "bulk_retirement_global_preflight_completed",
                    "asset_coordinate_count": asset_count,
                    "object_count": object_count,
                    "batch_count": len(batches),
                },
                sort_keys=True,
            )
        )
        return manifest
    finally:
        await ledger.close()


async def _finalize_bulk_delete(
    plan_sha256: str,
    manifest: dict[str, Any],
) -> None:
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        summary = await ledger.fetchrow(
            """select count(*) object_count,
                      count(*) filter(where status='deleted') deleted_count,
                      coalesce(sum(scope_asset_count),0) asset_coordinate_count
                 from analytics_history_media_r2_retirement_objects
                where plan_sha256=$1""",
            plan_sha256,
        )
        incomplete_batches = int(
            await ledger.fetchval(
                """select count(*) from analytics_history_media_r2_retirement_batches
                     where plan_sha256=$1 and status<>'completed'""",
                plan_sha256,
            )
        )
        if (
            int(summary["object_count"]) != int(manifest["object_count"])
            or int(summary["deleted_count"]) != int(manifest["object_count"])
            or int(summary["asset_coordinate_count"])
            != int(manifest["asset_coordinate_count"])
            or incomplete_batches
        ):
            raise RuntimeError("bulk retirement final ledger validation failed")
        await ledger.execute(
            """update analytics_history_media_r2_retirement_plans
                 set status='completed',completed_at=now(),updated_at=now()
               where plan_sha256=$1 and status='running'""",
            plan_sha256,
        )
        print(
            json.dumps(
                {
                    "event": "bulk_retirement_completed",
                    "asset_coordinate_count": int(
                        manifest["asset_coordinate_count"]
                    ),
                    "object_count": int(manifest["object_count"]),
                    "batch_count": int(manifest["batch_count"]),
                },
                sort_keys=True,
            )
        )
    finally:
        await ledger.close()


async def _execute_bulk_delete(args: argparse.Namespace) -> None:
    manifest = await _bulk_global_preflight(args)
    setattr(args, "_bulk_preflight_done", True)
    try:
        while True:
            await _execute_delete(args)
            ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
            try:
                state = await ledger.fetchrow(
                    """select p.status,
                              count(*) filter(where b.status<>'completed')
                                remaining_batches
                         from analytics_history_media_r2_retirement_plans p
                         join analytics_history_media_r2_retirement_batches b
                           using(plan_sha256)
                        where p.plan_sha256=$1 group by p.status""",
                    args.plan_sha256,
                )
                canary = await ledger.fetchrow(
                    """select status,object_count,outcome_counts
                         from analytics_history_media_r2_retirement_batches
                        where plan_sha256=$1 and is_canary""",
                    args.plan_sha256,
                )
                if state is None or canary is None:
                    raise RuntimeError("bulk retirement plan disappeared")
                canary_outcomes = (
                    json.loads(canary["outcome_counts"])
                    if isinstance(canary["outcome_counts"], str)
                    else dict(canary["outcome_counts"])
                )
                if canary["status"] != "completed" or int(
                    canary_outcomes.get("deleted") or 0
                ) != int(canary["object_count"]):
                    raise RuntimeError("bulk retirement canary did not complete")
                if int(state["remaining_batches"]) == 0:
                    await ledger.close()
                    ledger = None
                    await _finalize_bulk_delete(args.plan_sha256, manifest)
                    return
            finally:
                if ledger is not None:
                    await ledger.close()
    except Exception:
        await _mark_retirement_plan_paused(args.plan_sha256)
        raise


def _bounded_delete_concurrency(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_DELETE_CONCURRENCY:
        raise argparse.ArgumentTypeError("delete concurrency must be between 1 and 8")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare-delete-indexes")
    prepare.add_argument("--timeout-seconds", type=int, default=3600)
    report = commands.add_parser("report")
    report.add_argument("--parent-copy-plan-sha256", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--archive-candidates-output")
    report.add_argument("--archive-candidate-limit", type=int, default=1000)
    plan = commands.add_parser("plan-delete")
    plan.add_argument("--parent-copy-plan-sha256", required=True)
    plan.add_argument("--report", required=True)
    plan.add_argument("--history-id-file", required=True)
    plan.add_argument("--config", required=True)
    plan.add_argument("--archive-config")
    plan.add_argument(
        "--durability-basis", choices=DURABILITY_BASES, default=DURABILITY_NAS_ARCHIVE
    )
    plan.add_argument("--artifact-digest", required=True)
    plan.add_argument("--limit", type=int, default=1000)
    plan.add_argument("--batch-size", type=int, default=1000)
    plan.add_argument("--head-concurrency", type=_bounded_delete_concurrency, default=8)
    plan.add_argument("--output", required=True)
    bulk_plan = commands.add_parser("plan-bulk-delete")
    bulk_plan.add_argument("--switch-plan-sha256", action="append", required=True)
    bulk_plan.add_argument(
        "--expected-switch-asset-count", action="append", required=True
    )
    bulk_plan.add_argument("--config", required=True)
    bulk_plan.add_argument("--artifact-digest", required=True)
    bulk_plan.add_argument("--canary-size", type=int, default=100)
    bulk_plan.add_argument("--batch-size", type=int, default=1000)
    bulk_plan.add_argument("--output", required=True)
    execute = commands.add_parser("execute-delete")
    execute.add_argument("--plan-sha256", required=True)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--config", required=True)
    execute.add_argument("--archive-config")
    execute.add_argument(
        "--durability-basis", choices=DURABILITY_BASES, default=DURABILITY_NAS_ARCHIVE
    )
    execute.add_argument("--artifact-digest", required=True)
    execute.add_argument(
        "--delete-concurrency", type=_bounded_delete_concurrency, default=4
    )
    bulk_execute = commands.add_parser("execute-bulk-delete")
    bulk_execute.add_argument("--plan-sha256", required=True)
    bulk_execute.add_argument("--confirm", required=True)
    bulk_execute.add_argument("--config", required=True)
    bulk_execute.add_argument("--artifact-digest", required=True)
    bulk_execute.add_argument(
        "--delete-concurrency", type=_bounded_delete_concurrency, default=4
    )
    bulk_execute.set_defaults(
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_config=None,
    )
    return parser


async def _main(args: argparse.Namespace) -> None:
    if args.command == "prepare-delete-indexes":
        if args.timeout_seconds < 1:
            raise ValueError("index timeout must be positive")
        await _prepare_delete_indexes(args)
    elif args.command == "report":
        if not 1 <= args.archive_candidate_limit <= 1000:
            raise ValueError("archive candidate limit must be between 1 and 1000")
        await _report(args)
    elif args.command == "plan-delete":
        if not 1 <= args.limit <= 1000 or not 1 <= args.batch_size <= 1000:
            raise ValueError("retirement plan limits must be between 1 and 1000")
        await _plan_delete(args)
    elif args.command == "plan-bulk-delete":
        if not 1 <= args.canary_size <= args.batch_size <= RETIREMENT_BATCH_SIZE:
            raise ValueError("bulk retirement batch sizes are invalid")
        await _plan_bulk_delete(args)
    elif args.command == "execute-delete":
        await _execute_delete(args)
    elif args.command == "execute-bulk-delete":
        await _execute_bulk_delete(args)


def main() -> None:
    asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    main()
