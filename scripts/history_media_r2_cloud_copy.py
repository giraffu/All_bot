#!/usr/bin/env python3
"""Run frozen History R2 HEAD/CopyObject tasks without direct ledger access."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import stat
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.history_media_r2_migration import (
    BUCKET,
    CLOUD_COPY_PROTOCOL,
    _connect_env,
    _copy_execution,
    _load_plan,
    _load_secure_config,
    _head_s3_identity,
    _normalize_etag,
    _normalize_modified,
    _r2_transport,
    _runtime_identity,
    _s3_client,
    _timed_server_side_copy_with_retries,
    _validate_copy_batch_identity,
    _validate_copy_plan_preflight,
    _validate_r2_transport_runtime,
    _validate_runtime_identity,
    classify_copy_request_failure,
    group_copy_candidates,
    validate_copy_gate,
)

SCHEMA_TASK = "allbot-history-r2-cloud-copy-task/v1"
SCHEMA_RECEIPT = "allbot-history-r2-cloud-copy-receipt/v1"
ALLOWED_OPERATIONS = {"head_probe", "copy_object"}
CLOUD_TASK_DDL = """
create table if not exists analytics_history_media_r2_cloud_copy_plan_sessions (
    plan_sha256 char(64) primary key references analytics_history_media_migration_plans(plan_sha256),
    run_id uuid not null references analytics_history_media_migration_runs(id),
    worker_id text not null,
    artifact_digest text not null,
    preflight_rowset_sha256 char(64) not null,
    status text not null check (status in ('active','completed','failed')),
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);
create table if not exists analytics_history_media_r2_cloud_copy_tasks (
    task_id uuid primary key,
    run_id uuid not null references analytics_history_media_migration_runs(id),
    plan_sha256 char(64) not null references analytics_history_media_migration_plans(plan_sha256),
    worker_id text not null,
    artifact_digest text not null,
    batch_no integer not null,
    rowset_sha256 char(64) not null,
    ledger_ids bigint[] not null,
    bundle_sha256 char(64) not null,
    status text not null check (status in ('exported','committed','failed','expired','superseded')),
    lease_expires_at timestamptz not null,
    receipt_sha256 char(64),
    outcome_counts jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    updated_at timestamptz not null default now()
);
create index if not exists ix_history_media_r2_cloud_copy_tasks_plan_status
  on analytics_history_media_r2_cloud_copy_tasks(plan_sha256,status,created_at);
