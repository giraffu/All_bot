#!/usr/bin/env python3
"""Run frozen History Switch batches near production through signed receipts.

The local coordinator is the only writer of the migration ledger.  The cloud
worker consumes an HMAC-bound task, connects only to production PostgreSQL, and
returns a signed receipt after the production transaction commits.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.history_media_r2_cloud_copy import (
    _canonical_json,
    _load_signing_key,
    read_signed_document,
    write_signed_document,
)
from scripts.history_media_r2_migration import (
    SWITCH_HISTORY_BATCH_SIZE,
    _connect_env,
    _dsn,
    _ensure_schema,
    _finalize_plan_batch,
    _history_record_refs,
    _insert_plan_with_batches,
    _load_plan,
    _plan_row,
    _plan_rows,
    _predecessor_switch_identity,
    _runtime_identity,
    _sha256_json,
    _stream_plan_rowset,
    normalized_history_cas_state,
    replace_asset_reference,
    validate_switch_gate,
)

CLOUD_SWITCH_PROTOCOL = "history-r2-cloud-switch/v1"
SCHEMA_TASK = "allbot-history-r2-cloud-switch-task/v1"
SCHEMA_RECEIPT = "allbot-history-r2-cloud-switch-receipt/v1"
SCHEMA_PLAN = "allbot-history-media-r2-cloud-switch-successor-plan/v1"

CLOUD_SWITCH_TASK_DDL = """
create table if not exists analytics_history_media_r2_cloud_switch_plan_sessions (
    plan_sha256 char(64) primary key references analytics_history_media_migration_plans(plan_sha256),
    run_id uuid not null references analytics_history_media_migration_runs(id),
    worker_id text not null,
    artifact_digest text not null,
    production_route_sha256 char(64) not null,
    preflight_rowset_sha256 char(64) not null,
    predecessor_plans_sha256 char(64) not null,
    status text not null check (status in ('active','completed','failed')),
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);
create table if not exists analytics_history_media_r2_cloud_switch_tasks (
    task_id uuid primary key,
    run_id uuid not null references analytics_history_media_migration_runs(id),
    plan_sha256 char(64) not null references analytics_history_media_migration_plans(plan_sha256),
    worker_id text not null,
    artifact_digest text not null,
    production_route_sha256 char(64) not null,
    batch_no integer not null,
    batch_rowset_sha256 char(64) not null,
    cas_state_sha256 char(64) not null,
    ledger_ids bigint[] not null,
    bundle_sha256 char(64) not null,
    status text not null check (status in ('exported','committed','expired','superseded','failed')),
    lease_expires_at timestamptz not null,
    receipt_sha256 char(64),
    outcome_counts jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);
create index if not exists ix_history_media_r2_cloud_switch_tasks_plan_status
  on analytics_history_media_r2_cloud_switch_tasks(plan_sha256,status,batch_no);
