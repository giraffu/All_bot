#!/usr/bin/env python3
"""History-row-driven, resumable R2 media migration ledger.

The planner addresses only keys referenced by frozen History rows.  It deliberately
has no bucket enumeration or object removal capability.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import socket
import stat
import sys
import threading
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, BinaryIO
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlsplit, urlunsplit

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
SINGLE_COPY_LIMIT = 5 * 1024 * 1024 * 1024 - 5 * 1024 * 1024
MULTIPART_COPY_PART_SIZE = 512 * 1024 * 1024
MAX_DIAGNOSTICS = 100
COPY_PLAN_METADATA_KEY = "allbot-copy-plan-sha256"
PROBE_BATCH_SIZE = 10_000
COPY_BATCH_SIZE = 1_000
SWITCH_HISTORY_BATCH_SIZE = 1_000
PROBE_MAX_CONCURRENCY = 128
CANDIDATE_ALGORITHM_VERSION = "history-r2-candidates/v1"
R2_COPY_PROXY_URL = "http://127.0.0.1:7890"
CLOUD_COPY_PROTOCOL = "history-r2-cloud-copy/v1"
TRANSIENT_COPY_FAILURE_PATTERN = re.compile(
    r"EndpointConnectionError|ConnectionClosedError|ProxyConnectionError|ProxyError|"
    r"Failed to connect to proxy URL|ReadTimeoutError|Read\s+timeout|"
    r"UNEXPECTED_EOF_WHILE_READING|EOF occurred in violation of protocol|"
    r"ConnectTimeoutError|TimeoutError|TooManyRequests|SlowDown|InternalError|"
    r"ServiceUnavailable|RequestTimeout|ProtocolError|RemoteDisconnected|"
    r"Connection reset by peer|HTTPStatusCode[^0-9]*(?:429|500|502|503|504)|"
    r"An error occurred \((?:429|500|502|503|504)\)",
    re.IGNORECASE,
)


def is_transient_copy_failure(error_text: str) -> bool:
    return bool(TRANSIENT_COPY_FAILURE_PATTERN.search(error_text))


def classify_copy_request_failure(exc: BaseException) -> str:
    """Return a low-cardinality health class without exposing object identity."""
    cause = getattr(exc, "cause", exc)
    error_text = f"{type(cause).__name__}: {cause}"
    if re.search(r"429|TooManyRequests|SlowDown", error_text, re.IGNORECASE):
        return "rate_limit"
    if re.search(
        r"InternalError|ServiceUnavailable|"
        r"HTTPStatusCode[^0-9]*(?:500|502|503|504)|"
        r"An error occurred \((?:500|502|503|504)\)",
        error_text,
        re.IGNORECASE,
    ):
        return "server_5xx"
    if re.search(
        r"ReadTimeout|Read\s+timeout|ConnectTimeout|RequestTimeout|TimeoutError",
        error_text,
        re.IGNORECASE,
    ):
        return "timeout"
    if re.search(
        r"EndpointConnection|ConnectionClosed|ProxyConnection|ProxyError|"
        r"Failed to connect to proxy URL|ProtocolError|RemoteDisconnected|"
        r"UNEXPECTED_EOF_WHILE_READING|EOF occurred in violation of protocol|"
        r"Connection reset by peer",
        error_text,
        re.IGNORECASE,
    ):
        return "connection_transient"
    if is_transient_copy_failure(error_text):
        return "other_transient"
    return "fatal"


_COPY_OPERATION_STAGES = {
    "source_head_before",
    "target_head_before",
    "copy_object",
    "multipart_create",
    "multipart_part_copy",
    "multipart_complete",
    "multipart_abort",
    "source_head_after",
    "target_head_after",
}


def copy_request_evidence(exc: BaseException) -> dict[str, Any]:
    """Return support-safe provider evidence without keys, URLs, or raw request IDs."""

    cause = getattr(exc, "cause", exc)
    response = getattr(cause, "response", None)
    metadata = dict(response.get("ResponseMetadata") or {}) if response else {}
    result: dict[str, Any] = {"kind": classify_copy_request_failure(exc)}
    stage = getattr(exc, "stage", None)
    if stage in _COPY_OPERATION_STAGES:
        result["stage"] = stage
    status = metadata.get("HTTPStatusCode")
    if isinstance(status, int) and 100 <= status <= 599:
        result["http_status"] = status
    request_id = metadata.get("RequestId")
    if request_id:
        result["provider_request_id_sha256"] = hashlib.sha256(
            str(request_id).encode()
        ).hexdigest()
    return result


class R2CopyOperationError(RuntimeError):
    """Sanitized stage wrapper that retains the original exception for classification."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        if stage not in _COPY_OPERATION_STAGES:
            raise ValueError("invalid R2 Copy operation stage")
        self.stage = stage
        self.cause = cause
        evidence = copy_request_evidence(self)
        safe_token = {
            "rate_limit": "TooManyRequests",
            "server_5xx": "ServiceUnavailable",
            "timeout": "ReadTimeoutError",
            "connection_transient": "ConnectionClosedError",
            "other_transient": "RequestTimeout",
            "fatal": "FatalError",
        }[evidence["kind"]]
        fields = [f"stage={stage}", f"class={safe_token}"]
        if "http_status" in evidence:
            fields.append(f"http_status={evidence['http_status']}")
        if "provider_request_id_sha256" in evidence:
            fields.append(
                "provider_request_id_sha256="
                + str(evidence["provider_request_id_sha256"])
            )
        super().__init__("R2_COPY_OPERATION_FAILED " + " ".join(fields))


def _call_r2_copy_operation(
    stage: str, operation: Callable[..., Any], /, *args: Any, **kwargs: Any
) -> Any:
    try:
        return operation(*args, **kwargs)
    except R2CopyOperationError:
        raise
    except BaseException as exc:
        raise R2CopyOperationError(stage, exc) from exc


@dataclass
class AdaptiveCopyController:
    initial_concurrency: int = 128
    clean_batches_to_raise: int = 3
    maximum_concurrency: int = 128

    def __post_init__(self) -> None:
        if self.initial_concurrency not in {16, 32, 64, 128}:
            raise ValueError("adaptive copy concurrency must be 16, 32, 64, or 128")
        if self.clean_batches_to_raise <= 0:
            raise ValueError("clean batch threshold must be positive")
        if self.maximum_concurrency not in {16, 32, 64, 128}:
            raise ValueError("adaptive copy maximum concurrency is invalid")
        if self.maximum_concurrency < self.initial_concurrency:
            raise ValueError("adaptive copy maximum is below its initial concurrency")
        self.concurrency = self.initial_concurrency
        self.clean_batches = 0

    def record_failure(self, error_text: str) -> int:
        if not is_transient_copy_failure(error_text):
            raise RuntimeError("non-transient copy failure")
        self.clean_batches = 0
        self.concurrency = {128: 64, 64: 32, 32: 16, 16: 16}[self.concurrency]
        return self.concurrency

    def record_success(self) -> int:
        self.clean_batches += 1
        if self.clean_batches >= self.clean_batches_to_raise:
            raised = {16: 32, 32: 64, 64: 128, 128: 128}[self.concurrency]
            self.concurrency = min(raised, self.maximum_concurrency)
            self.clean_batches = 0
        return self.concurrency


class AdaptiveConcurrencyLimiter:
    """Thread-safe live limit shared by bulk and retry Copy executors."""

    def __init__(self, *, limit: int) -> None:
        if limit <= 0:
            raise ValueError("adaptive concurrency limit must be positive")
        self._condition = threading.Condition()
        self._limit = int(limit)
        self._active = 0
        self._cooldown_until = 0.0
        self.peak_active = 0

    @property
    def limit(self) -> int:
        with self._condition:
            return self._limit

    def set_limit(self, limit: int) -> None:
        if limit <= 0:
            raise ValueError("adaptive concurrency limit must be positive")
        with self._condition:
            self._limit = int(limit)
            self._condition.notify_all()

    @property
    def cooldown_remaining_seconds(self) -> float:
        with self._condition:
            return max(0.0, self._cooldown_until - time.monotonic())

    def record_rate_limit(
        self, *, cooldown_seconds: float, minimum_concurrency: int = 16
    ) -> int:
        if cooldown_seconds <= 0:
            raise ValueError("rate limit cooldown must be positive")
        if minimum_concurrency <= 0:
            raise ValueError("minimum Copy concurrency must be positive")
        with self._condition:
            if self._limit > minimum_concurrency:
                self._limit = max(minimum_concurrency, self._limit // 2)
            self._cooldown_until = max(
                self._cooldown_until, time.monotonic() + cooldown_seconds
            )
            self._condition.notify_all()
            return self._limit

    @contextmanager
    def slot(self):
        with self._condition:
            while True:
                cooldown_remaining = self._cooldown_until - time.monotonic()
                if cooldown_remaining > 0:
                    self._condition.wait(timeout=cooldown_remaining)
                    continue
                if self._active >= self._limit:
                    self._condition.wait()
                    continue
                break
            self._active += 1
            self.peak_active = max(self.peak_active, self._active)
        try:
            yield
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()


@dataclass
class CopyObjectCircuitBreaker:
    max_error_rate: float = 0.5
    consecutive_windows: int = 3
    minimum_objects: int = 8

    def __post_init__(self) -> None:
        self.systemic_windows = 0

    def observe(self, *, copied_objects: int, failed_objects: int) -> bool:
        total = copied_objects + failed_objects
        systemic = (
            total >= self.minimum_objects
            and failed_objects / total >= self.max_error_rate
        )
        self.systemic_windows = self.systemic_windows + 1 if systemic else 0
        return self.systemic_windows >= self.consecutive_windows


@dataclass
class AdaptiveProbeController:
    initial_concurrency: int = 64
    clean_batches_to_raise: int = 3

    def __post_init__(self) -> None:
        if self.initial_concurrency not in {8, 16, 32, 64, 128}:
            raise ValueError("adaptive probe concurrency must be 8, 16, 32, 64, or 128")
        self.concurrency = self.initial_concurrency
        self.clean_batches = 0

    def record_failure(self, error_text: str) -> int:
        if not is_transient_copy_failure(error_text):
            raise RuntimeError("non-transient probe failure")
        self.clean_batches = 0
        self.concurrency = {128: 64, 64: 32, 32: 16, 16: 8, 8: 8}[self.concurrency]
        return self.concurrency

    def record_success(self) -> int:
        self.clean_batches += 1
        if self.clean_batches >= self.clean_batches_to_raise:
            self.concurrency = {8: 16, 16: 32, 32: 64, 64: 128, 128: 128}[
                self.concurrency
            ]
            self.clean_batches = 0
        return self.concurrency


@dataclass(frozen=True)
class ProbeHeadBatchResult:
    outcomes: list[dict[str, Any]]
    peak_workers: int
    worker_threads: int
    requested_concurrency: int


class _ProbeHeadActivity:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._peak = 0
        self._thread_ids: set[int] = set()

    def call(self, func: Any, *args: Any) -> Any:
        with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)
            self._thread_ids.add(threading.get_ident())
        try:
            return func(*args)
        finally:
            with self._lock:
                self._active -= 1

    @property
    def peak(self) -> int:
        with self._lock:
            return self._peak

    @property
    def thread_count(self) -> int:
        with self._lock:
            return len(self._thread_ids)


MIGRATION_DDL = """
create table if not exists analytics_history_media_migration_runs (
    id uuid primary key,
    history_min_id integer not null default 1 check (history_min_id >= 1),
    history_watermark integer not null check (history_watermark >= 0),
    history_reference_prefix text,
    history_source text not null default 'local-shadow',
    history_source_route_sha256 char(64),
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
    source_etag text,
    target_etag text,
    copy_method text,
    source_last_modified timestamptz,
    status text not null check (status in (
      'pending_probe','copy_required','target_verified','copied_verified',
      'target_conflict','source_missing','source_offline','blocked','unresolved',
      'failed','scope_context'
    )),
    error_code text,
    error_detail text,
    copy_plan_sha256 char(64),
    switch_plan_sha256 char(64),
    copy_completed_at timestamptz,
    switch_completed_at timestamptz,
    target_checked_at timestamptz,
    r2_checked_at timestamptz,
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
    plan_type text not null check (plan_type in ('probe','copy','switch')),
    rowset_sha256 char(64) not null,
    manifest jsonb not null,
    created_at timestamptz not null default now(),
    unique (run_id, plan_type, rowset_sha256)
);
alter table analytics_history_media_migration_plans
  drop constraint if exists analytics_history_media_migration_plans_run_id_plan_type_rowset_sha256_key;
create index if not exists ix_history_media_migration_plans_rowset
  on analytics_history_media_migration_plans(run_id,plan_type,rowset_sha256);
drop index if exists ux_history_media_migration_noncopy_rowset;
create unique index if not exists ux_history_media_migration_noncopy_rowset_lineage
  on analytics_history_media_migration_plans(
    run_id,
    plan_type,
    rowset_sha256,
    (coalesce(
      manifest->>'predecessor_switch_plan_sha256',
      manifest->>'predecessor_probe_plan_sha256',
      ''
    ))
  )
  where plan_type<>'copy';
create table if not exists analytics_history_media_migration_plan_batches (
    plan_sha256 char(64) not null references analytics_history_media_migration_plans(plan_sha256),
    batch_no integer not null check (batch_no >= 0),
    first_ledger_id bigint not null,
    last_ledger_id bigint not null,
    first_history_id integer not null,
    last_history_id integer not null,
    asset_count integer not null check (asset_count >= 0),
    history_count integer not null check (history_count >= 0),
    rowset_sha256 char(64) not null,
    cas_state_sha256 char(64),
    status text not null default 'pending' check (status in (
      'pending','running','completed','failed','paused','superseded'
    )),
    outcome_counts jsonb not null default '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (plan_sha256,batch_no)
);
create index if not exists ix_history_media_migration_plan_batches_status
  on analytics_history_media_migration_plan_batches(plan_sha256,status,batch_no);
alter table analytics_history_media_migration_plan_batches
  drop constraint if exists analytics_history_media_migration_plan_batches_status_check;
alter table analytics_history_media_migration_plan_batches
  add constraint analytics_history_media_migration_plan_batches_status_check
  check (status in ('pending','running','completed','failed','paused','superseded'));
alter table analytics_history_media_r2_migrations
  add column if not exists target_checked_at timestamptz;
alter table analytics_history_media_r2_migrations
  add column if not exists r2_checked_at timestamptz;
alter table analytics_history_media_r2_migrations
  add column if not exists source_etag text;
alter table analytics_history_media_r2_migrations
  add column if not exists target_etag text;
alter table analytics_history_media_r2_migrations
  add column if not exists copy_method text;
alter table analytics_history_media_r2_migrations
  add column if not exists probe_plan_sha256 char(64);
alter table analytics_history_media_migration_runs
  add column if not exists history_min_id integer not null default 1;
alter table analytics_history_media_migration_runs
  add column if not exists history_reference_prefix text;
alter table analytics_history_media_migration_runs
  add column if not exists history_source text not null default 'local-shadow';
alter table analytics_history_media_migration_runs
  add column if not exists history_source_route_sha256 char(64);
alter table analytics_history_media_r2_migrations
  drop constraint if exists analytics_history_media_r2_migrations_status_check;
alter table analytics_history_media_r2_migrations
  add constraint analytics_history_media_r2_migrations_status_check
  check (status in (
    'pending_probe','copy_required','target_verified','copied_verified',
    'target_conflict','source_missing','source_offline','blocked','unresolved',
    'failed','scope_context'
  ));
do $$
declare plan_constraint record;
begin
  alter table analytics_history_media_migration_plans
    drop constraint if exists analytics_history_media_migration_plans_plan_type_check;
  for plan_constraint in
    select conname from pg_constraint
     where conrelid='analytics_history_media_migration_plans'::regclass
       and contype='u'
       and pg_get_constraintdef(oid) like 'UNIQUE (run_id, plan_type, rowset_sha256)%'
  loop
    execute format(
      'alter table analytics_history_media_migration_plans drop constraint %I',
      plan_constraint.conname
    );
  end loop;
  alter table analytics_history_media_migration_plans
    add constraint analytics_history_media_migration_plans_plan_type_check
    check (plan_type in ('probe','copy','switch'));
exception when duplicate_object then null;
end $$;
create index if not exists ix_history_media_migration_plans_rowset
  on analytics_history_media_migration_plans(run_id,plan_type,rowset_sha256);
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


def group_copy_candidates(
    rows: Iterable[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group identical ledger rows by target and reject ambiguous destinations."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    identities: dict[str, tuple[Any, ...]] = {}
    for raw in rows:
        row = dict(raw)
        target_key = str(row["target_key"])
        identity = (
            str(row.get("source_name") or ""),
            str(row.get("source_key") or ""),
            int(row.get("byte_size") or 0),
            row.get("source_last_modified"),
            str(row.get("source_etag") or "").strip().strip('"'),
            str(row.get("source_sha256") or ""),
        )
        previous = identities.setdefault(target_key, identity)
        if previous != identity:
            raise RuntimeError("target has conflicting frozen sources")
        grouped.setdefault(target_key, []).append(row)
    return [
        sorted(group, key=lambda row: int(row["id"]))
        for _target, group in sorted(grouped.items())
    ]


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
        default=lambda item: (
            item.isoformat() if isinstance(item, datetime) else str(item)
        ),
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
    return (
        PurePosixPath(parsed.path if parsed.scheme else reference).name or "media.bin"
    )


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


def build_candidate_keys(
    source_ref: str, registry_task_id: str | None
) -> tuple[str, ...]:
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


def classify_r2_head_outcomes(
    rows: Iterable[dict[str, Any]], facts: dict[str, dict[str, Any] | None]
) -> list[dict[str, Any]]:
    """Classify a completed set of HEAD results without performing any I/O."""
    outcomes: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        target_key = str(row["target_key"])
        target_head = facts.get(target_key)
        if target_head is not None:
            target_is_current = str(row["original_ref"]).lstrip("/") == target_key
            outcomes.append(
                {
                    "id": int(row["id"]),
                    "status": (
                        "target_verified" if target_is_current else "target_conflict"
                    ),
                    "source_key": target_key,
                    "byte_size": int(target_head["ContentLength"]),
                    "last_modified": _normalize_modified(target_head["LastModified"]),
                    "etag": _normalize_etag(target_head.get("ETag")),
                    "attempts": [],
                }
            )
            continue
        attempts: list[tuple[str, str]] = []
        found_key: str | None = None
        found_head: dict[str, Any] | None = None
        for key in build_candidate_keys(
            str(row["original_ref"]), row.get("registry_task_id")
        ):
            if key == target_key:
                continue
            head = facts.get(key)
            attempts.append((key, "found" if head is not None else "not_found"))
            if head is not None:
                found_key, found_head = key, head
                break
        if found_key is None or found_head is None:
            outcomes.append(
                {
                    "id": int(row["id"]),
                    "status": "pending_probe",
                    "source_key": None,
                    "byte_size": None,
                    "last_modified": None,
                    "etag": None,
                    "attempts": attempts,
                }
            )
            continue
        outcomes.append(
            {
                "id": int(row["id"]),
                "status": "copy_required",
                "source_key": found_key,
                "byte_size": int(found_head["ContentLength"]),
                "last_modified": _normalize_modified(found_head["LastModified"]),
                "etag": _normalize_etag(found_head.get("ETag")),
                "attempts": attempts,
            }
        )
    return outcomes


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


def validate_seed_scope_identity(
    *,
    stored_history_min_id: int,
    requested_history_min_id: int | None,
    stored_history_reference_prefix: str | None,
    requested_history_reference_prefix: str | None,
) -> tuple[int, str | None]:
    """Return a frozen seed scope or reject a resume that changes it."""
    history_min_id = int(stored_history_min_id)
    if requested_history_min_id is not None and int(requested_history_min_id) != history_min_id:
        raise ValueError("resume identity does not match frozen History seed scope")
    prefix = str(stored_history_reference_prefix) if stored_history_reference_prefix else None
    if (
        requested_history_reference_prefix is not None
        and requested_history_reference_prefix != prefix
    ):
        raise ValueError("resume identity does not match frozen History seed scope")
    return history_min_id, prefix


def validate_seed_source_identity(
    *,
    stored_history_source: str,
    requested_history_source: str | None,
    stored_history_source_route_sha256: str | None,
    actual_history_source_route_sha256: str | None,
) -> str:
    source = str(stored_history_source)
    if requested_history_source is not None and requested_history_source != source:
        raise ValueError("resume identity does not match frozen History seed source")
    if stored_history_source_route_sha256 != actual_history_source_route_sha256:
        raise ValueError("resume identity does not match frozen History seed source route")
    return source


def build_seed_scope_identity(
    *,
    history_min_id: int,
    history_watermark: int,
    history_reference_prefix: str | None,
    history_source: str = "local-shadow",
    history_source_route_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "history_min_id": int(history_min_id),
        "history_watermark": int(history_watermark),
        "history_reference_prefix": history_reference_prefix,
        "history_source": history_source,
        "history_source_route_sha256": history_source_route_sha256,
        "complete_history_manifests": True,
    }


def validate_plan_seed_scope(
    *, manifest: dict[str, Any], expected_scope: dict[str, Any]
) -> None:
    actual = manifest.get("seed_scope")
    default_scope = build_seed_scope_identity(
        history_min_id=1,
        history_watermark=int(expected_scope["history_watermark"]),
        history_reference_prefix=None,
    )
    if actual is None and expected_scope == default_scope:
        return
    if actual != expected_scope:
        raise RuntimeError("plan History seed scope changed")


def _seed_scope_from_run(run: Any) -> dict[str, Any]:
    return build_seed_scope_identity(
        history_min_id=int(run["history_min_id"]),
        history_watermark=int(run["history_watermark"]),
        history_reference_prefix=run["history_reference_prefix"],
        history_source=str(run["history_source"]),
        history_source_route_sha256=run["history_source_route_sha256"],
    )


def _nondefault_seed_scope(run: Any) -> dict[str, Any] | None:
    scope = _seed_scope_from_run(run)
    if scope["history_min_id"] == 1 and scope["history_reference_prefix"] is None:
        return None
    return scope


def select_history_assets_for_seed(
    assets: Iterable[AssetIdentity],
    *,
    history_reference_prefix: str | None,
) -> list[tuple[AssetIdentity, bool]]:
    """Select whole History manifests while marking prefix-matched migration assets."""
    frozen = list(assets)
    if history_reference_prefix is None:
        return [(asset, True) for asset in frozen]
    selected = [
        (asset, asset.source_ref.startswith(history_reference_prefix))
        for asset in frozen
    ]
    return selected if any(in_scope for _asset, in_scope in selected) else []


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
    "source_etag",
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
            if len(diagnostics) < MAX_DIAGNOSTICS and status in {
                "blocked",
                "unresolved",
                "target_conflict",
                "source_offline",
                "source_missing",
                "failed",
            }:
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
    seed_scope: dict[str, Any] | None = None,
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
    if seed_scope is not None:
        manifest["seed_scope"] = dict(seed_scope)
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


def build_switch_plan(
    *,
    run_id: str,
    history_watermark: int,
    rows: Iterable[dict[str, Any]],
    seed_scope: dict[str, Any] | None = None,
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
    if seed_scope is not None:
        manifest["seed_scope"] = dict(seed_scope)
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


PROBE_ROW_FIELDS = (
    "id",
    "history_id",
    "role",
    "ordinal",
    "original_ref",
    "target_key",
    "registry_task_id",
    "history_manifest_sha256",
)


def _probe_plan_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in PROBE_ROW_FIELDS}


def _finalize_plan_batch(
    *,
    batch_no: int,
    rows: list[dict[str, Any]],
    cas_state_sha256: str | None = None,
    row_transform: Any = _probe_plan_row,
) -> dict[str, Any]:
    identities = [row_transform(row) for row in rows]
    return {
        "batch_no": batch_no,
        "first_ledger_id": int(rows[0]["id"]),
        "last_ledger_id": int(rows[-1]["id"]),
        "first_history_id": min(int(row["history_id"]) for row in rows),
        "last_history_id": max(int(row["history_id"]) for row in rows),
        "asset_count": len(rows),
        "history_count": len({int(row["history_id"]) for row in rows}),
        "rowset_sha256": _sha256_json(identities),
        "cas_state_sha256": cas_state_sha256,
    }


def build_probe_plan(
    *,
    run_id: str,
    history_watermark: int,
    rows: Iterable[dict[str, Any]],
    batch_size: int = PROBE_BATCH_SIZE,
    runtime_identity: dict[str, Any] | None = None,
    seed_scope: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("probe batch size must be positive")
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (int(row["id"]), int(row["history_id"])),
    )
    batches = [
        _finalize_plan_batch(
            batch_no=batch_no,
            rows=ordered[offset : offset + batch_size],
        )
        for batch_no, offset in enumerate(range(0, len(ordered), batch_size))
    ]
    global_digest = StreamingJsonArraySha256()
    for row in ordered:
        global_digest.add(_probe_plan_row(row))
    batch_digest = StreamingJsonArraySha256()
    for batch in batches:
        batch_digest.add(batch)
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-probe-plan/v1",
        "run_id": run_id,
        "history_watermark": int(history_watermark),
        "asset_count": len(ordered),
        "history_count": len({int(row["history_id"]) for row in ordered}),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "rowset_sha256": global_digest.hexdigest(),
        "batches_sha256": batch_digest.hexdigest(),
        "runtime_identity": dict(runtime_identity or {}),
    }
    if seed_scope is not None:
        manifest["seed_scope"] = dict(seed_scope)
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, batches


def copy_plan_chain_sha256s(manifest: dict[str, Any]) -> tuple[str, ...]:
    plan_sha = str(manifest.get("plan_sha256") or "")
    if (
        _sha256_json(
            {key: value for key, value in manifest.items() if key != "plan_sha256"}
        )
        != plan_sha
    ):
        raise RuntimeError("copy plan identity is invalid")
    predecessors = tuple(
        str(value) for value in manifest.get("predecessor_copy_plan_sha256s", [])
    )
    chain = predecessors + (plan_sha,)
    if not plan_sha or len(set(chain)) != len(chain):
        raise RuntimeError("copy plan predecessor chain is invalid")
    return chain


def build_rolling_switch_scope_identity(
    *,
    copy_chain: Iterable[str],
    parent_copy_plan_sha256: str,
    completed_current_batches: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Freeze the terminal predecessor chain and exact completed parent batches."""

    chain = tuple(str(value) for value in copy_chain)
    if not chain or chain[-1] != parent_copy_plan_sha256:
        raise RuntimeError("rolling Switch parent is not the Copy chain head")
    canonical_batches: list[dict[str, Any]] = []
    seen_batch_nos: set[int] = set()
    for original in completed_current_batches:
        batch = dict(original)
        batch_no = int(batch["batch_no"])
        if (
            str(batch.get("plan_sha256") or "") != parent_copy_plan_sha256
            or str(batch.get("status") or "") != "completed"
            or batch_no in seen_batch_nos
        ):
            raise RuntimeError("rolling Switch requires exact completed Copy batches")
        seen_batch_nos.add(batch_no)
        canonical_batches.append(
            {
                "plan_sha256": parent_copy_plan_sha256,
                "batch_no": batch_no,
                "first_ledger_id": int(batch["first_ledger_id"]),
                "last_ledger_id": int(batch["last_ledger_id"]),
                "asset_count": int(batch["asset_count"]),
                "rowset_sha256": str(batch["rowset_sha256"]),
            }
        )
    canonical_batches.sort(key=lambda item: item["batch_no"])
    return {
        "terminal_predecessor_copy_plan_sha256s": list(chain[:-1]),
        "current_completed_batch_nos": [
            item["batch_no"] for item in canonical_batches
        ],
        "current_completed_batch_count": len(canonical_batches),
        "current_completed_asset_count": sum(
            item["asset_count"] for item in canonical_batches
        ),
        "completed_copy_batches_sha256": _sha256_json(canonical_batches),
    }