"""


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _rowset_sha256(rows: Iterable[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(list(rows))).hexdigest()


def _bundle_row(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "history_id",
        "role",
        "ordinal",
        "target_key",
        "source_name",
        "source_key",
        "source_last_modified",
        "source_etag",
        "byte_size",
        "status",
        "history_manifest_sha256",
        "copy_plan_sha256",
    )
    return _json_value({field: row.get(field) for field in fields})


def build_task_bundle(
    *,
    operation: str,
    rows: Iterable[dict[str, Any]],
    plan_sha256: str,
    artifact_digest: str,
    worker_id: str,
    runtime_identity: dict[str, Any],
    task_id: str | None = None,
) -> dict[str, Any]:
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("cloud Copy task operation is invalid")
    if not all(character in "0123456789abcdef" for character in plan_sha256) or len(
        plan_sha256
    ) != 64:
        raise ValueError("cloud Copy plan SHA is invalid")
    artifact_sha = artifact_digest.removeprefix("sha256:")
    if (
        len(artifact_sha) != 64
        or not artifact_digest.startswith("sha256:")
        or not all(character in "0123456789abcdef" for character in artifact_sha)
    ):
        raise ValueError("cloud Copy artifact digest is invalid")
    normalized = sorted(
        (_bundle_row(row) for row in rows), key=lambda row: int(row["id"])
    )
    if not normalized:
        raise ValueError("cloud Copy task cannot be empty")
    return {
        "schema": SCHEMA_TASK,
        "task_id": task_id or str(uuid.uuid4()),
        "operation": operation,
        "plan_sha256": plan_sha256,
        "artifact_digest": artifact_digest,
        "worker_id": worker_id,
        "protocol": CLOUD_COPY_PROTOCOL,
        "runtime_identity": _json_value(runtime_identity),
        "asset_count": len(normalized),
        "rowset_sha256": _rowset_sha256(normalized),
        "rows": normalized,
    }


def _signature(payload: dict[str, Any], *, key: bytes) -> str:
    if len(key) < 32:
        raise ValueError("cloud Copy signing key must contain at least 32 bytes")
    return hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest()


def write_signed_document(path: Path, payload: dict[str, Any], *, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"payload": payload, "hmac_sha256": _signature(payload, key=key)}
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_json(document) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_signed_document(path: Path, *, key: bytes) -> dict[str, Any]:
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise PermissionError("cloud Copy document must be current-user-owned 0600")
    document = json.loads(path.read_text(encoding="utf-8"))
    payload = document.get("payload")
    supplied = str(document.get("hmac_sha256") or "")
    if not isinstance(payload, dict) or not hmac.compare_digest(
        supplied, _signature(payload, key=key)
    ):
        raise ValueError("cloud Copy document signature changed")
    return document


def _load_signing_key(path: Path) -> bytes:
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise PermissionError("cloud Copy signing key must be current-user-owned 0600")
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("cloud Copy signing key must contain at least 32 bytes")
    return key


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _latencies(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "max": round(max(values), 3) if values else 0.0,
    }


def _parse_modified(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def run_head_probe(
    rows: Iterable[dict[str, Any]], *, client: Any, concurrency: int
) -> dict[str, Any]:
    normalized = list(rows)
    if not 1 <= concurrency <= 32:
        raise ValueError("cloud HEAD concurrency must be between 1 and 32")
    latencies: list[float] = []

    def inspect(row: dict[str, Any]) -> tuple[float, bool]:
        started = time.perf_counter()
        source = _head_s3_identity(client, BUCKET, str(row["source_key"]))
        if source is None:
            raise RuntimeError("cloud HEAD source disappeared")
        if (
            int(source["ContentLength"]) != int(row["byte_size"])
            or _normalize_modified(source["LastModified"])
            != _normalize_modified(_parse_modified(row["source_last_modified"]))
            or _normalize_etag(source.get("ETag"))
            != _normalize_etag(row.get("source_etag"))
        ):
            raise RuntimeError("cloud HEAD source identity changed")
        target = _head_s3_identity(client, BUCKET, str(row["target_key"]))
        return (time.perf_counter() - started) * 1000, target is not None

    target_existing = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for future in as_completed(
            [executor.submit(inspect, row) for row in normalized]
        ):
            latency, exists = future.result()
            latencies.append(float(latency))
            target_existing += int(exists)
    return {
        "operation": "HeadObject",
        "assets": len(normalized),
        "requests": len(normalized) * 2,
        "concurrency": concurrency,
        "target_existing": target_existing,
        "target_missing": len(normalized) - target_existing,
        "latency_ms": _latencies(latencies),
    }


def run_copy_task(
    rows: Iterable[dict[str, Any]],
    *,
    client: Any,
    plan_sha256: str,
    concurrency: int,
    copy_one: Callable[..., dict[str, Any]] | None = None,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not 1 <= concurrency <= 32:
        raise ValueError("cloud Copy concurrency must be between 1 and 32")
    groups = group_copy_candidates(list(rows))
    operation = copy_one or _timed_server_side_copy_with_retries
    results: list[dict[str, Any]] = []
    request_kinds: Counter[str] = Counter()
    latencies: list[float] = []

    def execute(
        group: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        row = group[0]
        outcome = operation(
            client,
            bucket=BUCKET,
            source_key=str(row["source_key"]),
            target_key=str(row["target_key"]),
            expected_size=int(row["byte_size"]),
            expected_last_modified=_parse_modified(row["source_last_modified"]),
            expected_etag=row.get("source_etag"),
            copy_plan_sha256=plan_sha256,
        )
        return group, outcome

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(execute, group) for group in groups]
        for future in as_completed(futures):
            group, attempted = future.result()
            ids = sorted(int(row["id"]) for row in group)
            latencies.append(float(attempted.get("elapsed_ms", 0.0)))
            for event in attempted.get("request_events", []):
                request_kinds[str(event.get("kind") or "unknown")] += 1
            error = attempted.get("error")
            if error is None:
                outcome = attempted["outcome"]
                result = {
                    "ledger_ids": ids,
                    "outcome": "copied_verified",
                    "target_etag": str(outcome.get("etag") or ""),
                }
            else:
                kind = classify_copy_request_failure(error)
                result = {
                    "ledger_ids": ids,
                    "outcome": "fatal" if kind == "fatal" else "retryable",
                    "error_kind": kind,
                }
            results.append(result)
            results.sort(key=lambda item: int(item["ledger_ids"][0]))
            if checkpoint is not None:
                checkpoint({"results": list(results)})
    counts = Counter(str(item["outcome"]) for item in results)
    return {
        "results": results,
        "outcome_counts": dict(sorted(counts.items())),
        "request_kinds": dict(sorted(request_kinds.items())),
        "latency_ms": _latencies(latencies),
    }


def validate_copy_task_gate(
    bundle: dict[str, Any],
    *,
    plan_sha256: str,
    confirm: str,
    artifact_digest: str,
    worker_id: str,
) -> None:
    if bundle.get("operation") != "copy_object":
        raise ValueError("cloud task does not authorize CopyObject")
    if bundle.get("plan_sha256") != plan_sha256:
        raise ValueError("cloud task plan SHA changed")
    if confirm != f"COPY_HISTORY_MEDIA_{plan_sha256}":
        raise ValueError("exact cloud Copy confirmation is required")
    if bundle.get("artifact_digest") != artifact_digest:
        raise ValueError("cloud task artifact digest changed")
    if bundle.get("worker_id") != worker_id:
        raise ValueError("cloud task worker identity changed")


def build_copy_receipt(
    bundle: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    receipt = {
        "schema": SCHEMA_RECEIPT,
        "task_id": bundle["task_id"],
        "plan_sha256": bundle["plan_sha256"],
        "artifact_digest": bundle["artifact_digest"],
        "worker_id": bundle["worker_id"],
        "protocol": bundle["protocol"],
        "rowset_sha256": bundle["rowset_sha256"],
        "asset_count": bundle["asset_count"],
        "results": result["results"],
        "outcome_counts": result["outcome_counts"],
        "request_kinds": result["request_kinds"],
        "latency_ms": result["latency_ms"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    return receipt


def _checkpoint_receipt(
    bundle: dict[str, Any], partial: dict[str, Any]
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for item in partial["results"]:
        counts[str(item["outcome"])] += len(item["ledger_ids"])
    receipt = {
        "schema": SCHEMA_RECEIPT,
        "task_id": bundle["task_id"],
        "plan_sha256": bundle["plan_sha256"],
        "artifact_digest": bundle["artifact_digest"],
        "worker_id": bundle["worker_id"],
        "protocol": bundle["protocol"],
        "rowset_sha256": bundle["rowset_sha256"],
        "asset_count": bundle["asset_count"],
        "complete": False,
        "results": partial["results"],
        "outcome_counts": dict(sorted(counts.items())),
        "request_kinds": {},
        "latency_ms": {},
        "completed_at": None,
    }
    receipt["receipt_sha256"] = hashlib.sha256(_canonical_json(receipt)).hexdigest()
    return receipt


def validate_copy_receipt(
    bundle: dict[str, Any], receipt: dict[str, Any]
) -> None:
    identity_fields = (
        "task_id",
        "plan_sha256",
        "artifact_digest",
        "worker_id",
        "protocol",
        "rowset_sha256",
        "asset_count",
    )
    if receipt.get("schema") != SCHEMA_RECEIPT or any(
        receipt.get(field) != bundle.get(field) for field in identity_fields
    ):
        raise ValueError("cloud Copy receipt identity changed")
    expected_ids = sorted(int(row["id"]) for row in bundle["rows"])
    result_ids: list[int] = []
    counts: Counter[str] = Counter()
    for item in receipt.get("results", []):
        outcome = str(item.get("outcome") or "")
        if outcome not in {"copied_verified", "retryable", "fatal"}:
            raise ValueError("cloud Copy receipt outcome is invalid")
        ids = [int(value) for value in item.get("ledger_ids", [])]
        if not ids or ids != sorted(set(ids)):
            raise ValueError("cloud Copy receipt row coverage changed")
        if outcome == "copied_verified" and not str(item.get("target_etag") or ""):
            raise ValueError("cloud Copy receipt target identity is missing")
        result_ids.extend(ids)
        counts[outcome] += len(ids)
    complete = bool(receipt.get("complete", True))
    coverage_changed = (
        sorted(result_ids) != expected_ids
        if complete
        else not set(result_ids).issubset(expected_ids)
    )
    if coverage_changed or len(result_ids) != len(set(result_ids)):
        raise ValueError("cloud Copy receipt row coverage changed")
    if dict(sorted(counts.items())) != dict(receipt.get("outcome_counts") or {}):
        raise ValueError("cloud Copy receipt outcome counts changed")
    expected_receipt_sha = hashlib.sha256(
        _canonical_json(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
    ).hexdigest()
    if receipt.get("receipt_sha256") != expected_receipt_sha:
        raise ValueError("cloud Copy receipt identity changed")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    export_head = commands.add_parser("export-head-task")
    export_head.add_argument("--plan-sha256", required=True)
    export_head.add_argument("--config", required=True)
    export_head.add_argument("--artifact-digest", required=True)
    export_head.add_argument("--worker-id", required=True)
    export_head.add_argument("--signing-key-file", required=True)
    export_head.add_argument("--limit", type=int, default=100)
    export_head.add_argument("--output", required=True)

    export_copy = commands.add_parser("export-copy-task")
    export_copy.add_argument("--plan-sha256", required=True)
    export_copy.add_argument("--confirm", required=True)
    export_copy.add_argument("--config", required=True)
    export_copy.add_argument("--artifact-digest", required=True)
    export_copy.add_argument("--worker-id", required=True)
    export_copy.add_argument("--signing-key-file", required=True)
    export_copy.add_argument("--limit", type=int, default=1000)
    export_copy.add_argument("--lease-seconds", type=int, default=3600)
    export_copy.add_argument("--output", required=True)

    run_head = commands.add_parser("run-head-task")
    run_head.add_argument("--task", required=True)
    run_head.add_argument("--config", required=True)
    run_head.add_argument("--artifact-digest", required=True)
    run_head.add_argument("--worker-id", required=True)
    run_head.add_argument("--signing-key-file", required=True)
    run_head.add_argument("--concurrency", type=int, default=16)
    run_head.add_argument("--receipt-output", required=True)

    run_copy = commands.add_parser("run-copy-task")
    run_copy.add_argument("--task", required=True)
    run_copy.add_argument("--confirm", required=True)
    run_copy.add_argument("--config", required=True)
    run_copy.add_argument("--artifact-digest", required=True)
    run_copy.add_argument("--worker-id", required=True)
    run_copy.add_argument("--signing-key-file", required=True)
    run_copy.add_argument("--concurrency", type=int, default=16)
    run_copy.add_argument("--receipt-output", required=True)

    importer = commands.add_parser("import-copy-receipt")
    importer.add_argument("--task", required=True)
    importer.add_argument("--receipt", required=True)
    importer.add_argument("--plan-sha256", required=True)
    importer.add_argument("--confirm", required=True)
    importer.add_argument("--artifact-digest", required=True)
    importer.add_argument("--worker-id", required=True)
    importer.add_argument("--signing-key-file", required=True)
    return parser


def _bundle_sha256(bundle: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(bundle)).hexdigest()


def _validate_worker_runtime(
    bundle: dict[str, Any],
    *,
    config: dict[str, Any],
    artifact_digest: str,
    worker_id: str,
) -> None:
    if bundle.get("artifact_digest") != artifact_digest:
        raise ValueError("cloud task artifact digest changed")
    if bundle.get("worker_id") != worker_id:
        raise ValueError("cloud task worker identity changed")
    actual = _runtime_identity(artifact_digest=artifact_digest, config=config)
    if dict(bundle.get("runtime_identity") or {}) != actual:
        raise RuntimeError("cloud task runtime identity changed")
    execution = _copy_execution(config)
    if execution.get("mode") != "cloud_receipt" or execution.get("worker_id") != worker_id:
        raise RuntimeError("cloud task execution identity changed")


async def _export_head_task(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 1000:
        raise ValueError("cloud HEAD task limit must be between 1 and 1000")
    key = _load_signing_key(Path(args.signing_key_file))
    config = _load_secure_config(Path(args.config))
    runtime_identity = _runtime_identity(
        artifact_digest=args.artifact_digest, config=config
    )
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        run_id, _manifest = await _load_plan(conn, args.plan_sha256, "copy")
        rows = [
            dict(row)
            for row in await conn.fetch(
                """select * from analytics_history_media_r2_migrations
                     where run_id=$1 and copy_plan_sha256=$2
                       and status='copy_required'
                     order by id limit $3""",
                run_id,
                args.plan_sha256,
                args.limit,
            )
        ]
        bundle = build_task_bundle(
            operation="head_probe",
            rows=rows,
            plan_sha256=args.plan_sha256,
            artifact_digest=args.artifact_digest,
            worker_id=args.worker_id,
            runtime_identity=runtime_identity,
        )
        write_signed_document(Path(args.output), bundle, key=key)
        print(
            json.dumps(
                {
                    "operation": "HeadObject",
                    "task_id": bundle["task_id"],
                    "assets": bundle["asset_count"],
                    "rowset_sha256": bundle["rowset_sha256"],
                },
                sort_keys=True,
            )
        )
    finally:
        await conn.close()


async def _run_head_task(args: argparse.Namespace) -> None:
    key = _load_signing_key(Path(args.signing_key_file))
    bundle = read_signed_document(Path(args.task), key=key)["payload"]
    if bundle.get("operation") != "head_probe":
        raise ValueError("cloud task does not authorize HEAD probe")
    config = _load_secure_config(Path(args.config))
    _validate_worker_runtime(
        bundle,
        config=config,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
    )
    transport = _r2_transport(config)
    _validate_r2_transport_runtime(transport)
    client = _s3_client(
        config["target"],
        max_pool_connections=max(16, int(args.concurrency)),
        transport=transport,
    )
    try:
        result = run_head_probe(
            bundle["rows"], client=client, concurrency=args.concurrency
        )
    finally:
        client.close()
    receipt = {
        "schema": "allbot-history-r2-cloud-head-receipt/v1",
        "task_id": bundle["task_id"],
        "plan_sha256": bundle["plan_sha256"],
        "artifact_digest": bundle["artifact_digest"],
        "worker_id": bundle["worker_id"],
        "rowset_sha256": bundle["rowset_sha256"],
        **result,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    write_signed_document(Path(args.receipt_output), receipt, key=key)
    print(json.dumps(result, sort_keys=True))


async def _export_copy_task(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 1000:
        raise ValueError("cloud Copy task limit must be between 1 and 1000")
    if not 60 <= args.lease_seconds <= 86400:
        raise ValueError("cloud Copy task lease must be between 60 and 86400 seconds")
    key = _load_signing_key(Path(args.signing_key_file))
    config = _load_secure_config(Path(args.config))
    expected_execution = {
        "mode": "cloud_receipt",
        "protocol": CLOUD_COPY_PROTOCOL,
        "worker_id": args.worker_id,
    }
    if _copy_execution(config) != expected_execution:
        raise RuntimeError("cloud Copy config worker identity changed")
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await conn.execute(CLOUD_TASK_DDL)
        run_id, manifest = await _load_plan(conn, args.plan_sha256, "copy")
        validate_copy_gate(
            expected_plan_sha256=manifest["plan_sha256"],
            supplied_plan_sha256=args.plan_sha256,
            confirmation=args.confirm,
        )
        _validate_runtime_identity(
            manifest["runtime_identity"],
            artifact_digest=args.artifact_digest,
            config=config,
        )
        async with conn.transaction():
            await conn.execute(
                "select pg_advisory_xact_lock(hashtext($1))", args.plan_sha256
            )
            session = await conn.fetchrow(
                """select * from analytics_history_media_r2_cloud_copy_plan_sessions
                     where plan_sha256=$1 for update""",
                args.plan_sha256,
            )
            if session is None:
                await _validate_copy_plan_preflight(
                    conn,
                    run_id=run_id,
                    manifest=manifest,
                    plan_sha256=args.plan_sha256,
                )
                await conn.execute(
                    """insert into analytics_history_media_r2_cloud_copy_plan_sessions(
                           plan_sha256,run_id,worker_id,artifact_digest,
                           preflight_rowset_sha256,status)
                         values($1,$2,$3,$4,$5,'active')""",
                    args.plan_sha256,
                    run_id,
                    args.worker_id,
                    args.artifact_digest,
                    manifest["rowset_sha256"],
                )
            elif (
                str(session["run_id"]) != str(run_id)
                or session["worker_id"] != args.worker_id
                or session["artifact_digest"] != args.artifact_digest
                or session["preflight_rowset_sha256"] != manifest["rowset_sha256"]
                or session["status"] != "active"
            ):
                raise RuntimeError("cloud Copy preflight session identity changed")
            await conn.execute(
                """update analytics_history_media_r2_cloud_copy_tasks
                      set status='expired',updated_at=now()
                    where plan_sha256=$1 and status='exported'
                      and lease_expires_at<=now()""",
                args.plan_sha256,
            )
            active = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_cloud_copy_tasks
                         where plan_sha256=$1 and status='exported'""",
                    args.plan_sha256,
                )
            )
            if active:
                raise RuntimeError("cloud Copy plan already has an exported task")
            batch = await conn.fetchrow(
                """select * from analytics_history_media_migration_plan_batches
                     where plan_sha256=$1 and status<>'completed'
                     order by batch_no limit 1 for update""",
                args.plan_sha256,
            )
            if batch is None:
                raise RuntimeError("cloud Copy plan has no remaining batch")
            await _validate_copy_batch_identity(
                conn,
                run_id=run_id,
                plan_sha256=args.plan_sha256,
                batch=dict(batch),
            )
            rows = [
                dict(row)
                for row in await conn.fetch(
                    """select * from analytics_history_media_r2_migrations
                         where run_id=$1 and copy_plan_sha256=$2
                           and status='copy_required'
                           and id between $3 and $4
                         order by id limit $5""",
                    run_id,
                    args.plan_sha256,
                    int(batch["first_ledger_id"]),
                    int(batch["last_ledger_id"]),
                    args.limit,
                )
            ]
            if not rows:
                raise RuntimeError("cloud Copy batch has no exportable rows")
            selected_targets = list(
                dict.fromkeys(str(row["target_key"]) for row in rows)
            )
            rows = [
                dict(row)
                for row in await conn.fetch(
                    """select * from analytics_history_media_r2_migrations
                         where run_id=$1 and copy_plan_sha256=$2
                           and status='copy_required' and target_key=any($3::text[])
                         order by id""",
                    run_id,
                    args.plan_sha256,
                    selected_targets,
                )
            ]
            bundle = build_task_bundle(
                operation="copy_object",
                rows=rows,
                plan_sha256=args.plan_sha256,
                artifact_digest=args.artifact_digest,
                worker_id=args.worker_id,
                runtime_identity=manifest["runtime_identity"],
            )
            write_signed_document(Path(args.output), bundle, key=key)
            await conn.execute(
                """insert into analytics_history_media_r2_cloud_copy_tasks(
                       task_id,run_id,plan_sha256,worker_id,artifact_digest,batch_no,
                       rowset_sha256,ledger_ids,bundle_sha256,status,lease_expires_at)
                     values($1::uuid,$2,$3,$4,$5,$6,$7,$8::bigint[],$9,'exported',
                            now()+($10 * interval '1 second'))""",
                bundle["task_id"],
                run_id,
                args.plan_sha256,
                args.worker_id,
                args.artifact_digest,
                int(batch["batch_no"]),
                bundle["rowset_sha256"],
                [int(row["id"]) for row in rows],
                _bundle_sha256(bundle),
                args.lease_seconds,
            )
        print(
            json.dumps(
                {
                    "task_id": bundle["task_id"],
                    "assets": bundle["asset_count"],
                    "batch_no": int(batch["batch_no"]),
                    "rowset_sha256": bundle["rowset_sha256"],
                },
                sort_keys=True,
            )
        )
    finally:
        await conn.close()