"""

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ARTIFACT = re.compile(r"sha256:[0-9a-f]{64}")
_WORKER = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")


def _require_sha256(value: str, label: str) -> str:
    if not _SHA256.fullmatch(str(value)):
        raise ValueError(f"{label} must be an exact sha256")
    return str(value)


def _validate_execution_identity(
    *, artifact_digest: str, worker_id: str, production_route_sha256: str
) -> None:
    if not _ARTIFACT.fullmatch(str(artifact_digest)):
        raise ValueError("cloud Switch artifact digest is invalid")
    if not _WORKER.fullmatch(str(worker_id)):
        raise ValueError("cloud Switch worker identity is invalid")
    _require_sha256(production_route_sha256, "cloud Switch production route")


def production_route_sha256_from_dsn(dsn: str) -> str:
    """Fingerprint the non-secret production route and database identity."""

    parsed = urlsplit(dsn.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("production database route is invalid")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    identity = {
        "host": parsed.hostname.lower(),
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
        "ssl": bool(query.get("ssl") or query.get("sslmode")),
    }
    return _sha256_json(identity)


def _task_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "history_id": int(row["history_id"]),
        "role": str(row["role"]),
        "ordinal": int(row["ordinal"]),
        "original_ref": str(row["original_ref"]),
        "target_key": str(row["target_key"]),
        "switch_plan_sha256": (
            str(row["switch_plan_sha256"]) if row.get("switch_plan_sha256") else None
        ),
        "switch_completed_at": (
            row["switch_completed_at"].astimezone(timezone.utc).isoformat()
            if isinstance(row.get("switch_completed_at"), datetime)
            else row.get("switch_completed_at")
        ),
        "selected": bool(row.get("selected")),
    }


def _task_rows_sha256(rows: Iterable[dict[str, Any]]) -> str:
    return _sha256_json(list(rows))


def build_switch_task_bundle(
    *,
    rows: Iterable[dict[str, Any]],
    plan_sha256: str,
    predecessor_plan_sha256: str,
    artifact_digest: str,
    worker_id: str,
    production_route_sha256: str,
    batch_no: int,
    batch_rowset_sha256: str,
    cas_state_sha256: str,
    task_id: str | None = None,
    lease_expires_at: datetime | None = None,
) -> dict[str, Any]:
    _require_sha256(plan_sha256, "cloud Switch plan")
    _require_sha256(predecessor_plan_sha256, "cloud Switch predecessor plan")
    _require_sha256(batch_rowset_sha256, "cloud Switch batch rowset")
    _require_sha256(cas_state_sha256, "cloud Switch CAS state")
    _validate_execution_identity(
        artifact_digest=artifact_digest,
        worker_id=worker_id,
        production_route_sha256=production_route_sha256,
    )
    normalized = sorted(
        (_task_row(dict(row)) for row in rows),
        key=lambda row: (row["history_id"], row["role"], row["ordinal"]),
    )
    if not normalized:
        raise ValueError("cloud Switch task cannot be empty")
    coordinates = [
        (int(row["history_id"]), str(row["role"]), int(row["ordinal"]))
        for row in normalized
    ]
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("cloud Switch task contains duplicate coordinates")
    selected = [row for row in normalized if row["selected"]]
    if not selected or any(
        row["switch_plan_sha256"] != plan_sha256 for row in selected
    ):
        raise ValueError("cloud Switch selected ledger ownership changed")
    history_ids = sorted({int(row["history_id"]) for row in selected})
    if any(int(row["history_id"]) not in history_ids for row in normalized):
        raise ValueError("cloud Switch task contains unrelated History evidence")
    expires_at = lease_expires_at or datetime.now(timezone.utc) + timedelta(hours=1)
    if expires_at.tzinfo is None:
        raise ValueError("cloud Switch task lease must be timezone-aware")
    return {
        "schema": SCHEMA_TASK,
        "protocol": CLOUD_SWITCH_PROTOCOL,
        "task_id": task_id or str(uuid.uuid4()),
        "plan_sha256": plan_sha256,
        "predecessor_plan_sha256": predecessor_plan_sha256,
        "artifact_digest": artifact_digest,
        "worker_id": worker_id,
        "production_route_sha256": production_route_sha256,
        "batch_no": int(batch_no),
        "batch_rowset_sha256": batch_rowset_sha256,
        "cas_state_sha256": cas_state_sha256,
        "lease_expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "asset_count": len(selected),
        "history_count": len(history_ids),
        "history_ids": history_ids,
        "ledger_ids": sorted(int(row["id"]) for row in selected),
        "ledger_evidence_sha256": _task_rows_sha256(normalized),
        "rows": normalized,
    }


def _bundle_sha256(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(bundle)).hexdigest()


def _task_lease_datetime(bundle: dict[str, Any]) -> datetime:
    """Return the signed task lease in asyncpg's timestamptz value type."""

    try:
        expires_at = datetime.fromisoformat(
            str(bundle["lease_expires_at"]).replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("cloud Switch task lease changed") from None
    if expires_at.tzinfo is None:
        raise ValueError("cloud Switch task lease changed")
    return expires_at.astimezone(timezone.utc)


def validate_switch_task_gate(
    bundle: dict[str, Any],
    *,
    plan_sha256: str,
    confirm: str,
    artifact_digest: str,
    worker_id: str,
    production_route_sha256: str,
) -> None:
    _validate_execution_identity(
        artifact_digest=artifact_digest,
        worker_id=worker_id,
        production_route_sha256=production_route_sha256,
    )
    identity = (
        bundle.get("schema") == SCHEMA_TASK
        and bundle.get("protocol") == CLOUD_SWITCH_PROTOCOL
        and bundle.get("plan_sha256") == plan_sha256
        and bundle.get("artifact_digest") == artifact_digest
        and bundle.get("worker_id") == worker_id
        and bundle.get("production_route_sha256") == production_route_sha256
    )
    if not identity:
        raise ValueError("cloud Switch task identity changed")
    if confirm != f"SWITCH_HISTORY_MEDIA_{plan_sha256}":
        raise ValueError("exact cloud Switch confirmation is required")
    expires_at = _task_lease_datetime(bundle)
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("cloud Switch task lease expired")
    rows = [_task_row(dict(row)) for row in bundle.get("rows", [])]
    if _task_rows_sha256(rows) != bundle.get("ledger_evidence_sha256") or sorted(
        int(row["id"]) for row in rows if row["selected"]
    ) != list(bundle.get("ledger_ids") or []):
        raise ValueError("cloud Switch task row coverage changed")


def _rows_by_history(bundle: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for original in bundle["rows"]:
        row = dict(original)
        grouped.setdefault(int(row["history_id"]), []).append(row)
    return grouped


def switch_task_cas_sha256(
    bundle: dict[str, Any], histories: Iterable[dict[str, Any]]
) -> str:
    grouped = _rows_by_history(bundle)
    states: list[dict[str, Any]] = []
    history_list = sorted(
        (dict(row) for row in histories), key=lambda row: int(row["id"])
    )
    if [int(row["id"]) for row in history_list] != list(bundle["history_ids"]):
        raise RuntimeError("cloud Switch History rowset changed")
    for history in history_list:
        history_id = int(history["id"])
        states.append(
            normalized_history_cas_state(
                history_id,
                _history_record_refs(history),
                grouped.get(history_id, []),
                allow_selected_target=True,
            )
        )
    return _sha256_json(states)


def _post_state_sha256(histories: Iterable[dict[str, Any]]) -> str:
    states = []
    for history in sorted(
        (dict(row) for row in histories), key=lambda row: int(row["id"])
    ):
        refs = _history_record_refs(history)
        states.append(
            {
                "history_id": int(history["id"]),
                "assets": [
                    {"role": role, "ordinal": ordinal, "value": value}
                    for (role, ordinal), value in sorted(refs.items())
                ],
            }
        )
    return _sha256_json(states)


async def apply_switch_task_to_production(
    production: Any, bundle: dict[str, Any]
) -> dict[str, Any]:
    history_ids = [int(value) for value in bundle["history_ids"]]
    grouped = _rows_by_history(bundle)
    histories_updated = 0
    async with production.transaction():
        await production.execute("set local lock_timeout = '10s'")
        records = await production.fetch(
            """select id,input_file,output_file,extra_outputs from history
                 where id=any($1::integer[]) order by id for update""",
            history_ids,
        )
        histories = [dict(row) for row in records]
        if switch_task_cas_sha256(bundle, histories) != bundle["cas_state_sha256"]:
            raise RuntimeError("cloud Switch production CAS state changed")
        for current in histories:
            history_id = int(current["id"])
            extras = current.get("extra_outputs")
            if isinstance(extras, str):
                try:
                    current["extra_outputs"] = json.loads(extras)
                except json.JSONDecodeError:
                    current["extra_outputs"] = {}
            selected = [row for row in grouped[history_id] if row["selected"]]
            current_refs = _history_record_refs(current)
            changed = False
            for asset in selected:
                coord = (str(asset["role"]), int(asset["ordinal"]))
                if current_refs[coord] == str(asset["target_key"]):
                    continue
                replace_asset_reference(
                    current, coord[0], coord[1], str(asset["target_key"])
                )
                current_refs[coord] = str(asset["target_key"])
                changed = True
            if changed:
                result = await production.execute(
                    """update history set input_file=$2,output_file=$3,
                         extra_outputs=$4::jsonb where id=$1""",
                    history_id,
                    current.get("input_file"),
                    current.get("output_file"),
                    json.dumps(current.get("extra_outputs") or {}),
                )
                if result != "UPDATE 1":
                    raise RuntimeError("cloud Switch History CAS update changed")
                histories_updated += 1
        post_state_sha256 = _post_state_sha256(histories)
    return {
        "assets": int(bundle["asset_count"]),
        "histories": int(bundle["history_count"]),
        "histories_updated": histories_updated,
        "post_state_sha256": post_state_sha256,
    }


def build_switch_receipt(
    bundle: dict[str, Any], *, histories_updated: int, post_state_sha256: str
) -> dict[str, Any]:
    _require_sha256(post_state_sha256, "cloud Switch post state")
    receipt = {
        "schema": SCHEMA_RECEIPT,
        "protocol": bundle["protocol"],
        "task_id": bundle["task_id"],
        "plan_sha256": bundle["plan_sha256"],
        "predecessor_plan_sha256": bundle["predecessor_plan_sha256"],
        "artifact_digest": bundle["artifact_digest"],
        "worker_id": bundle["worker_id"],
        "production_route_sha256": bundle["production_route_sha256"],
        "batch_no": bundle["batch_no"],
        "batch_rowset_sha256": bundle["batch_rowset_sha256"],
        "cas_state_sha256": bundle["cas_state_sha256"],
        "lease_expires_at": bundle["lease_expires_at"],
        "ledger_evidence_sha256": bundle["ledger_evidence_sha256"],
        "asset_count": bundle["asset_count"],
        "history_count": bundle["history_count"],
        "histories_updated": int(histories_updated),
        "post_state_sha256": post_state_sha256,
        "production_committed": True,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    return receipt


def validate_switch_receipt(bundle: dict[str, Any], receipt: dict[str, Any]) -> None:
    identity_fields = (
        "protocol",
        "task_id",
        "plan_sha256",
        "predecessor_plan_sha256",
        "artifact_digest",
        "worker_id",
        "production_route_sha256",
        "batch_no",
        "batch_rowset_sha256",
        "cas_state_sha256",
        "lease_expires_at",
        "ledger_evidence_sha256",
        "asset_count",
        "history_count",
    )
    if receipt.get("schema") != SCHEMA_RECEIPT or any(
        receipt.get(field) != bundle.get(field) for field in identity_fields
    ):
        raise ValueError("cloud Switch receipt identity changed")
    if receipt.get("production_committed") is not True:
        raise ValueError("cloud Switch receipt lacks production commit proof")
    if (
        not 0
        <= int(receipt.get("histories_updated", -1))
        <= int(bundle["history_count"])
    ):
        raise ValueError("cloud Switch receipt outcome changed")
    _require_sha256(
        str(receipt.get("post_state_sha256") or ""), "cloud Switch post state"
    )
    expected = hashlib.sha256(
        _canonical_json(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
    ).hexdigest()
    if receipt.get("receipt_sha256") != expected:
        raise ValueError("cloud Switch receipt identity changed")


def build_cloud_switch_successor_manifest(
    *,
    predecessor_manifest: dict[str, Any],
    retained_rows: Iterable[dict[str, Any]],
    successor_rows: Iterable[dict[str, Any]],
    batches: Iterable[dict[str, Any]],
    artifact_digest: str,
    worker_id: str,
    production_route_sha256: str,
    cloud_switch_script_sha256: str,
    predecessor_switch_plan_count: int = 0,
    predecessor_switch_plans_sha256: str | None = None,
) -> dict[str, Any]:
    predecessor_plan_sha256 = _require_sha256(
        str(predecessor_manifest["plan_sha256"]), "predecessor Switch plan"
    )
    _validate_execution_identity(
        artifact_digest=artifact_digest,
        worker_id=worker_id,
        production_route_sha256=production_route_sha256,
    )
    _require_sha256(cloud_switch_script_sha256, "cloud Switch script")
    retained = [dict(row) for row in retained_rows]
    successor = [dict(row) for row in successor_rows]
    retained_ids = {int(row["id"]) for row in retained}
    successor_ids = {int(row["id"]) for row in successor}
    if len(retained_ids) != len(retained) or len(successor_ids) != len(successor):
        raise RuntimeError("cloud Switch successor contains duplicate assets")
    if retained_ids & successor_ids:
        raise RuntimeError("cloud Switch successor overlaps retained assets")
    root_count = int(predecessor_manifest["count"])
    if len(retained) + len(successor) != root_count:
        raise RuntimeError(
            "cloud Switch successor does not conserve predecessor assets"
        )
    canonical_batches = sorted(
        (dict(batch) for batch in batches), key=lambda batch: int(batch["batch_no"])
    )
    if sum(int(batch["asset_count"]) for batch in canonical_batches) != len(successor):
        raise RuntimeError("cloud Switch successor batches changed")
    if not successor:
        raise RuntimeError("cloud Switch predecessor has no remaining assets")
    predecessor_chain = list(
        predecessor_manifest.get("predecessor_switch_plan_sha256s", [])
    ) + [predecessor_plan_sha256]
    predecessor_identity_sha = predecessor_switch_plans_sha256 or _sha256_json(
        predecessor_chain
    )
    _require_sha256(predecessor_identity_sha, "predecessor Switch identity")
    manifest: dict[str, Any] = {
        "schema": SCHEMA_PLAN,
        "run_id": str(predecessor_manifest["run_id"]),
        "history_watermark": int(predecessor_manifest["history_watermark"]),
        "parent_copy_plan_sha256": predecessor_manifest["parent_copy_plan_sha256"],
        "copy_chain_plan_sha256s": list(
            predecessor_manifest.get("copy_chain_plan_sha256s", [])
        ),
        "predecessor_switch_plan_sha256": predecessor_plan_sha256,
        "predecessor_switch_plan_sha256s": predecessor_chain,
        "root_switch_asset_count": root_count,
        "retained_asset_count": len(retained),
        "retained_history_count": len({int(row["history_id"]) for row in retained}),
        "retained_batch_count": int(
            predecessor_manifest.get("completed_batch_count", 0)
        ),
        "retained_rowset_sha256": _sha256_json(sorted(retained_ids)),
        "count": len(successor),
        "bytes": sum(int(row.get("byte_size") or 0) for row in successor),
        "history_count": len({int(row["history_id"]) for row in successor}),
        "batch_count": len(canonical_batches),
        "history_batch_size": SWITCH_HISTORY_BATCH_SIZE,
        "rowset_sha256": _sha256_json(_plan_rows(successor)),
        "batches_sha256": _sha256_json(canonical_batches),
        "intersection_asset_count": 0,
        "conserved_asset_count": len(retained) + len(successor),
        "predecessor_switch_plan_count": int(predecessor_switch_plan_count),
        "predecessor_switch_plans_sha256": predecessor_identity_sha,
        "runtime_identity": _runtime_identity(artifact_digest=artifact_digest),
        "switch_execution": {
            "mode": "cloud_receipt",
            "protocol": CLOUD_SWITCH_PROTOCOL,
            "worker_id": worker_id,
            "production_route_sha256": production_route_sha256,
            "cloud_switch_script_sha256": cloud_switch_script_sha256,
        },
    }
    if predecessor_manifest.get("seed_scope") is not None:
        manifest["seed_scope"] = dict(predecessor_manifest["seed_scope"])
    manifest["plan_sha256"] = _sha256_json(manifest)
    return manifest


async def build_successor_switch_batches(
    production: Any,
    ledger: Any,
    *,
    run_id: Any,
    successor_rows: Iterable[dict[str, Any]],
    history_batch_size: int = SWITCH_HISTORY_BATCH_SIZE,
    prefetch_history_count: int = SWITCH_HISTORY_BATCH_SIZE * 10,
) -> list[dict[str, Any]]:
    """Freeze exact per-batch CAS with fewer production round trips."""

    if history_batch_size <= 0 or prefetch_history_count < history_batch_size:
        raise ValueError("cloud Switch CAS prefetch size is invalid")
    ordered = [dict(row) for row in successor_rows]
    logical_rows: list[list[dict[str, Any]]] = []
    batch_rows: list[dict[str, Any]] = []
    batch_history_ids: list[int] = []
    for row in ordered:
        history_id = int(row["history_id"])
        if (
            batch_history_ids
            and history_id != batch_history_ids[-1]
            and len(batch_history_ids) >= history_batch_size
        ):
            logical_rows.append(batch_rows)
            batch_rows = []
            batch_history_ids = []
        if not batch_history_ids or history_id != batch_history_ids[-1]:
            batch_history_ids.append(history_id)
        batch_rows.append(row)
    if batch_rows:
        logical_rows.append(batch_rows)

    batches: list[dict[str, Any]] = []
    offset = 0
    while offset < len(logical_rows):
        window: list[list[dict[str, Any]]] = []
        window_history_ids: list[int] = []
        while offset < len(logical_rows):
            candidate = logical_rows[offset]
            candidate_history_ids = list(
                dict.fromkeys(int(row["history_id"]) for row in candidate)
            )
            if (
                window
                and len(window_history_ids) + len(candidate_history_ids)
                > prefetch_history_count
            ):
                break
            window.append(candidate)
            window_history_ids.extend(candidate_history_ids)
            offset += 1

        production_refs = await production.fetch(
            """with selected_history as (
                   select h.id,h.input_file,h.output_file,h.extra_outputs
                     from history h
                    where h.id between $1 and $2
                 ), reference_coordinates as (
                   select h.id history_id,'input'::text role,
                          (input_ref.ordinality-1)::integer ordinal,
                          btrim(input_ref.value) value
                     from selected_history h
                     cross join lateral unnest(
                       string_to_array(coalesce(h.input_file,''),'|')
                     ) with ordinality input_ref(value,ordinality)
                    where btrim(input_ref.value)<>''
                   union all
                   select h.id,'output'::text,0,h.output_file
                     from selected_history h
                    where btrim(coalesce(h.output_file,''))<>''
                   union all
                   select h.id,'extra:'||extra.key,
                          (path.ordinality-1)::integer,
                          path.value #>> '{}'
                     from selected_history h
                     cross join lateral jsonb_each(
                       coalesce(h.extra_outputs::jsonb,'{}'::jsonb)
                     ) extra
                     cross join lateral jsonb_path_query(
                       extra.value,'strict $.**.path'
                     ) with ordinality path(value,ordinality)
                    where jsonb_typeof(path.value)='string'
                      and btrim(path.value #>> '{}')<>''
                 )
                 select history_id,role,ordinal,value
                   from reference_coordinates
                  order by history_id,role,ordinal""",
            min(window_history_ids),
            max(window_history_ids),
        )
        selected_history_ids = set(window_history_ids)
        current_refs_by_history: dict[int, dict[tuple[str, int], str]] = {}
        for record in production_refs:
            history_id = int(record["history_id"])
            if history_id not in selected_history_ids:
                continue
            coord = (str(record["role"]), int(record["ordinal"]))
            refs = current_refs_by_history.setdefault(history_id, {})
            if coord in refs:
                raise RuntimeError("cloud Switch planning coordinate duplicated")
            refs[coord] = str(record["value"])
        if set(current_refs_by_history) != selected_history_ids:
            raise RuntimeError("cloud Switch planning History row disappeared")
        ledger_records = await ledger.fetch(
            """select id,history_id,role,ordinal,original_ref,target_key,
                      switch_plan_sha256,switch_completed_at
                 from analytics_history_media_r2_migrations
                where run_id=$1 and history_id=any($2::integer[])
                order by history_id,role,ordinal""",
            run_id,
            window_history_ids,
        )
        selected_ids = {
            int(row["id"]) for logical_batch in window for row in logical_batch
        }
        ledger_by_history: dict[int, list[dict[str, Any]]] = {}
        for record in ledger_records:
            row = dict(record)
            row["selected"] = int(row["id"]) in selected_ids
            ledger_by_history.setdefault(int(row["history_id"]), []).append(row)

        for logical_batch in window:
            history_ids = list(
                dict.fromkeys(int(row["history_id"]) for row in logical_batch)
            )
            states = [
                normalized_history_cas_state(
                    history_id,
                    current_refs_by_history[history_id],
                    ledger_by_history.get(history_id, []),
                    allow_selected_target=True,
                )
                for history_id in history_ids
            ]
            batches.append(
                _finalize_plan_batch(
                    batch_no=len(batches),
                    rows=logical_batch,
                    cas_state_sha256=_sha256_json(states),
                    row_transform=_plan_row,
                )
            )
    return batches


async def _plan_successor(args: argparse.Namespace) -> None:
    _validate_execution_identity(
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
        production_route_sha256=args.production_route_sha256,
    )
    ledger = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    production = await _connect_env("PRODUCTION_DATABASE_URL")
    try:
        await _ensure_schema(ledger)
        await ledger.execute(CLOUD_SWITCH_TASK_DDL)
        run_id, predecessor = await _load_plan(
            ledger, args.predecessor_plan_sha256, "switch"
        )
        if predecessor.get("schema") not in {
            "allbot-history-media-r2-switch-plan/v2",
            SCHEMA_PLAN,
        }:
            raise RuntimeError("cloud Switch successor requires a current Switch plan")
        rows = [
            dict(row)
            for row in await ledger.fetch(
                """select * from analytics_history_media_r2_migrations
                     where run_id=$1 and switch_plan_sha256=$2
                     order by history_id,role,ordinal""",
                run_id,
                args.predecessor_plan_sha256,
            )
        ]
        retained = [row for row in rows if row.get("switch_completed_at")]
        successor = [row for row in rows if not row.get("switch_completed_at")]
        if any(row.get("status") != "copied_verified" for row in successor):
            raise RuntimeError("cloud Switch successor contains an ineligible asset")
        batches = await build_successor_switch_batches(
            production,
            ledger,
            run_id=run_id,
            successor_rows=successor,
        )
        predecessor_count, predecessor_sha = await _predecessor_switch_identity(
            ledger, run_id
        )
        completed_batch_count = int(
            await ledger.fetchval(
                """select count(*) from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status='completed'""",
                args.predecessor_plan_sha256,
            )
        )
        predecessor_for_successor = dict(predecessor)
        predecessor_for_successor["completed_batch_count"] = completed_batch_count
        script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        manifest = build_cloud_switch_successor_manifest(
            predecessor_manifest=predecessor_for_successor,
            retained_rows=retained,
            successor_rows=successor,
            batches=batches,
            artifact_digest=args.artifact_digest,
            worker_id=args.worker_id,
            production_route_sha256=args.production_route_sha256,
            cloud_switch_script_sha256=script_sha,
            predecessor_switch_plan_count=predecessor_count,
            predecessor_switch_plans_sha256=predecessor_sha,
        )
        async with ledger.transaction():
            await ledger.execute(
                "select pg_advisory_xact_lock(hashtext($1))",
                args.predecessor_plan_sha256,
            )
            locked_batches = await ledger.fetch(
                """select status from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 order by batch_no for update""",
                args.predecessor_plan_sha256,
            )
            if not locked_batches or any(
                row["status"] not in {"pending", "completed"} for row in locked_batches
            ):
                raise RuntimeError("cloud Switch predecessor is not safely stopped")
            current = await ledger.fetchrow(
                """select count(*) filter(where switch_completed_at is not null)::bigint retained,
                          count(*) filter(where switch_completed_at is null)::bigint remaining
                     from analytics_history_media_r2_migrations
                    where run_id=$1 and switch_plan_sha256=$2""",
                run_id,
                args.predecessor_plan_sha256,
            )
            if int(current["retained"]) != len(retained) or int(
                current["remaining"]
            ) != len(successor):
                raise RuntimeError("cloud Switch predecessor frontier changed")
            await _insert_plan_with_batches(
                ledger, manifest=manifest, plan_type="switch", batches=batches
            )
            await ledger.execute(
                """update analytics_history_media_migration_plan_batches
                      set status='superseded',updated_at=now()
                    where plan_sha256=$1 and status<>'completed'""",
                args.predecessor_plan_sha256,
            )
            updated = await ledger.execute(
                """update analytics_history_media_r2_migrations
                      set switch_plan_sha256=$3,updated_at=now()
                    where run_id=$1 and switch_plan_sha256=$2
                      and switch_completed_at is null and status='copied_verified'""",
                run_id,
                args.predecessor_plan_sha256,
                manifest["plan_sha256"],
            )
            if updated != f"UPDATE {len(successor)}":
                raise RuntimeError("cloud Switch successor reassignment changed")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_json(manifest) + b"\n")
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "plan_sha256": manifest["plan_sha256"],
                    "predecessor_plan_sha256": args.predecessor_plan_sha256,
                    "retained_assets": len(retained),
                    "successor_assets": len(successor),
                    "successor_histories": manifest["history_count"],
                    "successor_batches": len(batches),
                    "rowset_sha256": manifest["rowset_sha256"],
                    "batches_sha256": manifest["batches_sha256"],
                },
                sort_keys=True,
            )
        )
    finally:
        await production.close()
        await ledger.close()


