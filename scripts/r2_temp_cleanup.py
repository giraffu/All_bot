#!/usr/bin/env python3
"""Reference-aware cleanup for legacy duplicate R2 Worker objects."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from src.runtime_environment import require_env  # noqa: E402


PRODUCTION_BUCKET = "user-data-prod"
DEFAULT_MAX_DELETE_BYTES = 50 * 1024**3


@dataclass(frozen=True)
class Candidate:
    key: str
    durable_key: str
    byte_size: int
    etag: str
    last_modified: str


def select_duplicate_candidates(
    connection: sqlite3.Connection, *, cutoff: str, limit: int
) -> list[Candidate]:
    # The production inventory has millions of rows and intentionally only a
    # primary-key index on ``key``.  Joining the table to itself by size/etag
    # therefore degenerates into a multi-terabyte nested scan.  Materialize the
    # much smaller durable signature set with an exact lookup key first.  This
    # is a TEMP table, so the immutable inventory and its sealed fingerprint are
    # not changed.
    connection.execute("drop table if exists temp.cleanup_durable_twins")
    connection.execute(
        """
        create temp table cleanup_durable_twins(
          size integer not null,
          etag text not null,
          key text not null,
          primary key(size,etag)
        ) without rowid
        """
    )
    connection.execute(
        """
        insert into cleanup_durable_twins(size,etag,key)
        select size,etag,min(key)
          from objects
         where key like 'task-results/%'
            or key like 'history/%'
            or key glob '[0-9]*/output_images/*'
         group by size,etag
        """
    )
    rows = connection.execute(
        """
        select source.key, durable.key, source.size, source.etag,
               source.last_modified
        from objects source
        join cleanup_durable_twins durable
          on durable.size=source.size and durable.etag=source.etag
         and durable.key<>source.key
        where instr(source.key, '/')=0
          and source.key glob '????????-????-????-????-????????????__*'
          and source.last_modified < ?
        order by source.last_modified,source.key
        limit ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [Candidate(*row) for row in rows]


def validate_delete_gate(
    *, bucket: str, enabled: bool, confirmation: str, plan_sha256: str = ""
) -> None:
    if bucket != PRODUCTION_BUCKET:
        raise ValueError("temporary cleanup is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMP_CLEANUP_ENABLED must be true")
    expected = f"DELETE_VERIFIED_TEMP_R2_{bucket}"
    if plan_sha256:
        expected = f"{expected}:{plan_sha256}"
    if confirmation != expected:
        raise ValueError("exact temporary cleanup confirmation is required")