ROLLING_SWITCH_ROWSET_SQL = """select m.id,m.history_id,m.role,m.ordinal,
          m.original_ref,m.target_key,m.source_name,m.source_key,
          m.source_last_modified,m.source_etag,m.source_sha256,m.target_sha256,
          m.byte_size,m.status,m.history_manifest_sha256
     from analytics_history_media_r2_migrations m
    where m.run_id=$1
      and (
        m.copy_plan_sha256=any($2::text[])
        or (
          m.copy_plan_sha256=$3
          and exists(
            select 1 from analytics_history_media_migration_plan_batches b
             where b.plan_sha256=$3 and b.batch_no=any($4::integer[])
               and b.status='completed'
               and m.id between b.first_ledger_id and b.last_ledger_id
          )
        )
      )
      and m.status='copied_verified'
      and m.switch_completed_at is null
      and m.switch_plan_sha256 is null
      and m.original_ref <> m.target_key
    order by m.history_id,m.role,m.ordinal"""

ROLLING_SWITCH_BIND_SQL = """update analytics_history_media_r2_migrations m
   set switch_plan_sha256=$5,updated_at=now()
 where m.run_id=$1
   and (
     m.copy_plan_sha256=any($2::text[])
     or (
       m.copy_plan_sha256=$3
       and exists(
         select 1 from analytics_history_media_migration_plan_batches b
          where b.plan_sha256=$3 and b.batch_no=any($4::integer[])
            and b.status='completed'
            and m.id between b.first_ledger_id and b.last_ledger_id
       )
     )
   )
   and m.status='copied_verified'
   and m.switch_completed_at is null
   and m.switch_plan_sha256 is null
   and m.original_ref <> m.target_key"""


def _normalized_frozen_copy_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["status"] = "copy_required"
    normalized["target_sha256"] = None
    return normalized


def _failed_copy_reconciliation_row(row: dict[str, Any]) -> dict[str, Any]:
    frozen = _plan_row(dict(row))
    frozen.update(
        {
            "id": int(row["id"]),
            "copy_plan_sha256": str(row["copy_plan_sha256"]),
            "error_code": str(row.get("error_code") or ""),
            "error_detail_sha256": hashlib.sha256(
                str(row.get("error_detail") or "").encode()
            ).hexdigest(),
        }
    )
    return frozen


def build_successor_copy_plan(
    *,
    predecessor_manifest: dict[str, Any] | None,
    predecessor_plan_sha256: str | None,
    retained_rows: Iterable[dict[str, Any]],
    successor_rows: Iterable[dict[str, Any]],
    run_id: str | None = None,
    history_watermark: int | None = None,
    batch_size: int = COPY_BATCH_SIZE,
    runtime_identity: dict[str, Any] | None = None,
    seed_scope: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Freeze a zero-overlap Copy successor while conserving the root rowset."""
    if batch_size <= 0:
        raise ValueError("copy batch size must be positive")
    retained = sorted(
        (dict(row) for row in retained_rows), key=lambda row: int(row["id"])
    )
    remaining = sorted(
        (dict(row) for row in successor_rows), key=lambda row: int(row["id"])
    )
    retained_ids = {int(row["id"]) for row in retained}
    remaining_ids = {int(row["id"]) for row in remaining}
    if retained_ids & remaining_ids:
        raise RuntimeError(
            "successor Copy rowset overlaps predecessor completed assets"
        )

    predecessor_chain: tuple[str, ...] = ()
    if predecessor_manifest is not None:
        predecessor_chain = copy_plan_chain_sha256s(predecessor_manifest)
        if predecessor_plan_sha256 != predecessor_chain[-1]:
            raise RuntimeError("predecessor Copy identity does not match its manifest")
        expected_run_id = str(predecessor_manifest["run_id"])
        expected_watermark = int(predecessor_manifest["history_watermark"])
        root_asset_count = int(
            predecessor_manifest.get(
                "root_asset_count",
                predecessor_manifest.get(
                    "count", sum(predecessor_manifest.get("counts", {}).values())
                ),
            )
        )
        if run_id is not None and str(run_id) != expected_run_id:
            raise RuntimeError("successor Copy run identity changed")
        if (
            history_watermark is not None
            and int(history_watermark) != expected_watermark
        ):
            raise RuntimeError("successor Copy History watermark changed")
        run_id = expected_run_id
        history_watermark = expected_watermark
        predecessor_scope = predecessor_manifest.get("seed_scope")
        if seed_scope is not None and seed_scope != predecessor_scope:
            raise RuntimeError("successor Copy History seed scope changed")
        seed_scope = predecessor_scope
    else:
        if not run_id or history_watermark is None:
            raise ValueError("initial Copy plan requires run_id and history_watermark")
        root_asset_count = len(remaining)

    if len(retained) + len(remaining) != root_asset_count:
        raise RuntimeError("successor Copy rowset does not conserve root assets")
    normalized_remaining = [_normalized_frozen_copy_row(row) for row in remaining]
    batches = [
        _finalize_plan_batch(
            batch_no=batch_no,
            rows=normalized_remaining[offset : offset + batch_size],
            row_transform=_plan_row,
        )
        for batch_no, offset in enumerate(
            range(0, len(normalized_remaining), batch_size)
        )
    ]
    rowset = StreamingJsonArraySha256()
    for row in normalized_remaining:
        rowset.add(_plan_row(row))
    batch_digest = StreamingJsonArraySha256()
    for batch in batches:
        batch_digest.add(batch)
    retained_digest = StreamingJsonArraySha256()
    for row in retained:
        retained_digest.add(_plan_row(_normalized_frozen_copy_row(row)))
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-copy-plan/v3",
        "run_id": str(run_id),
        "history_watermark": int(history_watermark),
        "count": len(normalized_remaining),
        "counts": {"copy_required": len(normalized_remaining)},
        "bytes": {
            "copy_required": sum(
                int(row.get("byte_size") or 0) for row in normalized_remaining
            )
        },
        "history_count": len({int(row["history_id"]) for row in normalized_remaining}),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "rowset_sha256": rowset.hexdigest(),
        "batches_sha256": batch_digest.hexdigest(),
        "root_asset_count": root_asset_count,
        "retained_asset_count": len(retained),
        "retained_rowset_sha256": retained_digest.hexdigest(),
        "intersection_asset_count": 0,
        "conserved_asset_count": len(retained) + len(normalized_remaining),
        "runtime_identity": dict(runtime_identity or {}),
    }
    if seed_scope is not None:
        manifest["seed_scope"] = dict(seed_scope)
    if predecessor_chain:
        manifest["predecessor_copy_plan_sha256s"] = list(predecessor_chain)
        manifest["supersedes_copy_plan_sha256"] = predecessor_chain[-1]
        manifest["predecessor_copy_chain_sha256"] = _sha256_json(
            list(predecessor_chain)
        )
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, batches


def build_copy_predecessor_recovery_plan(
    *,
    current_manifest: dict[str, Any],
    current_plan_sha256: str,
    predecessor_plan_sha256: str,
    frontier_batch: dict[str, Any],
    rows: Iterable[dict[str, Any]],
    runtime_identity: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Freeze the sole predecessor batch that could contain uncommitted copies."""

    chain = copy_plan_chain_sha256s(current_manifest)
    if current_plan_sha256 != chain[-1]:
        raise RuntimeError("copy recovery current plan identity changed")
    if len(chain) < 2 or predecessor_plan_sha256 != chain[-2]:
        raise RuntimeError("copy recovery requires the direct predecessor plan")
    first_id = int(frontier_batch["first_ledger_id"])
    last_id = int(frontier_batch["last_ledger_id"])
    candidates = sorted(
        (_normalized_frozen_copy_row(dict(row)) for row in rows),
        key=lambda row: int(row["id"]),
    )
    if not candidates:
        raise RuntimeError("copy recovery frontier has no unfinished assets")
    if any(not first_id <= int(row["id"]) <= last_id for row in candidates):
        raise RuntimeError("copy recovery row is outside the predecessor frontier")
    batch = _finalize_plan_batch(
        batch_no=0,
        rows=candidates,
        row_transform=_plan_row,
    )
    rowset = StreamingJsonArraySha256()
    for row in candidates:
        rowset.add(_plan_row(row))
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-copy-recovery-plan/v1",
        "run_id": str(current_manifest["run_id"]),
        "history_watermark": int(current_manifest["history_watermark"]),
        "current_copy_plan_sha256": current_plan_sha256,
        "predecessor_copy_plan_sha256": predecessor_plan_sha256,
        "copy_chain_plan_sha256s": list(chain),
        "copy_chain_sha256": _sha256_json(list(chain)),
        "frontier_batch_no": int(frontier_batch["batch_no"]),
        "frontier_batch_rowset_sha256": str(frontier_batch["rowset_sha256"]),
        "count": len(candidates),
        "history_count": len({int(row["history_id"]) for row in candidates}),
        "batch_count": 1,
        "batches_sha256": _sha256_json([batch]),
        "rowset_sha256": rowset.hexdigest(),
        "runtime_identity": dict(runtime_identity or {}),
    }
    if current_manifest.get("seed_scope") is not None:
        manifest["seed_scope"] = dict(current_manifest["seed_scope"])
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, [batch]


def probe_plan_chain_sha256s(manifest: dict[str, Any]) -> tuple[str, ...]:
    plan_sha = str(manifest.get("plan_sha256") or "")
    if (
        _sha256_json(
            {key: value for key, value in manifest.items() if key != "plan_sha256"}
        )
        != plan_sha
    ):
        raise RuntimeError("probe plan identity is invalid")
    predecessors = tuple(
        str(value) for value in manifest.get("predecessor_probe_plan_sha256s", [])
    )
    chain = predecessors + (plan_sha,)
    if not plan_sha or len(set(chain)) != len(chain):
        raise RuntimeError("probe plan predecessor chain is invalid")
    return chain


def _retained_probe_batch_identity(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_sha256": str(batch["plan_sha256"]),
        "batch_no": int(batch["batch_no"]),
        "asset_count": int(batch["asset_count"]),
        "history_count": int(batch["history_count"]),
        "rowset_sha256": str(batch["rowset_sha256"]),
        "outcome_counts": dict(sorted(dict(batch.get("outcome_counts") or {}).items())),
    }


def build_successor_probe_plan(
    *,
    predecessor_manifest: dict[str, Any],
    predecessor_plan_sha256: str,
    retained_rows: Iterable[dict[str, Any]],
    successor_rows: Iterable[dict[str, Any]],
    retained_batches: Iterable[dict[str, Any]],
    batch_size: int = PROBE_BATCH_SIZE,
    runtime_identity: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    predecessor_chain = probe_plan_chain_sha256s(predecessor_manifest)
    if predecessor_plan_sha256 != predecessor_chain[-1]:
        raise RuntimeError("predecessor plan identity does not match its manifest")

    retained = sorted(
        (dict(row) for row in retained_rows), key=lambda row: int(row["id"])
    )
    remaining = sorted(
        (dict(row) for row in successor_rows), key=lambda row: int(row["id"])
    )
    retained_ids = {int(row["id"]) for row in retained}
    remaining_ids = {int(row["id"]) for row in remaining}
    if retained_ids & remaining_ids:
        raise RuntimeError("successor rowset overlaps predecessor completed assets")

    root_asset_count = int(
        predecessor_manifest.get(
            "root_asset_count", predecessor_manifest["asset_count"]
        )
    )
    if len(retained) + len(remaining) != root_asset_count:
        raise RuntimeError(
            "successor rowset does not conserve the root Probe asset count"
        )

    canonical_retained_batches = sorted(
        (_retained_probe_batch_identity(batch) for batch in retained_batches),
        key=lambda batch: (
            predecessor_chain.index(batch["plan_sha256"]),
            batch["batch_no"],
        ),
    )
    if sum(batch["asset_count"] for batch in canonical_retained_batches) != len(
        retained
    ):
        raise RuntimeError("retained Probe batches do not match retained assets")

    successor_base, batches = build_probe_plan(
        run_id=str(predecessor_manifest["run_id"]),
        history_watermark=int(predecessor_manifest["history_watermark"]),
        rows=remaining,
        batch_size=batch_size,
        runtime_identity=runtime_identity,
        seed_scope=predecessor_manifest.get("seed_scope"),
    )
    retained_outcomes: Counter[str] = Counter()
    for batch in canonical_retained_batches:
        retained_outcomes.update(
            {key: int(value) for key, value in batch["outcome_counts"].items()}
        )
    retained_identities = [_probe_plan_row(row) for row in retained]
    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-probe-successor-plan/v1",
        "run_id": successor_base["run_id"],
        "history_watermark": successor_base["history_watermark"],
        "predecessor_probe_plan_sha256": predecessor_plan_sha256,
        "predecessor_probe_plan_sha256s": list(predecessor_chain),
        "root_probe_plan_sha256": predecessor_chain[0],
        "root_asset_count": root_asset_count,
        "retained_asset_count": len(retained),
        "retained_history_count": len({int(row["history_id"]) for row in retained}),
        "retained_batch_count": len(canonical_retained_batches),
        "retained_outcome_counts": dict(sorted(retained_outcomes.items())),
        "retained_rowset_sha256": _sha256_json(retained_identities),
        "retained_batches_sha256": _sha256_json(canonical_retained_batches),
        "asset_count": successor_base["asset_count"],
        "history_count": successor_base["history_count"],
        "batch_count": successor_base["batch_count"],
        "batch_size": successor_base["batch_size"],
        "rowset_sha256": successor_base["rowset_sha256"],
        "batches_sha256": successor_base["batches_sha256"],
        "intersection_asset_count": 0,
        "conserved_asset_count": len(retained) + len(remaining),
        "runtime_identity": dict(runtime_identity or {}),
    }
    if predecessor_manifest.get("seed_scope") is not None:
        manifest["seed_scope"] = dict(predecessor_manifest["seed_scope"])
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, batches


def validate_probe_gate(
    *, expected_plan_sha256: str, supplied_plan_sha256: str, confirmation: str
) -> None:
    if supplied_plan_sha256 != expected_plan_sha256 or confirmation != (
        f"PROBE_HISTORY_MEDIA_{expected_plan_sha256}"
    ):
        raise ValueError("exact probe plan SHA and confirmation are required")


def normalized_history_cas_state(
    history_id: int,
    current_refs: dict[tuple[str, int], str],
    ledger_rows: Iterable[dict[str, Any]],
    *,
    allow_selected_target: bool = True,
) -> dict[str, Any]:
    """Return an idempotent CAS state or reject an unexplained production value."""
    normalized: list[dict[str, Any]] = []
    rows = [dict(row) for row in ledger_rows]
    expected_coords = {(str(row["role"]), int(row["ordinal"])) for row in rows}
    if set(current_refs) != expected_coords:
        raise RuntimeError("unknown History media state: coordinate set changed")
    for row in sorted(rows, key=lambda item: (str(item["role"]), int(item["ordinal"]))):
        coord = (str(row["role"]), int(row["ordinal"]))
        current = str(current_refs[coord])
        original = str(row["original_ref"])
        target = str(row["target_key"])
        selected = bool(row.get("selected"))
        prior_completed = bool(
            row.get("switch_completed_at") and row.get("switch_plan_sha256")
        )
        if selected and current == original:
            value = original
        elif selected and allow_selected_target and current == target:
            value = original
        elif not selected and current == original:
            value = original
        elif not selected and prior_completed and current == target:
            value = target
        else:
            raise RuntimeError("unknown History media state")
        normalized.append({"role": coord[0], "ordinal": coord[1], "value": value})
    return {"history_id": int(history_id), "assets": normalized}


def _history_record_refs(record: Any) -> dict[tuple[str, int], str]:
    return {
        (asset.role, asset.ordinal): asset.source_ref
        for asset in history_assets_from_record(record)
    }