async def _run_copy_task(args: argparse.Namespace) -> None:
    key = _load_signing_key(Path(args.signing_key_file))
    bundle = read_signed_document(Path(args.task), key=key)["payload"]
    validate_copy_task_gate(
        bundle,
        plan_sha256=bundle["plan_sha256"],
        confirm=args.confirm,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
    )
    config = _load_secure_config(Path(args.config))
    _validate_worker_runtime(
        bundle,
        config=config,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
    )
    transport = _r2_transport(config)
    _validate_r2_transport_runtime(transport)
    target = config["target"]
    source = next(
        item
        for item in config.get("sources", [])
        if item.get("name") == "r2-user-data-prod" and item.get("enabled", True)
    )
    if (
        target.get("bucket") != BUCKET
        or source.get("bucket") != BUCKET
        or str(target.get("endpoint", "")).rstrip("/")
        != str(source.get("endpoint", "")).rstrip("/")
    ):
        raise RuntimeError("cloud Copy source is not the same frozen R2 bucket")
    client = _s3_client(
        target,
        max_pool_connections=max(16, int(args.concurrency)),
        transport=transport,
        external_retry_lane=True,
    )

    def checkpoint(partial: dict[str, Any]) -> None:
        write_signed_document(
            Path(args.receipt_output),
            _checkpoint_receipt(bundle, partial),
            key=key,
        )

    try:
        result = await asyncio.to_thread(
            run_copy_task,
            bundle["rows"],
            client=client,
            plan_sha256=bundle["plan_sha256"],
            concurrency=args.concurrency,
            checkpoint=checkpoint,
        )
    finally:
        client.close()
    receipt = build_copy_receipt(bundle, result)
    receipt["complete"] = True
    receipt["receipt_sha256"] = hashlib.sha256(
        _canonical_json(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        )
    ).hexdigest()
    write_signed_document(Path(args.receipt_output), receipt, key=key)
    print(
        json.dumps(
            {
                "task_id": bundle["task_id"],
                "outcome_counts": result["outcome_counts"],
                "request_kinds": result["request_kinds"],
                "latency_ms": result["latency_ms"],
            },
            sort_keys=True,
        )
    )


