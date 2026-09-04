#!/usr/bin/env python3
"""Resumable same-bucket migration from temps/ to template-submissions/."""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


BUCKET = "user-data-prod"
SOURCE_PREFIX = "temps/"
TARGET_PREFIX = "template-submissions/"
RETIREMENT_SCHEMA = "allbot-r2-template-submission-retirement/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def destination_key(source_key: str) -> str:
    if not source_key.startswith(SOURCE_PREFIX) or source_key == SOURCE_PREFIX:
        raise ValueError("source key must be a non-empty temps/ object")
    return f"{TARGET_PREFIX}{source_key[len(SOURCE_PREFIX):]}"


def validate_execute_gate(*, bucket: str, enabled: bool, confirmation: str) -> None:
    if bucket != BUCKET:
        raise ValueError("template migration is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMPLATE_SUBMISSION_MIGRATION_ENABLED must be true")
    if confirmation != f"COPY_VERIFIED_TEMPLATE_SUBMISSIONS_{bucket}":
        raise ValueError("exact template migration confirmation is required")


def validate_switch_gate(*, bucket: str, enabled: bool, confirmation: str) -> None:
    if bucket != BUCKET or not enabled:
        raise ValueError("template database switch is restricted and disabled")
    if confirmation != f"SWITCH_VERIFIED_TEMPLATE_SUBMISSIONS_{bucket}":
        raise ValueError("exact template database switch confirmation is required")


def validate_retirement_gate(
    *,
    bucket: str,
    enabled: bool,
    confirmation: str,
    plan_sha256: str,
) -> None:
    if bucket != BUCKET or not enabled:
        raise ValueError("template source retirement is restricted and disabled")
    expected = (
        f"DELETE_VERIFIED_TEMPLATE_SUBMISSION_SOURCES_{bucket}:{plan_sha256}"
    )
    if not hmac.compare_digest(confirmation, expected):
        raise ValueError("exact plan-bound template source retirement confirmation is required")


def _canonical_json_sha256(value: dict) -> str:
    payload = dict(value)
    payload.pop("plan_sha256", None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_retirement_plan(plan: dict) -> dict:
    sealed = dict(plan)
    sealed["plan_sha256"] = _canonical_json_sha256(sealed)
    return sealed


def load_retirement_plan(path: Path, expected_sha256: str) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    actual = _canonical_json_sha256(plan)
    if (
        plan.get("schema") != RETIREMENT_SCHEMA
        or plan.get("mode") != "dry-run"
        or plan.get("plan_sha256") != actual
    ):
        raise ValueError("retirement plan is invalid or modified")
    if not expected_sha256 or not hmac.compare_digest(actual, expected_sha256):
        raise ValueError("retirement plan SHA-256 does not match")
    return plan


def _atomic_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def build_retirement_plan(
    db: sqlite3.Connection,
    *,
    bucket: str,
    scanned: int,
    database_references: int,
) -> dict:
    if bucket != BUCKET:
        raise ValueError("template source retirement is restricted to user-data-prod")
    if database_references:
        raise ValueError("template source retirement requires zero database references")
    rows = db.execute(
        """select source_key,target_key,byte_size,status,source_sha256,target_sha256
             from objects order by source_key"""
    ).fetchall()
    if len(rows) != int(scanned):
        raise ValueError("template source inventory does not fully match migration state")
    objects = []
    for source_key, target_key, byte_size, status, source_sha, target_sha in rows:
        if (
            status != "verified"
            or target_key != destination_key(str(source_key))
            or not _SHA256_RE.fullmatch(str(source_sha or ""))
            or source_sha != target_sha
        ):
            raise ValueError("template source retirement requires full verified migration")
        objects.append(
            {
                "source_key": str(source_key),
                "target_key": str(target_key),
                "byte_size": int(byte_size),
                "sha256": str(source_sha),
            }
        )
    return seal_retirement_plan(
        {
            "schema": RETIREMENT_SCHEMA,
            "mode": "dry-run",
            "bucket": bucket,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database_references": 0,
            "object_count": len(objects),
            "bytes": sum(item["byte_size"] for item in objects),
            "objects": objects,
        }
    )


def _source_inventory(client, bucket: str) -> dict[str, int]:
    result: dict[str, int] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=SOURCE_PREFIX):
        for item in page.get("Contents", []):
            key = str(item.get("Key") or "")
            if key and key != SOURCE_PREFIX:
                result[key] = int(item.get("Size") or 0)
    return result