async def _cas_state_for_histories(
    production: asyncpg.Connection,
    ledger: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    history_ids: list[int],
    selected_ledger_ids: set[int] | None = None,
    switch_plan_sha256: str | None = None,
    lock_rows: bool = False,
    allow_selected_target: bool = True,
) -> tuple[str, dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    if not history_ids:
        return _sha256_json([]), {}, {}
    lock_clause = " for update" if lock_rows else ""
    histories = await production.fetch(
        """select id,input_file,output_file,extra_outputs from history
             where id=any($1::integer[]) order by id""" + lock_clause,
        history_ids,
    )
    if len(histories) != len(set(history_ids)):
        raise RuntimeError("History row disappeared")
    ledger_records = await ledger.fetch(
        """select id,history_id,role,ordinal,original_ref,target_key,
                  switch_plan_sha256,switch_completed_at
             from analytics_history_media_r2_migrations
            where run_id=$1 and history_id=any($2::integer[])
            order by history_id,role,ordinal""",
        run_id,
        history_ids,
    )
    by_history: dict[int, list[dict[str, Any]]] = {}
    for record in ledger_records:
        row = dict(record)
        row["selected"] = (
            int(row["id"]) in selected_ledger_ids
            if selected_ledger_ids is not None
            else str(row.get("switch_plan_sha256") or "") == switch_plan_sha256
        )
        by_history.setdefault(int(row["history_id"]), []).append(row)
    states: list[dict[str, Any]] = []
    history_map: dict[int, dict[str, Any]] = {}
    for record in histories:
        current = dict(record)
        history_id = int(current["id"])
        history_map[history_id] = current
        states.append(
            normalized_history_cas_state(
                history_id,
                _history_record_refs(current),
                by_history.get(history_id, []),
                allow_selected_target=allow_selected_target,
            )
        )
    return _sha256_json(states), history_map, by_history


async def _predecessor_switch_identity(
    conn: asyncpg.Connection, run_id: uuid.UUID, *, excluding: str | None = None
) -> tuple[int, str]:
    values = [
        str(row["switch_plan_sha256"])
        for row in await conn.fetch(
            """select distinct switch_plan_sha256
                 from analytics_history_media_r2_migrations
                where run_id=$1 and switch_completed_at is not null
                  and switch_plan_sha256 is not null
                  and ($2::text is null or switch_plan_sha256::text<>$2)
                order by switch_plan_sha256""",
            run_id,
            excluding,
        )
    ]
    return len(values), _sha256_json(values)


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


def database_route_sha256(value: str) -> str:
    parsed = urlsplit(value.replace("postgresql+asyncpg://", "postgresql://", 1))
    route = {
        "scheme": parsed.scheme.lower(),
        "host": (parsed.hostname or "").lower(),
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "ssl": any(key == "ssl" for key, _item in parse_qsl(parsed.query)),
    }
    return _sha256_json(route)


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


def _endpoint_fingerprint(value: Any) -> str:
    parsed = urlsplit(str(value or "").rstrip("/"))
    identity = f"{parsed.scheme.lower()}://{(parsed.hostname or '').lower()}:{parsed.port or ''}{parsed.path}"
    return hashlib.sha256(identity.encode()).hexdigest()


@dataclass(frozen=True)
class R2Transport:
    mode: str
    proxy_url: str | None = None

    def identity(self) -> dict[str, Any]:
        if self.mode == "direct":
            return {"mode": "direct"}
        assert self.proxy_url is not None
        return {
            "mode": "https_proxy",
            "proxy_port": 7890,
            "proxy_sha256": hashlib.sha256(self.proxy_url.encode()).hexdigest(),
        }


def _r2_transport(config: dict[str, Any]) -> R2Transport:
    raw = config.get("r2_transport")
    if raw is None:
        return R2Transport(mode="direct")
    if not isinstance(raw, dict):
        raise ValueError("r2_transport must be an object")
    unknown = set(raw) - {"mode", "proxy_url"}
    if unknown:
        raise ValueError("r2_transport contains unknown fields")
    mode = str(raw.get("mode") or "")
    if mode == "direct":
        if raw.get("proxy_url") not in {None, ""}:
            raise ValueError("direct r2_transport must not define proxy_url")
        return R2Transport(mode="direct")
    if mode != "https_proxy":
        raise ValueError("r2_transport mode must be direct or https_proxy")
    proxy_url = str(raw.get("proxy_url") or "")
    if proxy_url != R2_COPY_PROXY_URL:
        raise ValueError("R2 Copy proxy must be exact loopback port 7890")
    return R2Transport(mode="https_proxy", proxy_url=proxy_url)


def _copy_execution(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("copy_execution")
    if raw is None:
        return {"mode": "local_ledger"}
    if not isinstance(raw, dict):
        raise ValueError("copy_execution must be an object")
    unknown = set(raw) - {"mode", "worker_id", "protocol"}
    if unknown:
        raise ValueError("copy_execution contains unknown fields")
    mode = str(raw.get("mode") or "")
    if mode == "local_ledger":
        if raw.get("worker_id") or raw.get("protocol"):
            raise ValueError("local copy_execution cannot define cloud identity")
        return {"mode": "local_ledger"}
    if mode != "cloud_receipt":
        raise ValueError("copy_execution mode must be local_ledger or cloud_receipt")
    worker_id = str(raw.get("worker_id") or "")
    protocol = str(raw.get("protocol") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", worker_id):
        raise ValueError("cloud copy worker_id is invalid")
    if protocol != CLOUD_COPY_PROTOCOL:
        raise ValueError("cloud copy protocol is unsupported")
    return {"mode": mode, "protocol": protocol, "worker_id": worker_id}


def validate_local_copy_execution(config: dict[str, Any]) -> None:
    if _copy_execution(config)["mode"] == "cloud_receipt":
        raise RuntimeError("cloud receipt Copy plan cannot use the local DB executor")


def _validate_r2_transport_runtime(
    transport: R2Transport,
    *,
    create_connection: Callable[..., Any] = socket.create_connection,
) -> None:
    if transport.mode == "direct":
        return
    connection = None
    try:
        connection = create_connection(("127.0.0.1", 7890), 2.0)
    except OSError:
        raise RuntimeError("configured R2 proxy is unavailable") from None
    finally:
        if connection is not None:
            connection.close()


def _runtime_identity(
    *, artifact_digest: str, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact_digest):
        raise ValueError("artifact digest must be an exact sha256 digest")
    identity: dict[str, Any] = {
        "artifact_digest": artifact_digest,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "bucket": BUCKET,
        "candidate_algorithm": CANDIDATE_ALGORITHM_VERSION,
    }
    if config is not None:
        target = config.get("target", {})
        r2_source = next(
            (
                item
                for item in config.get("sources", [])
                if item.get("name") == "r2-user-data-prod" and item.get("enabled", True)
            ),
            None,
        )
        identity["target_endpoint_sha256"] = _endpoint_fingerprint(
            target.get("endpoint")
        )
        identity["source_endpoint_sha256"] = _endpoint_fingerprint(
            (r2_source or {}).get("endpoint")
        )
        identity["r2_transport"] = _r2_transport(config).identity()
        if "copy_execution" in config:
            identity["copy_execution"] = _copy_execution(config)
    return identity


def _default_next_plan_output(plan_type: str, parent_sha256: str) -> Path:
    state_root = Path(
        os.getenv(
            "XDG_STATE_HOME",
            str(Path.home() / ".local" / "state"),
        )
    )
    return (
        state_root
        / "allbot"
        / "history-media-r2-migration"
        / "plans"
        / f"{plan_type}-{parent_sha256}.json"
    )


def _default_receipt_output(receipt_type: str, plan_sha256: str) -> Path:
    return (
        _default_next_plan_output("placeholder", plan_sha256).parent.parent
        / "receipts"
        / f"{receipt_type}-{plan_sha256}.json"
    )


def _validate_runtime_identity(
    expected: dict[str, Any], *, artifact_digest: str, config: dict[str, Any] | None
) -> None:
    actual = _runtime_identity(artifact_digest=artifact_digest, config=config)
    if actual != dict(expected):
        raise RuntimeError("migration runtime identity changed")


def _reconciliation_runtime_identity(
    expected: dict[str, Any], *, artifact_digest: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Bind reconciliation to new code while preserving the stopped plan config."""

    actual = _runtime_identity(artifact_digest=artifact_digest, config=config)
    stable_fields = {
        "bucket",
        "candidate_algorithm",
        "target_endpoint_sha256",
        "source_endpoint_sha256",
        "r2_transport",
        "copy_execution",
    }
    if any(expected.get(field) != actual.get(field) for field in stable_fields):
        raise RuntimeError("failed Copy reconciliation runtime configuration changed")
    return actual


def _process_r2_custom_arguments(
    params: dict[str, Any], context: dict[str, Any], **_kwargs: Any
) -> None:
    custom_headers = params.pop("custom_headers", None)
    if custom_headers:
        context["allbot_r2_custom_headers"] = dict(custom_headers)


def _add_r2_custom_headers(
    params: dict[str, Any], context: dict[str, Any], **_kwargs: Any
) -> None:
    custom_headers = context.get("allbot_r2_custom_headers")
    if custom_headers:
        params["headers"].update(custom_headers)


def _s3_client(
    config: dict[str, Any],
    *,
    max_pool_connections: int | None = None,
    transport: R2Transport | None = None,
    external_retry_lane: bool = False,
):
    selected_transport = transport or R2Transport(mode="direct")
    botocore_config: dict[str, Any] = {
        "signature_version": "s3v4",
        "retries": (
            {"total_max_attempts": 1, "mode": "standard"}
            if external_retry_lane
            else {"max_attempts": 3, "mode": "standard"}
        ),
        "proxies": (
            {"https": selected_transport.proxy_url}
            if selected_transport.mode == "https_proxy"
            else {}
        ),
    }
    if max_pool_connections is not None:
        botocore_config["max_pool_connections"] = max_pool_connections
    if external_retry_lane:
        botocore_config.update({"connect_timeout": 5, "read_timeout": 30})
    client = boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config.get("region", "auto"),
        verify=config.get("ca_file", True),
        config=Config(**botocore_config),
    )
    for operation in ("CopyObject", "CreateMultipartUpload"):
        client.meta.events.register(
            f"before-parameter-build.s3.{operation}",
            _process_r2_custom_arguments,
        )
        client.meta.events.register(
            f"before-call.s3.{operation}",
            _add_r2_custom_headers,
        )
    return client


def _not_found(exc: ClientError) -> bool:
    code = str((exc.response or {}).get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


def _normalize_modified(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("object HEAD did not return LastModified")
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _head_s3(client, bucket: str, key: str) -> tuple[int, datetime] | None:
    response = _head_s3_identity(client, bucket, key)
    if response is None:
        return None
    return int(response["ContentLength"]), _normalize_modified(response["LastModified"])


def _head_s3_identity(client, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        response = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if _not_found(exc):
            return None
        raise
    return response


def _normalize_etag(value: Any) -> str:
    etag = str(value or "").strip().strip('"')
    if not etag:
        raise RuntimeError("object HEAD did not return ETag")
    return etag


def classify_copy_predecessor_recovery(
    *,
    source_head: dict[str, Any] | None,
    target_head: dict[str, Any] | None,
    expected_size: int,
    expected_last_modified: datetime,
    expected_etag: str,
    current_plan_sha256: str,
    predecessor_plan_sha256: str,
) -> str:
    """Classify a stopped Copy frontier using HEAD identities only."""

    if source_head is None:
        raise RuntimeError("copy recovery source disappeared")
    source_size = int(source_head["ContentLength"])
    source_modified = _normalize_modified(source_head["LastModified"])
    source_etag = _normalize_etag(source_head.get("ETag"))
    if (
        source_size != int(expected_size)
        or source_modified != expected_last_modified
        or source_etag != _normalize_etag(expected_etag)
    ):
        raise RuntimeError("copy recovery source identity changed")
    if target_head is None:
        return "missing"

    target_size = int(target_head["ContentLength"])
    target_etag = _normalize_etag(target_head.get("ETag"))
    if target_size != source_size or target_etag != source_etag:
        raise RuntimeError("copy recovery target identity differs from source")
    metadata = {
        str(key).lower(): str(value)
        for key, value in dict(target_head.get("Metadata") or {}).items()
    }
    marker = metadata.get(COPY_PLAN_METADATA_KEY)
    if marker == current_plan_sha256:
        return "current"
    if marker == predecessor_plan_sha256:
        return "predecessor"
    raise RuntimeError("copy recovery target has unrecognized copy plan marker")


def classify_failed_copy_reconciliation(
    *,
    source_head: dict[str, Any] | None,
    target_head: dict[str, Any] | None,
    expected_size: int,
    expected_last_modified: datetime,
    expected_etag: str,
    current_plan_sha256: str,
) -> str:
    """Reconcile a failed Copy using HEAD and only the exact current marker."""

    outcome = classify_copy_predecessor_recovery(
        source_head=source_head,
        target_head=target_head,
        expected_size=expected_size,
        expected_last_modified=expected_last_modified,
        expected_etag=expected_etag,
        current_plan_sha256=current_plan_sha256,
        predecessor_plan_sha256="not-an-accepted-plan-marker",
    )
    if outcome not in {"missing", "current"}:
        raise RuntimeError("failed Copy reconciliation marker is not current")
    return outcome


def server_side_copy_r2_object(
    client: Any,
    *,
    bucket: str,
    source_key: str,
    target_key: str,
    expected_size: int,
    expected_last_modified: datetime,
    copy_plan_sha256: str,
    expected_etag: str | None = None,
    single_copy_limit: int = SINGLE_COPY_LIMIT,
    multipart_part_size: int = MULTIPART_COPY_PART_SIZE,
) -> dict[str, Any]:
    """Copy one immutable object inside R2 without transferring its body."""
    source_head = _call_r2_copy_operation(
        "source_head_before", _head_s3_identity, client, bucket, source_key
    )
    if source_head is None:
        raise RuntimeError("planned source disappeared before server-side copy")
    source_size = int(source_head["ContentLength"])
    source_modified = _normalize_modified(source_head["LastModified"])
    source_etag = _normalize_etag(source_head.get("ETag"))
    if source_size != int(expected_size) or source_modified != expected_last_modified:
        raise RuntimeError("planned source changed before server-side copy")
    if expected_etag and source_etag != _normalize_etag(expected_etag):
        raise RuntimeError("planned source ETag changed before server-side copy")
    target_before = _call_r2_copy_operation(
        "target_head_before", _head_s3_identity, client, bucket, target_key
    )
    if target_before is not None:
        metadata = {
            str(key).lower(): str(value)
            for key, value in dict(target_before.get("Metadata") or {}).items()
        }
        if metadata.get(COPY_PLAN_METADATA_KEY) != copy_plan_sha256:
            raise RuntimeError(
                "target already exists with different or missing copy plan marker"
            )
        if int(target_before["ContentLength"]) != source_size:
            raise RuntimeError("recovered copy target size mismatch")
        return {
            "byte_size": source_size,
            "source_etag": source_etag,
            "etag": _normalize_etag(target_before.get("ETag")),
            "multipart": source_size > single_copy_limit,
            "recovered": True,
        }

    multipart = source_size > single_copy_limit
    destination_race = False
    if not multipart:
        try:
            _call_r2_copy_operation(
                "copy_object",
                client.copy_object,
                Bucket=bucket,
                Key=target_key,
                CopySource={"Bucket": bucket, "Key": source_key},
                CopySourceIfMatch=source_etag,
                MetadataDirective="COPY",
                Metadata={COPY_PLAN_METADATA_KEY: copy_plan_sha256},
                custom_headers={
                    "cf-copy-destination-if-none-match": "*",
                    "x-amz-metadata-directive": "MERGE",
                },
            )
        except R2CopyOperationError as exc:
            cause = exc.cause
            code = (
                str((cause.response or {}).get("Error", {}).get("Code", ""))
                if isinstance(cause, ClientError)
                else ""
            )
            if code not in {"412", "PreconditionFailed"}:
                raise
            destination_race = True
    else:
        if multipart_part_size <= 0:
            raise ValueError("multipart copy part size must be positive")
        part_count = (source_size + multipart_part_size - 1) // multipart_part_size
        if part_count > 10_000:
            raise RuntimeError("multipart server-side copy would exceed 10000 parts")
        metadata = dict(source_head.get("Metadata") or {})
        metadata[COPY_PLAN_METADATA_KEY] = copy_plan_sha256
        created = _call_r2_copy_operation(
            "multipart_create",
            client.create_multipart_upload,
            Bucket=bucket,
            Key=target_key,
            Metadata=metadata,
            custom_headers={"If-None-Match": "*"},
        )
        upload_id = str(created["UploadId"])
        parts: list[dict[str, Any]] = []
        try:
            for part_number in range(1, part_count + 1):
                start = (part_number - 1) * multipart_part_size
                end = min(source_size, start + multipart_part_size) - 1
                copied = _call_r2_copy_operation(
                    "multipart_part_copy",
                    client.upload_part_copy,
                    Bucket=bucket,
                    Key=target_key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    CopySource={"Bucket": bucket, "Key": source_key},
                    CopySourceRange=f"bytes={start}-{end}",
                )
                parts.append(
                    {
                        "ETag": _normalize_etag(copied["CopyPartResult"]["ETag"]),
                        "PartNumber": part_number,
                    }
                )
            _call_r2_copy_operation(
                "multipart_complete",
                client.complete_multipart_upload,
                Bucket=bucket,
                Key=target_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            _call_r2_copy_operation(
                "multipart_abort",
                client.abort_multipart_upload,
                Bucket=bucket,
                Key=target_key,
                UploadId=upload_id,
            )
            raise

    source_after = _call_r2_copy_operation(
        "source_head_after", _head_s3_identity, client, bucket, source_key
    )
    target_after = _call_r2_copy_operation(
        "target_head_after", _head_s3_identity, client, bucket, target_key
    )
    if source_after is None or target_after is None:
        raise RuntimeError(
            "server-side copy did not leave both source and target present"
        )
    if (
        int(source_after["ContentLength"]) != source_size
        or _normalize_modified(source_after["LastModified"]) != source_modified
        or _normalize_etag(source_after.get("ETag")) != source_etag
    ):
        raise RuntimeError("source changed during server-side copy")
    if int(target_after["ContentLength"]) != source_size:
        raise RuntimeError("server-side copy target size mismatch")
    target_metadata = {
        str(key).lower(): str(value)
        for key, value in dict(target_after.get("Metadata") or {}).items()
    }
    if target_metadata.get(COPY_PLAN_METADATA_KEY) != copy_plan_sha256:
        raise RuntimeError("server-side copy target plan marker mismatch")
    return {
        "byte_size": source_size,
        "source_etag": source_etag,
        "etag": _normalize_etag(target_after.get("ETag")),
        "multipart": multipart,
        "recovered": destination_race,
    }


def validate_copy_verification_heads(
    row: dict[str, Any],
    *,
    source_head: dict[str, Any] | None,
    target_head: dict[str, Any] | None,
    copy_plan_sha256: str,
) -> None:
    if source_head is None:
        raise RuntimeError("verified copy source disappeared")
    if target_head is None:
        raise RuntimeError("verified copy target disappeared")
    if (
        int(source_head["ContentLength"]) != int(row["byte_size"])
        or _normalize_modified(source_head["LastModified"])
        != row["source_last_modified"]
        or _normalize_etag(source_head.get("ETag"))
        != _normalize_etag(row["source_etag"])
    ):
        raise RuntimeError("verified copy source identity changed")
    if int(target_head["ContentLength"]) != int(row["byte_size"]):
        raise RuntimeError("verified copy target size changed")
    metadata = {
        str(key).lower(): str(value)
        for key, value in dict(target_head.get("Metadata") or {}).items()
    }
    if metadata.get(COPY_PLAN_METADATA_KEY) != copy_plan_sha256:
        raise RuntimeError("verified copy target marker changed")


def _timed_server_side_copy_with_retries(
    client: Any,
    *,
    max_retries: int = 5,
    retry_base_seconds: float = 1.0,
    retry_max_seconds: float = 16.0,
    retry_jitter_ratio: float = 0.25,
    sleep_fn: Any = time.sleep,
    jitter_fn: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retry one idempotent, marker-bound CopyObject without slowing peer objects."""
    if not 0 <= max_retries <= 10:
        raise ValueError("object max retries must be between 0 and 10")
    if retry_base_seconds <= 0 or retry_max_seconds <= 0:
        raise ValueError("copy retry delays must be positive")
    if not 0 <= retry_jitter_ratio <= 1:
        raise ValueError("copy retry jitter ratio must be between 0 and 1")

    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    for attempt in range(max_retries + 1):
        try:
            outcome = server_side_copy_r2_object(client, **kwargs)
            events.append({"at": time.monotonic(), "kind": "ok"})
            return {
                "outcome": outcome,
                "error": None,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "attempt_count": attempt + 1,
                "request_events": events,
            }
        except BaseException as exc:  # noqa: BLE001 - classify at object boundary
            kind = classify_copy_request_failure(exc)
            events.append({"at": time.monotonic(), "kind": kind})
            if kind == "fatal" or attempt >= max_retries:
                return {
                    "outcome": None,
                    "error": exc,
                    "elapsed_ms": (time.perf_counter() - started) * 1000,
                    "attempt_count": attempt + 1,
                    "request_events": events,
                }
            delay = min(retry_max_seconds, retry_base_seconds * (2**attempt))
            if jitter_fn is not None:
                delay = float(jitter_fn(delay))
            else:
                spread = delay * retry_jitter_ratio
                delay = random.uniform(max(0.0, delay - spread), delay + spread)
            sleep_fn(delay)

    raise AssertionError("copy retry loop exhausted without returning")


def _timed_server_side_copy_attempt(
    client: Any,
    *,
    concurrency_limiter: AdaptiveConcurrencyLimiter,
    rate_limit_cooldown_seconds: float = 60.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run one CopyObject attempt under the shared live concurrency limit."""
    started: float | None = None
    attempt_concurrency = concurrency_limiter.limit
    try:
        with concurrency_limiter.slot():
            attempt_concurrency = concurrency_limiter.limit
            started = time.perf_counter()
            outcome = server_side_copy_r2_object(client, **kwargs)
        return {
            "outcome": outcome,
            "error": None,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "request_event": {
                "at": time.monotonic(),
                "kind": "ok",
                "copy_concurrency": attempt_concurrency,
            },
        }
    except BaseException as exc:  # noqa: BLE001 - classify at object boundary
        evidence = copy_request_evidence(exc)
        if evidence["kind"] == "rate_limit":
            new_limit = concurrency_limiter.record_rate_limit(
                cooldown_seconds=rate_limit_cooldown_seconds
            )
            evidence["rate_limit_cooldown_seconds"] = rate_limit_cooldown_seconds
            evidence["rate_limit_new_concurrency"] = new_limit
        return {
            "outcome": None,
            "error": exc,
            "elapsed_ms": (
                (time.perf_counter() - started) * 1000 if started is not None else 0.0
            ),
            "request_event": {
                "at": time.monotonic(),
                "copy_concurrency": attempt_concurrency,
                **evidence,
            },
        }


async def _run_copy_group_batch_with_retry_lane(
    groups: list[list[dict[str, Any]]],
    *,
    bulk_executor: ThreadPoolExecutor,
    retry_executor: ThreadPoolExecutor,
    concurrency_limiter: AdaptiveConcurrencyLimiter,
    copy_one_attempt: Callable[[list[dict[str, Any]]], dict[str, Any]],
    persist_success: Callable[[list[dict[str, Any]], dict[str, Any]], Awaitable[None]],
    persist_failure: Callable[[list[dict[str, Any]], BaseException], Awaitable[None]],
    max_retries: int = 5,
    retry_base_seconds: float = 1.0,
    retry_max_seconds: float = 16.0,
    retry_jitter_ratio: float = 0.25,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_bulk_in_flight: int | None = None,
    object_circuit: CopyObjectCircuitBreaker | None = None,
    request_event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Keep first attempts flowing while a bounded retry lane owns long tails."""
    if not 0 <= max_retries <= 10:
        raise ValueError("object max retries must be between 0 and 10")
    if retry_base_seconds <= 0 or retry_max_seconds <= 0:
        raise ValueError("copy retry delays must be positive")
    if not 0 <= retry_jitter_ratio <= 1:
        raise ValueError("copy retry jitter ratio must be between 0 and 1")

    loop = asyncio.get_running_loop()
    bulk_window = max_bulk_in_flight or max(1, bulk_executor._max_workers * 4)
    group_iterator = iter(groups)
    tasks: set[asyncio.Task[Any]] = set()
    copied_objects = 0
    copied_rows = 0
    recovered_objects = 0
    exhausted_transient_objects = 0
    retried_objects = 0
    operation_latencies_ms: list[float] = []
    request_events: list[dict[str, Any]] = []
    first_fatal_error: BaseException | None = None
    circuit_copied = 0
    circuit_failed = 0

    async def run_attempt(
        group: list[dict[str, Any]], attempt: int, object_started: float
    ) -> tuple[list[dict[str, Any]], int, float, dict[str, Any]]:
        if attempt:
            delay = min(retry_max_seconds, retry_base_seconds * (2 ** (attempt - 1)))
            spread = delay * retry_jitter_ratio
            if spread:
                delay = random.uniform(max(0.0, delay - spread), delay + spread)
            await sleep(delay)
        executor = retry_executor if attempt else bulk_executor
        result = await loop.run_in_executor(executor, copy_one_attempt, group)
        return group, attempt, object_started, result

    def schedule_bulk(slots: int) -> None:
        for _ in range(slots):
            try:
                group = next(group_iterator)
            except StopIteration:
                return
            tasks.add(asyncio.create_task(run_attempt(group, 0, time.perf_counter())))

    schedule_bulk(min(bulk_window, len(groups)))
    try:
        while tasks:
            completed, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            tasks = set(pending)
            bulk_slots = 0
            for task in completed:
                group, attempt, object_started, result = await task
                request_event = dict(result["request_event"])
                request_events.append(request_event)
                if request_event_sink is not None:
                    request_event_sink(dict(request_event))
                error = result["error"]
                if error is not None:
                    kind = classify_copy_request_failure(error)
                    if kind != "fatal" and attempt < max_retries:
                        if attempt == 0:
                            retried_objects += 1
                            bulk_slots += 1
                        tasks.add(
                            asyncio.create_task(
                                run_attempt(group, attempt + 1, object_started)
                            )
                        )
                        continue
                    await persist_failure(group, error)
                    operation_latencies_ms.append(
                        (time.perf_counter() - object_started) * 1000
                    )
                    if kind == "fatal":
                        first_fatal_error = first_fatal_error or error
                    else:
                        exhausted_transient_objects += 1
                        circuit_failed += 1
                    if attempt == 0:
                        bulk_slots += 1
                    continue

                outcome = result["outcome"]
                await persist_success(group, outcome)
                operation_latencies_ms.append(
                    (time.perf_counter() - object_started) * 1000
                )
                copied_objects += 1
                copied_rows += len(group)
                recovered_objects += int(bool(outcome.get("recovered")))
                circuit_copied += 1
                if attempt == 0:
                    bulk_slots += 1

            circuit_total = circuit_copied + circuit_failed
            if (
                object_circuit is not None
                and circuit_total >= bulk_window
                and object_circuit.observe(
                    copied_objects=circuit_copied,
                    failed_objects=circuit_failed,
                )
            ):
                first_fatal_error = first_fatal_error or RuntimeError(
                    "ServiceUnavailable: systemic object copy circuit open"
                )
            if circuit_total >= bulk_window:
                circuit_copied = 0
                circuit_failed = 0
            if first_fatal_error is None and bulk_slots:
                schedule_bulk(bulk_slots)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    if first_fatal_error is not None:
        raise first_fatal_error
    return {
        "copied_objects": copied_objects,
        "copied_rows": copied_rows,
        "recovered_objects": recovered_objects,
        "retried_objects": retried_objects,
        "exhausted_transient_objects": exhausted_transient_objects,
        "operation_latencies_ms": operation_latencies_ms,
        "request_events": request_events,
        "limiter_peak_active": concurrency_limiter.peak_active,
    }


async def _run_copy_group_batch(
    groups: list[list[dict[str, Any]]],
    *,
    executor: ThreadPoolExecutor,
    copy_one: Callable[[list[dict[str, Any]]], dict[str, Any]],
    persist_success: Callable[[list[dict[str, Any]], dict[str, Any]], Awaitable[None]],
    persist_failure: Callable[[list[dict[str, Any]], BaseException], Awaitable[None]],
    max_in_flight: int | None = None,
    object_circuit: CopyObjectCircuitBreaker | None = None,
) -> dict[str, Any]:
    """Continuously refill a bounded queue and persist each completed object."""
    loop = asyncio.get_running_loop()

    async def run_group(
        group: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        attempt = await loop.run_in_executor(executor, copy_one, group)
        return group, attempt

    copied_objects = 0
    copied_rows = 0
    recovered_objects = 0
    exhausted_transient_objects = 0
    first_fatal_error: BaseException | None = None
    operation_latencies_ms: list[float] = []
    request_events: list[dict[str, Any]] = []
    if not groups:
        max_in_flight = 1
    elif max_in_flight is None:
        max_in_flight = len(groups)
    if max_in_flight <= 0:
        raise ValueError("copy max_in_flight must be positive")

    group_iterator = iter(groups)
    tasks: set[asyncio.Task[tuple[list[dict[str, Any]], dict[str, Any]]]] = set()
    circuit_copied = 0
    circuit_failed = 0

    def refill(slots: int) -> None:
        for _ in range(slots):
            try:
                group = next(group_iterator)
            except StopIteration:
                break
            tasks.add(asyncio.create_task(run_group(group)))

    refill(min(max_in_flight, len(groups)))
    try:
        while tasks:
            completed, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            tasks = set(pending)
            for task in completed:
                group, attempt = await task
                operation_latencies_ms.append(float(attempt["elapsed_ms"]))
                request_events.extend(attempt["request_events"])
                if attempt["error"] is not None:
                    await persist_failure(group, attempt["error"])
                    if classify_copy_request_failure(attempt["error"]) == "fatal":
                        first_fatal_error = first_fatal_error or attempt["error"]
                    else:
                        exhausted_transient_objects += 1
                        circuit_failed += 1
                    continue
                outcome = attempt["outcome"]
                await persist_success(group, outcome)
                copied_objects += 1
                copied_rows += len(group)
                recovered_objects += int(bool(outcome.get("recovered")))
                circuit_copied += 1
            circuit_total = circuit_copied + circuit_failed
            if (
                object_circuit is not None
                and circuit_total >= max_in_flight
                and object_circuit.observe(
                    copied_objects=circuit_copied,
                    failed_objects=circuit_failed,
                )
            ):
                first_fatal_error = first_fatal_error or RuntimeError(
                    "ServiceUnavailable: systemic object copy circuit open"
                )
            if circuit_total >= max_in_flight:
                circuit_copied = 0
                circuit_failed = 0
            if first_fatal_error is None:
                refill(len(completed))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    if first_fatal_error is not None:
        raise first_fatal_error
    return {
        "copied_objects": copied_objects,
        "copied_rows": copied_rows,
        "recovered_objects": recovered_objects,
        "exhausted_transient_objects": exhausted_transient_objects,
        "operation_latencies_ms": operation_latencies_ms,
        "request_events": request_events,
    }


def _latency_summary(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
        return round(ordered[index], 3)

    return {
        "count": len(ordered),
        "mean": round(sum(ordered) / len(ordered), 3),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "max": round(ordered[-1], 3),
    }


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
        return int(info.st_size), datetime.fromtimestamp(info.st_mtime, tz=timezone.utc)
    return _head_s3(client, str(config["bucket"]), key)


def _read_source_sha(config: dict[str, Any], client: Any, key: str) -> tuple[str, int]:
    if config.get("type", "s3") == "filesystem":
        with _filesystem_path(config, key).open("rb") as body:
            return hash_body(body)
    return _read_s3_sha(client, str(config["bucket"]), key)


async def _ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(CATALOG_DDL)
    await conn.execute(MIGRATION_DDL)


async def _seed(args: argparse.Namespace) -> None:
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    history_source_conn = conn
    try:
        await _ensure_schema(conn)
        await conn.execute(SEED_STAGE_DDL)
        if args.resume_run_id:
            run_id = uuid.UUID(args.resume_run_id)
            row = await conn.fetchrow(
                """select history_min_id,history_watermark,
                          history_reference_prefix,history_source,
                          history_source_route_sha256,phase
                     from analytics_history_media_migration_runs where id=$1""",
                run_id,
            )
            if not row:
                raise RuntimeError("unknown migration run")
            watermark = validate_resume_identity(
                stored_watermark=int(row["history_watermark"]),
                requested_watermark=args.history_watermark,
            )
            history_min_id, history_reference_prefix = validate_seed_scope_identity(
                stored_history_min_id=int(row["history_min_id"]),
                requested_history_min_id=args.history_min_id,
                stored_history_reference_prefix=row["history_reference_prefix"],
                requested_history_reference_prefix=args.history_reference_prefix,
            )
            history_source = str(row["history_source"])
            source_env = (
                "PRODUCTION_DATABASE_URL"
                if history_source == "production-read-only"
                else "LOCAL_ANALYTICS_DATABASE_URL"
            )
            source_route_sha256 = (
                database_route_sha256(_dsn(source_env))
                if history_source == "production-read-only"
                else None
            )
            validate_seed_source_identity(
                stored_history_source=history_source,
                requested_history_source=args.history_source,
                stored_history_source_route_sha256=row[
                    "history_source_route_sha256"
                ],
                actual_history_source_route_sha256=source_route_sha256,
            )
            start = (
                int(
                    await conn.fetchval(
                        "select cursor_history_id from analytics_history_media_migration_runs where id=$1",
                        run_id,
                    )
                )
                + 1
            )
        else:
            history_source = args.history_source or "local-shadow"
            source_env = (
                "PRODUCTION_DATABASE_URL"
                if history_source == "production-read-only"
                else "LOCAL_ANALYTICS_DATABASE_URL"
            )
            source_route_sha256 = (
                database_route_sha256(_dsn(source_env))
                if history_source == "production-read-only"
                else None
            )
            history_min_id = int(args.history_min_id or 1)
            if history_min_id < 1:
                raise ValueError("History minimum id must be positive")
            history_reference_prefix = args.history_reference_prefix
            if history_reference_prefix == "":
                raise ValueError("History reference prefix must not be empty")
            watermark = (
                int(args.history_watermark)
                if args.history_watermark is not None
                else -1
            )
        if history_source == "production-read-only":
            history_source_conn = await _connect_env("PRODUCTION_DATABASE_URL")
            await history_source_conn.execute(
                "set default_transaction_read_only = on"
            )
        if not args.resume_run_id:
            if watermark < 0:
                watermark = int(
                    await history_source_conn.fetchval(
                        "select coalesce(max(id),0) from history"
                    )
                )
            if history_min_id > watermark:
                raise ValueError("History minimum id exceeds frozen watermark")
            run_id = uuid.uuid4()
            start = history_min_id
            await conn.execute(
                """insert into analytics_media_runs(id,run_type,status,cursor)
                   values($1,'history-r2-migration','running',
                          jsonb_build_object('history_watermark',$2::integer))""",
                run_id,
                watermark,
            )
            await conn.execute(
                """insert into analytics_history_media_migration_runs(
                       id,history_min_id,history_watermark,history_reference_prefix,
                       history_source,history_source_route_sha256,
                       status,phase,cursor_history_id)
                     values($1,$2,$3,$4,$5,$6,'running','seed',$2 - 1)""",
                run_id,
                history_min_id,
                watermark,
                history_reference_prefix,
                history_source,
                source_route_sha256,
            )

        start = max(start, history_min_id)
        for batch_start in range(start, watermark + 1, args.batch_size):
            batch_end = min(watermark, batch_start + args.batch_size - 1)
            histories = await history_source_conn.fetch(
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
                await history_source_conn.fetch(BACKEND_BATCH_SQL, registry_ids)
                if registry_ids
                else []
            )
            backend_map = {
                str(row["registry_task_id"]): (
                    str(row["backend_task_id"]),
                    int(row["backend_count"]),
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
                scoped_assets = select_history_assets_for_seed(
                    assets,
                    history_reference_prefix=history_reference_prefix,
                )
                if not scoped_assets:
                    continue
                manifest_sha = media_manifest_hash(assets)
                registry_id = str(history["task_id"] or "").strip() or None
                backend = backend_map.get(registry_id or "")
                backend_id = backend[0] if backend and backend[1] == 1 else None
                backend_ambiguous = bool(backend and backend[1] > 1)
                for asset, in_scope in scoped_assets:
                    identity = AssetIdentity(
                        asset.history_id, asset.role, asset.ordinal, asset.source_ref
                    )
                    target = build_standard_target(
                        identity,
                        registry_task_id=registry_id,
                        backend_task_id=backend_id,
                    )
                    ref_class = classify_reference(asset.source_ref)
                    status = "pending_probe" if in_scope else "scope_context"
                    error = None
                    if in_scope and ref_class == "blocked":
                        status, error = "blocked", "EXTERNAL_OR_UNMANAGED_REFERENCE"
                    elif in_scope and target is None:
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
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "history_min_id": history_min_id,
                    "history_watermark": watermark,
                    "history_reference_prefix": history_reference_prefix,
                    "history_source": history_source,
                    "history_source_route_sha256": source_route_sha256,
                }
            )
        )
    except Exception as exc:
        if "run_id" in locals():
            await conn.execute(
                "update analytics_history_media_migration_runs set status='paused',error=$2,updated_at=now() where id=$1",
                run_id,
                str(exc)[:1000],
            )
        raise
    finally:
        if history_source_conn is not conn:
            await history_source_conn.close()
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

    async def inspect(
        key: str,
    ) -> tuple[str, tuple[int, datetime] | None, str | None, int]:
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


async def _probe_r2_rows(
    conn: asyncpg.Connection,
    rows: list[asyncpg.Record],
    *,
    r2_client: Any,
    concurrency: int,
) -> int:
    """Resolve standard and legacy R2 keys with metadata-only HEAD requests."""
    if not 1 <= concurrency <= 128:
        raise ValueError("source concurrency must be between 1 and 128")
    row_keys: dict[int, tuple[str, tuple[str, ...]]] = {}
    unique_keys: dict[str, None] = {}
    for row in rows:
        target_key = str(row["target_key"])
        candidates = tuple(
            key
            for key in build_candidate_keys(
                str(row["original_ref"]), row["registry_task_id"]
            )
            if key != target_key
        )
        row_keys[int(row["id"])] = (target_key, candidates)
        unique_keys[target_key] = None
        for key in candidates:
            unique_keys[key] = None
    semaphore = asyncio.Semaphore(concurrency)

    async def inspect(
        key: str,
    ) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            return key, await asyncio.to_thread(
                _head_s3_identity, r2_client, BUCKET, key
            )

    inspected = await asyncio.gather(*(inspect(key) for key in unique_keys))
    facts = dict(inspected)
    for row in rows:
        target_key, candidates = row_keys[int(row["id"])]
        target_head = facts[target_key]
        if target_head is not None:
            byte_size = int(target_head["ContentLength"])
            modified = _normalize_modified(target_head["LastModified"])
            etag = _normalize_etag(target_head.get("ETag"))
            target_is_current_reference = (
                str(row["original_ref"]).lstrip("/") == target_key
            )
            status = (
                "target_verified" if target_is_current_reference else "target_conflict"
            )
            error_code = (
                None if target_is_current_reference else "TARGET_EXISTS_UNVERIFIED"
            )
            await conn.execute(
                """update analytics_history_media_r2_migrations set
                     source_name='target:user-data-prod',source_key=target_key,
                     byte_size=$2,source_last_modified=$3,source_etag=$4,
                     target_etag=$4,status=$5,error_code=$6,
                     target_checked_at=now(),r2_checked_at=now(),
                     error_detail=null,updated_at=now() where id=$1""",
                row["id"],
                byte_size,
                modified,
                etag,
                status,
                error_code,
            )
            await conn.execute(
                """update analytics_media_asset_catalog set status='found',
                     found_source='target:user-data-prod',source_key=$2,
                     last_checked_at=now(),missing_rounds=0,first_missing_at=null,
                     last_error=null where id=$1""",
                row["catalog_asset_id"],
                target_key,
            )
            continue

        found_key = None
        found_head = None
        attempts: list[tuple[Any, ...]] = []
        for key in candidates:
            head = facts[key]
            status = "found" if head is not None else "not_found"
            attempts.append((row["run_id"], row["catalog_asset_id"], key, status))
            if status == "found":
                found_key, found_head = key, head
                break
        if attempts:
            await conn.executemany(
                """insert into analytics_media_source_attempts
                     (run_id,asset_id,source,candidate_key,status)
                   values($1,$2,'r2-user-data-prod',$3,$4)""",
                attempts,
            )
        if found_key and found_head is not None:
            byte_size = int(found_head["ContentLength"])
            modified = _normalize_modified(found_head["LastModified"])
            etag = _normalize_etag(found_head.get("ETag"))
            await conn.execute(
                """update analytics_history_media_r2_migrations set
                     source_name='r2-user-data-prod',source_key=$2,byte_size=$3,
                     source_last_modified=$4,source_etag=$5,target_sha256=null,
                     status='copy_required',target_checked_at=now(),r2_checked_at=now(),
                     error_code=null,error_detail=null,updated_at=now() where id=$1""",
                row["id"],
                found_key,
                byte_size,
                modified,
                etag,
            )
            await conn.execute(
                """update analytics_media_asset_catalog set status='found',
                     found_source='r2-user-data-prod',source_key=$2,
                     last_checked_at=now(),missing_rounds=0,first_missing_at=null,
                     last_error=null where id=$1""",
                row["catalog_asset_id"],
                found_key,
            )
        else:
            await conn.execute(
                """update analytics_history_media_r2_migrations set
                     target_checked_at=now(),r2_checked_at=now(),
                     target_sha256=null,target_etag=null,
                     error_code='R2_CANDIDATES_NOT_FOUND',error_detail=null,
                     updated_at=now() where id=$1""",
                row["id"],
            )
    return 0


async def _probe_all_missing_filesystem_rows(
    conn: asyncpg.Connection,
    rows: list[asyncpg.Record],
    *,
    sources: list[dict[str, Any]],
    concurrency: int,
) -> bool:
    """Batch-persist a remaining-source pass when every filesystem key is absent.

    The fast path is intentionally narrow. Any receipt, non-filesystem source,
    or discovered object falls back to the full per-row probe and SHA path.
    """
    if not 1 <= concurrency <= 128:
        raise ValueError("source concurrency must be between 1 and 128")
    if any(row["receipt_nas_key"] is not None for row in rows):
        return False
    if any(source.get("type", "s3") != "filesystem" for source in sources):
        return False
    semaphore = asyncio.Semaphore(concurrency)

    async def inspect(row: asyncpg.Record) -> tuple[bool, list[tuple[Any, ...]]]:
        attempts: list[tuple[Any, ...]] = []
        for source in sources:
            source_name = str(source["name"])
            for key in build_candidate_keys(
                str(row["original_ref"]), row["registry_task_id"]
            ):
                async with semaphore:
                    head = await asyncio.to_thread(_head_source, source, None, key)
                attempts.append(
                    (
                        row["run_id"],
                        row["catalog_asset_id"],
                        source_name,
                        key,
                        "found" if head is not None else "not_found",
                    )
                )
                if head is not None:
                    return True, attempts
        return False, attempts

    inspected = await asyncio.gather(*(inspect(row) for row in rows))
    if any(found for found, _attempts in inspected):
        return False

    attempt_rows = [attempt for _found, attempts in inspected for attempt in attempts]
    now = datetime.now(timezone.utc)
    catalog_updates: list[tuple[Any, ...]] = []
    migration_updates: list[tuple[Any, ...]] = []
    not_found_statuses = ["not_found"] * (1 + len(sources))
    for row in rows:
        catalog_status, rounds, first = evaluate_missing_round(
            statuses=not_found_statuses,
            previous_rounds=int(row["catalog_missing_rounds"]),
            first_missing_at=row["catalog_first_missing_at"],
            now=now,
        )
        migration_status = (
            "source_missing"
            if catalog_status in {"provisional_missing", "confirmed_lost"}
            else catalog_status
        )
        catalog_updates.append(
            (row["catalog_asset_id"], catalog_status, rounds, first)
        )
        migration_updates.append(
            (
                row["id"],
                migration_status,
                catalog_status.upper(),
            )
        )
    async with conn.transaction():
        if attempt_rows:
            await conn.executemany(
                """insert into analytics_media_source_attempts
                     (run_id,asset_id,source,candidate_key,status)
                   values($1,$2,$3,$4,$5)""",
                attempt_rows,
            )
        await conn.executemany(
            """update analytics_media_asset_catalog set status=$2,
                 missing_rounds=$3,first_missing_at=$4,last_checked_at=now()
               where id=$1""",
            catalog_updates,
        )
        await conn.executemany(
            """update analytics_history_media_r2_migrations set status=$2,
                 error_code=$3,target_checked_at=now(),updated_at=now()
               where id=$1""",
            migration_updates,
        )
    return True


async def _probe(args: argparse.Namespace) -> None:
    if args.refresh_r2_checkpoint and not args.r2_only:
        raise ValueError("--refresh-r2-checkpoint requires --r2-only")
    checkpoint_not_before = None
    if args.refresh_r2_checkpoint or args.remaining_sources_only:
        if not args.r2_checkpoint_not_before:
            raise ValueError(
                "checkpoint refresh/remaining-source probe requires "
                "--r2-checkpoint-not-before"
            )
        checkpoint_not_before = datetime.fromisoformat(
            str(args.r2_checkpoint_not_before).replace("Z", "+00:00")
        )
        if checkpoint_not_before.tzinfo is None:
            raise ValueError("R2 checkpoint boundary must include a timezone")
        checkpoint_not_before = checkpoint_not_before.astimezone(timezone.utc)
        if checkpoint_not_before > datetime.now(timezone.utc):
            raise ValueError("R2 checkpoint boundary cannot be in the future")
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    r2_pool_connections = (
        _resolve_probe_max_pool_connections(args.source_concurrency)
        if args.source_concurrency in {8, 16, 32, 64, 128}
        else max(10, args.source_concurrency)
    )
    target_config = config["target"]
    target_client = _s3_client(
        target_config,
        max_pool_connections=max(10, args.target_concurrency),
    )
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
                None
                if item.get("type", "s3") == "filesystem"
                else _s3_client(
                    item,
                    max_pool_connections=r2_pool_connections,
                )
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
            else "probe-r2-refresh"
            if args.r2_only and args.refresh_r2_checkpoint
            else "probe-r2"
            if args.r2_only
            else "probe-receipts"
            if args.receipt_only
            else "probe-remaining-sources"
            if args.remaining_sources_only
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
        elif args.r2_only:
            if args.refresh_r2_checkpoint:
                rows = await conn.fetch(
                    """select m.* from analytics_history_media_r2_migrations m
                         where m.run_id=$1 and m.status='pending_probe'
                           and (m.r2_checked_at is null or m.r2_checked_at < $3)
                         order by m.history_id,m.role,m.ordinal limit $2""",
                    run_id,
                    args.limit,
                    checkpoint_not_before,
                )
            else:
                rows = await conn.fetch(
                    """select m.* from analytics_history_media_r2_migrations m
                         where m.run_id=$1 and m.r2_checked_at is null
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
        elif args.remaining_sources_only:
            rows = await conn.fetch(
                """select m.*,a.missing_rounds as catalog_missing_rounds,
                          a.first_missing_at as catalog_first_missing_at,
                          b.nas_key as receipt_nas_key
                     from analytics_history_media_r2_migrations m
                     join analytics_media_asset_catalog a on a.id=m.catalog_asset_id
                     left join analytics_media_blobs b on b.sha256=a.sha256
                     where m.run_id=$1 and m.status='pending_probe'
                       and m.r2_checked_at >= $3 and m.target_checked_at >= $3
                     order by m.history_id,m.role,m.ordinal limit $2""",
                run_id,
                args.limit,
                checkpoint_not_before,
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
        elif args.r2_only:
            r2_source = configured.get("r2-user-data-prod")
            if not r2_source or r2_source.get("bucket") != BUCKET:
                raise RuntimeError(
                    "r2-user-data-prod source is not enabled for user-data-prod"
                )
            bytes_read = await _probe_r2_rows(
                conn,
                rows,
                r2_client=_s3_client(
                    r2_source,
                    max_pool_connections=r2_pool_connections,
                ),
                concurrency=args.source_concurrency,
            )
            rows = []
        elif args.remaining_sources_only:
            remaining_sources = [
                source
                for source in sources
                if str(source["name"]) != "r2-user-data-prod"
            ]
            if await _probe_all_missing_filesystem_rows(
                conn,
                rows,
                sources=remaining_sources,
                concurrency=args.source_concurrency,
            ):
                rows = []
        for row in rows:
            target_key = str(row["target_key"])
            target_head = None
            target_sha = row["target_sha256"]
            if not args.receipt_only and not args.remaining_sources_only:
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

            attempts: list[str] = (
                ["not_found"] if args.remaining_sources_only else []
            )
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
            sources_to_probe = (
                []
                if args.receipt_only
                else [
                    source
                    for source in sources
                    if not (
                        args.remaining_sources_only
                        and str(source["name"]) == "r2-user-data-prod"
                    )
                ]
            )
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
                        head = await asyncio.to_thread(
                            _head_source, source, client, key
                        )
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
        elif args.r2_only:
            if args.refresh_r2_checkpoint:
                remaining = int(
                    await conn.fetchval(
                        """select count(*) from analytics_history_media_r2_migrations
                             where run_id=$1 and status='pending_probe'
                               and (r2_checked_at is null or r2_checked_at < $2)""",
                        run_id,
                        checkpoint_not_before,
                    )
                )
            else:
                remaining = int(
                    await conn.fetchval(
                        """select count(*) from analytics_history_media_r2_migrations
                             where run_id=$1 and r2_checked_at is null
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
            "completed" if remaining == 0 and not args.receipt_only else "running",
            phase,
        )
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "probed": probed_count,
                    "remaining_pending": remaining,
                    "target_only": args.target_only,
                    "r2_only": args.r2_only,
                    "receipt_only": args.receipt_only,
                    "remaining_sources_only": args.remaining_sources_only,
                    "refresh_r2_checkpoint": args.refresh_r2_checkpoint,
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


async def _insert_plan_with_batches(
    conn: asyncpg.Connection,
    *,
    manifest: dict[str, Any],
    plan_type: str,
    batches: Iterable[dict[str, Any]],
) -> None:
    async with conn.transaction():
        await conn.execute(
            """insert into analytics_history_media_migration_plans
                 (plan_sha256,run_id,plan_type,rowset_sha256,manifest)
               values($1,$2,$3,$4,$5::jsonb) on conflict(plan_sha256) do nothing""",
            manifest["plan_sha256"],
            uuid.UUID(manifest["run_id"]),
            plan_type,
            manifest["rowset_sha256"],
            json.dumps(manifest),
        )
        batch_records = [
            (
                manifest["plan_sha256"],
                int(batch["batch_no"]),
                int(batch["first_ledger_id"]),
                int(batch["last_ledger_id"]),
                int(batch["first_history_id"]),
                int(batch["last_history_id"]),
                int(batch["asset_count"]),
                int(batch["history_count"]),
                batch["rowset_sha256"],
                batch.get("cas_state_sha256"),
            )
            for batch in batches
        ]
        if batch_records:
            await conn.executemany(
                """insert into analytics_history_media_migration_plan_batches(
                   plan_sha256,batch_no,first_ledger_id,last_ledger_id,
                   first_history_id,last_history_id,asset_count,history_count,
                   rowset_sha256,cas_state_sha256)
                 values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                 on conflict(plan_sha256,batch_no) do nothing""",
                batch_records,
            )


async def _replace_unexecuted_copy_plan(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    old_plan_sha256: str,
    manifest: dict[str, Any],
    batches: list[dict[str, Any]],
) -> None:
    """Atomically retain completed assets and rebind only a stopped remainder."""

    async with conn.transaction():
        old_plan = await conn.fetchrow(
            """select run_id,manifest from analytics_history_media_migration_plans
                 where plan_sha256=$1 and plan_type='copy' for update""",
            old_plan_sha256,
        )
        if not old_plan or old_plan["run_id"] != run_id:
            raise RuntimeError("copy replacement predecessor identity changed")
        old_manifest = (
            json.loads(old_plan["manifest"])
            if isinstance(old_plan["manifest"], str)
            else dict(old_plan["manifest"])
        )
        if (
            old_manifest.get("plan_sha256") != old_plan_sha256
            or _sha256_json(
                {
                    key: value
                    for key, value in old_manifest.items()
                    if key != "plan_sha256"
                }
            )
            != old_plan_sha256
            or old_manifest.get("parent_probe_plan_sha256")
            != manifest.get("parent_probe_plan_sha256")
        ):
            raise RuntimeError("copy replacement predecessor manifest changed")
        old_batches = await conn.fetch(
            """select batch_no,first_ledger_id,last_ledger_id,
                      first_history_id,last_history_id,asset_count,history_count,
                      rowset_sha256,status
                 from analytics_history_media_migration_plan_batches
                 where plan_sha256=$1 order by batch_no for update""",
            old_plan_sha256,
        )
        if not old_batches or any(
            row["status"] not in {"pending", "completed"} for row in old_batches
        ):
            raise RuntimeError("copy replacement predecessor is not safely stopped")
        predecessor_chain = copy_plan_chain_sha256s(old_manifest)
        ledger_state = await conn.fetchrow(
            """select count(*)::bigint remaining,
                      count(*) filter (where status='failed')::bigint failed,
                      count(*) filter (where copy_completed_at is not null)::bigint invalid_completed
                 from analytics_history_media_r2_migrations
                where run_id=$1 and copy_plan_sha256=$2
                  and status in ('copy_required','failed')""",
            run_id,
            old_plan_sha256,
        )
        retained_assets = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=any($2::text[])
                       and status='copied_verified' and copy_completed_at is not null""",
                run_id,
                list(predecessor_chain),
            )
        )
        root_asset_count = int(
            old_manifest.get("root_asset_count", old_manifest["count"])
        )
        if (
            int(ledger_state["remaining"]) != int(manifest["count"])
            or int(ledger_state["failed"]) != 0
            or int(ledger_state["invalid_completed"]) != 0
            or retained_assets != int(manifest["retained_asset_count"])
            or retained_assets + int(manifest["count"]) != root_asset_count
            or int(manifest["conserved_asset_count"]) != root_asset_count
            or list(predecessor_chain)
            != list(manifest["predecessor_copy_plan_sha256s"])
        ):
            raise RuntimeError("copy replacement predecessor state changed")
        await _insert_plan_with_batches(
            conn, manifest=manifest, plan_type="copy", batches=batches
        )
        await conn.execute(
            """update analytics_history_media_migration_plan_batches
                  set status='superseded',updated_at=now()
                where plan_sha256=$1 and status<>'completed'""",
            old_plan_sha256,
        )
        await conn.execute(
            """update analytics_history_media_r2_migrations
                  set copy_plan_sha256=$4,status='copy_required',
                      error_code=null,error_detail=null,updated_at=now()
                where run_id=$1 and copy_plan_sha256=$2
                  and copy_completed_at is null and status=$3""",
            run_id,
            old_plan_sha256,
            "copy_required",
            manifest["plan_sha256"],
        )
        replacement_count = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and copy_completed_at is null and status='copy_required'""",
                run_id,
                manifest["plan_sha256"],
            )
        )
        if replacement_count != int(manifest["count"]):
            raise RuntimeError("copy replacement ledger reassignment changed")


async def _reject_unacknowledged_copy_replan(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    manifest: dict[str, Any],
) -> None:
    active_plan = await conn.fetchval(
        """select p.plan_sha256
             from analytics_history_media_migration_plans p
            where p.run_id=$1 and p.plan_type='copy'
              and p.rowset_sha256=$2 and p.plan_sha256<>$3
              and exists (
                select 1 from analytics_history_media_migration_plan_batches b
                 where b.plan_sha256=p.plan_sha256 and b.status<>'superseded'
              )
            order by p.created_at desc limit 1""",
        run_id,
        manifest["rowset_sha256"],
        manifest["plan_sha256"],
    )
    if active_plan is not None:
        raise RuntimeError("existing copy plan must be explicitly superseded")


async def _create_probe_plan(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    batch_size = PROBE_BATCH_SIZE
    try:
        await _ensure_schema(conn)
        run = await conn.fetchrow(
            """select history_min_id,history_watermark,history_reference_prefix,
                      history_source,history_source_route_sha256
                 from analytics_history_media_migration_runs where id=$1""",
            run_id,
        )
        if not run:
            raise RuntimeError("unknown migration run")
        expected = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_r2_migrations
                     where run_id=$1 and status='pending_probe'""",
                run_id,
            )
        )
        history_count = int(
            await conn.fetchval(
                """select count(distinct history_id)
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and status='pending_probe'""",
                run_id,
            )
        )
        row_digest = StreamingJsonArraySha256()
        batches: list[dict[str, Any]] = []
        batch_rows: list[dict[str, Any]] = []
        async with conn.transaction():
            async for record in conn.cursor(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          registry_task_id,history_manifest_sha256
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and status='pending_probe'
                    order by id""",
                run_id,
                prefetch=batch_size,
            ):
                row = dict(record)
                identity = _probe_plan_row(row)
                row_digest.add(identity)
                batch_rows.append(row)
                if len(batch_rows) == batch_size:
                    batches.append(
                        _finalize_plan_batch(batch_no=len(batches), rows=batch_rows)
                    )
                    batch_rows = []
        if batch_rows:
            batches.append(_finalize_plan_batch(batch_no=len(batches), rows=batch_rows))
        if row_digest.count != expected:
            raise RuntimeError("pending probe rowset changed while freezing")
        batch_digest = StreamingJsonArraySha256()
        for batch in batches:
            batch_digest.add(batch)
        manifest: dict[str, Any] = {
            "schema": "allbot-history-media-r2-probe-plan/v1",
            "run_id": str(run_id),
            "history_watermark": int(run["history_watermark"]),
            "asset_count": row_digest.count,
            "history_count": history_count,
            "batch_count": len(batches),
            "batch_size": batch_size,
            "rowset_sha256": row_digest.hexdigest(),
            "batches_sha256": batch_digest.hexdigest(),
            "runtime_identity": _runtime_identity(
                artifact_digest=args.artifact_digest, config=config
            ),
        }
        seed_scope = _nondefault_seed_scope(run)
        if seed_scope is not None:
            manifest["seed_scope"] = seed_scope
        manifest["plan_sha256"] = _sha256_json(manifest)
        await _insert_plan_with_batches(
            conn, manifest=manifest, plan_type="probe", batches=batches
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "assets": manifest["asset_count"],
                    "histories": manifest["history_count"],
                    "batches": manifest["batch_count"],
                    "manifest": str(output),
                }
            )
        )
    finally:
        await conn.close()


async def _create_successor_probe_plan(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    predecessor_sha = str(args.predecessor_plan_sha256)
    try:
        await _ensure_schema(conn)
        async with conn.transaction():
            predecessor_row = await conn.fetchrow(
                """select run_id,manifest
                     from analytics_history_media_migration_plans
                    where plan_sha256=$1 and plan_type='probe'
                    for update""",
                predecessor_sha,
            )
            if not predecessor_row:
                raise RuntimeError("unknown exact predecessor Probe plan SHA")
            predecessor = (
                json.loads(predecessor_row["manifest"])
                if isinstance(predecessor_row["manifest"], str)
                else dict(predecessor_row["manifest"])
            )
            predecessor_chain = probe_plan_chain_sha256s(predecessor)
            if (
                predecessor_chain[-1] != predecessor_sha
                or predecessor_row["run_id"] != run_id
            ):
                raise RuntimeError("predecessor Probe plan identity mismatch")

            for index, plan_sha in enumerate(predecessor_chain):
                ancestor_run_id, ancestor = await _load_plan(conn, plan_sha, "probe")
                if (
                    ancestor_run_id != run_id
                    or probe_plan_chain_sha256s(ancestor)
                    != predecessor_chain[: index + 1]
                ):
                    raise RuntimeError("predecessor Probe chain identity mismatch")

            existing_successor = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_migration_plans
                        where plan_type='probe'
                          and manifest->>'predecessor_probe_plan_sha256'=$1""",
                    predecessor_sha,
                )
            )
            if existing_successor:
                raise RuntimeError("predecessor Probe plan already has a successor")

            predecessor_batches = await conn.fetch(
                """select * from analytics_history_media_migration_plan_batches
                    where plan_sha256=$1 order by batch_no for update""",
                predecessor_sha,
            )
            if not predecessor_batches:
                raise RuntimeError("predecessor Probe plan has no batches")
            unfinished_batches = [
                row for row in predecessor_batches if row["status"] != "completed"
            ]
            if not unfinished_batches:
                raise RuntimeError("predecessor Probe plan is already complete")
            if any(row["status"] == "superseded" for row in unfinished_batches):
                raise RuntimeError("predecessor Probe plan is already superseded")

            run = await conn.fetchrow(
                """select history_min_id,history_watermark,
                          history_reference_prefix,history_source,
                          history_source_route_sha256
                     from analytics_history_media_migration_runs
                    where id=$1 for update""",
                run_id,
            )
            if not run:
                raise RuntimeError("unknown migration run")

            retained_batches_raw = await conn.fetch(
                """select plan_sha256,batch_no,asset_count,history_count,
                          rowset_sha256,outcome_counts
                     from analytics_history_media_migration_plan_batches
                    where plan_sha256=any($1::text[]) and status='completed'""",
                list(predecessor_chain),
            )
            chain_order = {
                plan_sha: index for index, plan_sha in enumerate(predecessor_chain)
            }
            retained_batches = sorted(
                (
                    _retained_probe_batch_identity(
                        {
                            **dict(row),
                            "outcome_counts": (
                                json.loads(row["outcome_counts"])
                                if isinstance(row["outcome_counts"], str)
                                else dict(row["outcome_counts"] or {})
                            ),
                        }
                    )
                    for row in retained_batches_raw
                ),
                key=lambda batch: (
                    chain_order[batch["plan_sha256"]],
                    batch["batch_no"],
                ),
            )
            retained_batch_assets = sum(
                batch["asset_count"] for batch in retained_batches
            )
            retained_outcomes: Counter[str] = Counter()
            for batch in retained_batches:
                retained_outcomes.update(
                    {key: int(value) for key, value in batch["outcome_counts"].items()}
                )

            retained_digest = StreamingJsonArraySha256()
            async for record in conn.cursor(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          registry_task_id,history_manifest_sha256
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and probe_plan_sha256=any($2::text[])
                    order by id""",
                run_id,
                list(predecessor_chain),
                prefetch=PROBE_BATCH_SIZE,
            ):
                retained_digest.add(_probe_plan_row(dict(record)))
            retained_history_count = int(
                await conn.fetchval(
                    """select count(distinct history_id)
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and probe_plan_sha256=any($2::text[])""",
                    run_id,
                    list(predecessor_chain),
                )
            )
            if retained_digest.count != retained_batch_assets:
                raise RuntimeError(
                    "completed predecessor batches do not match retained ledger assets"
                )

            successor_query = """select m.id,m.history_id,m.role,m.ordinal,
                          m.original_ref,m.target_key,m.registry_task_id,
                          m.history_manifest_sha256
                     from analytics_history_media_r2_migrations m
                     join analytics_history_media_migration_plan_batches b
                       on b.plan_sha256=$2 and b.status<>'completed'
                      and m.id between b.first_ledger_id and b.last_ledger_id
                    where m.run_id=$1 and m.status='pending_probe'
                      and m.probe_plan_sha256 is null
                    order by m.id"""
            successor_history_count = int(
                await conn.fetchval(
                    """select count(distinct m.history_id)
                         from analytics_history_media_r2_migrations m
                         join analytics_history_media_migration_plan_batches b
                           on b.plan_sha256=$2 and b.status<>'completed'
                          and m.id between b.first_ledger_id and b.last_ledger_id
                        where m.run_id=$1 and m.status='pending_probe'
                          and m.probe_plan_sha256 is null""",
                    run_id,
                    predecessor_sha,
                )
            )
            successor_digest = StreamingJsonArraySha256()
            successor_batches: list[dict[str, Any]] = []
            batch_rows: list[dict[str, Any]] = []
            async for record in conn.cursor(
                successor_query,
                run_id,
                predecessor_sha,
                prefetch=PROBE_BATCH_SIZE,
            ):
                row = dict(record)
                successor_digest.add(_probe_plan_row(row))
                batch_rows.append(row)
                if len(batch_rows) == PROBE_BATCH_SIZE:
                    successor_batches.append(
                        _finalize_plan_batch(
                            batch_no=len(successor_batches), rows=batch_rows
                        )
                    )
                    batch_rows = []
            if batch_rows:
                successor_batches.append(
                    _finalize_plan_batch(
                        batch_no=len(successor_batches), rows=batch_rows
                    )
                )

            root_asset_count = int(
                predecessor.get("root_asset_count", predecessor["asset_count"])
            )
            if retained_digest.count + successor_digest.count != root_asset_count:
                raise RuntimeError("successor Probe asset conservation failed")
            expected_unfinished_assets = sum(
                int(batch["asset_count"]) for batch in unfinished_batches
            )
            if successor_digest.count != expected_unfinished_assets:
                raise RuntimeError(
                    "unfinished predecessor batches changed before successor freeze"
                )

            successor_batch_digest = StreamingJsonArraySha256()
            for batch in successor_batches:
                successor_batch_digest.add(batch)
            manifest: dict[str, Any] = {
                "schema": "allbot-history-media-r2-probe-successor-plan/v1",
                "run_id": str(run_id),
                "history_watermark": int(run["history_watermark"]),
                "predecessor_probe_plan_sha256": predecessor_sha,
                "predecessor_probe_plan_sha256s": list(predecessor_chain),
                "root_probe_plan_sha256": predecessor_chain[0],
                "root_asset_count": root_asset_count,
                "retained_asset_count": retained_digest.count,
                "retained_history_count": retained_history_count,
                "retained_batch_count": len(retained_batches),
                "retained_outcome_counts": dict(sorted(retained_outcomes.items())),
                "retained_rowset_sha256": retained_digest.hexdigest(),
                "retained_batches_sha256": _sha256_json(retained_batches),
                "asset_count": successor_digest.count,
                "history_count": successor_history_count,
                "batch_count": len(successor_batches),
                "batch_size": PROBE_BATCH_SIZE,
                "rowset_sha256": successor_digest.hexdigest(),
                "batches_sha256": successor_batch_digest.hexdigest(),
                "intersection_asset_count": 0,
                "conserved_asset_count": (
                    retained_digest.count + successor_digest.count
                ),
                "runtime_identity": _runtime_identity(
                    artifact_digest=args.artifact_digest, config=config
                ),
            }
            manifest["plan_sha256"] = _sha256_json(manifest)
            await _insert_plan_with_batches(
                conn,
                manifest=manifest,
                plan_type="probe",
                batches=successor_batches,
            )
            superseded = await conn.execute(
                """update analytics_history_media_migration_plan_batches
                      set status='superseded',updated_at=now()
                    where plan_sha256=$1 and status<>'completed'""",
                predecessor_sha,
            )
            if int(superseded.rsplit(" ", 1)[-1]) != len(unfinished_batches):
                raise RuntimeError("predecessor Probe supersede count changed")
            await conn.execute(
                """update analytics_history_media_migration_runs
                      set status='paused',phase='probe-successor-frozen',
                          error=null,updated_at=now() where id=$1""",
                run_id,
            )

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "predecessor_plan_sha256": predecessor_sha,
                    "retained_assets": manifest["retained_asset_count"],
                    "retained_batches": manifest["retained_batch_count"],
                    "assets": manifest["asset_count"],
                    "batches": manifest["batch_count"],
                    "manifest": str(output),
                }
            )
        )
    finally:
        await conn.close()