async def _validate_plan_preflight(
    ledger: Any, *, run_id: uuid.UUID, manifest: dict[str, Any]
) -> None:
    rowset_sha, count, _counts, _bytes, _diagnostics = await _stream_plan_rowset(
        ledger,
        """select id,history_id,role,ordinal,original_ref,target_key,
                  source_name,source_key,source_last_modified,source_etag,source_sha256,
                  target_sha256,byte_size,status,history_manifest_sha256
             from analytics_history_media_r2_migrations
            where run_id=$1 and switch_plan_sha256=$2
              and status='copied_verified' and switch_completed_at is null
            order by history_id,role,ordinal""",
        run_id,
        manifest["plan_sha256"],
    )
    if rowset_sha != manifest["rowset_sha256"] or count != int(manifest["count"]):
        raise RuntimeError("cloud Switch global rowset changed")
    predecessor_count, predecessor_sha = await _predecessor_switch_identity(
        ledger, run_id, excluding=manifest["plan_sha256"]
    )
    if (
        predecessor_count != int(manifest["predecessor_switch_plan_count"])
        or predecessor_sha != manifest["predecessor_switch_plans_sha256"]
    ):
        raise RuntimeError("cloud Switch predecessor identity changed")


def _manifest_execution(
    manifest: dict[str, Any], *, artifact_digest: str, worker_id: str, route: str
) -> None:
    expected = {
        "mode": "cloud_receipt",
        "protocol": CLOUD_SWITCH_PROTOCOL,
        "worker_id": worker_id,
        "production_route_sha256": route,
        "cloud_switch_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
    }
    if (
        manifest.get("schema") != SCHEMA_PLAN
        or manifest.get("switch_execution") != expected
    ):
        raise RuntimeError("cloud Switch execution identity changed")
    if manifest.get("runtime_identity") != _runtime_identity(
        artifact_digest=artifact_digest
    ):
        raise RuntimeError("cloud Switch artifact identity changed")