def _normalized_etag(head: dict) -> str:
    return str(head.get("ETag") or "").strip().strip('"')


def _retirement_preflight_one(
    client,
    bucket: str,
    source_key: str,
    item: dict,
    state_row: tuple,
    live_size: int,
) -> tuple[str, dict]:
    target_key = str(item.get("target_key") or "")
    byte_size = int(item.get("byte_size", -1))
    digest = str(item.get("sha256") or "")
    state_target, state_size, status, source_sha, target_sha = state_row
    if (
        target_key != destination_key(source_key)
        or state_target != target_key
        or int(state_size) != byte_size
        or status not in {"verified", "retirement_started", "retired"}
        or source_sha != digest
        or target_sha != digest
        or not _SHA256_RE.fullmatch(digest)
    ):
        raise ValueError("retirement plan object no longer matches migration state")

    target_head = _head_optional(client, bucket, target_key)
    if (
        target_head is None
        or int(target_head.get("ContentLength", -1)) != byte_size
        or _sha256(client, bucket, target_key) != digest
    ):
        raise RuntimeError("RETIREMENT_TARGET_CHANGED")

    source_head = _head_optional(client, bucket, source_key)
    if source_head is None:
        if status not in {"retirement_started", "retired"}:
            raise RuntimeError("RETIREMENT_SOURCE_MISSING_BEFORE_START")
        return source_key, {"present": False}
    if status == "retired":
        raise RuntimeError("RETIREMENT_SOURCE_REAPPEARED")
    if (
        int(live_size) != byte_size
        or int(source_head.get("ContentLength", -1)) != byte_size
        or _sha256(client, bucket, source_key) != digest
    ):
        raise RuntimeError("RETIREMENT_SOURCE_CHANGED")
    return source_key, {
        "present": True,
        "etag": _normalized_etag(source_head),
        "byte_size": byte_size,
    }


def _run_retirement_preflight_batch(
    client,
    bucket: str,
    inputs: list[tuple[str, dict, tuple, int]],
    *,
    workers: int,
) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _retirement_preflight_one,
                client,
                bucket,
                source_key,
                item,
                state_row,
                live_size,
            )
            for source_key, item, state_row, live_size in inputs
        ]
        return dict(future.result() for future in as_completed(futures))


def _retire_source_one(
    client,
    bucket: str,
    source_key: str,
    item: dict,
    preflight: dict,
) -> str:
    target_key = str(item["target_key"])
    digest = str(item["sha256"])
    current_head = _head_optional(client, bucket, source_key)
    if current_head is None:
        raise RuntimeError("RETIREMENT_SOURCE_DISAPPEARED_AFTER_PREFLIGHT")
    frozen_etag = str(preflight["etag"])
    if (
        int(current_head.get("ContentLength", -1)) != int(item["byte_size"])
        or (frozen_etag and _normalized_etag(current_head) != frozen_etag)
    ):
        raise RuntimeError("RETIREMENT_SOURCE_IDENTITY_DRIFT")
    if not frozen_etag and _sha256(client, bucket, source_key) != digest:
        raise RuntimeError("RETIREMENT_SOURCE_IDENTITY_DRIFT")
    client.delete_object(Bucket=bucket, Key=source_key)
    if _head_optional(client, bucket, source_key) is not None:
        raise RuntimeError("RETIREMENT_SOURCE_STILL_EXISTS")
    target_head = _head_optional(client, bucket, target_key)
    if (
        target_head is None
        or int(target_head.get("ContentLength", -1)) != int(item["byte_size"])
        or _sha256(client, bucket, target_key) != digest
    ):
        raise RuntimeError("RETIREMENT_TARGET_CHANGED_AFTER_DELETE")
    return source_key