async def _collect_probe_head_outcomes(
    rows: list[dict[str, Any]],
    *,
    client: Any,
    concurrency: int,
    head_func: Any = _head_s3_identity,
) -> ProbeHeadBatchResult:
    if concurrency not in {8, 16, 32, 64, 128}:
        raise ValueError("Probe HEAD concurrency must be an adaptive level up to 128")
    keys: dict[str, None] = {}
    for row in rows:
        keys[str(row["target_key"])] = None
        for key in build_candidate_keys(
            str(row["original_ref"]), row.get("registry_task_id")
        ):
            keys[key] = None
    semaphore = asyncio.Semaphore(concurrency)
    activity = _ProbeHeadActivity()
    loop = asyncio.get_running_loop()

    head_executor = ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="history-r2-probe-head",
    )
    tasks: list[asyncio.Task[tuple[str, dict[str, Any] | None]]] = []
    try:

        async def head(key: str) -> tuple[str, dict[str, Any] | None]:
            async with semaphore:
                return key, await loop.run_in_executor(
                    head_executor,
                    activity.call,
                    head_func,
                    client,
                    BUCKET,
                    key,
                )

        tasks = [asyncio.create_task(head(key)) for key in keys]
        facts = dict(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        head_executor.shutdown(wait=True, cancel_futures=True)
    return ProbeHeadBatchResult(
        outcomes=classify_r2_head_outcomes(rows, facts),
        peak_workers=activity.peak,
        worker_threads=activity.thread_count,
        requested_concurrency=concurrency,
    )


async def _persist_probe_batch(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    plan_sha: str,
    batch_no: int,
    rows: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> Counter[str]:
    by_id = {int(row["id"]): row for row in rows}
    counts: Counter[str] = Counter()
    async with conn.transaction():
        for outcome in outcomes:
            row = by_id[int(outcome["id"])]
            status = str(outcome["status"])
            counts[status] += 1
            error_code = (
                "TARGET_EXISTS_UNVERIFIED"
                if status == "target_conflict"
                else "R2_CANDIDATES_NOT_FOUND" if status == "pending_probe" else None
            )
            source_name = (
                "target:user-data-prod"
                if status in {"target_verified", "target_conflict"}
                else "r2-user-data-prod" if status == "copy_required" else None
            )
            await conn.execute(
                """update analytics_history_media_r2_migrations set
                     probe_plan_sha256=$2,source_name=$3,source_key=$4,byte_size=$5,
                     source_last_modified=$6,source_etag=$7,target_etag=
                       case when $8 in ('target_verified','target_conflict') then $7 else null end,
                     status=$8,error_code=$9,error_detail=null,target_checked_at=now(),
                     r2_checked_at=now(),updated_at=now() where id=$1""",
                int(outcome["id"]),
                plan_sha,
                source_name,
                outcome["source_key"],
                outcome["byte_size"],
                outcome["last_modified"],
                outcome["etag"],
                status,
                error_code,
            )
            if status != "pending_probe":
                await conn.execute(
                    """update analytics_media_asset_catalog set status='found',
                         found_source=$2,source_key=$3,last_checked_at=now(),
                         missing_rounds=0,first_missing_at=null,last_error=null where id=$1""",
                    row["catalog_asset_id"],
                    source_name,
                    outcome["source_key"],
                )
            if outcome["attempts"]:
                await conn.executemany(
                    """insert into analytics_media_source_attempts
                         (run_id,asset_id,source,candidate_key,status)
                       values($1,$2,'r2-user-data-prod',$3,$4)""",
                    [
                        (
                            run_id,
                            row["catalog_asset_id"],
                            key,
                            attempt_status,
                        )
                        for key, attempt_status in outcome["attempts"]
                    ],
                )
        completed = await conn.execute(
            """update analytics_history_media_migration_plan_batches set
                 status='completed',outcome_counts=$3::jsonb,
                 started_at=coalesce(started_at,now()),completed_at=now(),updated_at=now()
               where plan_sha256=$1 and batch_no=$2 and status='pending'""",
            plan_sha,
            batch_no,
            json.dumps(dict(sorted(counts.items()))),
        )
        if int(completed.rsplit(" ", 1)[-1]) != 1:
            raise RuntimeError(
                "Probe batch is no longer pending; rolling back uncommitted outcomes"
            )
    return counts


async def _execute_probe(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    r2_source = next(
        (
            item
            for item in config.get("sources", [])
            if item.get("name") == "r2-user-data-prod" and item.get("enabled", True)
        ),
        None,
    )
    if not r2_source or r2_source.get("bucket") != BUCKET:
        raise RuntimeError("r2-user-data-prod source is not enabled for user-data-prod")
    if str(r2_source.get("endpoint", "")).rstrip("/") != str(
        config["target"].get("endpoint", "")
    ).rstrip("/"):
        raise RuntimeError(
            "frozen HEAD probe requires the target and source R2 endpoint"
        )
    max_pool_connections = _resolve_probe_max_pool_connections(args.concurrency)
    client = _s3_client(
        r2_source,
        max_pool_connections=max_pool_connections,
    )
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        run_id, manifest = await _load_plan(conn, args.plan_sha256, "probe")
        validate_probe_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        _validate_runtime_identity(
            manifest["runtime_identity"],
            artifact_digest=args.artifact_digest,
            config=config,
        )
        predecessor_chain = tuple(
            str(value) for value in manifest.get("predecessor_probe_plan_sha256s", [])
        )
        if predecessor_chain:
            invalid_predecessor_batches = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_migration_plan_batches
                        where plan_sha256=any($1::text[])
                          and status not in ('completed','superseded')""",
                    list(predecessor_chain),
                )
            )
            retained_assets = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and probe_plan_sha256=any($2::text[])""",
                    run_id,
                    list(predecessor_chain),
                )
            )
            if invalid_predecessor_batches or retained_assets != int(
                manifest["retained_asset_count"]
            ):
                raise RuntimeError("successor Probe predecessor state changed")
            if retained_assets + int(manifest["asset_count"]) != int(
                manifest["root_asset_count"]
            ):
                raise RuntimeError("successor Probe asset conservation changed")
        controller = AdaptiveProbeController(initial_concurrency=args.concurrency)
        processed = 0
        totals: Counter[str] = Counter()
        peak_head_workers = 0
        head_worker_threads = 0
        while args.max_batches <= 0 or processed < args.max_batches:
            batch = await conn.fetchrow(
                """select * from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status='pending'
                     order by batch_no limit 1""",
                args.plan_sha256,
            )
            if not batch:
                break
            rows = [
                dict(row)
                for row in await conn.fetch(
                    """select id,catalog_asset_id,run_id,history_id,role,ordinal,
                              original_ref,target_key,registry_task_id,history_manifest_sha256
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and id between $2 and $3
                          and status='pending_probe' and probe_plan_sha256 is null
                        order by id""",
                    run_id,
                    batch["first_ledger_id"],
                    batch["last_ledger_id"],
                )
            ]
            if len(rows) != int(batch["asset_count"]) or _sha256_json(
                [_probe_plan_row(row) for row in rows]
            ) != str(batch["rowset_sha256"]):
                raise RuntimeError("probe batch rowset changed")
            attempt = 0
            while True:
                try:
                    head_batch = await _collect_probe_head_outcomes(
                        rows, client=client, concurrency=controller.concurrency
                    )
                    outcomes = head_batch.outcomes
                    peak_head_workers = max(peak_head_workers, head_batch.peak_workers)
                    head_worker_threads = max(
                        head_worker_threads, head_batch.worker_threads
                    )
                    controller.record_success()
                    break
                except Exception as exc:
                    attempt += 1
                    if attempt > args.max_retries or not is_transient_copy_failure(
                        str(exc)
                    ):
                        raise
                    controller.record_failure(str(exc))
                    await asyncio.sleep(min(2**attempt, 30))
            counts = await _persist_probe_batch(
                conn,
                run_id=run_id,
                plan_sha=args.plan_sha256,
                batch_no=int(batch["batch_no"]),
                rows=rows,
                outcomes=outcomes,
            )
            totals.update(counts)
            processed += 1
            print(
                json.dumps(
                    {
                        "event": "probe_batch_completed",
                        "plan_sha256": args.plan_sha256,
                        "batch_no": int(batch["batch_no"]),
                        "asset_count": int(batch["asset_count"]),
                        "outcomes": dict(sorted(counts.items())),
                        "requested_concurrency": head_batch.requested_concurrency,
                        "peak_head_workers": head_batch.peak_workers,
                        "head_worker_threads": head_batch.worker_threads,
                        "max_pool_connections": max_pool_connections,
                        "next_concurrency": controller.concurrency,
                    }
                ),
                flush=True,
            )
        remaining = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status<>'completed'""",
                args.plan_sha256,
            )
        )
        await conn.execute(
            """update analytics_history_media_migration_runs set status='running',
                 phase=$2,error=null,updated_at=now() where id=$1""",
            run_id,
            "probe-frozen-completed" if remaining == 0 else "probe-frozen",
        )
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "plan_sha256": args.plan_sha256,
                    "processed_batches": processed,
                    "remaining_batches": remaining,
                    "outcomes": dict(sorted(totals.items())),
                    "next_concurrency": controller.concurrency,
                    "peak_head_workers": peak_head_workers,
                    "head_worker_threads": head_worker_threads,
                    "max_pool_connections": max_pool_connections,
                }
            )
        )
        if remaining == 0:
            await _create_plan(
                SimpleNamespace(
                    run_id=str(run_id),
                    parent_plan_sha256=args.plan_sha256,
                    config=args.config,
                    artifact_digest=args.artifact_digest,
                    allow_incomplete=False,
                    output=str(
                        Path(args.next_plan_output)
                        if args.next_plan_output
                        else _default_next_plan_output("copy", args.plan_sha256)
                    ),
                ),
                plan_type="copy",
            )
    except Exception as exc:
        if "manifest" in locals():
            await conn.execute(
                """update analytics_history_media_migration_runs set status='paused',
                     error=$2,updated_at=now() where id=$1""",
                uuid.UUID(manifest["run_id"]),
                str(exc)[:1000],
            )
        raise
    finally:
        await conn.close()
        client.close()


async def _create_copy_predecessor_recovery_plan(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    try:
        await _ensure_schema(conn)
        current_run_id, current = await _load_plan(
            conn, args.current_plan_sha256, "copy"
        )
        if current_run_id != run_id:
            raise RuntimeError("copy recovery current plan belongs to another run")
        chain = copy_plan_chain_sha256s(current)
        if len(chain) < 2:
            raise RuntimeError("copy recovery requires a successor Copy plan")
        predecessor_sha = chain[-2]
        current_batches = await conn.fetch(
            """select status,count(*) batches from analytics_history_media_migration_plan_batches
                 where plan_sha256=$1 group by status""",
            args.current_plan_sha256,
        )
        if not current_batches or any(
            row["status"] not in {"pending", "completed"} for row in current_batches
        ):
            raise RuntimeError("copy recovery current plan is not safely stopped")
        predecessor_batches = [
            dict(row)
            for row in await conn.fetch(
                """select batch_no,first_ledger_id,last_ledger_id,
                          first_history_id,last_history_id,asset_count,history_count,
                          rowset_sha256,cas_state_sha256,status
                     from analytics_history_media_migration_plan_batches
                    where plan_sha256=$1 order by batch_no""",
                predecessor_sha,
            )
        ]
        frontier = next(
            (row for row in predecessor_batches if row["status"] != "completed"),
            None,
        )
        if frontier is None or frontier["status"] != "superseded":
            raise RuntimeError("copy recovery predecessor frontier is unavailable")
        frontier_no = int(frontier["batch_no"])
        if any(
            (int(row["batch_no"]) < frontier_no and row["status"] != "completed")
            or (int(row["batch_no"]) >= frontier_no and row["status"] != "superseded")
            for row in predecessor_batches
        ):
            raise RuntimeError("copy recovery predecessor batch sequence changed")
        rows = [
            dict(row)
            for row in await conn.fetch(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_etag,
                          source_sha256,target_sha256,byte_size,status,
                          history_manifest_sha256,error_code
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and copy_plan_sha256=$2
                      and copy_completed_at is null
                      and status in ('copy_required','failed')
                      and id between $3 and $4 order by id""",
                run_id,
                args.current_plan_sha256,
                int(frontier["first_ledger_id"]),
                int(frontier["last_ledger_id"]),
            )
        ]
        manifest, batches = build_copy_predecessor_recovery_plan(
            current_manifest=current,
            current_plan_sha256=args.current_plan_sha256,
            predecessor_plan_sha256=predecessor_sha,
            frontier_batch=frontier,
            rows=rows,
            runtime_identity=_runtime_identity(
                artifact_digest=args.artifact_digest, config=config
            ),
        )
        await _insert_plan_with_batches(
            conn, manifest=manifest, plan_type="copy", batches=batches
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "current_copy_plan_sha256": args.current_plan_sha256,
                    "predecessor_copy_plan_sha256": predecessor_sha,
                    "frontier_batch_no": frontier_no,
                    "assets": manifest["count"],
                    "manifest": str(output),
                }
            )
        )
    finally:
        await conn.close()


