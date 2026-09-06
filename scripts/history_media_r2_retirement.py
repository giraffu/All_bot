#!/usr/bin/env python3
"""Freeze and execute deletion of fully archived, unreferenced History R2 old sources."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import stat
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import asyncpg
import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.history_media_r2_migration import (  # noqa: E402
    R2Transport,
    _canonical_json,
    _load_secure_config,
    _r2_transport,
    _runtime_identity,
    _validate_r2_transport_runtime,
    normalize_asyncpg_dsn,
)
from scripts.media_archive_worker import (  # noqa: E402
    clear_proxy_environment,
    validate_endpoint_route,
)

RETIREMENT_BATCH_SIZE = 1000
MAX_DELETE_CONCURRENCY = 8
MAX_RETIREMENT_HEAD_CONCURRENCY = 128
DEFAULT_RETIREMENT_HEAD_CONCURRENCY = 128
DEFAULT_RETIREMENT_DELETE_CONCURRENCY = 4
RETIREMENT_EXECUTION_SCHEDULER = "persistent-context-bulk-delete-v3"
RETIREMENT_HEAD_CONCURRENCY_LEVELS = (128, 64, 32)
RETIREMENT_HEAD_MINIMUM_SAMPLES = 200
RETIREMENT_HEAD_LOWER_ERROR_RATE = 0.005
RETIREMENT_HEAD_RAISE_ERROR_RATE = 0.002
RETIREMENT_HEAD_SYSTEMIC_ERROR_RATE = 0.10
RETIREMENT_HEAD_HEALTHY_WINDOWS_TO_RAISE = 2
RETIREMENT_HEAD_RETRY_ATTEMPTS = 5
RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE = 250
RETIREMENT_DELETE_RETRY_ATTEMPTS = 5
DURABILITY_NAS_ARCHIVE = "nas-archive"
DURABILITY_R2_PERSISTENT_TARGET = "r2-persistent-target"
DURABILITY_BASES = (DURABILITY_NAS_ARCHIVE, DURABILITY_R2_PERSISTENT_TARGET)
BULK_SOURCE_IDENTITY_POLICY = "etag-or-size-last-modified"
BULK_RETIREMENT_DISPOSITIONS = (
    "eligible",
    "deferred",
    "retained_target",
)


@dataclass(frozen=True)
class RetirementHeadConcurrencyDecision:
    action: str
    reason: str
    previous_concurrency: int
    current_concurrency: int
    error_rate: float
    request_count: int


class RetirementHeadConcurrencyController:
    """Keep occasional HEAD failures local while adapting to sustained pressure."""

    def __init__(self, *, initial_concurrency: int) -> None:
        if not 1 <= initial_concurrency <= MAX_RETIREMENT_HEAD_CONCURRENCY:
            raise ValueError("retirement HEAD concurrency is out of range")
        self.maximum_concurrency = int(initial_concurrency)
        adaptive_levels = tuple(
            level for level in RETIREMENT_HEAD_CONCURRENCY_LEVELS
            if level <= self.maximum_concurrency
        )
        self.levels = (
            adaptive_levels
            if self.maximum_concurrency in adaptive_levels
            else (self.maximum_concurrency,)
        )
        self.current_concurrency = self.maximum_concurrency
        self._healthy_windows = 0

    def observe(
        self,
        *,
        request_count: int,
        transient_error_count: int,
        rate_limit_count: int,
    ) -> RetirementHeadConcurrencyDecision:
        if request_count <= 0:
            raise ValueError("retirement HEAD observation requires requests")
        if not 0 <= rate_limit_count <= transient_error_count <= request_count:
            raise ValueError("retirement HEAD error counts are invalid")
        previous = self.current_concurrency
        error_rate = transient_error_count / request_count
        action = "hold"
        reason = "within_error_budget"
        observation_ready = request_count >= RETIREMENT_HEAD_MINIMUM_SAMPLES

        if (
            observation_ready
            and error_rate >= RETIREMENT_HEAD_SYSTEMIC_ERROR_RATE
        ):
            action = "systemic"
            reason = "systemic_transient_error_rate"
            self._healthy_windows = 0
        elif rate_limit_count:
            self._healthy_windows = 0
            index = self.levels.index(self.current_concurrency)
            if index + 1 < len(self.levels):
                self.current_concurrency = self.levels[index + 1]
                action = "lower"
            reason = "rate_limit"
        elif observation_ready and error_rate > RETIREMENT_HEAD_LOWER_ERROR_RATE:
            self._healthy_windows = 0
            index = self.levels.index(self.current_concurrency)
            if index + 1 < len(self.levels):
                self.current_concurrency = self.levels[index + 1]
                action = "lower"
            reason = "sustained_transient_error_rate"
        elif observation_ready and error_rate < RETIREMENT_HEAD_RAISE_ERROR_RATE:
            self._healthy_windows += 1
            index = self.levels.index(self.current_concurrency)
            if (
                self._healthy_windows >= RETIREMENT_HEAD_HEALTHY_WINDOWS_TO_RAISE
                and index > 0
            ):
                self.current_concurrency = self.levels[index - 1]
                self._healthy_windows = 0
                action = "raise"
                reason = "healthy_request_windows"
            else:
                reason = "building_healthy_request_windows"
        else:
            self._healthy_windows = 0

        return RetirementHeadConcurrencyDecision(
            action=action,
            reason=reason,
            previous_concurrency=previous,
            current_concurrency=self.current_concurrency,
            error_rate=error_rate,
            request_count=request_count,
        )


class RetirementRequestExecutors:
    """Own the bounded request pools used for the complete retirement run."""

    def __init__(self, *, head_concurrency: int, delete_concurrency: int) -> None:
        if not 1 <= head_concurrency <= MAX_RETIREMENT_HEAD_CONCURRENCY:
            raise ValueError("retirement HEAD concurrency is out of range")
        if not 1 <= delete_concurrency <= MAX_DELETE_CONCURRENCY:
            raise ValueError("retirement delete concurrency is out of range")
        self.head_executor = ThreadPoolExecutor(
            max_workers=head_concurrency,
            thread_name_prefix="history-r2-retirement-head",
        )
        self.delete_executor = ThreadPoolExecutor(
            max_workers=delete_concurrency,
            thread_name_prefix="history-r2-retirement-delete",
        )
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.head_executor.shutdown(wait=True, cancel_futures=True)
        self.delete_executor.shutdown(wait=True, cancel_futures=True)


def _retirement_head_controller(
    args: argparse.Namespace, *, configured_concurrency: int
) -> RetirementHeadConcurrencyController:
    existing = getattr(args, "_retirement_head_concurrency_controller", None)
    if existing is None:
        existing = RetirementHeadConcurrencyController(
            initial_concurrency=configured_concurrency
        )
        setattr(args, "_retirement_head_concurrency_controller", existing)
    if existing.maximum_concurrency != configured_concurrency:
        raise RuntimeError("retirement HEAD controller maximum changed")
    return existing
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
alter table analytics_history_media_r2_retirement_batches
  add column if not exists disposition text not null default 'eligible';
alter table analytics_history_media_r2_retirement_batches
  add column if not exists is_retained boolean not null default false;
alter table analytics_history_media_r2_retirement_objects
  add column if not exists scope_asset_count integer not null default 0;
alter table analytics_history_media_r2_retirement_objects
  add column if not exists scope_facts jsonb not null default '{}'::jsonb;
alter table analytics_history_media_r2_retirement_objects
  add column if not exists retirement_disposition text not null default 'eligible';
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


def _exact_source_identity_hashes(values: Iterable[str]) -> list[str]:
    raw = [str(value) for value in values]
    exact = sorted(set(raw))
    if len(exact) != len(raw) or any(
        len(value) != 64
        or value.lower() != value
        or any(character not in "0123456789abcdef" for character in value)
        for value in exact
    ):
        raise ValueError("target identity drift source SHA-256 values are invalid")
    return exact


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
                "retirement_disposition": str(
                    candidate.get("retirement_disposition") or "eligible"
                ),
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
    deferred_live_history_ref_object_count: int = 0,
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

    frozen = [dict(item) for item in objects]
    for candidate in frozen:
        disposition = str(candidate.get("retirement_disposition") or "eligible")
        if disposition not in BULK_RETIREMENT_DISPOSITIONS:
            raise RuntimeError("bulk retirement object disposition is invalid")
        candidate["retirement_disposition"] = disposition
    disposition_rank = {
        disposition: rank
        for rank, disposition in enumerate(BULK_RETIREMENT_DISPOSITIONS)
    }
    frozen.sort(
        key=lambda item: (
            disposition_rank[str(item["retirement_disposition"])],
            -int(item["byte_size"]),
            _key_sha(str(item["source_name"]), str(item["source_key"])),
        )
    )
    keys = [(str(item["source_name"]), str(item["source_key"])) for item in frozen]
    if not frozen:
        raise RuntimeError("bulk retirement plan has no old sources")
    if not any(
        item["retirement_disposition"] == "eligible" for item in frozen
    ):
        raise RuntimeError("bulk retirement plan has no immediately eligible old sources")
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
    batch_no = 0
    for disposition in BULK_RETIREMENT_DISPOSITIONS:
        indexes = [
            index
            for index, item in enumerate(frozen)
            if item["retirement_disposition"] == disposition
        ]
        offset = 0
        while offset < len(indexes):
            size = (
                canary_size
                if disposition == "eligible" and offset == 0
                else batch_size
            )
            subset_indexes = indexes[offset : offset + size]
            subset = [frozen[index] for index in subset_indexes]
            subset_identities = [identities[index] for index in subset_indexes]
            is_canary = disposition == "eligible" and offset == 0
            is_retained = disposition == "retained_target"
            batches.append(
                {
                    "batch_no": batch_no,
                    "is_canary": is_canary,
                    "disposition": disposition,
                    "is_retained": is_retained,
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
        "schema": "allbot-history-media-r2-bulk-retirement-plan/v2",
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
        "deferred_live_history_ref_object_count": int(
            deferred_live_history_ref_object_count
        ),
        "object_count": len(frozen),
        "total_bytes": sum(int(item["byte_size"]) for item in frozen),
        "canary_object_count": min(
            canary_size,
            sum(
                item["retirement_disposition"] == "eligible" for item in frozen
            ),
        ),
        "batch_count": len(batches),
        "batch_size": batch_size,
        "rowset_sha256": _sha256_json(identities),
        "batches_sha256": _sha256_json(batches),
        "one_confirmation_covers_all_batches": True,
        "object_keys_redacted": True,
        "runtime_identity": dict(runtime_identity),
    }
    for disposition in BULK_RETIREMENT_DISPOSITIONS:
        manifest[f"{disposition}_object_count"] = sum(
            item["retirement_disposition"] == disposition for item in frozen
        )
        manifest[f"{disposition}_asset_coordinate_count"] = sum(
            int(item["scope_asset_count"])
            for item in frozen
            if item["retirement_disposition"] == disposition
        )
    if not 0 <= deferred_live_history_ref_object_count <= manifest[
        "deferred_object_count"
    ]:
        raise RuntimeError("bulk retirement live reference count is inconsistent")
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest, frozen, batches


def build_bulk_retirement_successor_manifest(
    *,
    predecessor_manifest: dict[str, Any],
    predecessor_plan_sha256: str,
    predecessor_completed_batches_sha256: str,
    predecessor_retained_object_count: int,
    predecessor_retained_asset_coordinate_count: int,
    predecessor_quarantined_object_count: int,
    predecessor_quarantined_asset_coordinate_count: int,
    predecessor_quarantined_rowset_sha256: str,
    predecessor_quarantined_evidence_sha256: str,
    predecessor_live_reference_retained_object_count: int,
    predecessor_live_reference_retained_asset_coordinate_count: int,
    predecessor_live_reference_retained_rowset_sha256: str,
    remaining_object_count: int,
    remaining_asset_coordinate_count: int,
    remaining_total_bytes: int,
    remaining_rowset_sha256: str,
    batches: list[dict[str, Any]],
    disposition_summary: dict[str, dict[str, int]],
    runtime_identity: dict[str, Any],
) -> dict[str, Any]:
    if predecessor_manifest.get("execution_mode") != "bulk":
        raise RuntimeError("bulk retirement successor requires a bulk predecessor")
    root_object_count = int(
        predecessor_manifest.get("root_object_count")
        or predecessor_manifest["object_count"]
    )
    root_asset_count = int(
        predecessor_manifest.get("root_asset_coordinate_count")
        or predecessor_manifest["asset_coordinate_count"]
    )
    if (
        int(predecessor_retained_object_count) + int(remaining_object_count)
        != root_object_count
    ):
        raise RuntimeError("bulk retirement successor object conservation failed")
    if (
        int(predecessor_retained_asset_coordinate_count)
        + int(remaining_asset_coordinate_count)
        != root_asset_count
    ):
        raise RuntimeError("bulk retirement successor asset conservation failed")
    if remaining_object_count < 1 or not batches:
        raise RuntimeError("bulk retirement successor has no remaining objects")
    if len(predecessor_completed_batches_sha256) != 64:
        raise RuntimeError("bulk retirement predecessor batch proof is invalid")
    if (
        predecessor_quarantined_object_count < 0
        or predecessor_quarantined_asset_coordinate_count < 0
        or predecessor_quarantined_object_count > predecessor_retained_object_count
        or predecessor_quarantined_asset_coordinate_count
        > predecessor_retained_asset_coordinate_count
        or len(predecessor_quarantined_rowset_sha256) != 64
        or len(predecessor_quarantined_evidence_sha256) != 64
    ):
        raise RuntimeError("bulk retirement predecessor quarantine proof is invalid")
    empty_proof = _sha256_json([])
    if not predecessor_quarantined_object_count and (
        predecessor_quarantined_asset_coordinate_count
        or predecessor_quarantined_rowset_sha256 != empty_proof
        or predecessor_quarantined_evidence_sha256 != empty_proof
    ):
        raise RuntimeError("bulk retirement empty quarantine proof is invalid")
    if (
        predecessor_live_reference_retained_object_count < 0
        or predecessor_live_reference_retained_asset_coordinate_count < 0
        or predecessor_live_reference_retained_object_count
        > predecessor_retained_object_count
        or predecessor_live_reference_retained_asset_coordinate_count
        > predecessor_retained_asset_coordinate_count
        or len(predecessor_live_reference_retained_rowset_sha256) != 64
    ):
        raise RuntimeError("bulk retirement live reference proof is invalid")
    if not predecessor_live_reference_retained_object_count and (
        predecessor_live_reference_retained_asset_coordinate_count
        or predecessor_live_reference_retained_rowset_sha256 != empty_proof
    ):
        raise RuntimeError("bulk retirement empty live reference proof is invalid")

    manifest: dict[str, Any] = {
        "schema": "allbot-history-media-r2-bulk-retirement-plan/v5",
        "execution_mode": "bulk",
        "durability_basis": DURABILITY_R2_PERSISTENT_TARGET,
        "run_id": str(predecessor_manifest["run_id"]),
        "parent_copy_plan_sha256s": list(
            predecessor_manifest["parent_copy_plan_sha256s"]
        ),
        "parent_switch_plan_sha256s": list(
            predecessor_manifest["parent_switch_plan_sha256s"]
        ),
        "switch_scopes": list(predecessor_manifest["switch_scopes"]),
        "asset_coordinate_count": int(remaining_asset_coordinate_count),
        "root_asset_coordinate_count": root_asset_count,
        "asset_scope_sha256": str(predecessor_manifest["asset_scope_sha256"]),
        "asset_scope_algorithm": str(
            predecessor_manifest["asset_scope_algorithm"]
        ),
        "source_identity_policy": str(
            predecessor_manifest["source_identity_policy"]
        ),
        "predecessor_plan_sha256": str(predecessor_plan_sha256),
        "predecessor_completed_batches_sha256": str(
            predecessor_completed_batches_sha256
        ),
        "predecessor_retained_object_count": int(
            predecessor_retained_object_count
        ),
        "predecessor_retained_asset_coordinate_count": int(
            predecessor_retained_asset_coordinate_count
        ),
        "predecessor_quarantined_object_count": int(
            predecessor_quarantined_object_count
        ),
        "predecessor_quarantined_asset_coordinate_count": int(
            predecessor_quarantined_asset_coordinate_count
        ),
        "predecessor_quarantined_rowset_sha256": str(
            predecessor_quarantined_rowset_sha256
        ),
        "predecessor_quarantined_evidence_sha256": str(
            predecessor_quarantined_evidence_sha256
        ),
        "predecessor_live_reference_retained_object_count": int(
            predecessor_live_reference_retained_object_count
        ),
        "predecessor_live_reference_retained_asset_coordinate_count": int(
            predecessor_live_reference_retained_asset_coordinate_count
        ),
        "predecessor_live_reference_retained_rowset_sha256": str(
            predecessor_live_reference_retained_rowset_sha256
        ),
        "root_object_count": root_object_count,
        "object_count": int(remaining_object_count),
        "total_bytes": int(remaining_total_bytes),
        "canary_object_count": int(batches[0]["object_count"]),
        "batch_count": len(batches),
        "batch_size": int(predecessor_manifest.get("batch_size") or 1000),
        "rowset_sha256": str(remaining_rowset_sha256),
        "batches_sha256": _sha256_json(batches),
        "one_confirmation_covers_all_batches": True,
        "object_keys_redacted": True,
        "runtime_identity": dict(runtime_identity),
    }
    for disposition in BULK_RETIREMENT_DISPOSITIONS:
        summary = disposition_summary.get(
            disposition, {"object_count": 0, "asset_coordinate_count": 0}
        )
        manifest[f"{disposition}_object_count"] = int(summary["object_count"])
        manifest[f"{disposition}_asset_coordinate_count"] = int(
            summary["asset_coordinate_count"]
        )
    if manifest["retained_target_object_count"]:
        raise RuntimeError("retained targets must stay with the predecessor plan")
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


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
    _validate_retirement_source_head(candidate, source_head=source_head)
    validate_retirement_survivor_heads(
        candidate, target_heads=target_heads, nas_head=nas_head
    )


def _validate_retirement_source_head(
    candidate: dict[str, Any], *, source_head: dict[str, Any] | None
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


def validate_retirement_target_identity_drift(
    candidate: dict[str, Any],
    *,
    source_head: dict[str, Any] | None,
    target_heads: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    """Prove a target identity drift without weakening normal delete gates."""

    _validate_retirement_source_head(candidate, source_head=source_head)
    marker_drift_count = 0
    etag_drift_count = 0
    drifted_target_count = 0
    for target in candidate["targets"]:
        key = str(target["target_key"])
        if key == str(candidate["source_key"]):
            raise RuntimeError("old source is also a standard target")
        head = target_heads.get(key)
        if head is None:
            raise RuntimeError("verified target is missing")
        if int(head.get("ContentLength") or -1) != int(candidate["byte_size"]):
            raise RuntimeError("verified target size changed")
        marker = str(
            (head.get("Metadata") or {}).get("allbot-copy-plan-sha256") or ""
        )
        marker_drifted = marker != str(target["copy_plan_sha256"])
        if marker_drifted:
            marker_drift_count += 1
        expected_etag = str(target.get("target_etag") or "")
        etag_drifted = bool(expected_etag) and _strip_etag(
            head.get("ETag")
        ) != _strip_etag(
            expected_etag
        )
        if etag_drifted:
            etag_drift_count += 1
        if marker_drifted or etag_drifted:
            drifted_target_count += 1
    if not drifted_target_count:
        raise RuntimeError("verified target does not show identity drift")
    return {
        "drifted_target_count": drifted_target_count,
        "marker_drift_count": marker_drift_count,
        "etag_drift_count": etag_drift_count,
        "target_facts_sha256": _sha256_json(candidate["targets"]),
    }


async def _head_target_identity_drift_candidates(
    candidates: list[dict[str, Any]],
    *,
    r2_client: Any,
    r2_bucket: str,
    concurrency: int,
    executor: ThreadPoolExecutor,
) -> list[dict[str, Any]]:
    request_funcs: list[Callable[[], Any]] = []
    source_indexes: list[int] = []
    target_indexes: list[dict[str, int]] = []
    for candidate in candidates:
        source_indexes.append(len(request_funcs))
        request_funcs.append(
            partial(
                r2_client.head_object,
                Bucket=r2_bucket,
                Key=str(candidate["source_key"]),
            )
        )
        indexes: dict[str, int] = {}
        for target in candidate["targets"]:
            key = str(target["target_key"])
            indexes[key] = len(request_funcs)
            request_funcs.append(
                partial(r2_client.head_object, Bucket=r2_bucket, Key=key)
            )
        target_indexes.append(indexes)
    controller = RetirementHeadConcurrencyController(
        initial_concurrency=concurrency
    )
    results, _ = await _run_retirement_head_requests(
        request_funcs,
        controller=controller,
        retry_sleep=asyncio.sleep,
        executor=executor,
    )
    try:
        evidence: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            target_heads = {
                key: results[result_index]
                for key, result_index in target_indexes[index].items()
            }
            evidence.append(
                validate_retirement_target_identity_drift(
                    candidate,
                    source_head=results[source_indexes[index]],
                    target_heads=target_heads,
                )
            )
        return evidence
    finally:
        results.clear()


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


def _s3_client(
    config: dict[str, Any],
    *,
    max_connections: int,
    transport: R2Transport | None = None,
) -> Any:
    selected_transport = transport or R2Transport(mode="direct")
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
            proxies=(
                {"https": selected_transport.proxy_url}
                if selected_transport.mode == "https_proxy"
                else {}
            ),
        ),
    )


@dataclass
class RetirementExecutionContext:
    ledger: asyncpg.Connection
    production: asyncpg.Connection
    r2_config: dict[str, Any]
    archive_config: dict[str, Any] | None
    r2_client: Any
    nas_client: Any | None
    head_controller: RetirementHeadConcurrencyController
    requests: RetirementRequestExecutors
    head_concurrency: int
    delete_concurrency: int

    async def reconnect_production(self) -> None:
        try:
            await self.production.close()
        except Exception:
            pass
        self.production = await _connect("PRODUCTION_DATABASE_URL")

    async def close(self) -> None:
        try:
            await self.production.close()
        finally:
            try:
                await self.ledger.close()
            finally:
                self.requests.close()
                self.r2_client.close()
                if self.nas_client is not None:
                    self.nas_client.close()


async def _open_retirement_execution_context(
    args: argparse.Namespace,
) -> RetirementExecutionContext:
    r2_config = _load_secure_config(Path(args.config))
    archive_config = _durability_archive_config(
        args.durability_basis, args.archive_config
    )
    clear_proxy_environment()
    r2_transport = _r2_transport(r2_config)
    _validate_r2_transport_runtime(r2_transport)
    validate_endpoint_route(r2_config["target"])
    if archive_config is not None:
        validate_endpoint_route(archive_config["nas"])
    head_concurrency = int(
        getattr(args, "head_concurrency", args.delete_concurrency)
    )
    connection_pool_size = max(head_concurrency, args.delete_concurrency)
    requests = RetirementRequestExecutors(
        head_concurrency=head_concurrency,
        delete_concurrency=args.delete_concurrency,
    )
    ledger: asyncpg.Connection | None = None
    production: asyncpg.Connection | None = None
    r2_client: Any | None = None
    nas_client: Any | None = None
    try:
        ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
        production = await _connect("PRODUCTION_DATABASE_URL")
        r2_client = _s3_client(
            r2_config["target"],
            max_connections=connection_pool_size,
            transport=r2_transport,
        )
        nas_client = (
            _s3_client(archive_config["nas"], max_connections=connection_pool_size)
            if archive_config is not None
            else None
        )
        return RetirementExecutionContext(
            ledger=ledger,
            production=production,
            r2_config=r2_config,
            archive_config=archive_config,
            r2_client=r2_client,
            nas_client=nas_client,
            head_controller=_retirement_head_controller(
                args, configured_concurrency=head_concurrency
            ),
            requests=requests,
            head_concurrency=head_concurrency,
            delete_concurrency=int(args.delete_concurrency),
        )
    except Exception:
        if production is not None:
            await production.close()
        if ledger is not None:
            await ledger.close()
        requests.close()
        if r2_client is not None:
            r2_client.close()
        if nas_client is not None:
            nas_client.close()
        raise


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
            "retirement_execution_policy": {
                "scheduler": RETIREMENT_EXECUTION_SCHEDULER,
                "head_concurrency": DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
                "head_concurrency_levels": list(
                    RETIREMENT_HEAD_CONCURRENCY_LEVELS
                ),
                "head_retry_attempts": RETIREMENT_HEAD_RETRY_ATTEMPTS,
                "head_lower_error_rate": RETIREMENT_HEAD_LOWER_ERROR_RATE,
                "head_raise_error_rate": RETIREMENT_HEAD_RAISE_ERROR_RATE,
                "head_systemic_error_rate": RETIREMENT_HEAD_SYSTEMIC_ERROR_RATE,
                "head_healthy_windows_to_raise": (
                    RETIREMENT_HEAD_HEALTHY_WINDOWS_TO_RAISE
                ),
                "delete_concurrency": DEFAULT_RETIREMENT_DELETE_CONCURRENCY,
                "delete_api": "DeleteObjects",
                "delete_chunk_size": RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE,
                "delete_retry_attempts": RETIREMENT_DELETE_RETRY_ATTEMPTS,
                "post_delete_verification": "source-head-only-full-batch",
                "request_context_lifecycle": "one-per-bulk-plan",
                "production_reference_retry_attempts": 3,
            },
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


def _validate_retirement_execution_policy(
    manifest: dict[str, Any], args: argparse.Namespace
) -> None:
    policy = dict(
        manifest["runtime_identity"].get("retirement_execution_policy") or {}
    )
    if not policy:
        return
    if (
        str(policy.get("scheduler") or "") != RETIREMENT_EXECUTION_SCHEDULER
        or int(policy.get("head_concurrency") or 0) != int(args.head_concurrency)
        or int(policy.get("delete_concurrency") or 0)
        != int(args.delete_concurrency)
        or str(policy.get("delete_api") or "") != "DeleteObjects"
        or int(policy.get("delete_chunk_size") or 0)
        != RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE
        or int(policy.get("delete_retry_attempts") or 0)
        != RETIREMENT_DELETE_RETRY_ATTEMPTS
        or str(policy.get("post_delete_verification") or "")
        != "source-head-only-full-batch"
        or str(policy.get("request_context_lifecycle") or "")
        != "one-per-bulk-plan"
        or int(policy.get("production_reference_retry_attempts") or 0) != 3
    ):
        raise RuntimeError("retirement execution policy changed")


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


def _retirement_head_error_kind(error: BaseException) -> str:
    if isinstance(error, ClientError):
        code = str(error.response.get("Error", {}).get("Code") or "")
        status = int(
            error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
        )
        if status == 429 or code in {
            "429",
            "SlowDown",
            "Throttling",
            "ThrottlingException",
            "TooManyRequestsException",
        }:
            return "rate_limit"
        if status >= 500 or code in {
            "InternalError",
            "RequestTimeout",
            "RequestTimeoutException",
            "ServiceUnavailable",
        }:
            return "transient"
        return "fatal"
    if isinstance(
        error,
        (
            ConnectTimeoutError,
            ConnectionClosedError,
            EndpointConnectionError,
            ReadTimeoutError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return "transient"
    return "fatal"


async def _run_retirement_head_requests(
    request_funcs: list[Callable[[], Any]],
    *,
    controller: RetirementHeadConcurrencyController,
    retry_sleep: Callable[[float], Awaitable[None]],
    executor: ThreadPoolExecutor | None = None,
) -> tuple[list[Any], int]:
    if not request_funcs:
        return [], controller.current_concurrency
    loop = asyncio.get_running_loop()
    pending = list(range(len(request_funcs)))
    results: list[Any] = [None] * len(request_funcs)
    peak_concurrency = controller.current_concurrency
    last_error: BaseException | None = None

    for attempt in range(1, RETIREMENT_HEAD_RETRY_ATTEMPTS + 1):
        attempt_concurrency = controller.current_concurrency
        peak_concurrency = max(peak_concurrency, attempt_concurrency)
        active_executor = executor or ThreadPoolExecutor(
            max_workers=attempt_concurrency,
            thread_name_prefix="history-r2-retirement-head",
        )
        request_slots = threading.BoundedSemaphore(attempt_concurrency)

        def run_request(index: int) -> Any:
            with request_slots:
                return request_funcs[index]()

        try:
            outcomes = await asyncio.gather(
                *(
                    loop.run_in_executor(active_executor, run_request, index)
                    for index in pending
                ),
                return_exceptions=True,
            )
        finally:
            if executor is None:
                active_executor.shutdown(wait=True, cancel_futures=True)

        retry_indexes: list[int] = []
        rate_limit_count = 0
        fatal_error: BaseException | None = None
        for index, outcome in zip(pending, outcomes):
            if not isinstance(outcome, BaseException):
                results[index] = outcome
                continue
            kind = _retirement_head_error_kind(outcome)
            if kind == "fatal":
                fatal_error = outcome
                break
            retry_indexes.append(index)
            last_error = outcome
            if kind == "rate_limit":
                rate_limit_count += 1
        if fatal_error is not None:
            raise fatal_error

        decision = controller.observe(
            request_count=len(pending),
            transient_error_count=len(retry_indexes),
            rate_limit_count=rate_limit_count,
        )
        if decision.action in {"lower", "raise", "systemic"}:
            print(
                json.dumps(
                    {
                        "event": "retirement_head_concurrency_decision",
                        "action": decision.action,
                        "reason": decision.reason,
                        "previous_concurrency": decision.previous_concurrency,
                        "current_concurrency": decision.current_concurrency,
                        "request_count": decision.request_count,
                        "error_rate": round(decision.error_rate, 6),
                        "rate_limit_count": rate_limit_count,
                    },
                    sort_keys=True,
                )
            )
        if decision.action == "systemic":
            raise RuntimeError("systemic retirement HEAD failure") from last_error
        if not retry_indexes:
            return results, peak_concurrency
        if attempt >= RETIREMENT_HEAD_RETRY_ATTEMPTS:
            raise RuntimeError("retirement HEAD retries exhausted") from last_error
        pending = retry_indexes
        delay = min(2 ** (attempt - 1), 16)
        await retry_sleep(delay + random.uniform(0, delay * 0.2))

    raise RuntimeError("retirement HEAD retry loop ended unexpectedly")


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


async def _live_reference_counts_with_retry(
    context: RetirementExecutionContext,
    keys: list[str],
    *,
    retry_sleep: Callable[[float], Awaitable[None]] | None = None,
    attempts: int = 3,
) -> dict[str, int]:
    """Recover a transient production connection without weakening the gate."""

    sleep_func = retry_sleep or asyncio.sleep
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await _live_reference_counts(context.production, keys)
        except (
            asyncpg.PostgresConnectionError,
            asyncpg.InterfaceError,
            OSError,
            TimeoutError,
        ) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(
                json.dumps(
                    {
                        "event": "retirement_production_connection_retry",
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                    },
                    sort_keys=True,
                )
            )
            await sleep_func(min(2 ** (attempt - 1), 4))
            try:
                await context.reconnect_production()
            except (
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                OSError,
                TimeoutError,
            ) as reconnect_error:
                last_error = reconnect_error
    raise RuntimeError("retirement production reference gate unavailable") from last_error


async def _head_candidates(
    candidates: list[dict[str, Any]],
    *,
    r2_client: Any,
    r2_bucket: str,
    nas_client: Any | None,
    concurrency: int,
    allow_source_missing: bool = False,
    phase: str = "head_gate",
    controller: RetirementHeadConcurrencyController | None = None,
    retry_sleep: Callable[[float], Awaitable[None]] | None = None,
    executor: ThreadPoolExecutor | None = None,
) -> int:
    started = time.monotonic()
    active_controller = controller or RetirementHeadConcurrencyController(
        initial_concurrency=concurrency
    )
    if active_controller.maximum_concurrency != concurrency:
        raise ValueError("retirement HEAD controller maximum changed")
    sleep_func = retry_sleep or asyncio.sleep

    def head_source(candidate: dict[str, Any]) -> Any | None:
        try:
            return r2_client.head_object(
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
            return None

    request_funcs: list[Callable[[], Any]] = []
    source_request_indexes: list[int] = []
    target_request_indexes: list[dict[str, int]] = []
    nas_request_indexes: list[int | None] = []
    for candidate in candidates:
        source_request_indexes.append(len(request_funcs))
        request_funcs.append(partial(head_source, candidate))
        targets: dict[str, int] = {}
        for target in candidate["targets"]:
            target_key = str(target["target_key"])
            targets[target_key] = len(request_funcs)
            request_funcs.append(
                partial(
                    r2_client.head_object,
                    Bucket=r2_bucket,
                    Key=target_key,
                )
            )
        target_request_indexes.append(targets)
        durability_basis = str(
            candidate.get("durability_basis") or DURABILITY_NAS_ARCHIVE
        )
        if durability_basis == DURABILITY_NAS_ARCHIVE:
            if nas_client is None:
                raise RuntimeError("NAS client is required for nas-archive durability")
            nas_request_indexes.append(len(request_funcs))
            request_funcs.append(
                partial(
                    nas_client.head_object,
                    Bucket=str(candidate["nas_bucket"]),
                    Key=str(candidate["nas_key"]),
                )
            )
        elif durability_basis == DURABILITY_R2_PERSISTENT_TARGET:
            nas_request_indexes.append(None)
        else:
            raise RuntimeError("unknown retirement durability basis")

    results, peak_concurrency = await _run_retirement_head_requests(
        request_funcs,
        controller=active_controller,
        retry_sleep=sleep_func,
        executor=executor,
    )
    try:
        missing = 0
        for index, candidate in enumerate(candidates):
            source = results[source_request_indexes[index]]
            targets = {
                key: results[request_index]
                for key, request_index in target_request_indexes[index].items()
            }
            nas_request_index = nas_request_indexes[index]
            nas = (
                results[nas_request_index]
                if nas_request_index is not None
                else None
            )
            if source is None:
                validate_retirement_survivor_heads(
                    candidate, target_heads=targets, nas_head=nas
                )
                candidate["_source_already_missing"] = True
                missing += 1
                continue
            validate_retirement_object_heads(
                candidate, source_head=source, target_heads=targets, nas_head=nas
            )
        print(
            json.dumps(
                {
                    "event": "retirement_head_phase_completed",
                    "phase": phase,
                    "object_count": len(candidates),
                    "request_count": len(request_funcs),
                    "source_missing_count": missing,
                    "concurrency": active_controller.current_concurrency,
                    "peak_concurrency": peak_concurrency,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                },
                sort_keys=True,
            )
        )
        return missing
    finally:
        results.clear()


async def _head_source_candidates(
    candidates: list[dict[str, Any]],
    *,
    r2_client: Any,
    r2_bucket: str,
    concurrency: int,
    pre_delete_proof: str,
    expected_pre_delete_proof: str,
    phase: str = "post_delete",
    controller: RetirementHeadConcurrencyController | None = None,
    retry_sleep: Callable[[float], Awaitable[None]] | None = None,
    executor: ThreadPoolExecutor | None = None,
) -> int:
    """Verify only old sources after deletion, bound to the successful pre-gate."""

    current_proof = _sha256_json(
        [_retirement_object_identity(candidate) for candidate in candidates]
    )
    if (
        not pre_delete_proof
        or pre_delete_proof != expected_pre_delete_proof
        or current_proof != expected_pre_delete_proof
    ):
        raise RuntimeError("retirement pre-delete survivor proof changed")
    started = time.monotonic()
    active_controller = controller or RetirementHeadConcurrencyController(
        initial_concurrency=concurrency
    )
    if active_controller.maximum_concurrency != concurrency:
        raise ValueError("retirement HEAD controller maximum changed")

    def head_source(candidate: dict[str, Any]) -> Any | None:
        try:
            return r2_client.head_object(
                Bucket=r2_bucket, Key=str(candidate["source_key"])
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            status = int(
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
            )
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return None
            raise

    results, peak_concurrency = await _run_retirement_head_requests(
        [partial(head_source, candidate) for candidate in candidates],
        controller=active_controller,
        retry_sleep=retry_sleep or asyncio.sleep,
        executor=executor,
    )
    missing = sum(result is None for result in results)
    print(
        json.dumps(
            {
                "event": "retirement_head_phase_completed",
                "phase": phase,
                "object_count": len(candidates),
                "request_count": len(candidates),
                "source_missing_count": missing,
                "concurrency": active_controller.current_concurrency,
                "peak_concurrency": peak_concurrency,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            },
            sort_keys=True,
        )
    )
    results.clear()
    return missing


async def _delete_sources(
    candidates: list[dict[str, Any]],
    *,
    r2_client: Any,
    r2_bucket: str,
    concurrency: int,
    retry_sleep: Callable[[float], Awaitable[None]] | None = None,
    executor: ThreadPoolExecutor | None = None,
) -> int:
    started = time.monotonic()
    selected = [
        candidate
        for candidate in candidates
        if not candidate.get("_source_already_missing")
    ]
    if not selected:
        return 0
    loop = asyncio.get_running_loop()
    active_executor = executor or ThreadPoolExecutor(
        max_workers=concurrency, thread_name_prefix="history-r2-retirement-delete"
    )
    sleep_func = retry_sleep or asyncio.sleep
    pending = [str(candidate["source_key"]) for candidate in selected]
    request_count = 0
    try:
        for attempt in range(1, RETIREMENT_DELETE_RETRY_ATTEMPTS + 1):
            chunks = [
                pending[offset : offset + RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE]
                for offset in range(
                    0, len(pending), RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE
                )
            ]
            retry_keys: list[str] = []
            for offset in range(0, len(chunks), concurrency):
                wave = chunks[offset : offset + concurrency]
                responses = await asyncio.gather(
                    *(
                        loop.run_in_executor(
                            active_executor,
                            partial(
                                r2_client.delete_objects,
                                Bucket=r2_bucket,
                                Delete={
                                    "Objects": [{"Key": key} for key in chunk],
                                    "Quiet": False,
                                },
                            ),
                        )
                        for chunk in wave
                    ),
                    return_exceptions=True,
                )
                request_count += len(wave)
                for chunk, response in zip(wave, responses):
                    if isinstance(response, BaseException):
                        if _retirement_head_error_kind(response) == "fatal":
                            raise response
                        retry_keys.extend(chunk)
                        continue
                    deleted_keys = {
                        str(item.get("Key") or "")
                        for item in response.get("Deleted", [])
                    }
                    errors = list(response.get("Errors", []))
                    error_keys = {str(item.get("Key") or "") for item in errors}
                    submitted = set(chunk)
                    if (
                        not deleted_keys.issubset(submitted)
                        or not error_keys.issubset(submitted)
                        or deleted_keys & error_keys
                        or deleted_keys | error_keys != submitted
                    ):
                        raise RuntimeError(
                            "retirement DeleteObjects response coverage changed"
                        )
                    for error in errors:
                        code = str(error.get("Code") or "")
                        if code not in {
                            "429",
                            "InternalError",
                            "RequestTimeout",
                            "RequestTimeoutException",
                            "ServiceUnavailable",
                            "SlowDown",
                            "Throttling",
                            "ThrottlingException",
                            "TooManyRequestsException",
                        }:
                            raise RuntimeError(
                                "retirement DeleteObjects returned a fatal error"
                            )
                    retry_keys.extend(error_keys)
            if not retry_keys:
                break
            if attempt >= RETIREMENT_DELETE_RETRY_ATTEMPTS:
                raise RuntimeError("retirement DeleteObjects retries exhausted")
            pending = sorted(set(retry_keys))
            delay = min(2 ** (attempt - 1), 16)
            await sleep_func(delay + random.uniform(0, delay * 0.2))
        print(
            json.dumps(
                {
                    "event": "retirement_delete_phase_completed",
                    "object_count": len(selected),
                    "concurrency": concurrency,
                    "chunk_size": RETIREMENT_DELETE_OBJECTS_CHUNK_SIZE,
                    "request_count": request_count,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                },
                sort_keys=True,
            )
        )
        return len(selected)
    finally:
        if executor is None:
            active_executor.shutdown(wait=True, cancel_futures=True)


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
    r2_transport = _r2_transport(r2_config)
    _validate_r2_transport_runtime(r2_transport)
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
    r2_client = _s3_client(
        r2_config["target"],
        max_connections=16,
        transport=r2_transport,
    )
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


def _switch_batch_proof(
    rows: Iterable[dict[str, Any]], *, include_batch_no: bool
) -> str:
    identities = []
    for row in sorted(rows, key=lambda item: int(item["batch_no"])):
        identity = {
            "asset_count": int(row["asset_count"]),
            "rowset_sha256": str(row["rowset_sha256"]),
        }
        if include_batch_no:
            identity["batch_no"] = int(row["batch_no"])
        identities.append(identity)
    return _sha256_json(identities)


def build_bulk_switch_scope_facts(
    *,
    plan_rows: Iterable[dict[str, Any]],
    batch_rows: Iterable[dict[str, Any]],
    expected_counts: dict[str, int],
) -> dict[str, dict[str, Any]]:
    """Freeze exact completed Switch scopes, including terminal predecessors."""

    plans: dict[str, dict[str, Any]] = {}
    for raw in plan_rows:
        row = dict(raw)
        plan_sha = str(row["plan_sha256"])
        manifest = (
            json.loads(row["manifest"])
            if isinstance(row["manifest"], str)
            else dict(row["manifest"])
        )
        plans[plan_sha] = {
            "manifest": manifest,
            "rowset_sha256": str(row["rowset_sha256"]),
        }
    if set(plans) != set(expected_counts):
        raise RuntimeError("bulk retirement Switch plan set changed")

    batches_by_plan: dict[str, list[dict[str, Any]]] = {
        plan_sha: [] for plan_sha in plans
    }
    for raw in batch_rows:
        row = dict(raw)
        plan_sha = str(row["plan_sha256"])
        if plan_sha not in batches_by_plan:
            raise RuntimeError("bulk retirement Switch batch owner changed")
        batches_by_plan[plan_sha].append(row)

    facts: dict[str, dict[str, Any]] = {}
    normalized_completed_proofs: dict[str, str] = {}
    for plan_sha in sorted(plans):
        manifest = plans[plan_sha]["manifest"]
        expected_count = int(expected_counts[plan_sha])
        root_count = int(manifest.get("count") or 0)
        if root_count < expected_count:
            raise RuntimeError("bulk retirement Switch root scope changed")
        rows = sorted(
            batches_by_plan[plan_sha], key=lambda item: int(item["batch_no"])
        )
        if not rows:
            if root_count != expected_count:
                raise RuntimeError("legacy bulk retirement Switch scope changed")
            empty_proof = _sha256_json([])
            normalized_completed_proofs[plan_sha] = empty_proof
            facts[plan_sha] = {
                "switch_plan_sha256": plan_sha,
                "asset_coordinate_count": expected_count,
                "rowset_sha256": plans[plan_sha]["rowset_sha256"],
                "terminal_scope_mode": "legacy-plan-rowset",
                "root_asset_coordinate_count": root_count,
                "completed_batch_count": 0,
                "completed_batches_sha256": empty_proof,
                "superseded_batch_count": 0,
                "superseded_asset_coordinate_count": 0,
                "superseded_batches_sha256": empty_proof,
            }
            continue

        batch_nos = [int(row["batch_no"]) for row in rows]
        if batch_nos != list(range(len(rows))):
            raise RuntimeError("bulk retirement Switch batch sequence changed")

        invalid_statuses = {
            str(row["status"])
            for row in rows
            if str(row["status"]) not in {"completed", "superseded"}
        }
        if invalid_statuses:
            raise RuntimeError("bulk retirement parent Switch is incomplete")
        completed = [row for row in rows if str(row["status"]) == "completed"]
        superseded = [row for row in rows if str(row["status"]) == "superseded"]
        if not completed:
            raise RuntimeError("bulk retirement completed Switch scope changed")
        if superseded and int(completed[-1]["batch_no"]) >= int(
            superseded[0]["batch_no"]
        ):
            raise RuntimeError("bulk retirement Switch terminal boundary changed")
        completed_count = sum(int(row["asset_count"]) for row in completed)
        superseded_count = sum(int(row["asset_count"]) for row in superseded)
        if completed_count != expected_count:
            raise RuntimeError("bulk retirement completed Switch scope changed")
        if completed_count + superseded_count != root_count:
            raise RuntimeError("bulk retirement Switch root conservation changed")
        normalized_completed_proofs[plan_sha] = _switch_batch_proof(
            completed, include_batch_no=False
        )
        facts[plan_sha] = {
            "switch_plan_sha256": plan_sha,
            "asset_coordinate_count": expected_count,
            "rowset_sha256": plans[plan_sha]["rowset_sha256"],
            "terminal_scope_mode": "completed-batches",
            "root_asset_coordinate_count": root_count,
            "completed_batch_count": len(completed),
            "completed_batches_sha256": _switch_batch_proof(
                completed, include_batch_no=True
            ),
            "superseded_batch_count": len(superseded),
            "superseded_asset_coordinate_count": superseded_count,
            "superseded_batches_sha256": _switch_batch_proof(
                superseded, include_batch_no=False
            ),
        }

    for plan_sha, scope in facts.items():
        superseded_count = int(scope["superseded_asset_coordinate_count"])
        if not superseded_count:
            continue
        successors = []
        for candidate_sha, candidate in facts.items():
            if candidate_sha == plan_sha or int(
                candidate["superseded_asset_coordinate_count"]
            ):
                continue
            candidate_manifest = plans[candidate_sha]["manifest"]
            predecessor_chain = {
                str(value)
                for value in candidate_manifest.get(
                    "predecessor_switch_plan_sha256s", []
                )
            }
            single_predecessor = str(
                candidate_manifest.get("predecessor_switch_plan_sha256") or ""
            )
            if single_predecessor:
                predecessor_chain.add(single_predecessor)
            if (
                plan_sha in predecessor_chain
                and int(candidate["asset_coordinate_count"]) == superseded_count
                and normalized_completed_proofs[candidate_sha]
                == scope["superseded_batches_sha256"]
            ):
                successors.append(candidate_sha)
        if len(successors) != 1:
            raise RuntimeError(
                "bulk retirement superseded Switch scope is not conserved"
            )
        scope["terminal_successor_plan_sha256"] = successors[0]

    return facts


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
select s.source_name,s.source_key,s.byte_size,coalesce(s.source_etag,'') source_etag,
       s.source_last_modified,
       s.asset_count,c.scope_asset_count,c.scope_facts,t.target_facts,
       s.byte_size_variants,s.source_etag_variants,s.source_time_variants
  from source_stats s join scope_counts c using(source_name,source_key)
  join target_rows t using(source_name,source_key)
"""