def _run_retirement_delete_batch(
    client,
    bucket: str,
    inputs: list[tuple[str, dict, dict]],
    *,
    workers: int,
    on_started,
    on_retired,
    on_failure,
) -> None:
    iterator = iter(inputs)
    first_error: Exception | None = None
    with ThreadPoolExecutor(max_workers=workers) as executor:
        active = {}

        def submit_next() -> bool:
            try:
                source_key, item, preflight = next(iterator)
            except StopIteration:
                return False
            on_started(source_key)
            future = executor.submit(
                _retire_source_one,
                client,
                bucket,
                source_key,
                item,
                preflight,
            )
            active[future] = source_key
            return True

        for _ in range(workers):
            if not submit_next():
                break
        while active:
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                source_key = active.pop(future)
                if future.cancelled():
                    continue
                try:
                    on_retired(future.result())
                except Exception as exc:
                    on_failure(source_key, exc)
                    if first_error is None:
                        first_error = exc
            if first_error is not None:
                for future in active:
                    future.cancel()
                continue
            while len(active) < workers and submit_next():
                pass
    if first_error is not None:
        raise first_error


def execute_retirement_plan(
    client,
    db: sqlite3.Connection,
    *,
    bucket: str,
    plan: dict,
    workers: int = 1,
) -> dict:
    if (
        bucket != BUCKET
        or plan.get("bucket") != bucket
        or plan.get("schema") != RETIREMENT_SCHEMA
        or plan.get("mode") != "dry-run"
        or plan.get("plan_sha256") != _canonical_json_sha256(plan)
    ):
        raise ValueError("retirement plan is invalid or modified")
    objects = list(plan.get("objects") or [])
    if (
        int(plan.get("object_count", -1)) != len(objects)
        or int(plan.get("bytes", -1))
        != sum(int(item.get("byte_size", -1)) for item in objects)
        or int(plan.get("database_references", -1)) != 0
    ):
        raise ValueError("retirement plan aggregate is invalid")
    plan_by_source = {str(item.get("source_key") or ""): item for item in objects}
    if "" in plan_by_source or len(plan_by_source) != len(objects):
        raise ValueError("retirement plan contains invalid or duplicate sources")

    state_rows = {
        str(row[0]): row[1:]
        for row in db.execute(
            """select source_key,target_key,byte_size,status,source_sha256,target_sha256
                 from objects order by source_key"""
        )
    }
    if set(state_rows) != set(plan_by_source):
        raise ValueError("retirement plan no longer matches migration state")
    live_sources = _source_inventory(client, bucket)
    unexpected = set(live_sources) - set(plan_by_source)
    if unexpected:
        raise ValueError("new template source objects appeared after plan freeze")

    preflight_inputs = []
    for source_key, item in plan_by_source.items():
        preflight_inputs.append(
            (source_key, item, state_rows[source_key], live_sources.get(source_key, -1))
        )
    preflight = _run_retirement_preflight_batch(
        client,
        bucket,
        preflight_inputs,
        workers=workers,
    )

    deleted_sources = []
    already_absent = 0
    retirement_inputs = []
    for source_key, item in plan_by_source.items():
        if not preflight[source_key]["present"]:
            already_absent += 1
            db.execute(
                "update objects set status='retired',error=null,updated_at=? where source_key=?",
                (datetime.now(timezone.utc).isoformat(), source_key),
            )
            db.commit()
            continue
        retirement_inputs.append((source_key, item, preflight[source_key]))

    def mark_started(source_key: str) -> None:
        db.execute(
            "update objects set status='retirement_started',error=null,updated_at=? where source_key=?",
            (datetime.now(timezone.utc).isoformat(), source_key),
        )
        db.commit()

    def mark_retired(source_key: str) -> None:
        db.execute(
            "update objects set status='retired',error=null,updated_at=? where source_key=?",
            (datetime.now(timezone.utc).isoformat(), source_key),
        )
        db.commit()
        deleted_sources.append(source_key)

    def mark_failed(source_key: str, exc: Exception) -> None:
        db.execute(
            "update objects set error=?,updated_at=? where source_key=?",
            (type(exc).__name__, datetime.now(timezone.utc).isoformat(), source_key),
        )
        db.commit()

    _run_retirement_delete_batch(
        client,
        bucket,
        retirement_inputs,
        workers=workers,
        on_started=mark_started,
        on_retired=mark_retired,
        on_failure=mark_failed,
    )

    return {
        "status": "completed",
        "approved_plan_sha256": str(plan["plan_sha256"]),
        "object_count": len(objects),
        "bytes": int(plan["bytes"]),
        "deleted_count": len(deleted_sources),
        "already_absent_count": already_absent,
        "post_delete_verified_count": len(deleted_sources) + already_absent,
    }


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("pragma journal_mode=wal")
    db.execute(
        """create table if not exists objects(
          source_key text primary key,target_key text not null,byte_size integer not null,
          status text not null,sha256 text,error text,updated_at text not null
        ) without rowid"""
    )
    columns = {row[1] for row in db.execute("pragma table_info(objects)")}
    for name, declaration in (
        ("source_sha256", "text"),
        ("target_sha256", "text"),
        ("contribution_id", "integer"),
    ):
        if name not in columns:
            db.execute(f"alter table objects add column {name} {declaration}")
    db.commit()
    os.chmod(path, 0o600)
    return db