async def _collect_copy_predecessor_recovery(
    groups: list[list[dict[str, Any]]],
    *,
    client: Any,
    current_plan_sha256: str,
    predecessor_plan_sha256: str,
    concurrency: int,
    head_func: Any = _head_s3_identity,
) -> list[tuple[list[dict[str, Any]], str, dict[str, Any] | None]]:
    if not 1 <= concurrency <= 128:
        raise ValueError("copy recovery concurrency must be between 1 and 128")
    loop = asyncio.get_running_loop()

    def inspect_group(
        group: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
        row = group[0]
        source_head = head_func(client, BUCKET, str(row["source_key"]))
        target_head = head_func(client, BUCKET, str(row["target_key"]))
        outcome = classify_copy_predecessor_recovery(
            source_head=source_head,
            target_head=target_head,
            expected_size=int(row["byte_size"]),
            expected_last_modified=row["source_last_modified"],
            expected_etag=str(row["source_etag"]),
            current_plan_sha256=current_plan_sha256,
            predecessor_plan_sha256=predecessor_plan_sha256,
        )
        return group, outcome, target_head

    executor = ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="history-r2-copy-recovery-head",
    )
    futures: list[asyncio.Future[Any]] = []
    try:
        futures = [
            loop.run_in_executor(executor, inspect_group, group) for group in groups
        ]
        return list(await asyncio.gather(*futures))
    except BaseException:
        for future in futures:
            future.cancel()
        await asyncio.gather(*futures, return_exceptions=True)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