async def _import_copy_receipt(args: argparse.Namespace) -> None:
    key = _load_signing_key(Path(args.signing_key_file))
    bundle = read_signed_document(Path(args.task), key=key)["payload"]
    receipt = read_signed_document(Path(args.receipt), key=key)["payload"]
    validate_copy_task_gate(
        bundle,
        plan_sha256=args.plan_sha256,
        confirm=args.confirm,
        artifact_digest=args.artifact_digest,
        worker_id=args.worker_id,
    )
    validate_copy_receipt(bundle, receipt)
    conn = await _connect_env("LOCAL_ANALYTICS_DATABASE_URL")
    try:
        await conn.execute(CLOUD_TASK_DDL)
        async with conn.transaction():
            task = await conn.fetchrow(
                """select * from analytics_history_media_r2_cloud_copy_tasks
                     where task_id=$1::uuid for update""",
                bundle["task_id"],
            )
            if task is None:
                raise RuntimeError("unknown cloud Copy task")
            if task["status"] in {"committed", "failed"}:
                if task["receipt_sha256"] != receipt["receipt_sha256"]:
                    raise RuntimeError("cloud Copy task was committed by another receipt")
                print(
                    json.dumps(
                        {"task_id": bundle["task_id"], "status": "idempotent"}
                    )
                )
                return
            if (
                task["status"] != "exported"
                or str(task["plan_sha256"]) != args.plan_sha256
                or task["artifact_digest"] != args.artifact_digest
                or task["worker_id"] != args.worker_id
                or task["rowset_sha256"] != bundle["rowset_sha256"]
                or task["bundle_sha256"] != _bundle_sha256(bundle)
            ):
                raise RuntimeError("cloud Copy task identity changed")
            rows = [
                dict(row)
                for row in await conn.fetch(
                    """select * from analytics_history_media_r2_migrations
                         where id=any($1::bigint[]) order by id for update""",
                    list(task["ledger_ids"]),
                )
            ]
            normalized = [_bundle_row(row) for row in rows]
            if (
                len(rows) != len(bundle["rows"])
                or _rowset_sha256(normalized) != bundle["rowset_sha256"]
                or any(
                    row["status"] != "copy_required"
                    or str(row["copy_plan_sha256"]) != args.plan_sha256
                    for row in rows
                )
            ):
                raise RuntimeError("cloud Copy ledger rowset changed")
            for result in receipt["results"]:
                ids = [int(value) for value in result["ledger_ids"]]
                if result["outcome"] == "copied_verified":
                    updated = await conn.execute(
                        """update analytics_history_media_r2_migrations set
                             status='copied_verified',target_sha256=source_sha256,
                             target_etag=$2,copy_method='r2_cloud_copy_receipt',
                             error_code=null,error_detail=null,
                             copy_completed_at=coalesce(copy_completed_at,now()),updated_at=now()
                           where id=any($1::bigint[]) and copy_plan_sha256=$3
                             and status='copy_required'""",
                        ids,
                        result["target_etag"],
                        args.plan_sha256,
                    )
                elif result["outcome"] == "retryable":
                    updated = await conn.execute(
                        """update analytics_history_media_r2_migrations set
                             error_code=null,error_detail=null,updated_at=now()
                           where id=any($1::bigint[]) and copy_plan_sha256=$2
                             and status='copy_required'""",
                        ids,
                        args.plan_sha256,
                    )
                else:
                    updated = await conn.execute(
                        """update analytics_history_media_r2_migrations set
                             status='failed',error_code='CLOUD_COPY_FATAL',
                             error_detail=$2,updated_at=now()
                           where id=any($1::bigint[]) and copy_plan_sha256=$3
                             and status='copy_required'""",
                        ids,
                        str(result.get("error_kind") or "fatal"),
                        args.plan_sha256,
                    )
                if updated != f"UPDATE {len(ids)}":
                    raise RuntimeError("cloud Copy ledger ownership changed")
            fatal = int(receipt["outcome_counts"].get("fatal", 0))
            await conn.execute(
                """update analytics_history_media_r2_cloud_copy_tasks set
                     status=$2,receipt_sha256=$3,outcome_counts=$4::jsonb,
                     completed_at=now(),updated_at=now()
                   where task_id=$1::uuid""",
                bundle["task_id"],
                "failed" if fatal else "committed",
                receipt["receipt_sha256"],
                json.dumps(receipt["outcome_counts"]),
            )
            remaining = int(
                await conn.fetchval(
                    """select count(*) from analytics_history_media_r2_migrations m
                         join analytics_history_media_migration_plan_batches b
                           on b.plan_sha256=$1 and b.batch_no=$2
                          and m.id between b.first_ledger_id and b.last_ledger_id
                        where m.copy_plan_sha256=$1
                          and m.status in ('copy_required','failed')""",
                    args.plan_sha256,
                    int(task["batch_no"]),
                )
            )
            if remaining == 0:
                copied_count = int(
                    await conn.fetchval(
                        """select count(*) from analytics_history_media_r2_migrations m
                             join analytics_history_media_migration_plan_batches b
                               on b.plan_sha256=$1 and b.batch_no=$2
                              and m.id between b.first_ledger_id and b.last_ledger_id
                            where m.copy_plan_sha256=$1
                              and m.status='copied_verified'""",
                        args.plan_sha256,
                        int(task["batch_no"]),
                    )
                )
                await conn.execute(
                    """update analytics_history_media_migration_plan_batches set
                         status='completed',started_at=coalesce(started_at,now()),
                         completed_at=now(),outcome_counts=$3::jsonb,updated_at=now()
                       where plan_sha256=$1 and batch_no=$2""",
                    args.plan_sha256,
                    int(task["batch_no"]),
                    json.dumps({"copied_verified": copied_count}),
                )
            if fatal:
                await conn.execute(
                    """update analytics_history_media_r2_cloud_copy_plan_sessions set
                         status='failed',updated_at=now() where plan_sha256=$1""",
                    args.plan_sha256,
                )
            elif not int(
                await conn.fetchval(
                    """select count(*)
                         from analytics_history_media_migration_plan_batches
                        where plan_sha256=$1 and status<>'completed'""",
                    args.plan_sha256,
                )
            ):
                await conn.execute(
                    """update analytics_history_media_r2_cloud_copy_plan_sessions set
                         status='completed',completed_at=now(),updated_at=now()
                       where plan_sha256=$1""",
                    args.plan_sha256,
                )
        print(
            json.dumps(
                {
                    "task_id": bundle["task_id"],
                    "status": "failed" if fatal else "committed",
                    "outcome_counts": receipt["outcome_counts"],
                },
                sort_keys=True,
            )
        )
    finally:
        await conn.close()


async def _main_async(args: argparse.Namespace) -> None:
    if args.command == "export-head-task":
        await _export_head_task(args)
    elif args.command == "export-copy-task":
        await _export_copy_task(args)
    elif args.command == "run-head-task":
        await _run_head_task(args)
    elif args.command == "run-copy-task":
        await _run_copy_task(args)
    elif args.command == "import-copy-receipt":
        await _import_copy_receipt(args)


def main() -> None:
    asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    main()