def _client(*, max_pool_connections: int = 8):
    required = ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit(f"missing R2 configuration: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            max_pool_connections=max(8, int(max_pool_connections)),
        ),
    )


def _sha256(client, bucket: str, key: str) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    try:
        while chunk := body.read(4 * 1024 * 1024):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def _head_optional(client, bucket: str, key: str):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def _scan(client, db: sqlite3.Connection, bucket: str) -> int:
    paginator = client.get_paginator("list_objects_v2")
    now = datetime.now(timezone.utc).isoformat()
    seen = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=SOURCE_PREFIX):
        for item in page.get("Contents", []):
            source_key = str(item["Key"])
            if source_key == SOURCE_PREFIX:
                continue
            db.execute(
                """insert into objects(source_key,target_key,byte_size,status,updated_at)
                   values(?,?,?,'pending',?) on conflict(source_key) do update set
                   target_key=excluded.target_key,byte_size=excluded.byte_size,
                   status=case when objects.status='verified' then objects.status else 'pending' end,
                   updated_at=excluded.updated_at""",
                (source_key, destination_key(source_key), int(item.get("Size") or 0), now),
            )
            seen += 1
    db.commit()
    return seen


def _target_inventory(client, db: sqlite3.Connection, bucket: str) -> dict[str, int]:
    summary = {
        "source_missing": 0,
        "target_existing": 0,
        "target_missing": 0,
        "target_size_conflicts": 0,
        "target_existing_unverified": 0,
    }
    rows = db.execute(
        "select source_key,target_key,byte_size,status from objects order by source_key"
    )
    for source_key, target_key, byte_size, status in rows:
        source_head = _head_optional(client, bucket, source_key)
        if source_head is None:
            summary["source_missing"] += 1
        target_head = _head_optional(client, bucket, target_key)
        if target_head is None:
            summary["target_missing"] += 1
            continue
        summary["target_existing"] += 1
        if int(target_head.get("ContentLength", -1)) != int(byte_size):
            summary["target_size_conflicts"] += 1
        elif status != "verified":
            summary["target_existing_unverified"] += 1
    return summary


async def _database_reference_count() -> int:
    from sqlalchemy import func, select
    from src.database.core import AsyncSessionLocal
    from src.database.models import TemplateContribution

    async with AsyncSessionLocal() as session:
        value = await session.scalar(
            select(func.count())
            .select_from(TemplateContribution)
            .where(TemplateContribution.file_path.like(f"{SOURCE_PREFIX}%"))
        )
        return int(value or 0)


async def _dispose_database_engine() -> None:
    from src.database.core import engine

    await engine.dispose()


def _execute_retirement_with_reference_guard(
    client,
    db: sqlite3.Connection,
    *,
    bucket: str,
    plan: dict,
    workers: int,
) -> dict:
    loop = asyncio.new_event_loop()
    try:
        database_references = loop.run_until_complete(_database_reference_count())
        if database_references:
            raise SystemExit(
                "template source retirement requires zero database references"
            )
        report = execute_retirement_plan(
            client,
            db,
            bucket=bucket,
            plan=plan,
            workers=workers,
        )
        report["database_references_before"] = database_references
        report["database_references_after"] = loop.run_until_complete(
            _database_reference_count()
        )
        if report["database_references_after"]:
            raise RuntimeError("template database references reappeared during retirement")
        return report
    finally:
        loop.run_until_complete(_dispose_database_engine())
        loop.close()