async def _collect_failed_copy_reconciliation(
    groups: list[list[dict[str, Any]]],
    *,
    client: Any,
    current_plan_sha256: str,
    concurrency: int,
    head_func: Any = _head_s3_identity,
) -> list[tuple[list[dict[str, Any]], str, dict[str, Any] | None]]:
    """HEAD both sides of stopped failed objects with a bounded private pool."""

    if not 1 <= concurrency <= 128:
        raise ValueError("failed Copy reconciliation concurrency must be between 1 and 128")
    loop = asyncio.get_running_loop()

    def inspect_group(
        group: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any] | None]:
        row = group[0]
        source_head = head_func(client, BUCKET, str(row["source_key"]))
        target_head = head_func(client, BUCKET, str(row["target_key"]))
        outcome = classify_failed_copy_reconciliation(
            source_head=source_head,
            target_head=target_head,
            expected_size=int(row["byte_size"]),
            expected_last_modified=row["source_last_modified"],
            expected_etag=str(row["source_etag"]),
            current_plan_sha256=current_plan_sha256,
        )
        return group, outcome, target_head

    executor = ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="history-r2-failed-copy-head",
    )
    futures: list[asyncio.Future[Any]] = []
    try:
        futures = [
            loop.run_in_executor(executor, inspect_group, group) for group in groups
        ]
        return list(await asyncio.gather(*futures))
    except BaseException:
        for future in futures:
            future.cancel()
        await asyncio.gather(*futures, return_exceptions=True)
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