async def _prepare_bulk_retirement_stage(
    ledger: asyncpg.Connection,
    switch_plan_sha256s: list[str],
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
    await ledger.execute(
        "alter table bulk_retirement_candidates "
        "add column retirement_disposition text not null default 'eligible'"
    )
    await ledger.execute(
        """create temporary table bulk_retirement_blockers
             on commit preserve rows as
             with pending as materialized (
               select distinct s.source_name,s.source_key
                 from bulk_retirement_candidates s
                 join analytics_history_media_r2_migrations m
                   using(source_name,source_key)
                where m.status in ('copy_required','failed')
             ), unswitched as materialized (
               select distinct s.source_name,s.source_key
                 from bulk_retirement_candidates s
                 join analytics_history_media_r2_migrations m
                   using(source_name,source_key)
                where m.original_ref<>m.target_key
                  and m.switch_completed_at is null
             ), collisions as materialized (
               select distinct s.source_name,s.source_key
                 from bulk_retirement_candidates s
                 join analytics_history_media_r2_migrations m
                   on m.target_key=s.source_key
             ), facts as (
               select source_name,source_key,true pending,false unswitched,
                      false collision from pending
               union all
               select source_name,source_key,false,true,false from unswitched
               union all
               select source_name,source_key,false,false,true from collisions
             )
             select source_name,source_key,bool_or(pending) pending,
                    bool_or(unswitched) unswitched,bool_or(collision) collision
               from facts group by source_name,source_key""",
        timeout=3600,
    )
    await ledger.execute(
        """update bulk_retirement_candidates c
              set retirement_disposition=case
                    when b.collision then 'retained_target'
                    when b.pending or b.unswitched then 'deferred'
                    else 'eligible' end
             from bulk_retirement_blockers b
            where (c.source_name,c.source_key)=(b.source_name,b.source_key)"""
    )


async def _materialize_bulk_retirement_order(
    ledger: asyncpg.Connection,
    *,
    canary_size: int,
    batch_size: int,
    require_eligible: bool = True,
) -> None:
    disposition_rows = await ledger.fetch(
        """select retirement_disposition,count(*) object_count,
                  coalesce(sum(scope_asset_count),0) asset_coordinate_count
             from bulk_retirement_candidates group by retirement_disposition"""
    )
    disposition_counts = {
        str(row["retirement_disposition"]): int(row["object_count"])
        for row in disposition_rows
    }
    eligible_count = disposition_counts.get("eligible", 0)
    deferred_count = disposition_counts.get("deferred", 0)
    if require_eligible and not eligible_count:
        raise RuntimeError("bulk retirement scope has no immediately eligible source")
    eligible_batch_count = (
        1 + max(0, (eligible_count - canary_size + batch_size - 1) // batch_size)
        if eligible_count
        else 0
    )
    deferred_batch_count = (
        (deferred_count + batch_size - 1) // batch_size if deferred_count else 0
    )
    await ledger.execute(
        """create temporary table bulk_retirement_ordered on commit preserve rows as
             select c.*,
                    (row_number() over(
                       order by case retirement_disposition
                                  when 'eligible' then 0
                                  when 'deferred' then 1 else 2 end,
                                byte_size desc,
                                encode(sha256(
                                  convert_to(source_name,'UTF8')||decode('00','hex')||
                                  convert_to(source_key,'UTF8')),'hex')
                     )-1)::integer object_no,
                    row_number() over(
                      partition by retirement_disposition
                      order by byte_size desc,
                               encode(sha256(
                                 convert_to(source_name,'UTF8')||decode('00','hex')||
                                 convert_to(source_key,'UTF8')),'hex')
                    )::integer disposition_object_no
               from bulk_retirement_candidates c"""
    )
    await ledger.execute(
        "alter table bulk_retirement_ordered add column batch_no integer"
    )
    await ledger.execute(
        """update bulk_retirement_ordered
              set batch_no=case retirement_disposition
                    when 'eligible' then
                      case when disposition_object_no<=$1 then 0
                           else 1+((disposition_object_no-$1-1)/$2) end
                    when 'deferred' then
                      $3+((disposition_object_no-1)/$2)
                    else $3+$4+((disposition_object_no-1)/$2)
                  end""",
        canary_size,
        batch_size,
        eligible_batch_count,
        deferred_batch_count,
    )


async def _materialize_bulk_production_live_source_hashes(
    ledger: asyncpg.Connection,
    production: asyncpg.Connection,
    *,
    eligible_only: bool,
) -> int:
    async with production.transaction():
        await production.execute(
            """create temporary table bulk_retirement_source_keys(
                 source_key_sha256 bytea not null) on commit drop"""
        )
        await production.execute("set local work_mem='256MB'")
        await production.execute("set local max_parallel_workers_per_gather=0")
        async with ledger.transaction():
            disposition_filter = (
                "where retirement_disposition='eligible'" if eligible_only else ""
            )
            statement = await ledger.prepare(
                f"""select distinct sha256(convert_to(source_key,'UTF8'))
                              source_key_sha256
                       from bulk_retirement_candidates
                       {disposition_filter}
                      order by source_key_sha256"""
            )
            pending: list[tuple[bytes]] = []
            async for row in statement.cursor(prefetch=10000):
                pending.append((bytes(row["source_key_sha256"]),))
                if len(pending) < 10000:
                    continue
                await production.copy_records_to_table(
                    "bulk_retirement_source_keys",
                    records=pending,
                    columns=["source_key_sha256"],
                )
                pending.clear()
            if pending:
                await production.copy_records_to_table(
                    "bulk_retirement_source_keys",
                    records=pending,
                    columns=["source_key_sha256"],
                )
        await production.execute(
            """create unique index bulk_retirement_source_keys_sha256
                 on bulk_retirement_source_keys(source_key_sha256)"""
        )
        await production.execute("analyze bulk_retirement_source_keys")
        await production.execute(
            """create temporary table bulk_retirement_live_source_hashes
                 on commit drop as
                 with refs as (
                   select btrim(x.ref) ref from history h
                    cross join lateral unnest(
                      string_to_array(coalesce(h.input_file,''),'|')) x(ref)
                   union all select btrim(output_file) from history
                    where btrim(coalesce(output_file,''))<>''
                   union all select trim(both '"' from p.path::text) from history h
                    cross join lateral jsonb_path_query(
                      coalesce(h.extra_outputs::jsonb,'{}'::jsonb),
                      'strict $.**.path') p(path)
                 )
                 select distinct s.source_key_sha256
                   from refs r join bulk_retirement_source_keys s
                     on s.source_key_sha256=sha256(convert_to(r.ref,'UTF8'))""",
            timeout=600,
        )
        match_count = int(
            await production.fetchval(
                "select count(*) from bulk_retirement_live_source_hashes"
            )
        )
        await ledger.execute(
            """create temporary table bulk_retirement_live_source_hashes(
                 source_key_sha256 bytea not null primary key)
                 on commit preserve rows"""
        )
        if not match_count:
            return 0
        statement = await production.prepare(
            """select source_key_sha256
                 from bulk_retirement_live_source_hashes
                order by source_key_sha256"""
        )
        pending: list[tuple[bytes]] = []
        async with ledger.transaction():
            async for row in statement.cursor(prefetch=10000):
                pending.append((bytes(row["source_key_sha256"]),))
                if len(pending) < 10000:
                    continue
                await ledger.copy_records_to_table(
                    "bulk_retirement_live_source_hashes",
                    records=pending,
                    columns=["source_key_sha256"],
                )
                pending.clear()
            if pending:
                await ledger.copy_records_to_table(
                    "bulk_retirement_live_source_hashes",
                    records=pending,
                    columns=["source_key_sha256"],
                )
        return match_count


async def _bulk_production_has_live_refs(
    ledger: asyncpg.Connection,
    production: asyncpg.Connection,
) -> int:
    match_count = await _materialize_bulk_production_live_source_hashes(
        ledger,
        production,
        eligible_only=True,
    )
    if not match_count:
        return 0
    updated = await ledger.fetchval(
        """with changed as (
             update bulk_retirement_candidates c
                set retirement_disposition='deferred'
              where retirement_disposition='eligible'
                and sha256(convert_to(source_key,'UTF8')) in (
                  select source_key_sha256
                    from bulk_retirement_live_source_hashes)
              returning 1)
           select count(*) from changed"""
    )
    if int(updated) != match_count:
        raise RuntimeError("bulk retirement live reference classification drifted")
    return match_count


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
        "retirement_disposition": str(row["retirement_disposition"]),
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
    batch_disposition = ""
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
                "disposition": batch_disposition,
                "is_retained": batch_disposition == "retained_target",
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
                batch_disposition = str(candidate["retirement_disposition"])
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


async def _completed_retirement_batch_proof(
    ledger: asyncpg.Connection,
    plan_sha256: str,
) -> tuple[str, int, int]:
    rows = await ledger.fetch(
        """select batch_no,object_count,asset_coordinate_count,total_bytes,
                  rowset_sha256,disposition,is_retained,outcome_counts
             from analytics_history_media_r2_retirement_batches
            where plan_sha256=$1 and status='completed' order by batch_no""",
        plan_sha256,
    )
    identities = [
        {
            "batch_no": int(row["batch_no"]),
            "object_count": int(row["object_count"]),
            "asset_coordinate_count": int(row["asset_coordinate_count"]),
            "total_bytes": int(row["total_bytes"]),
            "rowset_sha256": str(row["rowset_sha256"]),
            "disposition": str(row["disposition"]),
            "is_retained": bool(row["is_retained"]),
            "outcome_counts": (
                json.loads(row["outcome_counts"])
                if isinstance(row["outcome_counts"], str)
                else dict(row["outcome_counts"])
            ),
        }
        for row in rows
    ]
    return (
        _sha256_json(identities),
        sum(item["object_count"] for item in identities),
        sum(item["asset_coordinate_count"] for item in identities),
    )


async def _bulk_predecessor_retained_counts(
    ledger: asyncpg.Connection,
    plan_sha256: str,
) -> tuple[int, int]:
    row = await ledger.fetchrow(
        """select count(*) filter(where status<>'planned') object_count,
                  coalesce(sum(scope_asset_count)
                    filter(where status<>'planned'),0) asset_coordinate_count
             from analytics_history_media_r2_retirement_objects
            where plan_sha256=$1""",
        plan_sha256,
    )
    return int(row["object_count"]), int(row["asset_coordinate_count"])


def _bulk_predecessor_is_replaceable(
    status: str,
    *,
    nonplanned_object_count: int,
    nonpending_batch_count: int,
) -> bool:
    if status in {"running", "paused"}:
        return True
    return (
        status == "frozen"
        and nonplanned_object_count == 0
        and nonpending_batch_count == 0
    )


async def _bulk_predecessor_quarantine_proof(
    ledger: asyncpg.Connection,
    plan_sha256: str,
) -> tuple[str, int, int]:
    rows = await ledger.fetch(
        """select source_name,source_key,byte_size,source_etag,
                  source_last_modified,asset_count,scope_asset_count,scope_facts,
                  target_facts,retirement_disposition
             from analytics_history_media_r2_retirement_objects
            where plan_sha256=$1 and status='blocked'
              and error_code='TARGET_IDENTITY_DRIFT'
            order by source_key_sha256""",
        plan_sha256,
    )
    identities: list[dict[str, Any]] = []
    asset_count = 0
    for row in rows:
        candidate = {
            **_candidate_from_bulk_stage(row),
            "archive_sha256": "",
            "nas_bucket": "",
            "nas_key": "",
        }
        identities.append(_retirement_object_identity(candidate))
        asset_count += int(row["scope_asset_count"])
    return _sha256_json(identities), len(identities), asset_count


async def _bulk_predecessor_live_reference_proof(
    ledger: asyncpg.Connection,
    plan_sha256: str,
) -> tuple[str, int, int]:
    rows = await ledger.fetch(
        """select source_name,source_key,byte_size,source_etag,
                  source_last_modified,asset_count,scope_asset_count,scope_facts,
                  target_facts,retirement_disposition
            from analytics_history_media_r2_retirement_objects
            where plan_sha256=$1 and status='blocked'
              and error_code='LIVE_HISTORY_REFERENCE'
            order by sha256(convert_to(source_key,'UTF8'))""",
        plan_sha256,
    )
    identities: list[dict[str, Any]] = []
    asset_count = 0
    for row in rows:
        candidate = {
            **_candidate_from_bulk_stage(row),
            "archive_sha256": "",
            "nas_bucket": "",
            "nas_key": "",
        }
        identities.append(_retirement_object_identity(candidate))
        asset_count += int(row["scope_asset_count"])
    return _sha256_json(identities), len(identities), asset_count


async def _validate_bulk_successor_predecessor(
    ledger: asyncpg.Connection,
    manifest: dict[str, Any],
) -> None:
    predecessor_sha = str(manifest.get("predecessor_plan_sha256") or "")
    if not predecessor_sha:
        return
    row = await ledger.fetchrow(
        """select manifest,status from analytics_history_media_r2_retirement_plans
            where plan_sha256=$1""",
        predecessor_sha,
    )
    if row is None or str(row["status"]) != "paused":
        raise RuntimeError("bulk retirement predecessor is not safely paused")
    predecessor_manifest = (
        json.loads(row["manifest"])
        if isinstance(row["manifest"], str)
        else dict(row["manifest"])
    )
    if (
        str(predecessor_manifest.get("plan_sha256") or "") != predecessor_sha
        or _sha256_json(
            {
                key: value
                for key, value in predecessor_manifest.items()
                if key != "plan_sha256"
            }
        )
        != predecessor_sha
    ):
        raise RuntimeError("bulk retirement predecessor identity changed")
    proof_sha, batch_objects, batch_assets = (
        await _completed_retirement_batch_proof(ledger, predecessor_sha)
    )
    if proof_sha != str(manifest["predecessor_completed_batches_sha256"]):
        raise RuntimeError("bulk retirement predecessor completed batches changed")
    direct_objects, direct_assets = await _bulk_predecessor_retained_counts(
        ledger, predecessor_sha
    )
    quarantine_sha, quarantine_objects, quarantine_assets = (
        await _bulk_predecessor_quarantine_proof(ledger, predecessor_sha)
    )
    live_sha, live_objects, live_assets = (
        await _bulk_predecessor_live_reference_proof(ledger, predecessor_sha)
    )
    if (
        quarantine_sha
        != str(manifest.get("predecessor_quarantined_rowset_sha256") or "")
        or quarantine_objects
        != int(manifest.get("predecessor_quarantined_object_count") or 0)
        or quarantine_assets
        != int(manifest.get("predecessor_quarantined_asset_coordinate_count") or 0)
        or live_sha
        != str(
            manifest.get("predecessor_live_reference_retained_rowset_sha256")
            or ""
        )
        or live_objects
        != int(
            manifest.get("predecessor_live_reference_retained_object_count") or 0
        )
        or live_assets
        != int(
            manifest.get(
                "predecessor_live_reference_retained_asset_coordinate_count"
            )
            or 0
        )
    ):
        raise RuntimeError("bulk retirement predecessor retained proof changed")
    if (
        direct_objects != batch_objects + quarantine_objects + live_objects
        or direct_assets != batch_assets + quarantine_assets + live_assets
    ):
        raise RuntimeError("bulk retirement predecessor receipt coverage changed")
    inherited_objects = int(
        predecessor_manifest.get("predecessor_retained_object_count") or 0
    )
    inherited_assets = int(
        predecessor_manifest.get("predecessor_retained_asset_coordinate_count") or 0
    )
    if (
        direct_objects + inherited_objects
        != int(manifest["predecessor_retained_object_count"])
        or direct_assets + inherited_assets
        != int(manifest["predecessor_retained_asset_coordinate_count"])
    ):
        raise RuntimeError("bulk retirement predecessor retained scope changed")


async def _plan_bulk_delete_successor(args: argparse.Namespace) -> None:
    quarantine_hashes = _exact_source_identity_hashes(
        args.retain_target_identity_drift_source_sha256 or []
    )
    r2_config = _load_secure_config(Path(args.config))
    clear_proxy_environment()
    r2_transport = _r2_transport(r2_config)
    _validate_r2_transport_runtime(r2_transport)
    validate_endpoint_route(r2_config["target"])
    runtime_identity = _retirement_runtime_identity(
        artifact_digest=args.artifact_digest,
        r2_config=r2_config,
        durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
        archive_config=None,
    )
    ledger = await _connect("LOCAL_ANALYTICS_DATABASE_URL")
    production: asyncpg.Connection | None = None
    try:
        production = await _connect("PRODUCTION_DATABASE_URL")
        await ledger.execute(RETIREMENT_DDL)
        predecessor = await ledger.fetchrow(
            """select p.run_id,p.manifest,p.status,
                      (select count(*)
                         from analytics_history_media_r2_retirement_objects o
                        where o.plan_sha256=p.plan_sha256
                          and o.status<>'planned') nonplanned_object_count,
                      (select count(*)
                         from analytics_history_media_r2_retirement_batches b
                        where b.plan_sha256=p.plan_sha256
                          and b.status<>'pending') nonpending_batch_count
                 from analytics_history_media_r2_retirement_plans p
                where p.plan_sha256=$1""",
            args.predecessor_plan_sha256,
        )
        if predecessor is None or not _bulk_predecessor_is_replaceable(
            str(predecessor["status"]),
            nonplanned_object_count=int(predecessor["nonplanned_object_count"]),
            nonpending_batch_count=int(predecessor["nonpending_batch_count"]),
        ):
            raise RuntimeError("bulk retirement predecessor is not replaceable")
        predecessor_manifest = (
            json.loads(predecessor["manifest"])
            if isinstance(predecessor["manifest"], str)
            else dict(predecessor["manifest"])
        )
        if (
            str(predecessor_manifest.get("plan_sha256") or "")
            != args.predecessor_plan_sha256
            or _sha256_json(
                {
                    key: value
                    for key, value in predecessor_manifest.items()
                    if key != "plan_sha256"
                }
            )
            != args.predecessor_plan_sha256
            or predecessor_manifest.get("execution_mode") != "bulk"
        ):
            raise RuntimeError("bulk retirement predecessor identity changed")

        direct_retained_objects, direct_retained_assets = (
            await _bulk_predecessor_retained_counts(
                ledger, args.predecessor_plan_sha256
            )
        )
        inherited_objects = int(
            predecessor_manifest.get("predecessor_retained_object_count") or 0
        )
        inherited_assets = int(
            predecessor_manifest.get(
                "predecessor_retained_asset_coordinate_count"
            )
            or 0
        )
        retained_objects = inherited_objects + direct_retained_objects
        retained_assets = inherited_assets + direct_retained_assets
        completed_proof_sha, completed_objects, completed_assets = (
            await _completed_retirement_batch_proof(
                ledger, args.predecessor_plan_sha256
            )
        )
        if (
            direct_retained_objects != completed_objects
            or direct_retained_assets != completed_assets
        ):
            raise RuntimeError(
                "bulk retirement predecessor completed receipt coverage changed"
            )

        await ledger.execute(
            """create temporary table bulk_retirement_candidates
                 on commit preserve rows as
                 select source_name,source_key,byte_size,source_etag,
                        source_last_modified,asset_count,scope_asset_count,
                        scope_facts,target_facts,source_key_sha256,
                        1::bigint byte_size_variants,
                        1::bigint source_etag_variants,
                        1::bigint source_time_variants,
                        retirement_disposition
                   from analytics_history_media_r2_retirement_objects
                  where plan_sha256=$1 and status='planned'""",
            args.predecessor_plan_sha256,
            timeout=3600,
        )
        quarantine_rows = await ledger.fetch(
            """select * from bulk_retirement_candidates
                 where source_key_sha256=any($1::text[])
                 order by source_key_sha256""",
            quarantine_hashes,
        )
        if len(quarantine_rows) != len(quarantine_hashes):
            raise RuntimeError(
                "target identity drift quarantine does not match planned predecessor objects"
            )
        quarantine_candidates = [
            _candidate_from_bulk_stage(row) for row in quarantine_rows
        ]
        for candidate in quarantine_candidates:
            candidate["source_identity_policy"] = str(
                predecessor_manifest.get("source_identity_policy") or ""
            )
        quarantine_evidence: list[dict[str, Any]] = []
        if quarantine_candidates:
            r2_client = _s3_client(
                r2_config["target"],
                max_connections=DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
                transport=r2_transport,
            )
            executor = ThreadPoolExecutor(
                max_workers=DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
                thread_name_prefix="history-r2-retirement-quarantine-head",
            )
            try:
                quarantine_evidence = (
                    await _head_target_identity_drift_candidates(
                        quarantine_candidates,
                        r2_client=r2_client,
                        r2_bucket=str(r2_config["target"]["bucket"]),
                        concurrency=DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
                        executor=executor,
                    )
                )
            finally:
                executor.shutdown(wait=True, cancel_futures=True)
                r2_client.close()
        quarantine_identities = [
            _retirement_object_identity(candidate)
            for candidate in quarantine_candidates
        ]
        quarantine_rowset_sha = _sha256_json(quarantine_identities)
        quarantine_evidence_sha = _sha256_json(
            [
                {
                    "source_key_sha256": quarantine_hashes[index],
                    **evidence,
                }
                for index, evidence in enumerate(quarantine_evidence)
            ]
        )
        quarantine_asset_count = sum(
            int(candidate["scope_asset_count"])
            for candidate in quarantine_candidates
        )
        if quarantine_hashes:
            await ledger.execute(
                """delete from bulk_retirement_candidates
                     where source_key_sha256=any($1::text[])""",
                quarantine_hashes,
            )
        live_reference_count = (
            await _materialize_bulk_production_live_source_hashes(
                ledger,
                production,
                eligible_only=False,
            )
        )
        live_reference_rows = await ledger.fetch(
            """select c.* from bulk_retirement_candidates c
                 join bulk_retirement_live_source_hashes h
                   on h.source_key_sha256=sha256(convert_to(c.source_key,'UTF8'))
                order by h.source_key_sha256"""
        )
        if len(live_reference_rows) != live_reference_count:
            raise RuntimeError(
                "bulk retirement live reference retention coverage changed"
            )
        live_reference_candidates = [
            _candidate_from_bulk_stage(row) for row in live_reference_rows
        ]
        live_reference_identities = [
            _retirement_object_identity(candidate)
            for candidate in live_reference_candidates
        ]
        live_reference_rowset_sha = _sha256_json(live_reference_identities)
        live_reference_asset_count = sum(
            int(candidate["scope_asset_count"])
            for candidate in live_reference_candidates
        )
        if live_reference_count:
            await ledger.execute(
                """delete from bulk_retirement_candidates c
                      where sha256(convert_to(c.source_key,'UTF8')) in (
                        select source_key_sha256
                          from bulk_retirement_live_source_hashes)"""
            )
        live_ref_count = int(
            predecessor_manifest.get("deferred_live_history_ref_object_count") or 0
        )
        await _materialize_bulk_retirement_order(
            ledger,
            canary_size=args.canary_size,
            batch_size=args.batch_size,
            require_eligible=False,
        )
        rowset_sha, batches, object_count, total_bytes = (
            await _bulk_staged_identity(ledger)
        )
        asset_count = int(
            await ledger.fetchval(
                "select coalesce(sum(scope_asset_count),0) "
                "from bulk_retirement_ordered"
            )
        )
        disposition_rows = await ledger.fetch(
            """select retirement_disposition,count(*) object_count,
                      coalesce(sum(scope_asset_count),0) asset_coordinate_count
                 from bulk_retirement_ordered group by retirement_disposition"""
        )
        disposition_summary = {
            str(row["retirement_disposition"]): {
                "object_count": int(row["object_count"]),
                "asset_coordinate_count": int(row["asset_coordinate_count"]),
            }
            for row in disposition_rows
        }
        manifest = build_bulk_retirement_successor_manifest(
            predecessor_manifest=predecessor_manifest,
            predecessor_plan_sha256=args.predecessor_plan_sha256,
            predecessor_completed_batches_sha256=completed_proof_sha,
            predecessor_retained_object_count=(
                retained_objects
                + len(quarantine_candidates)
                + live_reference_count
            ),
            predecessor_retained_asset_coordinate_count=(
                retained_assets
                + quarantine_asset_count
                + live_reference_asset_count
            ),
            predecessor_quarantined_object_count=len(quarantine_candidates),
            predecessor_quarantined_asset_coordinate_count=quarantine_asset_count,
            predecessor_quarantined_rowset_sha256=quarantine_rowset_sha,
            predecessor_quarantined_evidence_sha256=quarantine_evidence_sha,
            predecessor_live_reference_retained_object_count=(
                live_reference_count
            ),
            predecessor_live_reference_retained_asset_coordinate_count=(
                live_reference_asset_count
            ),
            predecessor_live_reference_retained_rowset_sha256=(
                live_reference_rowset_sha
            ),
            remaining_object_count=object_count,
            remaining_asset_coordinate_count=asset_count,
            remaining_total_bytes=total_bytes,
            remaining_rowset_sha256=rowset_sha,
            batches=batches,
            disposition_summary=disposition_summary,
            runtime_identity=runtime_identity,
        )
        manifest["deferred_live_history_ref_object_count"] = live_ref_count
        manifest["plan_sha256"] = _sha256_json(
            {key: value for key, value in manifest.items() if key != "plan_sha256"}
        )

        async with ledger.transaction():
            locked = await ledger.fetchrow(
                """select p.status,
                          (select count(*)
                             from analytics_history_media_r2_retirement_objects o
                            where o.plan_sha256=p.plan_sha256
                              and o.status<>'planned') nonplanned_object_count,
                          (select count(*)
                             from analytics_history_media_r2_retirement_batches b
                            where b.plan_sha256=p.plan_sha256
                              and b.status<>'pending') nonpending_batch_count
                     from analytics_history_media_r2_retirement_plans p
                    where p.plan_sha256=$1 for update""",
                args.predecessor_plan_sha256,
            )
            if locked is None or not _bulk_predecessor_is_replaceable(
                str(locked["status"]),
                nonplanned_object_count=int(locked["nonplanned_object_count"]),
                nonpending_batch_count=int(locked["nonpending_batch_count"]),
            ):
                raise RuntimeError("bulk retirement predecessor state changed")
            await ledger.execute(
                """update analytics_history_media_r2_retirement_plans
                      set status='paused',updated_at=now()
                    where plan_sha256=$1""",
                args.predecessor_plan_sha256,
            )
            await ledger.execute(
                """update analytics_history_media_r2_retirement_batches
                      set status='paused',updated_at=now()
                    where plan_sha256=$1 and status<>'completed'""",
                args.predecessor_plan_sha256,
            )
            quarantined_count = int(
                await ledger.fetchval(
                    """with changed as (
                         update analytics_history_media_r2_retirement_objects
                            set status='blocked',error_code='TARGET_IDENTITY_DRIFT',
                                updated_at=now()
                          where plan_sha256=$1 and status='planned'
                            and source_key_sha256=any($2::text[])
                        returning 1)
                       select count(*) from changed""",
                    args.predecessor_plan_sha256,
                    quarantine_hashes,
                )
            )
            if quarantined_count != len(quarantine_hashes):
                raise RuntimeError(
                    "target identity drift quarantine predecessor state changed"
                )
            live_reference_retained_count = int(
                await ledger.fetchval(
                    """with changed as (
                         update analytics_history_media_r2_retirement_objects o
                            set status='blocked',
                                error_code='LIVE_HISTORY_REFERENCE',updated_at=now()
                          where o.plan_sha256=$1 and o.status='planned'
                            and sha256(convert_to(o.source_key,'UTF8')) in (
                              select source_key_sha256
                                from bulk_retirement_live_source_hashes)
                        returning 1)
                       select count(*) from changed""",
                    args.predecessor_plan_sha256,
                )
            )
            if live_reference_retained_count != live_reference_count:
                raise RuntimeError(
                    "live History reference retention predecessor state changed"
                )
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
                     is_canary,asset_coordinate_count,disposition,is_retained,
                     status,outcome_counts)
                   values($1,$2,$3,$4,$5,$6,$7,$8,false,'pending','{}'::jsonb)""",
                [
                    (
                        manifest["plan_sha256"],
                        item["batch_no"],
                        item["object_count"],
                        item["total_bytes"],
                        item["rowset_sha256"],
                        item["is_canary"],
                        item["asset_coordinate_count"],
                        item["disposition"],
                    )
                    for item in batches
                ],
            )
            await ledger.execute(
                """insert into analytics_history_media_r2_retirement_objects(
                     plan_sha256,batch_no,object_no,source_name,source_key,
                     source_key_sha256,byte_size,source_etag,source_last_modified,
                     asset_count,archive_sha256,nas_bucket,nas_key,target_facts,
                     scope_asset_count,scope_facts,retirement_disposition,
                     status,error_code)
                   select $1,batch_no,object_no,source_name,source_key,
                          encode(sha256(
                            convert_to(source_name,'UTF8')||decode('00','hex')||
                            convert_to(source_key,'UTF8')),'hex'),
                          byte_size,source_etag,source_last_modified,asset_count,
                          '', '', '',target_facts,scope_asset_count,scope_facts,
                          retirement_disposition,'planned',null
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
                    "predecessor_plan_sha256": args.predecessor_plan_sha256,
                    "predecessor_retained_object_count": manifest[
                        "predecessor_retained_object_count"
                    ],
                    "predecessor_retained_asset_coordinate_count": manifest[
                        "predecessor_retained_asset_coordinate_count"
                    ],
                    "predecessor_quarantined_object_count": len(
                        quarantine_candidates
                    ),
                    "predecessor_quarantined_asset_coordinate_count": (
                        quarantine_asset_count
                    ),
                    "predecessor_quarantined_rowset_sha256": quarantine_rowset_sha,
                    "predecessor_live_reference_retained_object_count": (
                        live_reference_count
                    ),
                    "predecessor_live_reference_retained_asset_coordinate_count": (
                        live_reference_asset_count
                    ),
                    "predecessor_live_reference_retained_rowset_sha256": (
                        live_reference_rowset_sha
                    ),
                    "object_count": object_count,
                    "asset_coordinate_count": asset_count,
                    "batch_count": len(batches),
                    "rowset_sha256": rowset_sha,
                    "batches_sha256": manifest["batches_sha256"],
                    "manifest": str(output),
                },
                sort_keys=True,
            )
        )
    finally:
        if production is not None:
            await production.close()
        await ledger.close()