def _copy_and_verify(client, bucket: str, source_key: str, target_key: str, size: int) -> tuple[str, str]:
    source_head = client.head_object(Bucket=bucket, Key=source_key)
    if int(source_head.get("ContentLength", -1)) != size:
        raise RuntimeError("SOURCE_SIZE_CHANGED")
    source_sha = _sha256(client, bucket, source_key)
    target_head = _head_optional(client, bucket, target_key)
    if target_head is None:
        client.copy_object(
            Bucket=bucket,
            Key=target_key,
            CopySource={"Bucket": bucket, "Key": source_key},
            MetadataDirective="COPY",
        )
        target_head = client.head_object(Bucket=bucket, Key=target_key)
    if int(target_head.get("ContentLength", -1)) != size:
        raise RuntimeError("TARGET_SIZE_MISMATCH")
    target_sha = _sha256(client, bucket, target_key)
    if target_sha != source_sha:
        raise RuntimeError("TARGET_SHA256_MISMATCH")
    return source_sha, target_sha


def _run_copy_batch(
    client,
    bucket: str,
    rows: list[tuple[str, str, int]],
    *,
    workers: int,
    on_success,
    on_failure,
) -> None:
    """Verify rows concurrently while keeping all SQLite writes in the caller thread."""
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {
        executor.submit(
            _copy_and_verify,
            client,
            bucket,
            source_key,
            target_key,
            int(size),
        ): (source_key, target_key, int(size))
        for source_key, target_key, size in rows
    }
    failed = False
    try:
        for future in as_completed(futures):
            row = futures[future]
            try:
                on_success(row, future.result())
            except Exception as exc:
                failed = True
                on_failure(row, exc)
                for pending in futures:
                    pending.cancel()
                raise
    finally:
        executor.shutdown(wait=not failed, cancel_futures=failed)


async def _switch_database_references(state_path: Path) -> int:
    from sqlalchemy import select
    from src.database.core import AsyncSessionLocal
    from src.database.models import TemplateContribution

    state = sqlite3.connect(state_path)
    verified = {
        row[0]: row[1]
        for row in state.execute(
            "select source_key,target_key from objects where status='verified'"
        )
    }
    switched = 0
    try:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(TemplateContribution)
                    .where(TemplateContribution.file_path.like(f"{SOURCE_PREFIX}%"))
                    .with_for_update()
                )
            ).scalars().all()
            for contribution in rows:
                mapping = verified.get(str(contribution.file_path))
                if mapping is None:
                    raise RuntimeError("UNVERIFIED_TEMPLATE_DATABASE_REFERENCE")
                source_key = str(contribution.file_path)
                target_key = mapping
                contribution.file_path = target_key
                state.execute(
                    "update objects set contribution_id=?,updated_at=? where source_key=?",
                    (contribution.id, datetime.now(timezone.utc).isoformat(), source_key),
                )
                switched += 1
            await session.commit()
        state.commit()
        return switched
    finally:
        state.close()