async def _reconcile_failed_copy_and_plan_successor(args: argparse.Namespace) -> None:
    """HEAD-reconcile transient failed rows, then freeze an unexecuted successor."""

    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    transport = _r2_transport(config)
    _validate_r2_transport_runtime(transport)
    max_pool_connections = _resolve_copy_max_pool_connections(args.concurrency, None)
    client = _s3_client(
        config["target"],
        max_pool_connections=max_pool_connections,
        transport=transport,
    )
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    try:
        current_run_id, current = await _load_plan(conn, args.plan_sha256, "copy")
        if current_run_id != run_id:
            raise RuntimeError("failed Copy reconciliation plan belongs to another run")
        runtime_identity = _reconciliation_runtime_identity(
            dict(current.get("runtime_identity") or {}),
            artifact_digest=args.artifact_digest,
            config=config,
        )
        batch_states = await conn.fetch(
            """select status,count(*) batches
                 from analytics_history_media_migration_plan_batches
                where plan_sha256=$1 group by status""",
            args.plan_sha256,
        )
        if not batch_states or any(
            row["status"] not in {"pending", "completed"} for row in batch_states
        ):
            raise RuntimeError("failed Copy reconciliation plan is not safely stopped")
        rows = [
            dict(row)
            for row in await conn.fetch(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_etag,
                          source_sha256,target_sha256,byte_size,status,
                          history_manifest_sha256,error_code,error_detail,
                          copy_plan_sha256,copy_completed_at
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and copy_plan_sha256=$2
                      and status='failed' and copy_completed_at is null
                    order by id""",
                run_id,
                args.plan_sha256,
            )
        ]
        if not rows:
            raise RuntimeError("failed Copy reconciliation found no failed rows")
        if any(
            row.get("error_code") != "COPY_FAILED"
            or not is_transient_copy_failure(str(row.get("error_detail") or ""))
            for row in rows
        ):
            raise RuntimeError("failed Copy reconciliation includes a non-transient failure")
        frozen_digest = StreamingJsonArraySha256()
        for row in rows:
            frozen_digest.add(_failed_copy_reconciliation_row(row))
        frozen_rowset_sha256 = frozen_digest.hexdigest()
        outcomes = await _collect_failed_copy_reconciliation(
            group_copy_candidates(rows),
            client=client,
            current_plan_sha256=args.plan_sha256,
            concurrency=args.concurrency,
        )
        object_outcomes = Counter(outcome for _group, outcome, _head in outcomes)
        asset_outcomes: Counter[str] = Counter()
        async with conn.transaction():
            locked = [
                dict(row)
                for row in await conn.fetch(
                    """select id,history_id,role,ordinal,original_ref,target_key,
                              source_name,source_key,source_last_modified,source_etag,
                              source_sha256,target_sha256,byte_size,status,
                              history_manifest_sha256,error_code,error_detail,
                              copy_plan_sha256,copy_completed_at
                         from analytics_history_media_r2_migrations
                        where id=any($1::bigint[]) order by id for update""",
                    [int(row["id"]) for row in rows],
                )
            ]
            locked_digest = StreamingJsonArraySha256()
            for row in locked:
                locked_digest.add(_failed_copy_reconciliation_row(row))
            if (
                len(locked) != len(rows)
                or locked_digest.hexdigest() != frozen_rowset_sha256
                or any(
                    row["status"] != "failed"
                    or str(row["copy_plan_sha256"]) != args.plan_sha256
                    or row["copy_completed_at"] is not None
                    for row in locked
                )
            ):
                raise RuntimeError("failed Copy reconciliation ledger rowset changed")
            for group, outcome, target_head in outcomes:
                ids = [int(row["id"]) for row in group]
                asset_outcomes[outcome] += len(ids)
                if outcome == "missing":
                    result = await conn.execute(
                        """update analytics_history_media_r2_migrations
                              set status='copy_required',error_code=null,error_detail=null,
                                  updated_at=now()
                            where id=any($1::bigint[]) and copy_plan_sha256=$2
                              and status='failed' and copy_completed_at is null""",
                        ids,
                        args.plan_sha256,
                    )
                else:
                    result = await conn.execute(
                        """update analytics_history_media_r2_migrations
                              set status='copied_verified',target_sha256=source_sha256,
                                  target_etag=$2,copy_method='r2_copy_object_reconciled_failed',
                                  error_code=null,error_detail=null,
                                  copy_completed_at=coalesce(copy_completed_at,now()),
                                  updated_at=now()
                            where id=any($1::bigint[]) and copy_plan_sha256=$3
                              and status='failed' and copy_completed_at is null""",
                        ids,
                        _normalize_etag(target_head.get("ETag")),
                        args.plan_sha256,
                    )
                if result != f"UPDATE {len(ids)}":
                    raise RuntimeError("failed Copy reconciliation ledger CAS changed")
        receipt = {
            "schema": "allbot-history-media-r2-failed-copy-reconciliation/v1",
            "run_id": str(run_id),
            "copy_plan_sha256": args.plan_sha256,
            "failed_asset_count": len(rows),
            "failed_rowset_sha256": frozen_rowset_sha256,
            "asset_outcomes": dict(sorted(asset_outcomes.items())),
            "object_outcomes": dict(sorted(object_outcomes.items())),
            "runtime_identity": runtime_identity,
            "concurrency": args.concurrency,
            "max_pool_connections": max_pool_connections,
            "operations": ["HeadObject"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt["receipt_sha256"] = _sha256_json(receipt)
        receipt_output = Path(args.receipt_output)
        receipt_output.parent.mkdir(parents=True, exist_ok=True)
        receipt_output.write_bytes(_canonical_json(receipt) + b"\n")
        os.chmod(receipt_output, 0o600)
        print(json.dumps(receipt), flush=True)
        await _create_plan(
            SimpleNamespace(
                run_id=str(run_id),
                parent_plan_sha256=current["parent_probe_plan_sha256"],
                config=args.config,
                artifact_digest=args.artifact_digest,
                output=args.next_plan_output,
                supersedes_plan_sha256=args.plan_sha256,
            ),
            plan_type="copy",
        )
    finally:
        await conn.close()
        client.close()


async def _execute_copy_predecessor_recovery(args: argparse.Namespace) -> None:
    config = _load_secure_config(Path(args.config))
    if config.get("target", {}).get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    max_pool_connections = _resolve_copy_max_pool_connections(args.concurrency, None)
    client = _s3_client(config["target"], max_pool_connections=max_pool_connections)
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        run_id, recovery = await _load_plan(conn, args.plan_sha256, "copy")
        if recovery.get("schema") != "allbot-history-media-r2-copy-recovery-plan/v1":
            raise RuntimeError("copy recovery plan schema is invalid")
        validate_copy_gate(
            expected_plan_sha256=recovery["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        _validate_runtime_identity(
            recovery["runtime_identity"],
            artifact_digest=args.artifact_digest,
            config=config,
        )
        current_sha = str(recovery["current_copy_plan_sha256"])
        predecessor_sha = str(recovery["predecessor_copy_plan_sha256"])
        current_run_id, current = await _load_plan(conn, current_sha, "copy")
        if current_run_id != run_id or copy_plan_chain_sha256s(current) != tuple(
            recovery["copy_chain_plan_sha256s"]
        ):
            raise RuntimeError("copy recovery chain identity changed")
        current_batch_states = await conn.fetch(
            """select status,count(*) batches from analytics_history_media_migration_plan_batches
                 where plan_sha256=$1 group by status""",
            current_sha,
        )
        if not current_batch_states or any(
            row["status"] not in {"pending", "completed"}
            for row in current_batch_states
        ):
            raise RuntimeError("copy recovery current plan is not safely stopped")
        frontier = await conn.fetchrow(
            """select * from analytics_history_media_migration_plan_batches
                 where plan_sha256=$1 and batch_no=$2 and status='superseded'""",
            predecessor_sha,
            int(recovery["frontier_batch_no"]),
        )
        if (
            not frontier
            or str(frontier["rowset_sha256"])
            != recovery["frontier_batch_rowset_sha256"]
        ):
            raise RuntimeError("copy recovery predecessor frontier changed")
        rows = [
            dict(row)
            for row in await conn.fetch(
                """select id,history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_etag,
                          source_sha256,target_sha256,byte_size,status,
                          history_manifest_sha256,error_code
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and copy_plan_sha256=$2
                      and copy_completed_at is null
                      and status in ('copy_required','failed')
                      and id between $3 and $4 order by id""",
                run_id,
                current_sha,
                int(frontier["first_ledger_id"]),
                int(frontier["last_ledger_id"]),
            )
        ]
        normalized = [_normalized_frozen_copy_row(row) for row in rows]
        digest = StreamingJsonArraySha256()
        for row in normalized:
            digest.add(_plan_row(row))
        if (
            digest.count != int(recovery["count"])
            or digest.hexdigest() != recovery["rowset_sha256"]
        ):
            raise RuntimeError("copy recovery rowset changed")
        groups = group_copy_candidates(rows)
        outcomes = await _collect_copy_predecessor_recovery(
            groups,
            client=client,
            current_plan_sha256=current_sha,
            predecessor_plan_sha256=predecessor_sha,
            concurrency=args.concurrency,
        )
        outcome_counts = Counter(outcome for _group, outcome, _head in outcomes)
        row_counts: Counter[str] = Counter()
        async with conn.transaction():
            locked = await conn.fetch(
                """select id,copy_plan_sha256,status,copy_completed_at
                     from analytics_history_media_r2_migrations
                    where id=any($1::bigint[]) order by id for update""",
                [int(row["id"]) for row in rows],
            )
            if len(locked) != len(rows) or any(
                str(row["copy_plan_sha256"]) != current_sha
                or row["status"] not in {"copy_required", "failed"}
                or row["copy_completed_at"] is not None
                for row in locked
            ):
                raise RuntimeError("copy recovery ledger ownership changed")
            for group, outcome, target_head in outcomes:
                ids = [int(row["id"]) for row in group]
                row_counts[outcome] += len(ids)
                if outcome == "missing":
                    result = await conn.execute(
                        """update analytics_history_media_r2_migrations
                              set status='copy_required',error_code=null,error_detail=null,
                                  updated_at=now()
                            where id=any($1::bigint[]) and copy_plan_sha256=$2
                              and status in ('copy_required','failed')
                              and copy_completed_at is null""",
                        ids,
                        current_sha,
                    )
                else:
                    owner = current_sha if outcome == "current" else predecessor_sha
                    method = (
                        "r2_copy_object_recovered"
                        if outcome == "current"
                        else "r2_copy_object_recovered_predecessor"
                    )
                    result = await conn.execute(
                        """update analytics_history_media_r2_migrations
                              set copy_plan_sha256=$2,status='copied_verified',
                                  target_sha256=source_sha256,target_etag=$3,
                                  copy_method=$4,error_code=null,error_detail=null,
                                  copy_completed_at=coalesce(copy_completed_at,now()),
                                  updated_at=now()
                            where id=any($1::bigint[]) and copy_plan_sha256=$5
                              and status in ('copy_required','failed')
                              and copy_completed_at is null""",
                        ids,
                        owner,
                        _normalize_etag(target_head.get("ETag")),
                        method,
                        current_sha,
                    )
                if int(result.rsplit(" ", 1)[-1]) != len(ids):
                    raise RuntimeError("copy recovery ledger CAS changed")
            completed = await conn.execute(
                """update analytics_history_media_migration_plan_batches
                      set status='completed',outcome_counts=$3::jsonb,
                          completed_at=now(),updated_at=now()
                    where plan_sha256=$1 and batch_no=$2 and status='pending'""",
                args.plan_sha256,
                0,
                json.dumps(dict(sorted(row_counts.items()))),
            )
            if completed != "UPDATE 1":
                raise RuntimeError("copy recovery plan batch state changed")
        receipt = {
            "schema": "allbot-history-media-r2-copy-recovery-receipt/v1",
            "plan_sha256": args.plan_sha256,
            "current_copy_plan_sha256": current_sha,
            "predecessor_copy_plan_sha256": predecessor_sha,
            "frontier_batch_no": int(recovery["frontier_batch_no"]),
            "rowset_sha256": recovery["rowset_sha256"],
            "asset_outcomes": dict(sorted(row_counts.items())),
            "object_outcomes": dict(sorted(outcome_counts.items())),
            "max_pool_connections": max_pool_connections,
            "concurrency": args.concurrency,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        receipt["receipt_sha256"] = _sha256_json(receipt)
        receipt_output = Path(args.receipt_output)
        receipt_output.parent.mkdir(parents=True, exist_ok=True)
        receipt_output.write_bytes(_canonical_json(receipt) + b"\n")
        os.chmod(receipt_output, 0o600)
        print(json.dumps(receipt), flush=True)
        await _create_plan(
            SimpleNamespace(
                run_id=str(run_id),
                parent_plan_sha256=current["parent_probe_plan_sha256"],
                config=args.config,
                artifact_digest=args.artifact_digest,
                output=args.next_plan_output,
                supersedes_plan_sha256=current_sha,
            ),
            plan_type="copy",
        )
    finally:
        await conn.close()
        client.close()


async def _create_plan(args: argparse.Namespace, *, plan_type: str) -> None:
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    run_id = uuid.UUID(args.run_id)
    try:
        await _ensure_schema(conn)
        run = await conn.fetchrow(
            """select history_min_id,history_watermark,history_reference_prefix,
                      history_source,history_source_route_sha256,sha_bytes_read,status
                 from analytics_history_media_migration_runs where id=$1""",
            run_id,
        )
        if not run:
            raise RuntimeError("unknown migration run")
        batches: list[dict[str, Any]] = []
        if plan_type == "copy":
            config = _load_secure_config(Path(args.config))
            parent_run_id, parent = await _load_plan(
                conn, args.parent_plan_sha256, "probe"
            )
            if parent_run_id != run_id:
                raise RuntimeError("copy parent probe belongs to another run")
            probe_chain = probe_plan_chain_sha256s(parent)
            incomplete_batches = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_migration_plan_batches
                         where plan_sha256=$1 and status<>'completed'""",
                    args.parent_plan_sha256,
                )
            )
            if incomplete_batches:
                raise RuntimeError(f"PROBE_NOT_COMPLETE: batches={incomplete_batches}")
            invalid_predecessor_batches = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_migration_plan_batches
                        where plan_sha256=any($1::text[])
                          and status not in ('completed','superseded')""",
                    list(probe_chain[:-1]),
                )
            )
            if invalid_predecessor_batches:
                raise RuntimeError("predecessor Probe chain is not terminal")
            completed_chain_assets = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and probe_plan_sha256=any($2::text[])""",
                    run_id,
                    list(probe_chain),
                )
            )
            root_asset_count = int(
                parent.get("root_asset_count", parent["asset_count"])
            )
            if completed_chain_assets != root_asset_count:
                raise RuntimeError("Probe chain ledger assets are incomplete")
            oversized = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and probe_plan_sha256=any($2::text[])
                           and status='copy_required' and byte_size > $3""",
                    run_id,
                    list(probe_chain),
                    SINGLE_COPY_LIMIT,
                )
            )
            if oversized:
                raise RuntimeError(
                    f"COPY_PLAN_HAS_UNSUPPORTED_MULTIPART_OBJECTS: count={oversized}"
                )
            supersedes_plan_sha256 = getattr(args, "supersedes_plan_sha256", None)
            predecessor_copy_chain: tuple[str, ...] = ()
            retained_count = 0
            retained_rowset_sha = StreamingJsonArraySha256().hexdigest()
            root_copy_asset_count = 0
            if supersedes_plan_sha256:
                old_run_id, old_copy = await _load_plan(
                    conn, supersedes_plan_sha256, "copy"
                )
                if old_run_id != run_id:
                    raise RuntimeError(
                        "copy replacement predecessor belongs to another run"
                    )
                if old_copy.get("parent_probe_plan_sha256") != parent["plan_sha256"]:
                    raise RuntimeError("copy replacement Probe parent changed")
                predecessor_copy_chain = copy_plan_chain_sha256s(old_copy)
                failed_count = int(
                    await conn.fetchval(
                        """select count(*) from analytics_history_media_r2_migrations
                             where run_id=$1 and copy_plan_sha256=$2
                               and status='failed'""",
                        run_id,
                        supersedes_plan_sha256,
                    )
                )
                if failed_count:
                    raise RuntimeError(
                        "copy replacement predecessor still has failed objects"
                    )
                query = """select id,history_id,role,ordinal,original_ref,target_key,
                              source_name,source_key,source_last_modified,source_etag,source_sha256,
                              target_sha256,byte_size,status,history_manifest_sha256,error_code,
                              copy_plan_sha256
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and copy_plan_sha256=$2
                          and copy_completed_at is null and status='copy_required'
                        order by id"""
                query_params: tuple[Any, ...] = (run_id, supersedes_plan_sha256)
                retained_query = """select id,history_id,role,ordinal,original_ref,target_key,
                              source_name,source_key,source_last_modified,source_etag,source_sha256,
                              null::char(64) target_sha256,byte_size,
                              'copy_required'::text status,history_manifest_sha256,error_code
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and copy_plan_sha256=any($2::text[])
                          and status='copied_verified' and copy_completed_at is not null
                        order by id"""
                (
                    retained_rowset_sha,
                    retained_count,
                    _rc,
                    _rb,
                    _rd,
                ) = await _stream_plan_rowset(
                    conn, retained_query, run_id, list(predecessor_copy_chain)
                )
                root_copy_asset_count = int(
                    old_copy.get("root_asset_count", old_copy["count"])
                )
            else:
                query = """select id,history_id,role,ordinal,original_ref,target_key,
                              source_name,source_key,source_last_modified,source_etag,source_sha256,
                              target_sha256,byte_size,status,history_manifest_sha256,error_code
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and probe_plan_sha256=any($2::text[])
                          and status='copy_required'
                        order by id"""
                query_params = (run_id, list(probe_chain))
            (
                rowset_sha,
                count,
                counts,
                byte_counts,
                diagnostics,
            ) = await _stream_plan_rowset(
                conn,
                query,
                *query_params,
                copy_plan_sha256=supersedes_plan_sha256,
            )
            if (
                supersedes_plan_sha256
                and retained_count + count != root_copy_asset_count
            ):
                raise RuntimeError("copy replacement asset conservation changed")
            batch_rows: list[dict[str, Any]] = []
            async with conn.transaction():
                async for record in conn.cursor(
                    query,
                    *query_params,
                    prefetch=COPY_BATCH_SIZE,
                ):
                    row = dict(record)
                    if supersedes_plan_sha256:
                        row = _normalized_frozen_copy_row(row)
                    batch_rows.append(row)
                    if len(batch_rows) == COPY_BATCH_SIZE:
                        batches.append(
                            _finalize_plan_batch(
                                batch_no=len(batches),
                                rows=batch_rows,
                                row_transform=_plan_row,
                            )
                        )
                        batch_rows = []
            if batch_rows:
                batches.append(
                    _finalize_plan_batch(
                        batch_no=len(batches),
                        rows=batch_rows,
                        row_transform=_plan_row,
                    )
                )
            batch_digest = StreamingJsonArraySha256()
            for batch in batches:
                batch_digest.add(batch)
            manifest = {
                "schema": (
                    "allbot-history-media-r2-copy-plan/v3"
                    if supersedes_plan_sha256
                    else "allbot-history-media-r2-copy-plan/v2"
                ),
                "run_id": str(run_id),
                "history_watermark": int(run["history_watermark"]),
                "parent_probe_plan_sha256": parent["plan_sha256"],
                "probe_chain_plan_sha256s": list(probe_chain),
                "probe_chain_sha256": _sha256_json(list(probe_chain)),
                "count": count,
                "counts": dict(sorted(counts.items())),
                "bytes": dict(sorted(byte_counts.items())),
                "sha_bytes_read": int(run["sha_bytes_read"]),
                "pending_at_freeze": incomplete_batches,
                "run_status_at_freeze": str(run["status"]),
                "partial_scope": False,
                "batch_count": len(batches),
                "batch_size": COPY_BATCH_SIZE,
                "batches_sha256": batch_digest.hexdigest(),
                "diagnostics": diagnostics,
                "rowset_sha256": rowset_sha,
                "runtime_identity": _runtime_identity(
                    artifact_digest=args.artifact_digest, config=config
                ),
            }
            seed_scope = _nondefault_seed_scope(run)
            if seed_scope is not None:
                manifest["seed_scope"] = seed_scope
            if supersedes_plan_sha256:
                manifest.update(
                    {
                        "supersedes_copy_plan_sha256": supersedes_plan_sha256,
                        "predecessor_copy_plan_sha256s": list(predecessor_copy_chain),
                        "predecessor_copy_chain_sha256": _sha256_json(
                            list(predecessor_copy_chain)
                        ),
                        "root_asset_count": root_copy_asset_count,
                        "retained_asset_count": retained_count,
                        "retained_rowset_sha256": retained_rowset_sha,
                        "intersection_asset_count": 0,
                        "conserved_asset_count": retained_count + count,
                    }
                )
            manifest["plan_sha256"] = _sha256_json(manifest)
        else:
            parent_run_id, parent = await _load_plan(
                conn, args.parent_plan_sha256, "copy"
            )
            if parent_run_id != run_id:
                raise RuntimeError("switch parent copy belongs to another run")
            copy_chain = copy_plan_chain_sha256s(parent)
            rolling_switch = bool(
                getattr(args, "completed_copy_batches_only", False)
            )
            rolling_scope: dict[str, Any] | None = None
            if rolling_switch:
                pending_switch_assets = int(
                    await conn.fetchval(
                        """select count(*)
                             from analytics_history_media_r2_migrations
                            where run_id=$1 and switch_plan_sha256 is not null
                              and switch_completed_at is null""",
                        run_id,
                    )
                )
                if pending_switch_assets:
                    raise RuntimeError(
                        "an earlier Switch plan is still pending execution"
                    )
                completed_current_batches = [
                    dict(record)
                    for record in await conn.fetch(
                        """select plan_sha256,batch_no,first_ledger_id,last_ledger_id,
                                  asset_count,rowset_sha256,status
                             from analytics_history_media_migration_plan_batches
                            where plan_sha256=$1 and status='completed'
                            order by batch_no""",
                        args.parent_plan_sha256,
                    )
                ]
                rolling_scope = build_rolling_switch_scope_identity(
                    copy_chain=copy_chain,
                    parent_copy_plan_sha256=args.parent_plan_sha256,
                    completed_current_batches=completed_current_batches,
                )
                query = ROLLING_SWITCH_ROWSET_SQL
                query_params: tuple[Any, ...] = (
                    run_id,
                    list(copy_chain[:-1]),
                    args.parent_plan_sha256,
                    rolling_scope["current_completed_batch_nos"],
                )
            else:
                incomplete_copy_batches = int(
                    await conn.fetchval(
                        """select count(*) from analytics_history_media_migration_plan_batches
                             where plan_sha256=$1 and status<>'completed'""",
                        args.parent_plan_sha256,
                    )
                )
                if incomplete_copy_batches:
                    raise RuntimeError(
                        f"COPY_NOT_COMPLETE: batches={incomplete_copy_batches}"
                    )
                query = """select id,history_id,role,ordinal,original_ref,target_key,
                              source_name,source_key,source_last_modified,source_etag,source_sha256,
                              target_sha256,byte_size,status,history_manifest_sha256
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and copy_plan_sha256=any($2::text[])
                          and status='copied_verified' and switch_completed_at is null
                          and original_ref <> target_key
                        order by history_id,role,ordinal"""
                query_params = (run_id, list(copy_chain))
            invalid_predecessor_copy_batches = int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_migration_plan_batches
                        where plan_sha256=any($1::text[])
                          and status not in ('completed','superseded')""",
                    list(copy_chain[:-1]),
                )
            )
            if invalid_predecessor_copy_batches:
                raise RuntimeError("predecessor Copy chain is not terminal")
            (
                rowset_sha,
                count,
                _counts,
                byte_counts,
                _diagnostics,
            ) = await _stream_plan_rowset(conn, query, *query_params)
            if not count:
                raise RuntimeError("no completed Copy assets are eligible for Switch")
            production = await _connect_env("PRODUCTION_DATABASE_URL")
            try:
                batch_rows: list[dict[str, Any]] = []
                batch_history_ids: list[int] = []

                async def flush_switch_batch() -> None:
                    nonlocal batch_rows, batch_history_ids
                    if not batch_rows:
                        return
                    cas_sha, _histories, _ledger_rows = await _cas_state_for_histories(
                        production,
                        conn,
                        run_id=run_id,
                        history_ids=batch_history_ids,
                        selected_ledger_ids={int(row["id"]) for row in batch_rows},
                        allow_selected_target=False,
                    )
                    batches.append(
                        _finalize_plan_batch(
                            batch_no=len(batches),
                            rows=batch_rows,
                            cas_state_sha256=cas_sha,
                            row_transform=_plan_row,
                        )
                    )
                    batch_rows = []
                    batch_history_ids = []

                async with conn.transaction():
                    async for record in conn.cursor(
                        query,
                        *query_params,
                        prefetch=SWITCH_HISTORY_BATCH_SIZE,
                    ):
                        row = dict(record)
                        history_id = int(row["history_id"])
                        if (
                            batch_history_ids
                            and history_id != batch_history_ids[-1]
                            and len(batch_history_ids) >= SWITCH_HISTORY_BATCH_SIZE
                        ):
                            await flush_switch_batch()
                        if not batch_history_ids or history_id != batch_history_ids[-1]:
                            batch_history_ids.append(history_id)
                        batch_rows.append(row)
                    await flush_switch_batch()
            finally:
                await production.close()
            predecessor_count, predecessor_sha = await _predecessor_switch_identity(
                conn, run_id
            )
            manifest = {
                "schema": "allbot-history-media-r2-switch-plan/v2",
                "run_id": str(run_id),
                "history_watermark": int(run["history_watermark"]),
                "parent_copy_plan_sha256": parent["plan_sha256"],
                "copy_chain_plan_sha256s": list(copy_chain),
                "copy_chain_sha256": _sha256_json(list(copy_chain)),
                "count": count,
                "bytes": sum(byte_counts.values()),
                "batch_count": len(batches),
                "history_batch_size": SWITCH_HISTORY_BATCH_SIZE,
                "rowset_sha256": rowset_sha,
                "predecessor_switch_plan_count": predecessor_count,
                "predecessor_switch_plans_sha256": predecessor_sha,
                "runtime_identity": _runtime_identity(
                    artifact_digest=args.artifact_digest
                ),
            }
            seed_scope = _nondefault_seed_scope(run)
            if seed_scope is not None:
                manifest["seed_scope"] = seed_scope
            if rolling_scope is not None:
                manifest.update(
                    {
                        "rolling_completed_copy_batches_only": True,
                        **rolling_scope,
                    }
                )
            manifest["plan_sha256"] = _sha256_json(manifest)
        plan_sha = manifest["plan_sha256"]
        supersedes_plan_sha256 = getattr(args, "supersedes_plan_sha256", None)
        if plan_type == "copy" and supersedes_plan_sha256:
            await _replace_unexecuted_copy_plan(
                conn,
                run_id=run_id,
                old_plan_sha256=supersedes_plan_sha256,
                manifest=manifest,
                batches=batches,
            )
        else:
            if plan_type == "copy":
                await _reject_unacknowledged_copy_replan(
                    conn, run_id=run_id, manifest=manifest
                )
            await _insert_plan_with_batches(
                conn, manifest=manifest, plan_type=plan_type, batches=batches
            )
        if plan_type == "copy":
            if not supersedes_plan_sha256:
                await conn.execute(
                    """update analytics_history_media_r2_migrations
                          set copy_plan_sha256=$3,updated_at=now()
                        where run_id=$1 and probe_plan_sha256=any($2::text[])
                          and status='copy_required'""",
                    run_id,
                    list(probe_chain),
                    plan_sha,
                )
        else:
            if rolling_scope is not None:
                result = await conn.execute(
                    ROLLING_SWITCH_BIND_SQL,
                    run_id,
                    list(copy_chain[:-1]),
                    args.parent_plan_sha256,
                    rolling_scope["current_completed_batch_nos"],
                    plan_sha,
                )
                if result != f"UPDATE {count}":
                    raise RuntimeError(
                        "rolling Switch rowset changed before plan binding"
                    )
            else:
                await conn.execute(
                    """update analytics_history_media_r2_migrations
                          set switch_plan_sha256=$3,updated_at=now()
                        where run_id=$1 and copy_plan_sha256=any($2::text[])
                          and status='copied_verified' and switch_completed_at is null
                          and original_ref <> target_key""",
                    run_id,
                    list(copy_chain),
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
        """select p.run_id,p.manifest,r.history_min_id,r.history_watermark,
                  r.history_reference_prefix,r.history_source,
                  r.history_source_route_sha256
             from analytics_history_media_migration_plans p
             join analytics_history_media_migration_runs r on r.id=p.run_id
            where p.plan_sha256=$1 and p.plan_type=$2""",
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
    if (
        _sha256_json(
            {key: value for key, value in manifest.items() if key != "plan_sha256"}
        )
        != plan_sha
    ):
        raise RuntimeError("stored plan identity is invalid")
    validate_plan_seed_scope(
        manifest=manifest,
        expected_scope=_seed_scope_from_run(row),
    )
    return row["run_id"], manifest


async def _persist_copy_success(
    conn: asyncpg.Connection,
    rows: Iterable[dict[str, Any]],
    copied: dict[str, Any],
    *,
    copy_plan_sha256: str | None = None,
) -> None:
    ids = [int(row["id"]) for row in rows]
    method = (
        "r2_multipart_copy"
        if copied["multipart"]
        else "r2_copy_object_recovered" if copied.get("recovered") else "r2_copy_object"
    )
    ownership_clause = " and copy_plan_sha256=$4" if copy_plan_sha256 else ""
    params: tuple[Any, ...] = (ids, copied["etag"], method)
    if copy_plan_sha256:
        params = (*params, copy_plan_sha256)
    result = await conn.execute(
        """update analytics_history_media_r2_migrations set
             status='copied_verified',target_sha256=source_sha256,
             target_etag=$2,copy_method=$3,error_code=null,error_detail=null,
             copy_completed_at=coalesce(copy_completed_at,now()),updated_at=now()
           where id=any($1::bigint[])""" + ownership_clause,
        *params,
    )
    if copy_plan_sha256 and result != f"UPDATE {len(ids)}":
        raise RuntimeError("copy plan ownership changed before success commit")


async def _persist_copy_failure(
    conn: asyncpg.Connection,
    rows: Iterable[dict[str, Any]],
    exc: BaseException,
    *,
    copy_plan_sha256: str | None = None,
) -> None:
    ownership_clause = " and copy_plan_sha256=$3" if copy_plan_sha256 else ""
    params: tuple[Any, ...] = ([int(row["id"]) for row in rows], str(exc)[:1000])
    if copy_plan_sha256:
        params = (*params, copy_plan_sha256)
    result = await conn.execute(
        """update analytics_history_media_r2_migrations set status='failed',
             error_code='COPY_FAILED',error_detail=$2,updated_at=now()
           where id=any($1::bigint[])""" + ownership_clause,
        *params,
    )
    if copy_plan_sha256 and result != f"UPDATE {len(params[0])}":
        raise RuntimeError("copy plan ownership changed before failure commit")


async def _verify_copy_plan_objects(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    plan_sha256: str,
    copy_plan_sha256s: Iterable[str] | None = None,
    client: Any,
    concurrency: int,
) -> dict[str, int]:
    plan_chain = tuple(copy_plan_sha256s or (plan_sha256,))
    ledger_rows = int(
        await conn.fetchval(
            """select count(*) from analytics_history_media_r2_migrations
                 where run_id=$1 and copy_plan_sha256=any($2::text[])
                   and status='copied_verified'""",
            run_id,
            list(plan_chain),
        )
    )
    verified_objects = 0
    buffer: list[dict[str, Any]] = []

    async def verify_buffer() -> None:
        nonlocal verified_objects, buffer
        if not buffer:
            return
        semaphore = asyncio.Semaphore(concurrency)

        async def verify(row: dict[str, Any]) -> None:
            async with semaphore:
                source_head, target_head = await asyncio.gather(
                    asyncio.to_thread(
                        _head_s3_identity,
                        client,
                        BUCKET,
                        str(row["source_key"]),
                    ),
                    asyncio.to_thread(
                        _head_s3_identity,
                        client,
                        BUCKET,
                        str(row["target_key"]),
                    ),
                )
                validate_copy_verification_heads(
                    row,
                    source_head=source_head,
                    target_head=target_head,
                    copy_plan_sha256=str(row["copy_plan_sha256"]),
                )

        await asyncio.gather(*(verify(row) for row in buffer))
        verified_objects += len(buffer)
        buffer = []

    last_target = ""
    while True:
        page = await conn.fetch(
            """select distinct on (target_key) target_key,source_key,byte_size,
                      source_last_modified,source_etag,copy_plan_sha256
                 from analytics_history_media_r2_migrations
                where run_id=$1 and copy_plan_sha256=any($2::text[])
                  and status='copied_verified' and target_key>$3
                order by target_key,id limit 1000""",
            run_id,
            list(plan_chain),
            last_target,
        )
        if not page:
            break
        buffer.extend(dict(record) for record in page)
        await verify_buffer()
        last_target = str(page[-1]["target_key"])
    return {"ledger_rows": ledger_rows, "verified_objects": verified_objects}


async def _validate_copy_plan_preflight(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    manifest: dict[str, Any],
    plan_sha256: str,
) -> None:
    """Validate immutable global Copy identity once per supervisor lifetime."""
    if manifest.get("batches_sha256"):
        frozen_batches = await conn.fetch(
            """select batch_no,first_ledger_id,last_ledger_id,
                      first_history_id,last_history_id,asset_count,history_count,
                      rowset_sha256,cas_state_sha256
                 from analytics_history_media_migration_plan_batches
                where plan_sha256=$1 order by batch_no""",
            plan_sha256,
        )
        batch_digest = StreamingJsonArraySha256()
        for record in frozen_batches:
            batch_digest.add(dict(record))
        if (
            len(frozen_batches) != int(manifest["batch_count"])
            or batch_digest.hexdigest() != manifest["batches_sha256"]
        ):
            raise RuntimeError("copy plan batches identity changed")

    rowset_sha, _count, _counts, _bytes, _diagnostics = await _stream_plan_rowset(
        conn,
        """select id,history_id,role,ordinal,original_ref,target_key,
                  source_name,source_key,source_last_modified,source_etag,source_sha256,
                  target_sha256,byte_size,status,history_manifest_sha256,
                  copy_plan_sha256
             from analytics_history_media_r2_migrations
            where run_id=$1 and copy_plan_sha256=$2
            order by id""",
        run_id,
        plan_sha256,
        copy_plan_sha256=plan_sha256,
    )
    if rowset_sha != manifest["rowset_sha256"]:
        raise RuntimeError("copy plan rowset changed")

    predecessor_copy_plans = tuple(
        str(value) for value in manifest.get("predecessor_copy_plan_sha256s", [])
    )
    if predecessor_copy_plans:
        if tuple(copy_plan_chain_sha256s(manifest)[:-1]) != predecessor_copy_plans:
            raise RuntimeError("copy predecessor chain identity changed")
        invalid_predecessor_batches = int(
            await conn.fetchval(
                """select count(*)
                     from analytics_history_media_migration_plan_batches
                    where plan_sha256=any($1::text[])
                      and status not in ('completed','superseded')""",
                list(predecessor_copy_plans),
            )
        )
        retained_assets = int(
            await conn.fetchval(
                """select count(*)
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and copy_plan_sha256=any($2::text[])
                      and status='copied_verified'
                      and copy_completed_at is not null""",
                run_id,
                list(predecessor_copy_plans),
            )
        )
        if (
            invalid_predecessor_batches
            or retained_assets != int(manifest["retained_asset_count"])
            or retained_assets + int(manifest["count"])
            != int(manifest["root_asset_count"])
        ):
            raise RuntimeError("copy predecessor retained state changed")

    conflicting_target = await conn.fetchval(
        """select target_key from (
             select target_key,
                    count(distinct (source_name,source_key,byte_size,
                                    source_last_modified,source_etag,source_sha256)) identities
               from analytics_history_media_r2_migrations
              where run_id=$1 and copy_plan_sha256=$2
              group by target_key
           ) grouped where identities > 1 limit 1""",
        run_id,
        plan_sha256,
    )
    if conflicting_target is not None:
        raise RuntimeError(
            "copy plan contains a target with conflicting frozen sources"
        )
    ineligible_source_count = int(
        await conn.fetchval(
            """select count(*) from analytics_history_media_r2_migrations
                 where run_id=$1 and copy_plan_sha256=$2
                   and status in ('copy_required','failed')
                   and source_name is distinct from 'r2-user-data-prod'""",
            run_id,
            plan_sha256,
        )
    )
    if ineligible_source_count:
        raise RuntimeError("copy plan contains a non-R2 source")
    multipart_count = int(
        await conn.fetchval(
            """select count(*) from analytics_history_media_r2_migrations
                 where run_id=$1 and copy_plan_sha256=$2
                   and status in ('copy_required','failed') and byte_size > $3""",
            run_id,
            plan_sha256,
            SINGLE_COPY_LIMIT,
        )
    )
    if multipart_count:
        raise RuntimeError("frozen production copy plan contains multipart objects")


async def _validate_copy_batch_identity(
    conn: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    plan_sha256: str,
    batch: dict[str, Any],
) -> None:
    rows = await conn.fetch(
        """select id,history_id,role,ordinal,original_ref,target_key,
                  source_name,source_key,source_last_modified,source_etag,source_sha256,
                  target_sha256,byte_size,status,history_manifest_sha256,
                  copy_plan_sha256
             from analytics_history_media_r2_migrations
            where run_id=$1 and copy_plan_sha256=$2
              and id between $3 and $4
            order by id""",
        run_id,
        plan_sha256,
        int(batch["first_ledger_id"]),
        int(batch["last_ledger_id"]),
    )
    digest = StreamingJsonArraySha256()
    for record in rows:
        digest.add(_plan_row(_normalized_frozen_copy_row(dict(record))))
    if len(rows) != int(batch["asset_count"]) or digest.hexdigest() != str(
        batch["rowset_sha256"]
    ):
        raise RuntimeError("copy batch rowset changed")


async def _execute_copy(args: argparse.Namespace) -> dict[str, Any]:
    execution_started = time.perf_counter()
    config = _load_secure_config(Path(args.config))
    validate_local_copy_execution(config)
    transport = _r2_transport(config)
    target = config["target"]
    if target.get("bucket") != BUCKET:
        raise RuntimeError("target is restricted to user-data-prod")
    sources = {str(item["name"]): item for item in config.get("sources", [])}
    if config.get("nas_archive"):
        sources[str(config["nas_archive"].get("name", "verified-nas-receipt"))] = (
            config["nas_archive"]
        )
    max_pool_connections = _resolve_copy_max_pool_connections(
        args.copy_concurrency, args.max_pool_connections
    )
    target_client = None
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        run_id, manifest = await _load_plan(conn, args.plan_sha256, "copy")
        validate_copy_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        if manifest.get("runtime_identity"):
            _validate_runtime_identity(
                manifest["runtime_identity"],
                artifact_digest=args.artifact_digest or "",
                config=config,
            )
        superseded_batches = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status='superseded'""",
                args.plan_sha256,
            )
        )
        if superseded_batches:
            raise RuntimeError("copy plan has been superseded")
        if not bool(getattr(args, "skip_global_preflight", False)):
            await _validate_copy_plan_preflight(
                conn,
                run_id=run_id,
                manifest=manifest,
                plan_sha256=args.plan_sha256,
            )
        if bool(getattr(args, "preflight_only", False)):
            return {
                "preflight": "validated",
                "remaining": int(manifest["count"]),
            }
        copy_shard_count = int(getattr(args, "copy_shard_count", 1))
        copy_shard_index = int(getattr(args, "copy_shard_index", 0))
        if copy_shard_count <= 0 or not 0 <= copy_shard_index < copy_shard_count:
            raise ValueError("copy shard identity is invalid")
        active_batch = await conn.fetchrow(
            """select * from analytics_history_media_migration_plan_batches
                 where plan_sha256=$1 and status<>'completed'
                   and mod(batch_no,$2)=$3
                 order by batch_no limit 1""",
            args.plan_sha256,
            copy_shard_count,
            copy_shard_index,
        )
        if active_batch:
            await _validate_copy_batch_identity(
                conn,
                run_id=run_id,
                plan_sha256=args.plan_sha256,
                batch=dict(active_batch),
            )
        first_ledger_id = int(active_batch["first_ledger_id"]) if active_batch else 0
        last_ledger_id = (
            int(active_batch["last_ledger_id"])
            if active_batch
            else 9_223_372_036_854_775_807
        )
        rows = []
        if active_batch:
            rows = await conn.fetch(
                """select * from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and status in ('copy_required','failed')
                       and id between $4 and $5
                     order by history_id,role,ordinal limit $3""",
                run_id,
                args.plan_sha256,
                args.limit,
                first_ledger_id,
                last_ledger_id,
            )
        selected_targets = list(dict.fromkeys(str(row["target_key"]) for row in rows))
        if selected_targets:
            rows = await conn.fetch(
                """select * from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and status in ('copy_required','failed')
                       and target_key=any($3::text[])
                     order by target_key,id""",
                run_id,
                args.plan_sha256,
                selected_targets,
            )
        groups = group_copy_candidates(rows)
        for group in groups:
            row = group[0]
            source = sources.get(str(row["source_name"]))
            if not source:
                raise RuntimeError("planned source is not enabled in this config")
            if (
                str(row["source_name"]) != "r2-user-data-prod"
                or source.get("type", "s3") != "s3"
                or source.get("bucket") != BUCKET
                or str(source.get("endpoint", "")).rstrip("/")
                != str(target.get("endpoint", "")).rstrip("/")
            ):
                raise RuntimeError(
                    "copy plan source is not eligible for same-R2 server-side copy"
                )

        bulk_executor = getattr(args, "bulk_executor", None)
        retry_executor = getattr(args, "retry_executor", None)
        concurrency_limiter = getattr(args, "concurrency_limiter", None)
        external_retry_lane = (
            bulk_executor is not None
            or retry_executor is not None
            or concurrency_limiter is not None
        )
        if external_retry_lane and not all(
            value is not None
            for value in (bulk_executor, retry_executor, concurrency_limiter)
        ):
            raise RuntimeError("copy retry lane dependencies are incomplete")

        _validate_r2_transport_runtime(transport)
        target_client = _s3_client(
            target,
            max_pool_connections=max_pool_connections,
            transport=transport,
            external_retry_lane=external_retry_lane,
        )

        copied_objects = 0
        copied_rows = 0
        recovered_objects = 0
        retried_objects = 0
        exhausted_transient_objects = 0
        r2_operation_latencies_ms: list[float] = []
        db_commit_latencies_ms: list[float] = []
        copy_request_events: list[dict[str, Any]] = []
        object_circuit = CopyObjectCircuitBreaker()
        copy_started = time.perf_counter()
        scheduling_window = max(args.copy_concurrency * 4, 256)

        def copy_one(group: list[dict[str, Any]]) -> dict[str, Any]:
            return _timed_server_side_copy_with_retries(
                target_client,
                max_retries=int(getattr(args, "object_max_retries", 5)),
                retry_base_seconds=float(getattr(args, "retry_base_seconds", 1.0)),
                retry_max_seconds=float(getattr(args, "retry_max_seconds", 16.0)),
                retry_jitter_ratio=float(getattr(args, "retry_jitter_ratio", 0.25)),
                bucket=BUCKET,
                source_key=str(group[0]["source_key"]),
                target_key=str(group[0]["target_key"]),
                expected_size=int(group[0]["byte_size"]),
                expected_last_modified=group[0]["source_last_modified"],
                expected_etag=group[0]["source_etag"],
                copy_plan_sha256=args.plan_sha256,
            )

        def copy_one_attempt(group: list[dict[str, Any]]) -> dict[str, Any]:
            return _timed_server_side_copy_attempt(
                target_client,
                concurrency_limiter=args.concurrency_limiter,
                rate_limit_cooldown_seconds=float(
                    getattr(args, "rate_limit_cooldown_seconds", 60.0)
                ),
                bucket=BUCKET,
                source_key=str(group[0]["source_key"]),
                target_key=str(group[0]["target_key"]),
                expected_size=int(group[0]["byte_size"]),
                expected_last_modified=group[0]["source_last_modified"],
                expected_etag=group[0]["source_etag"],
                copy_plan_sha256=args.plan_sha256,
            )

        async def persist_success(
            group: list[dict[str, Any]], outcome: dict[str, Any]
        ) -> None:
            db_started = time.perf_counter()
            await _persist_copy_success(
                conn,
                group,
                outcome,
                copy_plan_sha256=args.plan_sha256,
            )
            db_commit_latencies_ms.append((time.perf_counter() - db_started) * 1000)

        async def persist_failure(
            group: list[dict[str, Any]], exc: BaseException
        ) -> None:
            db_started = time.perf_counter()
            await _persist_copy_failure(
                conn,
                group,
                exc,
                copy_plan_sha256=args.plan_sha256,
            )
            db_commit_latencies_ms.append((time.perf_counter() - db_started) * 1000)

        if external_retry_lane:
            result = await _run_copy_group_batch_with_retry_lane(
                groups,
                bulk_executor=bulk_executor,
                retry_executor=retry_executor,
                concurrency_limiter=concurrency_limiter,
                copy_one_attempt=copy_one_attempt,
                persist_success=persist_success,
                persist_failure=persist_failure,
                max_retries=int(getattr(args, "object_max_retries", 5)),
                retry_base_seconds=float(getattr(args, "retry_base_seconds", 1.0)),
                retry_max_seconds=float(getattr(args, "retry_max_seconds", 16.0)),
                retry_jitter_ratio=float(getattr(args, "retry_jitter_ratio", 0.25)),
                max_bulk_in_flight=args.copy_concurrency,
                object_circuit=object_circuit,
                request_event_sink=getattr(args, "request_event_sink", None),
            )
        else:
            with ThreadPoolExecutor(max_workers=args.copy_concurrency) as copy_executor:
                result = await _run_copy_group_batch(
                    groups,
                    executor=copy_executor,
                    copy_one=copy_one,
                    persist_success=persist_success,
                    persist_failure=persist_failure,
                    max_in_flight=scheduling_window,
                    object_circuit=object_circuit,
                )
        copied_objects += int(result["copied_objects"])
        copied_rows += int(result["copied_rows"])
        recovered_objects += int(result["recovered_objects"])
        retried_objects += int(result.get("retried_objects", 0))
        exhausted_transient_objects += int(result["exhausted_transient_objects"])
        r2_operation_latencies_ms.extend(result["operation_latencies_ms"])
        copy_request_events.extend(result["request_events"])
        copy_elapsed_seconds = time.perf_counter() - copy_started
        remaining = int(
            await conn.fetchval(
                """select count(*) from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and status in ('copy_required','failed')""",
                run_id,
                args.plan_sha256,
            )
        )
        if active_batch:
            batch_remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations
                         where run_id=$1 and copy_plan_sha256=$2
                           and id between $3 and $4
                           and status in ('copy_required','failed')""",
                    run_id,
                    args.plan_sha256,
                    first_ledger_id,
                    last_ledger_id,
                )
            )
            if batch_remaining == 0:
                await conn.execute(
                    """update analytics_history_media_migration_plan_batches set
                         status='completed',started_at=coalesce(started_at,now()),
                         completed_at=now(),outcome_counts=$3::jsonb,updated_at=now()
                       where plan_sha256=$1 and batch_no=$2""",
                    args.plan_sha256,
                    int(active_batch["batch_no"]),
                    json.dumps({"copied_verified": int(active_batch["asset_count"])}),
                )
        summary = {
            "run_id": str(run_id),
            "copied": copied_rows,
            "copied_objects": copied_objects,
            "recovered_objects": recovered_objects,
            "retried_objects": retried_objects,
            "exhausted_transient_objects": exhausted_transient_objects,
            "remaining": remaining,
            "copy_concurrency": int(
                getattr(args, "global_copy_concurrency", args.copy_concurrency)
            ),
            "max_pool_connections": int(
                getattr(args, "global_max_pool_connections", max_pool_connections)
            ),
            "lane_copy_concurrency": args.copy_concurrency,
            "lane_max_pool_connections": max_pool_connections,
            "r2_transport": transport.identity(),
            "copy_elapsed_seconds": round(copy_elapsed_seconds, 3),
            "total_elapsed_seconds": round(time.perf_counter() - execution_started, 3),
            "copy_objects_per_second": round(
                (
                    copied_objects / copy_elapsed_seconds
                    if copy_elapsed_seconds > 0
                    else 0.0
                ),
                3,
            ),
            "r2_object_operation_latency_ms": _latency_summary(
                r2_operation_latencies_ms
            ),
            "db_commit_latency_ms": _latency_summary(db_commit_latencies_ms),
            "copy_request_count": len(copy_request_events),
            "copy_request_error_count": sum(
                event["kind"] != "ok" for event in copy_request_events
            ),
            "_copy_request_events": copy_request_events,
            "shard_complete": active_batch is None,
            "copy_shard_count": copy_shard_count,
            "copy_shard_index": copy_shard_index,
        }
        print(
            json.dumps(
                {
                    key: value
                    for key, value in summary.items()
                    if not key.startswith("_")
                }
            )
        )
        if (
            remaining == 0
            and bool(getattr(args, "finalize_plan", True))
            and manifest.get("schema")
            in {
                "allbot-history-media-r2-copy-plan/v2",
                "allbot-history-media-r2-copy-plan/v3",
            }
        ):
            verified_copy_chain = copy_plan_chain_sha256s(manifest)
            verification = await _verify_copy_plan_objects(
                conn,
                run_id=run_id,
                plan_sha256=args.plan_sha256,
                copy_plan_sha256s=verified_copy_chain,
                client=target_client,
                concurrency=args.copy_concurrency,
            )
            verification_receipt = {
                "schema": "allbot-history-media-r2-copy-verification/v1",
                "run_id": str(run_id),
                "copy_plan_sha256": args.plan_sha256,
                "copy_chain_plan_sha256s": list(verified_copy_chain),
                "copy_chain_sha256": _sha256_json(list(verified_copy_chain)),
                **verification,
                "old_sources_retained": verification["verified_objects"],
                "target_markers_verified": verification["verified_objects"],
            }
            receipt_path = (
                Path(args.verification_output)
                if getattr(args, "verification_output", None)
                else _default_receipt_output("copy-verification", args.plan_sha256)
            )
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_payload = _canonical_json(verification_receipt) + b"\n"
            receipt_path.write_bytes(receipt_payload)
            os.chmod(receipt_path, 0o600)
            print(
                json.dumps(
                    {
                        "copy_verification_receipt": str(receipt_path),
                        "receipt_sha256": hashlib.sha256(receipt_payload).hexdigest(),
                        **verification,
                    }
                )
            )
            await _create_plan(
                SimpleNamespace(
                    run_id=str(run_id),
                    parent_plan_sha256=args.plan_sha256,
                    artifact_digest=args.artifact_digest,
                    output=str(
                        Path(args.next_plan_output)
                        if getattr(args, "next_plan_output", None)
                        else _default_next_plan_output("switch", args.plan_sha256)
                    ),
                ),
                plan_type="switch",
            )
        return summary
    finally:
        await conn.close()
        if target_client is not None:
            target_client.close()