async def _plan_bulk_delete(args: argparse.Namespace) -> None:
    switch_plans = [str(value) for value in args.switch_plan_sha256]
    if len(switch_plans) != len(set(switch_plans)):
        raise ValueError("bulk retirement requires unique Switch plans")
    expected_counts = _expected_switch_counts(args.expected_switch_asset_count)
    if set(expected_counts) != set(switch_plans):
        raise ValueError("every bulk Switch plan requires one exact expected count")
    r2_config = _load_secure_config(Path(args.config))
    clear_proxy_environment()
    r2_transport = _r2_transport(r2_config)
    _validate_r2_transport_runtime(r2_transport)
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
        switch_batch_rows = await ledger.fetch(
            """select plan_sha256,batch_no,status,asset_count,rowset_sha256
                 from analytics_history_media_migration_plan_batches
                where plan_sha256=any($1::text[])
                order by plan_sha256,batch_no""",
            switch_plans,
        )
        switch_scope_facts = build_bulk_switch_scope_facts(
            plan_rows=[dict(row) for row in plan_rows],
            batch_rows=[dict(row) for row in switch_batch_rows],
            expected_counts=expected_counts,
        )
        asset_scope_sha, actual_counts, copy_plans = await _bulk_scope_fingerprint(
            ledger, sorted(switch_plans)
        )
        if actual_counts != expected_counts:
            raise RuntimeError("bulk retirement Switch asset counts changed")
        await _prepare_bulk_retirement_stage(
            ledger,
            sorted(switch_plans),
        )
        live_history_ref_object_count = await _bulk_production_has_live_refs(
            ledger, production
        )
        await _materialize_bulk_retirement_order(
            ledger,
            canary_size=args.canary_size,
            batch_size=args.batch_size,
        )
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
        disposition_rows = await ledger.fetch(
            """select retirement_disposition,count(*) object_count,
                      coalesce(sum(scope_asset_count),0) asset_coordinate_count
                 from bulk_retirement_ordered group by retirement_disposition"""
        )
        disposition_summary = {
            str(row["retirement_disposition"]): {
                "object_count": int(row["object_count"]),
                "asset_coordinate_count": int(row["asset_coordinate_count"]),
            }
            for row in disposition_rows
        }
        switch_scopes = [
            switch_scope_facts[plan_sha] for plan_sha in sorted(switch_plans)
        ]
        manifest: dict[str, Any] = {
            "schema": "allbot-history-media-r2-bulk-retirement-plan/v3",
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
            "deferred_live_history_ref_object_count": (
                live_history_ref_object_count
            ),
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
        for disposition in BULK_RETIREMENT_DISPOSITIONS:
            summary = disposition_summary.get(
                disposition, {"object_count": 0, "asset_coordinate_count": 0}
            )
            manifest[f"{disposition}_object_count"] = summary["object_count"]
            manifest[f"{disposition}_asset_coordinate_count"] = summary[
                "asset_coordinate_count"
            ]
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
                     is_canary,asset_coordinate_count,disposition,is_retained,
                     status,outcome_counts,started_at,completed_at)
                   values($1,$2,$3,$4,$5,$6,$7,$8,$9,
                          case when $9 then 'completed' else 'pending' end,
                          case when $9 then
                            jsonb_build_object(
                              'retained_source_is_target',$3::integer)
                            else '{}'::jsonb end,
                          case when $9 then now() else null end,
                          case when $9 then now() else null end)""",
                [
                    (
                        manifest["plan_sha256"],
                        item["batch_no"],
                        item["object_count"],
                        item["total_bytes"],
                        item["rowset_sha256"],
                        item["is_canary"],
                        item["asset_coordinate_count"],
                        item["disposition"],
                        item["is_retained"],
                    )
                    for item in batches
                ],
            )
            await ledger.execute(
                """insert into analytics_history_media_r2_retirement_objects(
                     plan_sha256,batch_no,object_no,source_name,source_key,
                     source_key_sha256,byte_size,source_etag,source_last_modified,
                     asset_count,archive_sha256,nas_bucket,nas_key,target_facts,
                     scope_asset_count,scope_facts,retirement_disposition,
                     status,error_code)
                   select $1,batch_no,object_no,source_name,source_key,
                          encode(sha256(
                            convert_to(source_name,'UTF8')||decode('00','hex')||
                            convert_to(source_key,'UTF8')),'hex'),
                          byte_size,source_etag,source_last_modified,asset_count,
                          '', '', '',target_facts,scope_asset_count,scope_facts,
                          retirement_disposition,
                          case when retirement_disposition='retained_target'
                               then 'blocked' else 'planned' end,
                          case when retirement_disposition='retained_target'
                               then 'SOURCE_IS_TARGET' else null end
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
                    "eligible_object_count": manifest["eligible_object_count"],
                    "deferred_object_count": manifest["deferred_object_count"],
                    "deferred_live_history_ref_object_count": (
                        live_history_ref_object_count
                    ),
                    "retained_target_count": disposition_summary.get(
                        "retained_target", {"object_count": 0}
                    )["object_count"],
                    "manifest": str(output),
                },
                sort_keys=True,
            )
        )
    finally:
        await production.close()
        await ledger.close()