def _json_sha256(value: dict) -> str:
    payload = dict(value)
    payload.pop("plan_sha256", None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def seal_plan(report: dict) -> dict:
    sealed = dict(report)
    sealed["plan_sha256"] = _json_sha256(sealed)
    return sealed


def load_approved_plan(path: str, expected_sha256: str) -> dict:
    if not path:
        raise SystemExit("execute requires --approved-plan")
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    actual = _json_sha256(plan)
    if plan.get("mode") != "dry-run" or plan.get("plan_sha256") != actual:
        raise SystemExit("approved cleanup plan is invalid or has been modified")
    if not expected_sha256 or actual != expected_sha256:
        raise SystemExit("approved cleanup plan SHA-256 does not match")
    return plan


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _history_references(keys: list[str]) -> set[str]:
    if not keys:
        return set()

    query = text(
        """
        with candidate(key) as (select unnest(cast(:keys as text[]))), refs as (
          select regexp_replace(btrim(coalesce(h.output_file,'')), '^.*/', '') key
            from history h
          union select regexp_replace(btrim(x.ref), '^.*/', '') key
            from history h cross join lateral
              unnest(string_to_array(coalesce(h.input_file,''),'|')) x(ref)
          union select regexp_replace(
              trim(both '"' from p.path::text), '^.*/', ''
            ) key
            from history h cross join lateral jsonb_path_query(
              coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path'
            ) p(path)
        ) select candidate.key from refs join candidate using(key)
        """
    )
    engine, session_factory = _runtime_database()
    try:
        async with session_factory() as session:
            rows = (await session.execute(query, {"keys": keys})).scalars().all()
    finally:
        await engine.dispose()
    return set(map(str, rows))


async def _business_references(keys: list[str]) -> dict[str, set[str]]:
    """Return non-History business references that make deletion unsafe.

    History is intentionally queried separately because every History role blocks
    cleanup, regardless of visibility.  This query covers business records that
    can retain an R2 key independently of History.  Referencing a table that is
    unavailable is an intentional fail-closed database error.
    """
    if not keys:
        return {}

    query = text(
        """
        with candidate(key) as (select unnest(cast(:keys as text[]))), refs as (
          select 'template_contribution' category, candidate.key
            from template_contributions value join candidate
              on btrim(coalesce(value.file_path,''))=candidate.key
              or btrim(coalesce(value.file_path,'')) like '%/'||candidate.key
          union select 'archive_receipt', candidate.key
            from media_archive_receipts value join candidate
              on btrim(coalesce(value.source_key,''))=candidate.key
              or btrim(coalesce(value.source_key,'')) like '%/'||candidate.key
          union select 'character_reference', candidate.key
            from character_references value join candidate on
              btrim(coalesce(value.source_object_key,''))=candidate.key
              or btrim(coalesce(value.source_object_key,'')) like '%/'||candidate.key
              or btrim(coalesce(value.sheet_object_key,''))=candidate.key
              or btrim(coalesce(value.sheet_object_key,'')) like '%/'||candidate.key
          union select 'character_reference_view', candidate.key
            from character_reference_views value join candidate
              on btrim(coalesce(value.object_key,''))=candidate.key
              or btrim(coalesce(value.object_key,'')) like '%/'||candidate.key
          union select 'official_character_asset', candidate.key
            from official_character_assets value join candidate on
              btrim(coalesce(value.source_object_key,''))=candidate.key
              or btrim(coalesce(value.source_object_key,'')) like '%/'||candidate.key
              or btrim(coalesce(value.sheet_object_key,''))=candidate.key
              or btrim(coalesce(value.sheet_object_key,'')) like '%/'||candidate.key
          union select 'official_character_asset_view', candidate.key
            from official_character_asset_views value join candidate
              on btrim(coalesce(value.object_key,''))=candidate.key
              or btrim(coalesce(value.object_key,'')) like '%/'||candidate.key
          union select 'official_environment_asset', candidate.key
            from official_environment_assets value join candidate
              on btrim(coalesce(value.object_key,''))=candidate.key
              or btrim(coalesce(value.object_key,'')) like '%/'||candidate.key
          union select 'character_model_asset', candidate.key
            from character_model_assets value join candidate on
              btrim(coalesce(value.model_object_key,''))=candidate.key
              or btrim(coalesce(value.model_object_key,'')) like '%/'||candidate.key
              or btrim(coalesce(value.render_source_object_key,''))=candidate.key
              or btrim(coalesce(value.render_source_object_key,'')) like '%/'||candidate.key
              or btrim(coalesce(value.thumbnail_object_key,''))=candidate.key
              or btrim(coalesce(value.thumbnail_object_key,'')) like '%/'||candidate.key
          union select 'character_model_input_view', candidate.key
            from character_model_input_views value join candidate
              on btrim(coalesce(value.object_key,''))=candidate.key
              or btrim(coalesce(value.object_key,'')) like '%/'||candidate.key
          union select 'character_render_job', candidate.key
            from character_render_jobs value join candidate
              on btrim(coalesce(value.output_object_key,''))=candidate.key
              or btrim(coalesce(value.output_object_key,'')) like '%/'||candidate.key
        ) select category,key from refs
        """
    )
    engine, session_factory = _runtime_database()
    try:
        async with session_factory() as session:
            rows = (await session.execute(query, {"keys": keys})).all()
    finally:
        await engine.dispose()
    result: dict[str, set[str]] = {}
    for category, key in rows:
        result.setdefault(str(category), set()).add(str(key))
    return result


def _eligible_candidates(
    candidates: list[Candidate], *blocked_groups: set[str]
) -> tuple[list[Candidate], set[str]]:
    blocked = set().union(*blocked_groups)
    return [item for item in candidates if item.key not in blocked], blocked


def _apply_delete_byte_cap(
    verified: list[dict], *, max_bytes: int
) -> tuple[list[dict], list[dict]]:
    selected: list[dict] = []
    used = 0
    for index, item in enumerate(verified):
        item_size = int(item["byte_size"])
        if used + item_size > max_bytes:
            return selected, verified[index:]
        selected.append(item)
        used += item_size
    return selected, []


def _matching_refs(value, keys: set[str]) -> set[str]:
    matches: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            matches.update(_matching_refs(nested, keys))
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            matches.update(_matching_refs(nested, keys))
    elif isinstance(value, str):
        normalized = value.strip()
        matches.update(
            key
            for key in keys
            if normalized == key or normalized.endswith(f"/{key}")
        )
    return matches


async def _active_task_references(
    keys: list[str], *, lookup_func=None
) -> set[str]:
    if not keys:
        return set()
    lookup = lookup_func or _strict_active_task_reference_lookup
    return await lookup(
        redis_url=require_env("REDIS_URL"),
        redis_prefix=require_env("REDIS_PREFIX"),
        keys=keys,
        socket_timeout=60,
    )


def _runtime_database():
    engine = create_async_engine(
        require_env("DATABASE_URL"),
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    return engine, sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _strict_active_task_reference_lookup(
    *,
    redis_url: str,
    redis_prefix: str,
    keys: list[str],
    socket_timeout: float,
) -> set[str]:
    from src.services.redis_connection import build_redis_client

    client = build_redis_client(
        redis_url,
        decode_responses=True,
        socket_timeout=socket_timeout,
    )
    try:
        raw_tasks = await client.hvals(f"{redis_prefix}active_tasks")
        targets = set(keys)
        matches: set[str] = set()
        for raw in raw_tasks:
            matches.update(_matching_refs(json.loads(raw), targets))
        return matches
    finally:
        await client.aclose()


def _r2_client():
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
        config=Config(signature_version="s3v4", max_pool_connections=16),
    )


def _sha256_object(client, bucket: str, key: str) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: body.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def _deleted_object_is_absent(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return True
        raise
    return False


async def _verify_candidates(
    client,
    bucket: str,
    candidates: list[Candidate],
    *,
    concurrency: int,
) -> tuple[list[dict], list[dict]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def hash_object(key: str) -> str:
        async with semaphore:
            return await asyncio.to_thread(_sha256_object, client, bucket, key)

    async def verify(item: Candidate) -> tuple[dict | None, dict | None]:
        try:
            source_sha, durable_sha = await asyncio.gather(
                hash_object(item.key), hash_object(item.durable_key)
            )
            if source_sha != durable_sha:
                raise RuntimeError("SHA256_MISMATCH")
            return {**asdict(item), "sha256": source_sha}, None
        except Exception as exc:
            return None, {"key": item.key, "error": type(exc).__name__}

    results = await asyncio.gather(*(verify(item) for item in candidates))
    verified = [item for item, _failure in results if item is not None]
    failures = [failure for _item, failure in results if failure is not None]
    return verified, failures


async def _delete_and_verify_candidates(
    client,
    bucket: str,
    objects: list[dict],
    *,
    concurrency: int,
) -> int:
    """Delete independently, preserving strict post-delete gates per object."""
    semaphore = asyncio.Semaphore(concurrency)

    async def delete_and_verify(item: dict) -> None:
        async with semaphore:
            await asyncio.to_thread(
                client.delete_object, Bucket=bucket, Key=item["key"]
            )
            absent = await asyncio.to_thread(
                _deleted_object_is_absent, client, bucket, item["key"]
            )
            if not absent:
                raise SystemExit("deleted temporary object still exists")
            durable_sha = await asyncio.to_thread(
                _sha256_object, client, bucket, item["durable_key"]
            )
            if durable_sha != item["sha256"]:
                raise SystemExit("durable twin changed after temporary deletion")

    await asyncio.gather(*(delete_and_verify(item) for item in objects))
    return len(objects)


async def resume_delete_started(
    *, client, plan: dict, receipt: dict, concurrency: int
) -> dict:
    """Finish one exact frozen batch after its process exited during deletion.

    Already absent sources count as completed only after every production
    reference is rechecked and the durable twin still has the frozen SHA-256.
    Still-present sources must pass the normal dual-object verification before
    the remaining delete path is entered.
    """
    actual_plan_sha = _json_sha256(plan)
    if plan.get("plan_sha256") != actual_plan_sha:
        raise RuntimeError("cleanup recovery plan is invalid or has been modified")
    if receipt.get("status") != "delete_started":
        raise RuntimeError("cleanup receipt is not in delete_started state")
    if plan.get("mode") != "dry-run" or plan.get("bucket") != PRODUCTION_BUCKET:
        raise RuntimeError("cleanup recovery plan is invalid")
    objects = list(plan.get("objects") or [])
    if receipt.get("objects") != objects:
        raise RuntimeError("delete_started receipt differs from frozen plan")
    if receipt.get("inventory", {}).get("sha256") != plan.get("inventory", {}).get(
        "sha256"
    ):
        raise RuntimeError("delete_started inventory identity changed")
    keys = [str(item["key"]) for item in objects]
    history_refs, active_refs, business_refs = await asyncio.gather(
        _history_references(keys),
        _active_task_references(keys),
        _business_references(keys),
    )
    business_keys = set().union(*business_refs.values()) if business_refs else set()
    if history_refs or active_refs or business_keys:
        raise RuntimeError("production references appeared after delete_started")

    semaphore = asyncio.Semaphore(concurrency)

    async def source_absent(item: dict) -> bool:
        async with semaphore:
            return await asyncio.to_thread(
                _deleted_object_is_absent,
                client,
                PRODUCTION_BUCKET,
                str(item["key"]),
            )

    absence = await asyncio.gather(*(source_absent(item) for item in objects))
    absent = [item for item, is_absent in zip(objects, absence) if is_absent]
    present = [item for item, is_absent in zip(objects, absence) if not is_absent]

    async def durable_matches(item: dict) -> bool:
        async with semaphore:
            digest = await asyncio.to_thread(
                _sha256_object,
                client,
                PRODUCTION_BUCKET,
                str(item["durable_key"]),
            )
        return digest == str(item["sha256"])

    if absent:
        durable_results = await asyncio.gather(
            *(durable_matches(item) for item in absent)
        )
        if not all(durable_results):
            raise RuntimeError("durable twin changed after partial deletion")

    if present:
        candidates = [
            Candidate(
                key=str(item["key"]),
                durable_key=str(item["durable_key"]),
                byte_size=int(item["byte_size"]),
                etag=str(item["etag"]),
                last_modified=str(item["last_modified"]),
            )
            for item in present
        ]
        verified, failures = await _verify_candidates(
            client,
            PRODUCTION_BUCKET,
            candidates,
            concurrency=concurrency,
        )
        frozen = {str(item["key"]): str(item["sha256"]) for item in present}
        if failures or len(verified) != len(present) or any(
            str(item["sha256"]) != frozen[str(item["key"])] for item in verified
        ):
            raise RuntimeError("source or durable twin changed after delete_started")
        deleted = await _delete_and_verify_candidates(
            client,
            PRODUCTION_BUCKET,
            present,
            concurrency=concurrency,
        )
    else:
        deleted = 0

    recovered = dict(receipt)
    recovered.update(
        {
            "approved_plan_sha256": str(plan.get("plan_sha256") or ""),
            "post_delete_verified_count": len(absent) + deleted,
            "status": "completed",
            "recovery": {
                "schema": "allbot-r2-temp-cleanup-delete-recovery/v1",
                "recovered_at": datetime.now(timezone.utc).isoformat(),
                "absent_before_recovery": len(absent),
                "present_before_recovery": len(present),
                "post_delete_verified_count": len(absent) + deleted,
            },
        }
    )
    return recovered


async def run(args) -> dict:
    if args.limit < 1 or args.limit > 10_000:
        raise SystemExit("limit must be between 1 and 10000")
    if args.verification_concurrency < 1 or args.verification_concurrency > 16:
        raise SystemExit("verification concurrency must be between 1 and 16")
    if args.max_delete_bytes < 1 or args.max_delete_bytes > DEFAULT_MAX_DELETE_BYTES:
        raise SystemExit("max delete bytes must be between 1 and 50 GiB")
    approved_plan_path = str(getattr(args, "approved_plan", "") or "")
    expected_plan_sha = str(getattr(args, "plan_sha256", "") or "")
    approved_plan = (
        load_approved_plan(approved_plan_path, expected_plan_sha)
        if args.execute
        else None
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.min_age_hours)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    if approved_plan:
        cutoff_text = str(approved_plan["cutoff"])
    inventory_path = Path(args.inventory)
    inventory = sqlite3.connect(inventory_path)
    try:
        integrity = str(inventory.execute("pragma integrity_check").fetchone()[0])
        if integrity != "ok":
            raise SystemExit("inventory integrity check failed")
        if approved_plan:
            candidates = [
                Candidate(
                    key=item["key"], durable_key=item["durable_key"],
                    byte_size=int(item["byte_size"]), etag=item["etag"],
                    last_modified=item["last_modified"],
                )
                for item in approved_plan.get("objects", [])
            ]
        else:
            candidates = select_duplicate_candidates(
                inventory, cutoff=cutoff_text, limit=args.limit
            )
        orphan_uploads = inventory.execute(
            """select count(*),coalesce(sum(size),0) from objects
               where key like 'web_uploads/%' and last_modified < ?""",
            (cutoff_text,),
        ).fetchone()
        staging = inventory.execute(
            """select count(*),coalesce(sum(size),0),min(last_modified)
               from objects where key like 'staging/%'"""
        ).fetchone()
        inventory_total = inventory.execute(
            "select count(*),coalesce(sum(size),0) from objects"
        ).fetchone()
    finally:
        inventory.close()

    candidate_keys = [item.key for item in candidates]
    history_referenced, active_referenced, business_references = await asyncio.gather(
        _history_references(candidate_keys),
        _active_task_references(candidate_keys),
        _business_references(candidate_keys),
    )
    business_referenced = set().union(*business_references.values())
    eligible, referenced = _eligible_candidates(
        candidates,
        history_referenced,
        active_referenced,
        business_referenced,
    )
    client = _r2_client()
    verified, failures = await _verify_candidates(
        client,
        args.bucket,
        eligible,
        concurrency=args.verification_concurrency,
    )
    delete_objects, byte_cap_blocked = _apply_delete_byte_cap(
        verified, max_bytes=args.max_delete_bytes
    )

    report = {
        "batch_id": (
            str(approved_plan.get("batch_id"))
            if approved_plan
            else str(uuid.uuid4())
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "bucket": args.bucket,
        "cutoff": cutoff_text,
        "verification_concurrency": args.verification_concurrency,
        "candidate_count": len(candidates),
        "referenced_blocked_count": len(referenced),
        "referenced_blocked_bytes": sum(
            item.byte_size for item in candidates if item.key in referenced
        ),
        "history_referenced_blocked_count": len(history_referenced),
        "active_task_blocked_count": len(active_referenced),
        "business_referenced_blocked_count": len(business_referenced),
        "business_reference_categories": {
            category: len(values)
            for category, values in sorted(business_references.items())
        },
        "verified_count": len(verified),
        "verified_bytes": sum(item["byte_size"] for item in verified),
        "max_delete_bytes": args.max_delete_bytes,
        "delete_count": len(delete_objects),
        "delete_bytes": sum(item["byte_size"] for item in delete_objects),
        "byte_cap_blocked_count": len(byte_cap_blocked),
        "byte_cap_blocked_bytes": sum(
            int(item["byte_size"]) for item in byte_cap_blocked
        ),
        "probe_failures": failures,
        "inventory": {
            "path": str(inventory_path),
            "sha256": _file_sha256(inventory_path),
            "mtime": inventory_path.stat().st_mtime,
            "object_count": int(inventory_total[0]),
            "bytes": int(inventory_total[1]),
            "integrity": integrity,
        },
        "staging": {
            "object_count": int(staging[0]),
            "bytes": int(staging[1]),
            "oldest_last_modified": staging[2],
        },
        "legacy_web_uploads_report_only": {
            "object_count": int(orphan_uploads[0]),
            "bytes": int(orphan_uploads[1]),
            "reason": "not deleted without a durable content twin",
        },
        "objects": delete_objects,
    }
    if (
        approved_plan
        and approved_plan.get("inventory", {}).get("sha256")
        != report["inventory"]["sha256"]
    ):
        raise SystemExit("inventory changed after the approved cleanup plan")
    if not args.execute:
        report = seal_plan(report)
    else:
        validate_delete_gate(
            bucket=args.bucket,
            enabled=os.getenv("R2_TEMP_CLEANUP_ENABLED", "").lower() == "true",
            confirmation=args.confirm,
            plan_sha256=expected_plan_sha,
        )
        if failures:
            raise SystemExit("execute rejected because at least one SHA probe failed")
        report["status"] = "delete_started"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(output, 0o600)
    if not args.execute:
        return report
    post_delete_verified = await _delete_and_verify_candidates(
        client,
        args.bucket,
        delete_objects,
        concurrency=args.verification_concurrency,
    )
    report["approved_plan"] = approved_plan_path
    report["approved_plan_sha256"] = expected_plan_sha
    report["post_delete_verified_count"] = post_delete_verified
    report["status"] = "completed"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(output, 0o600)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bucket", default=PRODUCTION_BUCKET)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-age-hours", type=int, default=24)
    parser.add_argument("--verification-concurrency", type=int, default=8)
    parser.add_argument(
        "--max-delete-bytes", type=int, default=DEFAULT_MAX_DELETE_BYTES
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approved-plan", default="")
    parser.add_argument("--plan-sha256", default="")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    print(
        f"{report['mode']} candidates={report['candidate_count']} "
        f"verified={report['verified_count']} bytes={report['verified_bytes']}"
    )


if __name__ == "__main__":
    main()
