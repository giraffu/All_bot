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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boto3  # noqa: E402
from botocore.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402


PRODUCTION_BUCKET = "user-data-prod"


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
    rows = connection.execute(
        """
        select source.key, min(durable.key), source.size, source.etag,
               source.last_modified
        from objects source
        join objects durable
          on durable.size=source.size and durable.etag=source.etag
         and durable.key<>source.key
        where instr(source.key, '/')=0
          and source.key glob '????????-????-????-????-????????????__*'
          and source.last_modified < ?
          and (
            durable.key like 'task-results/%'
            or durable.key like 'history/%'
            or durable.key glob '[0-9]*/output_images/*'
          )
        group by source.key,source.size,source.etag,source.last_modified
        order by source.last_modified,source.key
        limit ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [Candidate(*row) for row in rows]


def validate_delete_gate(*, bucket: str, enabled: bool, confirmation: str) -> None:
    if bucket != PRODUCTION_BUCKET:
        raise ValueError("temporary cleanup is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMP_CLEANUP_ENABLED must be true")
    if confirmation != f"DELETE_VERIFIED_TEMP_R2_{bucket}":
        raise ValueError("exact temporary cleanup confirmation is required")


async def _history_references(keys: list[str]) -> set[str]:
    if not keys:
        return set()
    from src.database.core import AsyncSessionLocal

    query = text(
        """
        with candidate(key) as (select unnest(cast(:keys as text[]))), refs as (
          select candidate.key from history h join candidate
            on btrim(coalesce(h.output_file,''))=candidate.key
            or btrim(coalesce(h.output_file,'')) like '%/'||candidate.key
          union select candidate.key from history h
            cross join lateral unnest(string_to_array(coalesce(h.input_file,''),'|')) x(ref)
            join candidate on btrim(x.ref)=candidate.key
              or btrim(x.ref) like '%/'||candidate.key
          union select candidate.key from history h
            cross join lateral jsonb_path_query(
              coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path'
            ) p(path)
            join candidate on trim(both '"' from p.path::text)=candidate.key
              or trim(both '"' from p.path::text) like '%/'||candidate.key
        ) select key from refs
        """
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query, {"keys": keys})).scalars().all()
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
    from src.database.core import AsyncSessionLocal

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
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query, {"keys": keys})).all()
    result: dict[str, set[str]] = {}
    for category, key in rows:
        result.setdefault(str(category), set()).add(str(key))
    return result


def _eligible_candidates(
    candidates: list[Candidate], *blocked_groups: set[str]
) -> tuple[list[Candidate], set[str]]:
    blocked = set().union(*blocked_groups)
    return [item for item in candidates if item.key not in blocked], blocked


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


async def _active_task_references(keys: list[str]) -> set[str]:
    if not keys:
        return set()
    from src.services.task_registry import TaskRegistry

    active_tasks = await TaskRegistry.get_all_tasks_strict()
    return _matching_refs(active_tasks, set(keys))


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


async def run(args) -> dict:
    if args.limit < 1 or args.limit > 10_000:
        raise SystemExit("limit must be between 1 and 10000")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.min_age_hours)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    inventory = sqlite3.connect(args.inventory)
    try:
        candidates = select_duplicate_candidates(
            inventory, cutoff=cutoff_text, limit=args.limit
        )
        orphan_uploads = inventory.execute(
            """select count(*),coalesce(sum(size),0) from objects
               where key like 'web_uploads/%' and last_modified < ?""",
            (cutoff_text,),
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
    verified = []
    failures = []
    for item in eligible:
        try:
            source_sha, durable_sha = await asyncio.gather(
                asyncio.to_thread(_sha256_object, client, args.bucket, item.key),
                asyncio.to_thread(
                    _sha256_object, client, args.bucket, item.durable_key
                ),
            )
            if source_sha != durable_sha:
                raise RuntimeError("SHA256_MISMATCH")
            verified.append({**asdict(item), "sha256": source_sha})
        except Exception as exc:
            failures.append({"key": item.key, "error": type(exc).__name__})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "bucket": args.bucket,
        "cutoff": cutoff_text,
        "candidate_count": len(candidates),
        "referenced_blocked_count": len(referenced),
        "history_referenced_blocked_count": len(history_referenced),
        "active_task_blocked_count": len(active_referenced),
        "business_referenced_blocked_count": len(business_referenced),
        "business_reference_categories": {
            category: len(values)
            for category, values in sorted(business_references.items())
        },
        "verified_count": len(verified),
        "verified_bytes": sum(item["byte_size"] for item in verified),
        "probe_failures": failures,
        "legacy_web_uploads_report_only": {
            "object_count": int(orphan_uploads[0]),
            "bytes": int(orphan_uploads[1]),
            "reason": "not deleted without a durable content twin",
        },
        "objects": verified,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(output, 0o600)
    if not args.execute:
        return report
    validate_delete_gate(
        bucket=args.bucket,
        enabled=os.getenv("R2_TEMP_CLEANUP_ENABLED", "").lower() == "true",
        confirmation=args.confirm,
    )
    if failures:
        raise SystemExit("execute rejected because at least one SHA probe failed")
    for item in verified:
        client.delete_object(Bucket=args.bucket, Key=item["key"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bucket", default=PRODUCTION_BUCKET)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-age-hours", type=int, default=24)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    report = asyncio.run(run(args))
    print(
        f"{report['mode']} candidates={report['candidate_count']} "
        f"verified={report['verified_count']} bytes={report['verified_bytes']}"
    )


if __name__ == "__main__":
    main()