async def _execute_delete(
    args: argparse.Namespace,
    *,
    execution_context: RetirementExecutionContext | None = None,
) -> None:
    owns_context = execution_context is None
    context = execution_context or await _open_retirement_execution_context(args)
    ledger = context.ledger
    r2_config = context.r2_config
    archive_config = context.archive_config
    head_concurrency = context.head_concurrency
    head_controller = context.head_controller
    r2_client = context.r2_client
    nas_client = context.nas_client
    batch_started = time.monotonic()
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
        _validate_retirement_execution_policy(manifest, args)
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
        phase_started = time.monotonic()
        batch_setup_and_rowset_ms = round(
            (phase_started - batch_started) * 1000
        )
        live_refs = await _live_reference_counts_with_retry(
            context, [str(item["source_key"]) for item in objects]
        )
        phase_timings = {
            "batch_setup_and_rowset_ms": batch_setup_and_rowset_ms,
            "live_reference_gate_ms": round(
                (time.monotonic() - phase_started) * 1000
            )
        }
        if live_refs:
            raise RuntimeError("retirement batch gained a live History reference")
        phase_started = time.monotonic()
        if await _retirement_has_blockers(ledger, objects):
            raise RuntimeError("retirement batch gained a Copy or Switch blocker")
        phase_timings["blocker_gate_ms"] = round(
            (time.monotonic() - phase_started) * 1000
        )
        phase_started = time.monotonic()
        recovered_missing = await _head_candidates(
            objects,
            r2_client=r2_client,
            r2_bucket=str(r2_config["target"]["bucket"]),
            nas_client=nas_client,
            concurrency=head_concurrency,
            allow_source_missing=True,
            phase="pre_delete",
            controller=head_controller,
            executor=context.requests.head_executor,
        )
        phase_timings["pre_delete_head_ms"] = round(
            (time.monotonic() - phase_started) * 1000
        )
        pre_delete_proof = _sha256_json(
            [_retirement_object_identity(item) for item in objects]
        )
        if pre_delete_proof != str(batch["rowset_sha256"]):
            raise RuntimeError("retirement pre-delete survivor proof changed")
        phase_started = time.monotonic()
        await _delete_sources(
            objects,
            r2_client=r2_client,
            r2_bucket=str(r2_config["target"]["bucket"]),
            concurrency=args.delete_concurrency,
            executor=context.requests.delete_executor,
        )
        phase_timings["delete_objects_ms"] = round(
            (time.monotonic() - phase_started) * 1000
        )
        phase_started = time.monotonic()
        verified_missing = await _head_source_candidates(
            objects,
            r2_client=r2_client,
            r2_bucket=str(r2_config["target"]["bucket"]),
            concurrency=head_concurrency,
            pre_delete_proof=pre_delete_proof,
            expected_pre_delete_proof=str(batch["rowset_sha256"]),
            phase="post_delete",
            controller=head_controller,
            executor=context.requests.head_executor,
        )
        phase_timings["post_delete_source_head_ms"] = round(
            (time.monotonic() - phase_started) * 1000
        )
        if verified_missing != len(objects):
            raise RuntimeError("old source still exists after delete")
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
                    "event": "retirement_batch_completed",
                    "deleted": len(objects),
                    "already_missing_recovered": recovered_missing,
                    "remaining_batches": remaining,
                    "phase_timings_ms": phase_timings,
                    "total_elapsed_ms": round(
                        (time.monotonic() - batch_started) * 1000
                    ),
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
        if owns_context:
            await context.close()


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
        r2_transport = _r2_transport(r2_config)
        _validate_r2_transport_runtime(r2_transport)
        validate_endpoint_route(r2_config["target"])
        actual_runtime = _retirement_runtime_identity(
            artifact_digest=args.artifact_digest,
            r2_config=r2_config,
            durability_basis=DURABILITY_R2_PERSISTENT_TARGET,
            archive_config=None,
        )
        if actual_runtime != manifest["runtime_identity"]:
            raise RuntimeError("bulk retirement runtime identity changed")
        _validate_retirement_execution_policy(manifest, args)
        switch_plans = [str(value) for value in manifest["parent_switch_plan_sha256s"]]
        expected_counts = {
            str(item["switch_plan_sha256"]): int(item["asset_coordinate_count"])
            for item in manifest["switch_scopes"]
        }
        switch_plan_rows = await ledger.fetch(
            """select plan_sha256,run_id,rowset_sha256,manifest from
                 analytics_history_media_migration_plans
                where plan_type='switch' and plan_sha256=any($1::text[])
                order by plan_sha256""",
            switch_plans,
        )
        switch_batch_rows = await ledger.fetch(
            """select plan_sha256,batch_no,status,asset_count,rowset_sha256
                 from analytics_history_media_migration_plan_batches
                where plan_sha256=any($1::text[])
                order by plan_sha256,batch_no""",
            switch_plans,
        )
        for row in switch_plan_rows:
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
        if {str(row["run_id"]) for row in switch_plan_rows} != {
            str(manifest["run_id"])
        }:
            raise RuntimeError("bulk retirement Switch run identity changed")
        actual_switch_scope_facts = build_bulk_switch_scope_facts(
            plan_rows=[dict(item) for item in switch_plan_rows],
            batch_rows=[dict(item) for item in switch_batch_rows],
            expected_counts=expected_counts,
        )
        actual_switch_scopes = [
            actual_switch_scope_facts[plan_sha] for plan_sha in sorted(switch_plans)
        ]
        stored_switch_scopes = list(manifest["switch_scopes"])
        if any("terminal_scope_mode" in item for item in stored_switch_scopes):
            switch_scope_identity_changed = (
                actual_switch_scopes != stored_switch_scopes
            )
        else:
            switch_scope_identity_changed = [
                {
                    "switch_plan_sha256": item["switch_plan_sha256"],
                    "asset_coordinate_count": item["asset_coordinate_count"],
                    "rowset_sha256": item["rowset_sha256"],
                }
                for item in actual_switch_scopes
            ] != stored_switch_scopes
        scope_sha, counts, copy_plans = await _bulk_scope_fingerprint(
            ledger, switch_plans
        )
        if (
            switch_scope_identity_changed
            or scope_sha != manifest["asset_scope_sha256"]
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
            """select batch_no,is_canary,disposition,is_retained,status,
                      object_count,asset_coordinate_count,total_bytes,rowset_sha256
                 from analytics_history_media_r2_retirement_batches
                where plan_sha256=$1 order by batch_no""",
            args.plan_sha256,
        )
        batches = [
            {
                "batch_no": int(item["batch_no"]),
                "is_canary": bool(item["is_canary"]),
                "disposition": str(item["disposition"]),
                "is_retained": bool(item["is_retained"]),
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
            or any(
                item["is_retained"] != (item["disposition"] == "retained_target")
                for item in batches
            )
            or any(
                item["disposition"] == "retained_target"
                and str(batch_rows[index]["status"]) != "completed"
                for index, item in enumerate(batches)
            )
        ):
            raise RuntimeError("bulk retirement batch identities changed")
        disposition_rows = await ledger.fetch(
            """select retirement_disposition,count(*) object_count,
                      coalesce(sum(scope_asset_count),0) asset_coordinate_count,
                      count(*) filter(where status='blocked') blocked_count,
                      count(*) filter(where error_code='SOURCE_IS_TARGET')
                        retained_error_count
                 from analytics_history_media_r2_retirement_objects
                where plan_sha256=$1 group by retirement_disposition""",
            args.plan_sha256,
        )
        disposition_summary = {
            str(item["retirement_disposition"]): item for item in disposition_rows
        }
        for disposition in BULK_RETIREMENT_DISPOSITIONS:
            summary = disposition_summary.get(disposition)
            stored_objects = int(summary["object_count"]) if summary else 0
            stored_assets = int(summary["asset_coordinate_count"]) if summary else 0
            if (
                stored_objects != int(manifest[f"{disposition}_object_count"])
                or stored_assets
                != int(manifest[f"{disposition}_asset_coordinate_count"])
            ):
                raise RuntimeError("bulk retirement disposition coverage changed")
        retained_summary = disposition_summary.get("retained_target")
        retained_count = int(manifest["retained_target_object_count"])
        if retained_count and (
            retained_summary is None
            or int(retained_summary["blocked_count"]) != retained_count
            or int(retained_summary["retained_error_count"]) != retained_count
        ):
            raise RuntimeError("bulk retirement retained target evidence changed")
        await _validate_bulk_successor_predecessor(ledger, manifest)
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
        await _validate_bulk_successor_predecessor(ledger, manifest)
        summary = await ledger.fetchrow(
            """select count(*) object_count,
                      count(*) filter(where status='deleted') deleted_count,
                      count(*) filter(where status='blocked') blocked_count,
                      count(*) filter(where status='blocked'
                                        and retirement_disposition='retained_target'
                                        and error_code='SOURCE_IS_TARGET')
                        retained_target_count,
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
            or int(summary["deleted_count"])
            != int(manifest["object_count"])
            - int(manifest["retained_target_object_count"])
            or int(summary["blocked_count"])
            != int(manifest["retained_target_object_count"])
            or int(summary["retained_target_count"])
            != int(manifest["retained_target_object_count"])
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
    context = await _open_retirement_execution_context(args)
    try:
        while True:
            await _execute_delete(args, execution_context=context)
            state = await context.ledger.fetchrow(
                """select p.status,
                          count(*) filter(where b.status<>'completed')
                            remaining_batches
                     from analytics_history_media_r2_retirement_plans p
                     join analytics_history_media_r2_retirement_batches b
                       using(plan_sha256)
                    where p.plan_sha256=$1 group by p.status""",
                args.plan_sha256,
            )
            canary = await context.ledger.fetchrow(
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
                await _finalize_bulk_delete(args.plan_sha256, manifest)
                return
    except Exception:
        await _mark_retirement_plan_paused(args.plan_sha256)
        raise
    finally:
        await context.close()


def _bounded_delete_concurrency(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_DELETE_CONCURRENCY:
        raise argparse.ArgumentTypeError("delete concurrency must be between 1 and 8")
    return parsed


def _bounded_retirement_head_concurrency(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_RETIREMENT_HEAD_CONCURRENCY:
        raise argparse.ArgumentTypeError(
            "retirement HEAD concurrency must be between 1 and 128"
        )
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
    bulk_successor = commands.add_parser("plan-bulk-delete-successor")
    bulk_successor.add_argument("--predecessor-plan-sha256", required=True)
    bulk_successor.add_argument("--config", required=True)
    bulk_successor.add_argument("--artifact-digest", required=True)
    bulk_successor.add_argument("--canary-size", type=int, default=100)
    bulk_successor.add_argument("--batch-size", type=int, default=1000)
    bulk_successor.add_argument(
        "--retain-target-identity-drift-source-sha256",
        action="append",
        default=[],
        help=(
            "exact old-source identity hash to re-HEAD and retain because its "
            "persistent target identity drifted"
        ),
    )
    bulk_successor.add_argument("--output", required=True)
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
        "--head-concurrency",
        type=_bounded_retirement_head_concurrency,
        default=DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
    )
    execute.add_argument(
        "--delete-concurrency",
        type=_bounded_delete_concurrency,
        default=DEFAULT_RETIREMENT_DELETE_CONCURRENCY,
    )
    bulk_execute = commands.add_parser("execute-bulk-delete")
    bulk_execute.add_argument("--plan-sha256", required=True)
    bulk_execute.add_argument("--confirm", required=True)
    bulk_execute.add_argument("--config", required=True)
    bulk_execute.add_argument("--artifact-digest", required=True)
    bulk_execute.add_argument(
        "--head-concurrency",
        type=_bounded_retirement_head_concurrency,
        default=DEFAULT_RETIREMENT_HEAD_CONCURRENCY,
    )
    bulk_execute.add_argument(
        "--delete-concurrency",
        type=_bounded_delete_concurrency,
        default=DEFAULT_RETIREMENT_DELETE_CONCURRENCY,
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
    elif args.command == "plan-bulk-delete-successor":
        if not 1 <= args.canary_size <= args.batch_size <= RETIREMENT_BATCH_SIZE:
            raise ValueError("bulk retirement successor batch sizes are invalid")
        await _plan_bulk_delete_successor(args)
    elif args.command == "execute-delete":
        await _execute_delete(args)
    elif args.command == "execute-bulk-delete":
        await _execute_bulk_delete(args)


def main() -> None:
    asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    main()
