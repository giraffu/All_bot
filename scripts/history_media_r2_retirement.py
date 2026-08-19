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
"""


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
    return {
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
        "archive_sha256": str(candidate["archive_sha256"]),
        "nas_object_sha256": _key_sha(
            str(candidate["nas_bucket"]), str(candidate["nas_key"])
        ),
        "target_facts_sha256": _sha256_json(target_identities),
        "target_count": len(target_identities),
    }


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
    if _strip_etag(source_head.get("ETag")) != _strip_etag(candidate["source_etag"]):
        raise RuntimeError("old source identity changed")
    expected_modified = candidate.get("source_last_modified")
    actual_modified = source_head.get("LastModified")
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
            item["archive_verified_asset_count"] = int(item["asset_count"])
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
            or _sha256_json([_retirement_object_identity(item) for item in all_objects])
            != manifest["rowset_sha256"]
        ):
            raise RuntimeError("retirement global rowset changed")
        identities = [_retirement_object_identity(item) for item in objects]
        if len(objects) != int(batch["object_count"]) or _sha256_json(
            identities
        ) != str(batch["rowset_sha256"]):
            raise RuntimeError("retirement batch rowset changed")
        live_refs = await _live_reference_counts(
            production, [str(item["source_key"]) for item in objects]
        )
        if live_refs:
            raise RuntimeError("retirement batch gained a live History reference")
        ledger_blockers = int(
            await ledger.fetchval(
                """with selected as (
                     select * from unnest($1::text[],$2::text[])
                       as x(source_name,source_key)
                   ) select count(*) from selected s where
                     exists(select 1 from analytics_history_media_r2_migrations m
                             where m.source_name=s.source_name and m.source_key=s.source_key
                               and m.status in ('copy_required','failed'))
                     or exists(select 1 from analytics_history_media_r2_migrations m
                               where m.source_name=s.source_name and m.source_key=s.source_key
                                 and m.original_ref<>m.target_key
                                 and m.switch_completed_at is null)
                     or exists(select 1 from analytics_history_media_r2_migrations m
                               where m.target_key=s.source_key)""",
                [str(item["source_name"]) for item in objects],
                [str(item["source_key"]) for item in objects],
            )
        )
        if ledger_blockers:
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
        if remaining == 0:
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
        await ledger.execute(
            """update analytics_history_media_r2_retirement_plans
                 set status='paused',updated_at=now() where plan_sha256=$1""",
            args.plan_sha256,
        )
        raise
    finally:
        await production.close()
        await ledger.close()
        r2_client.close()
        if nas_client is not None:
            nas_client.close()


def _bounded_delete_concurrency(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= MAX_DELETE_CONCURRENCY:
        raise argparse.ArgumentTypeError("delete concurrency must be between 1 and 8")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
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
    return parser


async def _main(args: argparse.Namespace) -> None:
    if args.command == "report":
        if not 1 <= args.archive_candidate_limit <= 1000:
            raise ValueError("archive candidate limit must be between 1 and 1000")
        await _report(args)
    elif args.command == "plan-delete":
        if not 1 <= args.limit <= 1000 or not 1 <= args.batch_size <= 1000:
            raise ValueError("retirement plan limits must be between 1 and 1000")
        await _plan_delete(args)
    elif args.command == "execute-delete":
        await _execute_delete(args)


def main() -> None:
    asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    main()