async def _export_task(args: argparse.Namespace) -> None:
    if not 60 <= args.lease_seconds <= 86400:
        raise ValueError("cloud Switch task lease is invalid")
    key = _load_signing_key(Path(args.signing_key_file))
    ledger = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await ledger.execute(CLOUD_SWITCH_TASK_DDL)
        run_id, manifest = await _load_plan(ledger, args.plan_sha256, "switch")
        validate_switch_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            expected_manifest_sha256="gate",
            actual_manifest_sha256="gate",
            confirmation=args.confirm,
        )
        _manifest_execution(
            manifest,
            artifact_digest=args.artifact_digest,
            worker_id=args.worker_id,
            route=args.production_route_sha256,
        )
        async with ledger.transaction():
            await ledger.execute(
                "select pg_advisory_xact_lock(hashtext($1))", args.plan_sha256
            )
            session = await ledger.fetchrow(
                """select * from analytics_history_media_r2_cloud_switch_plan_sessions
                     where plan_sha256=$1 for update""",
                args.plan_sha256,
            )
            if session is None:
                await _validate_plan_preflight(ledger, run_id=run_id, manifest=manifest)
                await ledger.execute(
                    """insert into analytics_history_media_r2_cloud_switch_plan_sessions(
                         plan_sha256,run_id,worker_id,artifact_digest,
                         production_route_sha256,preflight_rowset_sha256,
                         predecessor_plans_sha256,status)
                       values($1,$2,$3,$4,$5,$6,$7,'active')""",
                    args.plan_sha256,
                    run_id,
                    args.worker_id,
                    args.artifact_digest,
                    args.production_route_sha256,
                    manifest["rowset_sha256"],
                    manifest["predecessor_switch_plans_sha256"],
                )
            elif (
                str(session["run_id"]) != str(run_id)
                or session["worker_id"] != args.worker_id
                or session["artifact_digest"] != args.artifact_digest
                or session["production_route_sha256"] != args.production_route_sha256
                or session["preflight_rowset_sha256"] != manifest["rowset_sha256"]
                or session["predecessor_plans_sha256"]
                != manifest["predecessor_switch_plans_sha256"]
                or session["status"] != "active"
            ):
                raise RuntimeError("cloud Switch preflight session identity changed")
            await ledger.execute(
                """update analytics_history_media_r2_cloud_switch_tasks
                      set status='expired',updated_at=now()
                    where plan_sha256=$1 and status='exported'
                      and lease_expires_at<=now()""",
                args.plan_sha256,
            )
            active = int(
                await ledger.fetchval(
                    """select count(*) from analytics_history_media_r2_cloud_switch_tasks
                         where plan_sha256=$1 and status='exported'""",
                    args.plan_sha256,
                )
            )
            if active:
                raise RuntimeError("cloud Switch plan already has an exported task")
            batch = await ledger.fetchrow(
                """select * from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status<>'completed'
                     order by batch_no limit 1 for update""",
                args.plan_sha256,
            )
            if batch is None:
                raise RuntimeError("cloud Switch plan has no remaining batch")
            if batch["status"] not in {"pending", "paused"}:
                raise RuntimeError("cloud Switch batch is not exportable")
            selected = [
                dict(row)
                for row in await ledger.fetch(
                    """select * from analytics_history_media_r2_migrations
                         where run_id=$1 and switch_plan_sha256=$2
                           and status='copied_verified' and switch_completed_at is null
                           and history_id between $3 and $4
                         order by history_id,role,ordinal""",
                    run_id,
                    args.plan_sha256,
                    int(batch["first_history_id"]),
                    int(batch["last_history_id"]),
                )
            ]
            if len(selected) != int(batch["asset_count"]) or _sha256_json(
                [_plan_row(row) for row in selected]
            ) != str(batch["rowset_sha256"]):
                raise RuntimeError("cloud Switch batch rowset changed")
            history_ids = sorted({int(row["history_id"]) for row in selected})
            all_rows = [
                dict(row)
                for row in await ledger.fetch(
                    """select id,history_id,role,ordinal,original_ref,target_key,
                              switch_plan_sha256,switch_completed_at
                         from analytics_history_media_r2_migrations
                        where run_id=$1 and history_id=any($2::integer[])
                        order by history_id,role,ordinal""",
                    run_id,
                    history_ids,
                )
            ]
            selected_ids = {int(row["id"]) for row in selected}
            for row in all_rows:
                row["selected"] = int(row["id"]) in selected_ids
            bundle = build_switch_task_bundle(
                rows=all_rows,
                plan_sha256=args.plan_sha256,
                predecessor_plan_sha256=manifest["predecessor_switch_plan_sha256"],
                artifact_digest=args.artifact_digest,
                worker_id=args.worker_id,
                production_route_sha256=args.production_route_sha256,
                batch_no=int(batch["batch_no"]),
                batch_rowset_sha256=str(batch["rowset_sha256"]),
                cas_state_sha256=str(batch["cas_state_sha256"]),
                lease_expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=args.lease_seconds),
            )
            write_signed_document(Path(args.output), bundle, key=key)
            await ledger.execute(
                """insert into analytics_history_media_r2_cloud_switch_tasks(
                     task_id,run_id,plan_sha256,worker_id,artifact_digest,
                     production_route_sha256,batch_no,batch_rowset_sha256,
                     cas_state_sha256,ledger_ids,bundle_sha256,status,lease_expires_at)
                   values($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10::bigint[],$11,
                          'exported',$12::timestamptz)""",
                bundle["task_id"],
                run_id,
                args.plan_sha256,
                args.worker_id,
                args.artifact_digest,
                args.production_route_sha256,
                int(batch["batch_no"]),
                batch["rowset_sha256"],
                batch["cas_state_sha256"],
                bundle["ledger_ids"],
                _bundle_sha256(bundle),
                _task_lease_datetime(bundle),
            )
        print(
            json.dumps(
                {
                    "task_id": bundle["task_id"],
                    "batch_no": bundle["batch_no"],
                    "assets": bundle["asset_count"],
                    "histories": bundle["history_count"],
                },
                sort_keys=True,
            )
        )
    finally:
        await ledger.close()