def _replace_extra_path(
    value: Any, target_ordinal: int, replacement: str
) -> tuple[Any, int]:
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


def replace_asset_reference(
    history: dict[str, Any], role: str, ordinal: int, target: str
) -> None:
    if role == "input":
        refs = [
            item.strip()
            for item in str(history.get("input_file") or "").split("|")
            if item.strip()
        ]
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


async def _verify_switch_plan(
    ledger: asyncpg.Connection,
    production: asyncpg.Connection,
    *,
    run_id: uuid.UUID,
    plan_sha256: str,
) -> dict[str, Any]:
    batches = await ledger.fetch(
        """select first_history_id,last_history_id
             from analytics_history_media_migration_plan_batches
            where plan_sha256=$1 order by batch_no""",
        plan_sha256,
    )
    verified_assets = 0
    verified_histories = 0
    owner_samples: list[dict[str, Any]] = []
    gallery_samples: list[dict[str, Any]] = []
    for batch in batches:
        assets = [
            dict(row)
            for row in await ledger.fetch(
                """select history_id,role,ordinal,target_key
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and switch_plan_sha256=$2
                      and history_id between $3 and $4
                    order by history_id,role,ordinal""",
                run_id,
                plan_sha256,
                int(batch["first_history_id"]),
                int(batch["last_history_id"]),
            )
        ]
        history_ids = list(dict.fromkeys(int(row["history_id"]) for row in assets))
        histories = await production.fetch(
            """select id,user_id,task_id,input_file,output_file,extra_outputs
                 from history where id=any($1::integer[]) order by id""",
            history_ids,
        )
        if len(histories) != len(history_ids):
            raise RuntimeError("switch verification History row disappeared")
        expected: dict[int, dict[tuple[str, int], str]] = {}
        for asset in assets:
            expected.setdefault(int(asset["history_id"]), {})[
                (str(asset["role"]), int(asset["ordinal"]))
            ] = str(asset["target_key"])
        for record in histories:
            history_id = int(record["id"])
            actual = _history_record_refs(record)
            for coord, target in expected[history_id].items():
                if actual.get(coord) != target:
                    raise RuntimeError(
                        "switch verification found an old History reference"
                    )
            if len(owner_samples) < 64:
                owner_samples.append(
                    {
                        "history_id": history_id,
                        "user_id": int(record["user_id"]),
                        "task_id": str(record["task_id"]),
                    }
                )
        if history_ids:
            for media_type in ("image", "video"):
                existing = sum(
                    1
                    for sample in gallery_samples
                    if sample.get("media_type") == media_type
                )
                if existing >= 16:
                    continue
                gallery_rows = await production.fetch(
                    """select gp.id post_id,gp.media_type,h.id history_id,
                              h.user_id,h.task_id
                         from gallery_posts gp join history h on h.task_id=gp.task_id
                        where gp.is_active is true and gp.media_type=$2
                          and h.id=any($1::integer[])
                        order by gp.id,h.id limit $3""",
                    history_ids,
                    media_type,
                    16 - existing,
                )
                gallery_samples.extend(dict(row) for row in gallery_rows)
        verified_assets += len(assets)
        verified_histories += len(history_ids)
    if verified_assets and len(owner_samples) < min(64, verified_histories):
        raise RuntimeError("owner verification sample is incomplete")
    if verified_assets and len(gallery_samples) < 32:
        raise RuntimeError("Gallery verification sample is incomplete")
    return {
        "verified_assets": verified_assets,
        "verified_histories": verified_histories,
        "owner_samples": owner_samples,
        "gallery_samples": gallery_samples,
        "gallery_sample_target": 32,
        "owner_sample_target": 64,
        "apply_context_contract": "existing supported payloads; expected unsupported cases remain HTTP 400",
    }


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
        if manifest.get("runtime_identity"):
            _validate_runtime_identity(
                manifest["runtime_identity"],
                artifact_digest=args.artifact_digest or "",
                config=None,
            )
        if manifest.get("schema") != "allbot-history-media-r2-switch-plan/v2":
            raise RuntimeError(
                "legacy switch plans require their original executor artifact"
            )
        rowset_sha, _count, _counts, _bytes, _diagnostics = await _stream_plan_rowset(
            ledger,
            """select id,history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_etag,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256
                     from analytics_history_media_r2_migrations
                 where run_id=$1 and switch_plan_sha256=$2
                   and status='copied_verified'
                 order by history_id,role,ordinal""",
            run_id,
            args.plan_sha256,
        )
        if rowset_sha != manifest["rowset_sha256"]:
            raise RuntimeError("switch plan rowset changed")
        predecessor_count, predecessor_sha = await _predecessor_switch_identity(
            ledger, run_id, excluding=args.plan_sha256
        )
        if (
            predecessor_count != int(manifest["predecessor_switch_plan_count"])
            or predecessor_sha != manifest["predecessor_switch_plans_sha256"]
        ):
            raise RuntimeError("predecessor switch plan identity changed")
        switched = 0
        processed_batches = 0
        while args.max_batches <= 0 or processed_batches < args.max_batches:
            batch = await ledger.fetchrow(
                """select * from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status<>'completed'
                     order by batch_no limit 1""",
                args.plan_sha256,
            )
            if not batch:
                break
            assets = [
                dict(row)
                for row in await ledger.fetch(
                    """select * from analytics_history_media_r2_migrations
                         where run_id=$1 and switch_plan_sha256=$2
                           and status='copied_verified'
                           and history_id between $3 and $4
                         order by history_id,role,ordinal""",
                    run_id,
                    args.plan_sha256,
                    int(batch["first_history_id"]),
                    int(batch["last_history_id"]),
                )
            ]
            if len(assets) != int(batch["asset_count"]) or _sha256_json(
                [_plan_row(row) for row in assets]
            ) != str(batch["rowset_sha256"]):
                raise RuntimeError("switch batch rowset changed")
            history_ids = list(dict.fromkeys(int(row["history_id"]) for row in assets))
            changed_history_ids: list[int] = []
            async with production.transaction():
                await production.execute("set local lock_timeout = '10s'")
                cas_sha, histories, all_assets = await _cas_state_for_histories(
                    production,
                    ledger,
                    run_id=run_id,
                    history_ids=history_ids,
                    switch_plan_sha256=args.plan_sha256,
                    lock_rows=True,
                )
                if cas_sha != str(batch["cas_state_sha256"]):
                    raise RuntimeError("switch batch production CAS state changed")
                for history_id in history_ids:
                    current = histories[history_id]
                    extras = current.get("extra_outputs")
                    if isinstance(extras, str):
                        try:
                            current["extra_outputs"] = json.loads(extras)
                        except json.JSONDecodeError:
                            current["extra_outputs"] = {}
                    selected = [
                        row for row in all_assets[history_id] if row["selected"]
                    ]
                    current_refs = _history_record_refs(current)
                    changed = False
                    for asset in selected:
                        coord = (str(asset["role"]), int(asset["ordinal"]))
                        if current_refs[coord] == str(asset["target_key"]):
                            continue
                        replace_asset_reference(
                            current,
                            coord[0],
                            coord[1],
                            str(asset["target_key"]),
                        )
                        changed = True
                        switched += 1
                    if changed:
                        await production.execute(
                            """update history set input_file=$2,output_file=$3,
                                 extra_outputs=$4::jsonb where id=$1""",
                            history_id,
                            current["input_file"],
                            current["output_file"],
                            json.dumps(current["extra_outputs"]),
                        )
                        changed_history_ids.append(history_id)
            async with ledger.transaction():
                await ledger.execute(
                    """update analytics_history_media_r2_migrations set
                         switch_completed_at=coalesce(switch_completed_at,now()),
                         updated_at=now()
                       where run_id=$1 and switch_plan_sha256=$2
                         and history_id=any($3::integer[])""",
                    run_id,
                    args.plan_sha256,
                    history_ids,
                )
                await ledger.execute(
                    """update analytics_history_media_migration_plan_batches set
                         status='completed',started_at=coalesce(started_at,now()),
                         completed_at=now(),outcome_counts=$3::jsonb,updated_at=now()
                       where plan_sha256=$1 and batch_no=$2""",
                    args.plan_sha256,
                    int(batch["batch_no"]),
                    json.dumps(
                        {
                            "assets": len(assets),
                            "histories": len(history_ids),
                            "histories_updated": len(changed_history_ids),
                        }
                    ),
                )
            processed_batches += 1
        remaining_batches = int(
            await ledger.fetchval(
                """select count(*) from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status<>'completed'""",
                args.plan_sha256,
            )
        )
        verification_receipt_path: str | None = None
        if remaining_batches == 0:
            verification = await _verify_switch_plan(
                ledger,
                production,
                run_id=run_id,
                plan_sha256=args.plan_sha256,
            )
            receipt = {
                "schema": "allbot-history-media-r2-switch-verification/v1",
                "run_id": str(run_id),
                "switch_plan_sha256": args.plan_sha256,
                **verification,
                "old_objects_deleted": 0,
                "shadow_restore_ready": True,
            }
            receipt_path = (
                Path(args.verification_output)
                if args.verification_output
                else _default_receipt_output("switch-verification", args.plan_sha256)
            )
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_payload = _canonical_json(receipt) + b"\n"
            receipt_path.write_bytes(receipt_payload)
            os.chmod(receipt_path, 0o600)
            verification_receipt_path = str(receipt_path)
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "switched": switched,
                    "processed_batches": processed_batches,
                    "remaining_batches": remaining_batches,
                    "verification_receipt": verification_receipt_path,
                }
            )
        )
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
        (
            rowset_sha,
            row_count,
            _counts,
            _bytes,
            _diagnostics,
        ) = await _stream_plan_rowset(
            conn,
            """select history_id,role,ordinal,original_ref,target_key,
                          source_name,source_key,source_last_modified,source_etag,source_sha256,
                          target_sha256,byte_size,status,history_manifest_sha256,error_code
                     from analytics_history_media_r2_migrations where run_id=$1
                     order by history_id,role,ordinal""",
            run_id,
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
        seed_scope = _nondefault_seed_scope(run)
        if seed_scope is not None:
            report["seed_scope"] = seed_scope
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(report) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {"report": str(output), "rowset_sha256": report["rowset_sha256"]}
            )
        )
    finally:
        await conn.close()


def _bounded_copy_concurrency(value: str) -> int:
    concurrency = int(value)
    if not 1 <= concurrency <= 128:
        raise argparse.ArgumentTypeError("copy concurrency must be between 1 and 128")
    return concurrency


def _bounded_copy_retries(value: str) -> int:
    retries = int(value)
    if not 0 <= retries <= 10:
        raise argparse.ArgumentTypeError("object max retries must be between 0 and 10")
    return retries


def _positive_float(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _unit_ratio(value: str) -> float:
    ratio = float(value)
    if not 0 <= ratio <= 1:
        raise argparse.ArgumentTypeError("ratio must be between 0 and 1")
    return ratio


def _positive_pool_connections(value: str) -> int:
    connections = int(value)
    if connections <= 0:
        raise argparse.ArgumentTypeError("max pool connections must be positive")
    return connections


def _resolve_copy_max_pool_connections(
    copy_concurrency: int, configured: int | None
) -> int:
    if not 1 <= copy_concurrency <= 128:
        raise ValueError("copy concurrency must be between 1 and 128")
    connections = (
        configured if configured is not None else (copy_concurrency * 3 + 1) // 2
    )
    if connections < copy_concurrency:
        raise ValueError(
            "max pool connections must not be smaller than copy concurrency"
        )
    return connections


def _resolve_probe_max_pool_connections(concurrency: int) -> int:
    if concurrency not in {8, 16, 32, 64, 128}:
        raise ValueError("Probe concurrency must be 8, 16, 32, 64, or 128")
    return PROBE_MAX_CONCURRENCY


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed")
    seed.add_argument("--history-min-id", type=int)
    seed.add_argument("--history-watermark", type=int)
    seed.add_argument("--history-reference-prefix")
    seed.add_argument(
        "--history-source",
        choices=("local-shadow", "production-read-only"),
    )
    seed.add_argument("--resume-run-id")
    seed.add_argument("--batch-size", type=int, default=1000)
    probe = commands.add_parser("probe")
    probe.add_argument("--run-id", required=True)
    probe.add_argument("--config", required=True)
    probe.add_argument("--limit", type=int, default=1000)
    probe.add_argument("--systemic-error-threshold", type=int, default=5)
    probe_mode = probe.add_mutually_exclusive_group()
    probe_mode.add_argument("--target-only", action="store_true")
    probe_mode.add_argument("--r2-only", action="store_true")
    probe_mode.add_argument("--receipt-only", action="store_true")
    probe_mode.add_argument("--remaining-sources-only", action="store_true")
    probe.add_argument("--target-concurrency", type=int, default=32)
    probe.add_argument("--source-concurrency", type=int, default=32)
    probe.add_argument("--refresh-r2-checkpoint", action="store_true")
    probe.add_argument("--r2-checkpoint-not-before")
    probe.add_argument("--recheck-deferred", action="store_true")
    probe.add_argument("--deferred-min-age-hours", type=int, default=24)
    plan_probe = commands.add_parser("plan-probe")
    plan_probe.add_argument("--run-id", required=True)
    plan_probe.add_argument("--config", required=True)
    plan_probe.add_argument("--artifact-digest", required=True)
    plan_probe.add_argument("--output", required=True)
    successor_probe = commands.add_parser("plan-probe-successor")
    successor_probe.add_argument("--run-id", required=True)
    successor_probe.add_argument("--predecessor-plan-sha256", required=True)
    successor_probe.add_argument("--config", required=True)
    successor_probe.add_argument("--artifact-digest", required=True)
    successor_probe.add_argument("--output", required=True)
    execute_probe = commands.add_parser("execute-probe")
    execute_probe.add_argument("--plan-sha256", required=True)
    execute_probe.add_argument("--confirm", required=True)
    execute_probe.add_argument("--config", required=True)
    execute_probe.add_argument("--artifact-digest", required=True)
    execute_probe.add_argument("--concurrency", type=int, default=64)
    execute_probe.add_argument("--max-retries", type=int, default=5)
    execute_probe.add_argument("--max-batches", type=int, default=0)
    execute_probe.add_argument("--next-plan-output")
    plan_copy = commands.add_parser("plan-copy")
    plan_copy.add_argument("--run-id", required=True)
    plan_copy.add_argument("--parent-plan-sha256", required=True)
    plan_copy.add_argument("--config", required=True)
    plan_copy.add_argument("--artifact-digest", required=True)
    plan_copy.add_argument("--output", required=True)
    plan_copy.add_argument("--supersedes-plan-sha256")
    plan_copy_recovery = commands.add_parser("plan-copy-recovery")
    plan_copy_recovery.add_argument("--run-id", required=True)
    plan_copy_recovery.add_argument("--current-plan-sha256", required=True)
    plan_copy_recovery.add_argument("--config", required=True)
    plan_copy_recovery.add_argument("--artifact-digest", required=True)
    plan_copy_recovery.add_argument("--output", required=True)
    plan_switch = commands.add_parser("plan-switch")
    plan_switch.add_argument("--run-id", required=True)
    plan_switch.add_argument("--parent-plan-sha256", required=True)
    plan_switch.add_argument("--artifact-digest", required=True)
    plan_switch.add_argument("--output", required=True)
    rolling_switch = commands.add_parser("plan-switch-completed")
    rolling_switch.add_argument("--run-id", required=True)
    rolling_switch.add_argument("--parent-plan-sha256", required=True)
    rolling_switch.add_argument("--artifact-digest", required=True)
    rolling_switch.add_argument("--output", required=True)
    rolling_switch.set_defaults(completed_copy_batches_only=True)
    copy = commands.add_parser("execute-copy")
    copy.add_argument("--plan-sha256", required=True)
    copy.add_argument("--confirm", required=True)
    copy.add_argument("--config", required=True)
    copy.add_argument("--artifact-digest")
    copy.add_argument("--limit", type=int, default=1000)
    copy.add_argument("--copy-concurrency", type=_bounded_copy_concurrency, default=1)
    copy.add_argument("--max-pool-connections", type=_positive_pool_connections)
    copy.add_argument("--object-max-retries", type=_bounded_copy_retries, default=5)
    copy.add_argument("--retry-base-seconds", type=_positive_float, default=1.0)
    copy.add_argument("--retry-max-seconds", type=_positive_float, default=16.0)
    copy.add_argument("--retry-jitter-ratio", type=_unit_ratio, default=0.25)
    copy.add_argument("--next-plan-output")
    copy.add_argument("--verification-output")
    copy_recovery = commands.add_parser("execute-copy-recovery")
    copy_recovery.add_argument("--plan-sha256", required=True)
    copy_recovery.add_argument("--confirm", required=True)
    copy_recovery.add_argument("--config", required=True)
    copy_recovery.add_argument("--artifact-digest", required=True)
    copy_recovery.add_argument(
        "--concurrency", type=_bounded_copy_concurrency, default=64
    )
    copy_recovery.add_argument("--receipt-output", required=True)
    copy_recovery.add_argument("--next-plan-output", required=True)
    reconcile_failures = commands.add_parser("reconcile-copy-failures")
    reconcile_failures.add_argument("--run-id", required=True)
    reconcile_failures.add_argument("--plan-sha256", required=True)
    reconcile_failures.add_argument("--config", required=True)
    reconcile_failures.add_argument("--artifact-digest", required=True)
    reconcile_failures.add_argument(
        "--concurrency", type=_bounded_copy_concurrency, default=16
    )
    reconcile_failures.add_argument("--receipt-output", required=True)
    reconcile_failures.add_argument("--next-plan-output", required=True)
    switch = commands.add_parser("execute-switch")
    switch.add_argument("--plan-sha256", required=True)
    switch.add_argument("--confirm", required=True)
    switch.add_argument("--artifact-digest")
    switch.add_argument("--max-batches", type=int, default=0)
    switch.add_argument("--verification-output")
    report = commands.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--output", required=True)
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "seed":
        await _seed(args)
    elif args.command == "probe":
        await _probe(args)
    elif args.command == "plan-probe":
        await _create_probe_plan(args)
    elif args.command == "plan-probe-successor":
        await _create_successor_probe_plan(args)
    elif args.command == "execute-probe":
        await _execute_probe(args)
    elif args.command == "plan-copy":
        await _create_plan(args, plan_type="copy")
    elif args.command == "plan-copy-recovery":
        await _create_copy_predecessor_recovery_plan(args)
    elif args.command == "execute-copy":
        await _execute_copy(args)
    elif args.command == "execute-copy-recovery":
        await _execute_copy_predecessor_recovery(args)
    elif args.command == "reconcile-copy-failures":
        await _reconcile_failed_copy_and_plan_successor(args)
    elif args.command in {"plan-switch", "plan-switch-completed"}:
        await _create_plan(args, plan_type="switch")
    elif args.command == "execute-switch":
        await _execute_switch(args)
    elif args.command == "report":
        await _report(args)


def main() -> None:
    asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    main()