def run(args) -> dict:
    client = _client(max_pool_connections=args.workers * 2)
    state_path = Path(args.state)
    db = _connect(state_path)
    try:
        if args.execute_retirement:
            plan = load_retirement_plan(
                Path(args.approved_retirement_plan),
                args.retirement_plan_sha256,
            )
            validate_retirement_gate(
                bucket=args.bucket,
                enabled=os.getenv(
                    "R2_TEMPLATE_SUBMISSION_RETIREMENT_ENABLED", ""
                ).lower()
                == "true",
                confirmation=args.retirement_confirm,
                plan_sha256=args.retirement_plan_sha256,
            )
            report = _execute_retirement_with_reference_guard(
                client,
                db,
                bucket=args.bucket,
                plan=plan,
                workers=args.workers,
            )
            _atomic_private_json(Path(args.retirement_receipt), report)
            return report

        scanned = _scan(client, db, args.bucket)
        if args.plan_retirement:
            database_references = asyncio.run(_database_reference_count())
            plan = build_retirement_plan(
                db,
                bucket=args.bucket,
                scanned=scanned,
                database_references=database_references,
            )
            plan_path = Path(args.retirement_plan_out)
            _atomic_private_json(plan_path, plan)
            return {
                "mode": "retirement-dry-run",
                "bucket": args.bucket,
                "object_count": int(plan["object_count"]),
                "bytes": int(plan["bytes"]),
                "database_references": database_references,
                "plan_sha256": str(plan["plan_sha256"]),
                "plan": str(plan_path),
            }
        if args.execute:
            validate_execute_gate(
                bucket=args.bucket,
                enabled=os.getenv("R2_TEMPLATE_SUBMISSION_MIGRATION_ENABLED", "").lower() == "true",
                confirmation=args.confirm,
            )
            rows = db.execute(
                """select source_key,target_key,byte_size from objects
                   where status<>'verified' order by source_key limit ?""",
                (args.limit,),
            ).fetchall()
            def mark_verified(row, digests) -> None:
                source_key = row[0]
                source_digest, target_digest = digests
                db.execute(
                    """update objects set status='verified',sha256=?,source_sha256=?,
                       target_sha256=?,error=null,updated_at=? where source_key=?""",
                    (source_digest, source_digest, target_digest,
                     datetime.now(timezone.utc).isoformat(), source_key),
                )
                db.commit()

            def mark_failed(row, exc: Exception) -> None:
                db.execute(
                    "update objects set status='failed',error=?,updated_at=? where source_key=?",
                    (type(exc).__name__, datetime.now(timezone.utc).isoformat(), row[0]),
                )
                db.commit()

            _run_copy_batch(
                client,
                args.bucket,
                rows,
                workers=args.workers,
                on_success=mark_verified,
                on_failure=mark_failed,
            )
        total, verified, failed, total_bytes = db.execute(
            """select count(*),count(*) filter(where status='verified'),
               count(*) filter(where status='failed'),coalesce(sum(byte_size),0) from objects"""
        ).fetchone()
        report = {
            "mode": "execute" if args.execute else "dry-run",
            "bucket": args.bucket,
            "scanned": scanned,
            "total": int(total),
            "verified": int(verified),
            "failed": int(failed),
            "bytes": int(total_bytes),
            "state": str(state_path),
        }
        if not args.execute:
            report.update(_target_inventory(client, db, args.bucket))
            report["database_references"] = asyncio.run(
                _database_reference_count()
            )
        if args.switch_db_references:
            if not args.execute or verified != total or failed:
                raise SystemExit("database switch requires a fully verified migration")
            validate_switch_gate(
                bucket=args.bucket,
                enabled=os.getenv("R2_TEMPLATE_SUBMISSION_DB_SWITCH_ENABLED", "").lower() == "true",
                confirmation=args.switch_confirm,
            )
            report["database_references_switched"] = asyncio.run(
                _switch_database_references(state_path)
            )
        return report
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--switch-db-references", action="store_true")
    parser.add_argument("--switch-confirm", default="")
    parser.add_argument("--plan-retirement", action="store_true")
    parser.add_argument("--retirement-plan-out", default="")
    parser.add_argument("--execute-retirement", action="store_true")
    parser.add_argument("--approved-retirement-plan", default="")
    parser.add_argument("--retirement-plan-sha256", default="")
    parser.add_argument("--retirement-confirm", default="")
    parser.add_argument("--retirement-receipt", default="")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10_000:
        raise SystemExit("limit must be between 1 and 10000")
    if args.workers < 1 or args.workers > 32:
        raise SystemExit("workers must be between 1 and 32")
    if args.plan_retirement and not args.retirement_plan_out:
        raise SystemExit("--plan-retirement requires --retirement-plan-out")
    if args.execute_retirement and not all(
        (
            args.approved_retirement_plan,
            args.retirement_plan_sha256,
            args.retirement_confirm,
            args.retirement_receipt,
        )
    ):
        raise SystemExit(
            "--execute-retirement requires approved plan, SHA, confirmation, and receipt"
        )
    if args.execute_retirement and (
        args.execute or args.switch_db_references or args.plan_retirement
    ):
        raise SystemExit("template retirement cannot be combined with migration modes")
    print(json.dumps(run(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