async def _run_switch_task(args: argparse.Namespace) -> None:
    key = _load_signing_key(Path(args.signing_key_file))
    bundle = read_signed_document(Path(args.task), key=key)["payload"]
    validate_switch_task_gate(
        bundle,
        plan_sha256=bundle["plan_sha256"],
        confirm=args.confirm,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
        production_route_sha256=args.production_route_sha256,
    )
    actual_route = production_route_sha256_from_dsn(_dsn("PRODUCTION_DATABASE_URL"))
    if actual_route != args.production_route_sha256:
        raise RuntimeError("cloud Switch production route changed")
    production = await _connect_env("PRODUCTION_DATABASE_URL")
    try:
        result = await apply_switch_task_to_production(production, bundle)
    finally:
        await production.close()
    receipt = build_switch_receipt(
        bundle,
        histories_updated=result["histories_updated"],
        post_state_sha256=result["post_state_sha256"],
    )
    write_signed_document(Path(args.receipt_output), receipt, key=key)
    print(
        json.dumps(
            {
                "task_id": bundle["task_id"],
                "batch_no": bundle["batch_no"],
                "assets": result["assets"],
                "histories": result["histories"],
                "histories_updated": result["histories_updated"],
            },
            sort_keys=True,
        )
    )


async def _import_receipt(args: argparse.Namespace) -> None:
    key = _load_signing_key(Path(args.signing_key_file))
    bundle = read_signed_document(Path(args.task), key=key)["payload"]
    receipt = read_signed_document(Path(args.receipt), key=key)["payload"]
    validate_switch_task_gate(
        bundle,
        plan_sha256=args.plan_sha256,
        confirm=args.confirm,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
        production_route_sha256=args.production_route_sha256,
    )
    validate_switch_receipt(bundle, receipt)
    ledger = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await ledger.execute(CLOUD_SWITCH_TASK_DDL)
        async with ledger.transaction():
            task = await ledger.fetchrow(
                """select * from analytics_history_media_r2_cloud_switch_tasks
                     where task_id=$1::uuid for update""",
                bundle["task_id"],
            )
            if task is None:
                raise RuntimeError("unknown cloud Switch task")
            if task["status"] == "committed":
                if task["receipt_sha256"] != receipt["receipt_sha256"]:
                    raise RuntimeError("cloud Switch task has another receipt")
                print(
                    json.dumps({"task_id": bundle["task_id"], "status": "idempotent"})
                )
                return
            if (
                task["status"] != "exported"
                or str(task["plan_sha256"]) != args.plan_sha256
                or task["artifact_digest"] != args.artifact_digest
                or task["worker_id"] != args.worker_id
                or task["production_route_sha256"] != args.production_route_sha256
                or int(task["batch_no"]) != int(bundle["batch_no"])
                or task["batch_rowset_sha256"] != bundle["batch_rowset_sha256"]
                or task["cas_state_sha256"] != bundle["cas_state_sha256"]
                or task["bundle_sha256"] != _bundle_sha256(bundle)
            ):
                raise RuntimeError("cloud Switch task identity changed")
            rows = [
                dict(row)
                for row in await ledger.fetch(
                    """select id,switch_plan_sha256,switch_completed_at,status
                         from analytics_history_media_r2_migrations
                        where id=any($1::bigint[]) order by id for update""",
                    list(task["ledger_ids"]),
                )
            ]
            if (
                len(rows) != len(bundle["ledger_ids"])
                or [int(row["id"]) for row in rows] != list(bundle["ledger_ids"])
                or any(
                    str(row.get("switch_plan_sha256") or "") != args.plan_sha256
                    or row["status"] != "copied_verified"
                    or row.get("switch_completed_at") is not None
                    for row in rows
                )
            ):
                raise RuntimeError("cloud Switch ledger ownership changed")
            updated = await ledger.execute(
                """update analytics_history_media_r2_migrations set
                     switch_completed_at=coalesce(switch_completed_at,now()),updated_at=now()
                   where id=any($1::bigint[]) and switch_plan_sha256=$2
                     and switch_completed_at is null and status='copied_verified'""",
                list(task["ledger_ids"]),
                args.plan_sha256,
            )
            if updated != f"UPDATE {len(bundle['ledger_ids'])}":
                raise RuntimeError("cloud Switch ledger commit changed")
            await ledger.execute(
                """update analytics_history_media_migration_plan_batches set
                     status='completed',started_at=coalesce(started_at,now()),
                     completed_at=now(),outcome_counts=$3::jsonb,updated_at=now()
                   where plan_sha256=$1 and batch_no=$2""",
                args.plan_sha256,
                int(bundle["batch_no"]),
                json.dumps(
                    {
                        "assets": bundle["asset_count"],
                        "histories": bundle["history_count"],
                        "histories_updated": receipt["histories_updated"],
                        "execution": "cloud_receipt",
                    }
                ),
            )
            await ledger.execute(
                """update analytics_history_media_r2_cloud_switch_tasks set
                     status='committed',receipt_sha256=$2,
                     outcome_counts=$3::jsonb,completed_at=now(),updated_at=now()
                   where task_id=$1::uuid""",
                bundle["task_id"],
                receipt["receipt_sha256"],
                json.dumps(
                    {
                        "assets": bundle["asset_count"],
                        "histories": bundle["history_count"],
                        "histories_updated": receipt["histories_updated"],
                    }
                ),
            )
            remaining = int(
                await ledger.fetchval(
                    """select count(*) from analytics_history_media_migration_plan_batches
                         where plan_sha256=$1 and status<>'completed'""",
                    args.plan_sha256,
                )
            )
            if not remaining:
                await ledger.execute(
                    """update analytics_history_media_r2_cloud_switch_plan_sessions
                          set status='completed',completed_at=now(),updated_at=now()
                        where plan_sha256=$1""",
                    args.plan_sha256,
                )
        print(
            json.dumps(
                {
                    "task_id": bundle["task_id"],
                    "batch_no": bundle["batch_no"],
                    "status": "committed",
                },
                sort_keys=True,
            )
        )
    finally:
        await ledger.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    fingerprint = commands.add_parser("fingerprint-production-route")
    fingerprint.add_argument("--dsn-env", default="PRODUCTION_DATABASE_URL")
    planner = commands.add_parser("plan-successor")
    planner.add_argument("--predecessor-plan-sha256", required=True)
    planner.add_argument("--artifact-digest", required=True)
    planner.add_argument("--worker-id", required=True)
    planner.add_argument("--production-route-sha256", required=True)
    planner.add_argument("--output", required=True)
    exporter = commands.add_parser("export-task")
    exporter.add_argument("--plan-sha256", required=True)
    exporter.add_argument("--confirm", required=True)
    exporter.add_argument("--artifact-digest", required=True)
    exporter.add_argument("--worker-id", required=True)
    exporter.add_argument("--production-route-sha256", required=True)
    exporter.add_argument("--signing-key-file", required=True)
    exporter.add_argument("--output", required=True)
    exporter.add_argument("--lease-seconds", type=int, default=3600)
    worker = commands.add_parser("run-task")
    worker.add_argument("--task", required=True)
    worker.add_argument("--confirm", required=True)
    worker.add_argument("--artifact-digest", required=True)
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--production-route-sha256", required=True)
    worker.add_argument("--signing-key-file", required=True)
    worker.add_argument("--receipt-output", required=True)
    importer = commands.add_parser("import-receipt")
    importer.add_argument("--task", required=True)
    importer.add_argument("--receipt", required=True)
    importer.add_argument("--plan-sha256", required=True)
    importer.add_argument("--confirm", required=True)
    importer.add_argument("--artifact-digest", required=True)
    importer.add_argument("--worker-id", required=True)
    importer.add_argument("--production-route-sha256", required=True)
    importer.add_argument("--signing-key-file", required=True)
    return parser


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "fingerprint-production-route":
        print(production_route_sha256_from_dsn(_dsn(args.dsn_env)))
    elif args.command == "plan-successor":
        await _plan_successor(args)
    elif args.command == "export-task":
        await _export_task(args)
    elif args.command == "run-task":
        await _run_switch_task(args)
    elif args.command == "import-receipt":
        await _import_receipt(args)


def main() -> None:
    asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    main()
