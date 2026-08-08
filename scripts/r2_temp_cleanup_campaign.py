#!/usr/bin/env python3
"""Freeze and resume a complete verified R2 staging cleanup campaign."""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botocore.exceptions import ClientError  # noqa: E402
from sqlalchemy import text  # noqa: E402

from scripts.r2_temp_cleanup import (  # noqa: E402
    Candidate,
    DEFAULT_MAX_DELETE_BYTES,
    PRODUCTION_BUCKET,
    _active_task_references,
    _business_references,
    _deleted_object_is_absent,
    _file_sha256,
    _r2_client,
    _sha256_object,
)


DEFAULT_MAX_BATCH_OBJECTS = 10_000
REFERENCE_CHUNK_SIZE = 10_000
VERIFY_CHUNK_SIZE = 1_000
KNOWN_STAGING_PREFIXES = (
    "staging/user-uploads/",
    "staging/worker-results/",
)


def _known_staging_kind(key: str) -> str | None:
    for prefix, kind in (
        ("staging/user-uploads/", "input"),
        ("staging/worker-results/", "output"),
    ):
        if key.startswith(prefix):
            parts = key[len(prefix) :].split("/")
            return kind if len(parts) >= 2 and all(parts) else None
    return None


def _durable_kind(key: str) -> str | None:
    for prefix, kind in (("task-inputs/", "input"), ("task-results/", "output")):
        if key.startswith(prefix):
            parts = key[len(prefix) :].split("/")
            return kind if len(parts) >= 2 and all(parts) else None
    return None


def _canonical_json_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("plan_sha256", None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def select_full_staging_candidates(
    connection: sqlite3.Connection, *, cutoff: str
) -> list[Candidate]:
    """Return every old, known staging object with a typed durable twin.

    ETag and size are only the indexed prefilter. Full HEAD, size and SHA checks
    happen before an object enters the frozen campaign.
    """
    connection.execute("drop table if exists temp.campaign_durable_twins")
    connection.execute(
        """
        create temp table campaign_durable_twins(
          kind text not null,
          size integer not null,
          etag text not null,
          key text not null,
          primary key(kind,size,etag)
        ) without rowid
        """
    )
    connection.execute(
        """
        insert into campaign_durable_twins(kind,size,etag,key)
        select case
                 when key like 'task-inputs/%' then 'input'
                 else 'output'
               end,
               size,etag,min(key)
          from objects
         where key like 'task-inputs/%'
            or key like 'task-results/%'
         group by 1,size,etag
        """
    )
    rows = connection.execute(
        """
        select source.key,durable.key,source.size,source.etag,
               source.last_modified
          from objects source
          join campaign_durable_twins durable
            on durable.kind=case
                 when source.key like 'staging/user-uploads/%' then 'input'
                 else 'output'
               end
           and durable.size=source.size
           and durable.etag=source.etag
         where source.last_modified < ?
           and (
             source.key glob 'staging/user-uploads/*/*'
             or source.key glob 'staging/worker-results/*/*'
           )
         order by source.last_modified,source.key
        """,
        (cutoff,),
    ).fetchall()
    return [Candidate(*row) for row in rows if _known_staging_kind(str(row[0]))]


async def _history_campaign_references(keys: list[str]) -> dict[str, set[str]]:
    if not keys:
        return {}
    from src.database.core import AsyncSessionLocal

    query = text(
        """
        with candidate(key) as (select unnest(cast(:keys as text[]))), refs as (
          select h.id history_id,h.task_id,h.is_favorited,h.is_public,
                 btrim(coalesce(h.output_file,'')) ref
            from history h
          union all
          select h.id,h.task_id,h.is_favorited,h.is_public,btrim(x.ref)
            from history h cross join lateral
              unnest(string_to_array(coalesce(h.input_file,''),'|')) x(ref)
          union all
          select h.id,h.task_id,h.is_favorited,h.is_public,
                 trim(both '"' from p.path::text)
            from history h cross join lateral jsonb_path_query(
              coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path'
            ) p(path)
        ), matched as (
          select distinct candidate.key,refs.history_id,refs.task_id,
                          refs.is_favorited,refs.is_public
            from refs join candidate
              on refs.ref=candidate.key or refs.ref like '%/'||candidate.key
        ), categorized as (
          select 'history' category,key from matched
          union select 'favorite',key from matched where is_favorited is true
          union select 'public',key from matched where is_public is true
          union select 'gallery',matched.key
            from matched join gallery_posts post on post.task_id=matched.task_id
        ) select category,key from categorized
        """
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query, {"keys": keys})).all()
    result: dict[str, set[str]] = defaultdict(set)
    for category, key in rows:
        result[str(category)].add(str(key))
    return dict(result)


def _merge_reference_maps(
    target: dict[str, set[str]], source: dict[str, set[str]]
) -> None:
    for category, keys in source.items():
        target.setdefault(category, set()).update(keys)


async def campaign_reference_categories(
    keys: list[str], *, chunk_size: int = REFERENCE_CHUNK_SIZE
) -> dict[str, set[str]]:
    """Fail closed if any required database or active-task lookup fails."""
    result: dict[str, set[str]] = {}
    for offset in range(0, len(keys), chunk_size):
        chunk = keys[offset : offset + chunk_size]
        history, business, active = await asyncio.gather(
            _history_campaign_references(chunk),
            _business_references(chunk),
            _active_task_references(chunk),
        )
        _merge_reference_maps(result, history)
        _merge_reference_maps(result, business)
        if active:
            result.setdefault("active_task", set()).update(active)
    return result


def _head_size(client, bucket: str, key: str) -> int:
    return int(client.head_object(Bucket=bucket, Key=key)["ContentLength"])


async def verify_campaign_candidates(
    client,
    bucket: str,
    candidates: list[Candidate],
    *,
    concurrency: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def io(function, *args):
        async with semaphore:
            return await asyncio.to_thread(function, *args)

    async def verify(item: Candidate):
        try:
            source_size, durable_size = await asyncio.gather(
                io(_head_size, client, bucket, item.key),
                io(_head_size, client, bucket, item.durable_key),
            )
            if source_size != item.byte_size or durable_size != item.byte_size:
                raise RuntimeError("HEAD_SIZE_MISMATCH")
            source_sha, durable_sha = await asyncio.gather(
                io(_sha256_object, client, bucket, item.key),
                io(_sha256_object, client, bucket, item.durable_key),
            )
            if source_sha != durable_sha:
                raise RuntimeError("SHA256_MISMATCH")
            return {**asdict(item), "sha256": source_sha}, None
        except Exception as exc:  # Object probes are reported and excluded.
            return None, {"key": item.key, "error": type(exc).__name__}

    verified: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for offset in range(0, len(candidates), VERIFY_CHUNK_SIZE):
        rows = await asyncio.gather(
            *(verify(item) for item in candidates[offset : offset + VERIFY_CHUNK_SIZE])
        )
        verified.extend(item for item, _ in rows if item is not None)
        failures.extend(failure for _, failure in rows if failure is not None)
    return verified, failures


def build_campaign_plan(
    *,
    inventory_path: Path,
    cutoff: str,
    candidates: list[Candidate],
    verified: list[dict[str, Any]],
    blocked: dict[str, set[str]],
    probe_failures: list[dict[str, str]],
    inventory_integrity: str,
    inventory_object_count: int,
    inventory_bytes: int,
    inventory_mtime: float | None = None,
    staging_summary: dict[str, Any] | None = None,
    excluded_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    campaign_id = str(uuid.uuid4())
    blocked_keys = set().union(*blocked.values()) if blocked else set()
    plan: dict[str, Any] = {
        "campaign_id": campaign_id,
        "batch_id": campaign_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "campaign-dry-run",
        "bucket": PRODUCTION_BUCKET,
        "cutoff": cutoff,
        "known_staging_prefixes": list(KNOWN_STAGING_PREFIXES),
        "inventory": {
            "path": str(inventory_path),
            "sha256": _file_sha256(inventory_path),
            "mtime": inventory_mtime if inventory_mtime is not None else inventory_path.stat().st_mtime,
            "object_count": int(inventory_object_count),
            "bytes": int(inventory_bytes),
            "integrity": inventory_integrity,
        },
        "prefilter_candidate_count": len(candidates),
        "referenced_blocked_count": len(blocked_keys),
        "reference_categories": {
            category: len(keys) for category, keys in sorted(blocked.items())
        },
        "probe_failure_count": len(probe_failures),
        "probe_failures": probe_failures,
        "campaign_object_count": len(verified),
        "campaign_bytes": sum(int(item["byte_size"]) for item in verified),
        "staging": staging_summary or {},
        "excluded_report_only": excluded_summary or {},
        "objects": verified,
    }
    plan["plan_sha256"] = _canonical_json_sha256(plan)
    return plan


def load_campaign_plan(path: Path | str, expected_sha256: str) -> dict[str, Any]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    actual = _canonical_json_sha256(plan)
    if plan.get("mode") != "campaign-dry-run" or plan.get("plan_sha256") != actual:
        raise SystemExit("approved cleanup campaign is invalid or has been modified")
    if not expected_sha256 or actual != expected_sha256:
        raise SystemExit("approved cleanup campaign SHA-256 does not match")
    if int(plan.get("campaign_object_count", -1)) != len(plan.get("objects", [])):
        raise SystemExit("approved cleanup campaign object count is invalid")
    if int(plan.get("campaign_bytes", -1)) != sum(
        int(item["byte_size"]) for item in plan.get("objects", [])
    ):
        raise SystemExit("approved cleanup campaign byte count is invalid")
    for item in plan.get("objects", []):
        staging_kind = _known_staging_kind(str(item.get("key", "")))
        if staging_kind is None or staging_kind != _durable_kind(str(item.get("durable_key", ""))):
            raise SystemExit("approved cleanup campaign contains an unsafe key mapping")
    return plan


def validate_campaign_execute_gate(
    *, bucket: str, enabled: bool, confirmation: str, plan_sha256: str
) -> None:
    if bucket != PRODUCTION_BUCKET:
        raise ValueError("cleanup campaign is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMP_CLEANUP_CAMPAIGN_ENABLED must be true")
    expected = f"EXECUTE_R2_TEMP_CAMPAIGN_{bucket}:{plan_sha256}"
    if confirmation != expected:
        raise ValueError("exact cleanup campaign confirmation is required")


class CampaignState:
    def __init__(self, path: Path, connection: sqlite3.Connection):
        self.path = path
        self.connection = connection

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        campaign_id: str,
        plan_sha256: str,
        inventory_sha256: str,
        objects: list[dict[str, Any]],
    ) -> "CampaignState":
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            create table if not exists metadata(key text primary key,value text not null);
            create table if not exists objects(
              ordinal integer primary key,
              key text not null unique,
              byte_size integer not null,
              payload text not null,
              status text not null default 'pending',
              reason text,
              updated_at text
            );
            """
        )
        metadata = {
            "campaign_id": campaign_id,
            "plan_sha256": plan_sha256,
            "inventory_sha256": inventory_sha256,
        }
        for key, value in metadata.items():
            existing = connection.execute(
                "select value from metadata where key=?", (key,)
            ).fetchone()
            if existing is not None and existing[0] != value:
                connection.close()
                raise SystemExit(f"campaign state {key} does not match")
            connection.execute(
                "insert or ignore into metadata(key,value) values(?,?)", (key, value)
            )
        existing_count = connection.execute("select count(*) from objects").fetchone()[0]
        if existing_count == 0:
            connection.executemany(
                "insert into objects(ordinal,key,byte_size,payload) values(?,?,?,?)",
                [
                    (
                        ordinal,
                        str(item["key"]),
                        int(item["byte_size"]),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                    )
                    for ordinal, item in enumerate(objects)
                ],
            )
        elif existing_count != len(objects):
            connection.close()
            raise SystemExit("campaign state object count does not match plan")
        else:
            stored = connection.execute(
                "select payload from objects order by ordinal"
            ).fetchall()
            expected = [
                json.dumps(item, ensure_ascii=False, sort_keys=True) for item in objects
            ]
            if [row[0] for row in stored] != expected:
                connection.close()
                raise SystemExit("campaign state objects do not match frozen plan")
        connection.commit()
        os.chmod(path, 0o600)
        return cls(path, connection)

    def next_batch(self, *, max_objects: int, max_bytes: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select payload,byte_size from objects where status='pending' order by ordinal"
        )
        selected: list[dict[str, Any]] = []
        used = 0
        for row in rows:
            size = int(row["byte_size"])
            if selected and (len(selected) >= max_objects or used + size > max_bytes):
                break
            if not selected and size > max_bytes:
                break
            selected.append(json.loads(row["payload"]))
            used += size
        return selected

    def first_pending(self) -> dict[str, Any] | None:
        row = self.connection.execute(
            "select payload from objects where status='pending' order by ordinal limit 1"
        ).fetchone()
        return json.loads(row[0]) if row else None

    def mark(self, key: str, status: str, *, reason: str) -> None:
        self.connection.execute(
            "update objects set status=?,reason=?,updated_at=? where key=?",
            (status, reason, datetime.now(timezone.utc).isoformat(), key),
        )
        self.connection.commit()

    def set_campaign_status(self, status: str, error: str = "") -> None:
        for key, value in (("status", status), ("last_error", error)):
            self.connection.execute(
                "insert into metadata(key,value) values(?,?) "
                "on conflict(key) do update set value=excluded.value",
                (key, value),
            )
        self.connection.commit()

    def summary(self) -> dict[str, Any]:
        counts = {
            str(status): {"count": int(count), "bytes": int(byte_count)}
            for status, count, byte_count in self.connection.execute(
                "select status,count(*),coalesce(sum(byte_size),0) from objects group by status"
            )
        }
        result: dict[str, Any] = {}
        for status, values in counts.items():
            result[f"{status}_count"] = values["count"]
            result[f"{status}_bytes"] = values["bytes"]
        return result

    def close(self) -> None:
        self.connection.close()


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


async def generate_campaign(args) -> dict[str, Any]:
    if not 1 <= args.verification_concurrency <= 16:
        raise SystemExit("verification concurrency must be between 1 and 16")
    inventory_path = Path(args.inventory)
    inventory = sqlite3.connect(inventory_path)
    try:
        integrity = str(inventory.execute("pragma integrity_check").fetchone()[0])
        if integrity != "ok":
            raise SystemExit("inventory integrity check failed")
        inventory_total = inventory.execute(
            "select count(*),coalesce(sum(size),0) from objects"
        ).fetchone()
        staging = inventory.execute(
            "select count(*),coalesce(sum(size),0),min(last_modified) "
            "from objects where key like 'staging/%'"
        ).fetchone()
        unknown_staging = inventory.execute(
            "select count(*),coalesce(sum(size),0) from objects "
            "where key like 'staging/%' "
            "and key not like 'staging/user-uploads/%' "
            "and key not like 'staging/worker-results/%'"
        ).fetchone()
        report_only = {}
        for label, predicate in (
            ("web_uploads", "key like 'web_uploads/%'"),
            ("temps", "key like 'temps/%'"),
            ("template_submissions", "key like 'template-submissions/%'"),
            ("flat_root", "instr(key,'/')=0"),
        ):
            count, size = inventory.execute(
                f"select count(*),coalesce(sum(size),0) from objects where {predicate}"
            ).fetchone()
            report_only[label] = {"object_count": int(count), "bytes": int(size)}
        candidates = select_full_staging_candidates(inventory, cutoff=args.cutoff)
    finally:
        inventory.close()
    references = await campaign_reference_categories([item.key for item in candidates])
    referenced = set().union(*references.values()) if references else set()
    eligible = [item for item in candidates if item.key not in referenced]
    verified, failures = await verify_campaign_candidates(
        _r2_client(), args.bucket, eligible, concurrency=args.verification_concurrency
    )
    plan = build_campaign_plan(
        inventory_path=inventory_path,
        cutoff=args.cutoff,
        candidates=candidates,
        verified=verified,
        blocked=references,
        probe_failures=failures,
        inventory_integrity=integrity,
        inventory_object_count=int(inventory_total[0]),
        inventory_bytes=int(inventory_total[1]),
        staging_summary={
            "object_count": int(staging[0]),
            "bytes": int(staging[1]),
            "oldest_last_modified": staging[2],
            "unknown_object_count": int(unknown_staging[0]),
            "unknown_bytes": int(unknown_staging[1]),
        },
        excluded_summary=report_only,
    )
    _atomic_private_json(Path(args.output), plan)
    return plan


def _client_error_code(exc: ClientError) -> str:
    return str((exc.response or {}).get("Error", {}).get("Code", ""))


async def _revalidate_planned_object(client, bucket: str, item: dict[str, Any]):
    try:
        source_size, durable_size = await asyncio.gather(
            asyncio.to_thread(_head_size, client, bucket, item["key"]),
            asyncio.to_thread(_head_size, client, bucket, item["durable_key"]),
        )
    except ClientError as exc:
        if _client_error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
            return False, "object_missing"
        raise
    expected_size = int(item["byte_size"])
    if source_size != expected_size or durable_size != expected_size:
        return False, "size_changed"
    try:
        source_sha, durable_sha = await asyncio.gather(
            asyncio.to_thread(_sha256_object, client, bucket, item["key"]),
            asyncio.to_thread(_sha256_object, client, bucket, item["durable_key"]),
        )
    except ClientError as exc:
        if _client_error_code(exc) in {"404", "NoSuchKey", "NotFound"}:
            return False, "object_missing"
        raise
    if source_sha != item["sha256"] or durable_sha != item["sha256"]:
        return False, "sha_changed"
    return True, "verified"


def _campaign_receipt(
    *, plan: dict[str, Any], state: CampaignState, status: str, error: str = ""
) -> dict[str, Any]:
    return {
        "campaign_id": plan["campaign_id"],
        "plan_sha256": plan["plan_sha256"],
        "inventory_sha256": plan["inventory"]["sha256"],
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
        **state.summary(),
    }


async def execute_campaign(args) -> dict[str, Any]:
    if not 1 <= args.max_batch_objects <= DEFAULT_MAX_BATCH_OBJECTS:
        raise SystemExit("max batch objects must be between 1 and 10000")
    if not 1 <= args.max_batch_bytes <= DEFAULT_MAX_DELETE_BYTES:
        raise SystemExit("max batch bytes must be between 1 and 50 GiB")
    plan = load_campaign_plan(args.approved_campaign, args.plan_sha256)
    validate_campaign_execute_gate(
        bucket=args.bucket,
        enabled=os.getenv("R2_TEMP_CLEANUP_CAMPAIGN_ENABLED", "").lower() == "true",
        confirmation=args.confirm,
        plan_sha256=args.plan_sha256,
    )
    state = CampaignState.open(
        Path(args.state),
        campaign_id=plan["campaign_id"],
        plan_sha256=plan["plan_sha256"],
        inventory_sha256=plan["inventory"]["sha256"],
        objects=plan["objects"],
    )
    receipt_path = Path(args.output)
    client = _r2_client()
    try:
        state.set_campaign_status("running")
        while True:
            batch = state.next_batch(
                max_objects=args.max_batch_objects, max_bytes=args.max_batch_bytes
            )
            if not batch:
                oversized = state.first_pending()
                if oversized is None:
                    break
                state.mark(oversized["key"], "blocked", reason="exceeds_batch_byte_limit")
                continue
            references = await campaign_reference_categories(
                [item["key"] for item in batch]
            )
            referenced = set().union(*references.values()) if references else set()
            for item in batch:
                key = item["key"]
                if key in referenced:
                    categories = sorted(
                        category for category, keys in references.items() if key in keys
                    )
                    state.mark(key, "blocked", reason="referenced:" + ",".join(categories))
                    continue
                valid, reason = await _revalidate_planned_object(client, args.bucket, item)
                if not valid:
                    state.mark(key, "blocked", reason=reason)
                    continue
                client.delete_object(Bucket=args.bucket, Key=key)
                if not _deleted_object_is_absent(client, args.bucket, key):
                    raise RuntimeError(f"deleted staging object still exists: {key}")
                durable_sha = _sha256_object(client, args.bucket, item["durable_key"])
                if durable_sha != item["sha256"]:
                    raise RuntimeError(f"durable twin changed after deletion: {key}")
                state.mark(key, "deleted", reason="post_delete_verified")
            _atomic_private_json(
                receipt_path,
                _campaign_receipt(plan=plan, state=state, status="running"),
            )
        state.set_campaign_status("completed")
        receipt = _campaign_receipt(plan=plan, state=state, status="completed")
        _atomic_private_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        state.set_campaign_status("paused", f"{type(exc).__name__}: {exc}")
        _atomic_private_json(
            receipt_path,
            _campaign_receipt(
                plan=plan,
                state=state,
                status="paused",
                error=f"{type(exc).__name__}: {exc}",
            ),
        )
        raise
    finally:
        state.close()


def _cutoff(hours: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--bucket", default=PRODUCTION_BUCKET)
    plan.add_argument("--min-age-hours", type=int, default=24)
    plan.add_argument("--cutoff", default="")
    plan.add_argument("--verification-concurrency", type=int, default=8)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--approved-campaign", required=True)
    execute.add_argument("--plan-sha256", required=True)
    execute.add_argument("--state", required=True)
    execute.add_argument("--output", required=True)
    execute.add_argument("--bucket", default=PRODUCTION_BUCKET)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--max-batch-objects", type=int, default=DEFAULT_MAX_BATCH_OBJECTS)
    execute.add_argument("--max-batch-bytes", type=int, default=DEFAULT_MAX_DELETE_BYTES)
    args = parser.parse_args()
    if args.command == "plan":
        if args.bucket != PRODUCTION_BUCKET:
            raise SystemExit("cleanup campaign is restricted to user-data-prod")
        args.cutoff = args.cutoff or _cutoff(args.min_age_hours)
        report = asyncio.run(generate_campaign(args))
        print(
            f"campaign-dry-run objects={report['campaign_object_count']} "
            f"bytes={report['campaign_bytes']} plan_sha256={report['plan_sha256']}"
        )
    else:
        receipt = asyncio.run(execute_campaign(args))
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
