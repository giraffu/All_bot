#!/usr/bin/env python3
"""Unified, inventory-backed governance for legacy user-data-prod media keys."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from typing import Any, Iterable


NUMERIC_MEDIA_RE = re.compile(r"^[0-9]+/(input_images|output_images)/[^/]+$")
DURABLE_PREFIXES = ("task-inputs/", "task-results/", "history/")


@dataclass(frozen=True)
class MediaReference:
    object_key: str
    registry_task_id: str | None
    backend_task_id: str | None
    role: str | None
    ordinal: int | None
    referenced_by: str


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_inventory(path: Path) -> dict[str, Any]:
    stat_before = path.stat()
    sha256 = _file_sha256(path)
    db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        integrity = str(db.execute("pragma integrity_check").fetchone()[0])
        schema = db.execute(
            "select sql from sqlite_master where type='table' and name='objects'"
        ).fetchone()
        if integrity != "ok" or schema is None:
            raise ValueError("inventory integrity or schema validation failed")
        count, byte_size = db.execute(
            "select count(*),coalesce(sum(size),0) from objects"
        ).fetchone()
    finally:
        db.close()
    stat_after = path.stat()
    if (stat_before.st_size, stat_before.st_mtime_ns) != (
        stat_after.st_size,
        stat_after.st_mtime_ns,
    ):
        raise ValueError("inventory changed while it was being validated")
    return {
        "path": str(path),
        "sha256": sha256,
        "mtime_ns": stat_after.st_mtime_ns,
        "file_size": stat_after.st_size,
        "object_count": int(count),
        "bytes": int(byte_size),
        "integrity": integrity,
    }


def _object_class(key: str) -> str:
    if NUMERIC_MEDIA_RE.match(key):
        return "numeric_user_directory"
    if "/" not in key:
        return "flat_root"
    for prefix in DURABLE_PREFIXES:
        if key.startswith(prefix):
            return "durable"
    if key.startswith("web_uploads/"):
        return "web_uploads"
    if key.startswith("temps/") or key.startswith("template-submissions/"):
        return "protected_legacy"
    return "other"


def build_governance_index(inventory: Path, output: Path) -> dict[str, Any]:
    """Atomically derive the unified index without issuing another R2 LIST."""
    evidence = validate_inventory(inventory)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    db = sqlite3.connect(temporary)
    try:
        db.executescript(
            """
            create table media_objects(
              object_key text primary key,
              size integer not null,
              sha256 text,
              object_class text not null,
              registry_task_id text,
              backend_task_id text,
              role text,
              ordinal integer,
              referenced_by text,
              durable_target text,
              migration_status text not null default 'pending',
              cleanup_status text not null default 'not_applicable',
              error text
            ) without rowid;
            create table governance_metadata(key text primary key,value text not null)
              without rowid;
            """
        )
        db.execute("attach database ? as inventory", (str(inventory),))
        db.execute(
            """
            insert into media_objects(object_key,size,object_class,cleanup_status)
            select key,size,
                   case
                     when key glob '[0-9]*/input_images/*'
                       or key glob '[0-9]*/output_images/*' then 'numeric_user_directory'
                     when instr(key,'/')=0 then 'flat_root'
                     when key like 'task-inputs/%' or key like 'task-results/%'
                       or key like 'history/%' then 'durable'
                     when key like 'web_uploads/%' then 'web_uploads'
                     when key like 'temps/%' or key like 'template-submissions/%'
                       then 'protected_legacy'
                     else 'other'
                   end,
                   case when instr(key,'/')=0 then 'pending' else 'not_applicable' end
              from inventory.objects
             order by key
            """
        )
        db.commit()
        db.execute("detach database inventory")
        after = inventory.stat()
        if after.st_mtime_ns != evidence["mtime_ns"] or after.st_size != evidence["file_size"]:
            raise ValueError("inventory changed while governance index was built")
        metadata = {
            "inventory_path": str(inventory),
            "inventory_sha256": evidence["sha256"],
            "inventory_mtime_ns": str(evidence["mtime_ns"]),
            "inventory_object_count": str(evidence["object_count"]),
            "inventory_bytes": str(evidence["bytes"]),
        }
        db.executemany("insert into governance_metadata values(?,?)", metadata.items())
        db.execute("create index ix_media_objects_class_size on media_objects(object_class,size)")
        db.execute("create index ix_media_objects_sha256 on media_objects(sha256) where sha256 is not null")
        db.commit()
        if db.execute("pragma integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("governance index integrity check failed")
    except Exception:
        db.close()
        temporary.unlink(missing_ok=True)
        raise
    db.close()
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    return {**evidence, "path": str(output), "inventory_sha256": evidence["sha256"]}


def _extension(key: str) -> str:
    suffix = Path(key).suffix.lower()
    return suffix if suffix and len(suffix) <= 16 else ""


def _durable_target(reference: MediaReference) -> str | None:
    extension = _extension(reference.object_key)
    if reference.role == "input" and reference.registry_task_id and reference.ordinal is not None:
        return f"task-inputs/{reference.registry_task_id}/{reference.ordinal}{extension}"
    if reference.role == "primary" and reference.backend_task_id and reference.ordinal == 0:
        return f"task-results/{reference.backend_task_id}/primary{extension}"
    if reference.role == "extra" and reference.backend_task_id and reference.ordinal is not None:
        return f"task-results/{reference.backend_task_id}/extra-{reference.ordinal}{extension}"
    return None


def _canonical_sha(payload: dict[str, Any]) -> str:
    value = dict(payload)
    value.pop("plan_sha256", None)
    value.pop("campaign_sha256", None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def freeze_numeric_migration_plan(
    index: Path, references: Iterable[MediaReference], output: Path
) -> dict[str, Any]:
    db = sqlite3.connect(index)
    db.row_factory = sqlite3.Row
    objects: list[dict[str, Any]] = []
    unresolved_samples: list[dict[str, Any]] = []
    db.execute(
        "update media_objects set migration_status='unresolved',error='no_database_reference' "
        "where object_class='numeric_user_directory'"
    )
    grouped: dict[str, list[MediaReference]] = {}
    for reference in references:
        grouped.setdefault(reference.object_key, []).append(reference)
    for key, candidates in grouped.items():
        signatures = {
            (item.registry_task_id, item.backend_task_id, item.role, item.ordinal)
            for item in candidates
        }
        reference = candidates[0]
        if len(signatures) != 1 or not NUMERIC_MEDIA_RE.match(key):
            if len(unresolved_samples) < 100:
                unresolved_samples.append({**asdict(reference), "error": "ambiguous_or_invalid_reference"})
            db.execute(
                "update media_objects set migration_status='unresolved',error=? where object_key=?",
                ("ambiguous_or_invalid_reference", reference.object_key),
            )
            continue
        row = db.execute(
            "select size from media_objects where object_key=?", (reference.object_key,)
        ).fetchone()
        target = _durable_target(reference)
        if row is None or target is None:
            reason = "source_missing" if row is None else "incomplete_task_role_mapping"
            if len(unresolved_samples) < 100:
                unresolved_samples.append({**asdict(reference), "error": reason})
            if row is not None:
                db.execute(
                    "update media_objects set registry_task_id=?,backend_task_id=?,role=?,"
                    "ordinal=?,referenced_by=?,migration_status='unresolved',error=? where object_key=?",
                    (reference.registry_task_id, reference.backend_task_id, reference.role,
                     reference.ordinal, reference.referenced_by, reason, reference.object_key),
                )
            continue
        item = {**asdict(reference), "size": int(row["size"]), "durable_target": target}
        objects.append(item)
        db.execute(
            "update media_objects set registry_task_id=?,backend_task_id=?,role=?,ordinal=?,"
            "referenced_by=?,durable_target=?,migration_status='planned',error=null where object_key=?",
            (reference.registry_task_id, reference.backend_task_id, reference.role, reference.ordinal,
             reference.referenced_by, target, reference.object_key),
        )
    remaining = 100 - len(unresolved_samples)
    if remaining > 0:
        unresolved_samples.extend(
            {
                "object_key": str(row["object_key"]), "size": int(row["size"]),
                "registry_task_id": None, "backend_task_id": None, "role": None,
                "ordinal": None, "referenced_by": "", "error": str(row["error"]),
            }
            for row in db.execute(
                "select object_key,size,error from media_objects "
                "where object_class='numeric_user_directory' and migration_status='unresolved' "
                "order by object_key limit ?", (remaining,)
            )
        )
    unresolved_count, unresolved_bytes = db.execute(
        "select count(*),coalesce(sum(size),0) from media_objects "
        "where object_class='numeric_user_directory' and migration_status='unresolved'"
    ).fetchone()
    metadata = dict(db.execute("select key,value from governance_metadata"))
    db.commit()
    db.close()
    plan = {
        "mode": "numeric-user-directory-migration-dry-run",
        "inventory_sha256": metadata["inventory_sha256"],
        "inventory_mtime_ns": int(metadata["inventory_mtime_ns"]),
        "migratable_count": len(objects),
        "migratable_bytes": sum(item["size"] for item in objects),
        "estimated_full_sha_read_bytes": 2 * sum(item["size"] for item in objects),
        "unresolved_count": int(unresolved_count),
        "unresolved_bytes": int(unresolved_bytes),
        "objects": sorted(objects, key=lambda item: item["object_key"]),
        "unresolved_sample_limit": 100,
        "unresolved_samples": sorted(unresolved_samples, key=lambda item: item["object_key"]),
    }
    plan["plan_sha256"] = _canonical_sha(plan)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    return plan


def select_flat_root_size_candidates(index: Path) -> list[tuple[str, str, int]]:
    db = sqlite3.connect(index)
    try:
        return [
            (str(source), str(twin), int(size))
            for source, twin, size in db.execute(
                """
                select source.object_key,min(twin.object_key),source.size
                  from media_objects source join media_objects twin using(size)
                 where source.object_class='flat_root' and twin.object_class='durable'
                 group by source.object_key,source.size order by source.object_key
                """
            )
        ]
    finally:
        db.close()


def select_flat_root_size_candidate_groups(index: Path) -> dict[str, tuple[int, list[str]]]:
    db = sqlite3.connect(index)
    result: dict[str, tuple[int, list[str]]] = {}
    try:
        rows = db.execute(
            """
            select source.object_key,source.size,twin.object_key
              from media_objects source join media_objects twin using(size)
             where source.object_class='flat_root' and twin.object_class='durable'
             order by source.object_key,twin.object_key
            """
        )
        for source, size, twin in rows:
            current = result.setdefault(str(source), (int(size), []))
            current[1].append(str(twin))
        return result
    finally:
        db.close()


async def load_numeric_history_references() -> list[MediaReference]:
    """Read explicit History roles; never infer backend IDs from filenames."""
    from sqlalchemy import text
    from src.database.core import AsyncSessionLocal

    query = text(
        """
        with backend_map as (
          select registry_task_id,min(backend_task_id) backend_task_id
            from private_bot_task_submissions
           where backend_task_id is not null
           group by registry_task_id
          having count(distinct backend_task_id)=1
        ), refs as (
          select h.id,h.task_id registry_task_id,b.backend_task_id,
                 btrim(value.ref) object_key,'input' role,value.ordinality-1 ordinal
            from history h
            left join backend_map b on b.registry_task_id=h.task_id
            cross join lateral unnest(string_to_array(coalesce(h.input_file,''),'|'))
              with ordinality value(ref,ordinality)
          union all
          select h.id,h.task_id,b.backend_task_id,btrim(h.output_file),
                 'primary',0
            from history h left join backend_map b on b.registry_task_id=h.task_id
          union all
          select h.id,h.task_id,b.backend_task_id,
                 trim(both '"' from value.path::text),'extra',value.ordinality-1
            from history h
            left join backend_map b on b.registry_task_id=h.task_id
            cross join lateral jsonb_path_query(
              coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path'
            ) with ordinality value(path,ordinality)
        )
        select object_key,registry_task_id,backend_task_id,role,ordinal,id
          from refs
         where object_key ~ '^[0-9]+/(input_images|output_images)/[^/]+$'
         order by object_key,id
        """
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query)).all()
    return [
        MediaReference(
            object_key=str(key), registry_task_id=str(registry) if registry else None,
            backend_task_id=str(backend) if backend else None, role=str(role),
            ordinal=int(ordinal), referenced_by=f"history:{history_id}",
        )
        for key, registry, backend, role, ordinal, history_id in rows
    ]


async def flat_root_reference_audit(keys: list[str]) -> dict[str, set[str]]:
    from scripts.r2_temp_cleanup import (
        _active_task_references,
        _business_references,
        _history_references,
    )

    history, business, active = await asyncio.gather(
        _history_references(keys), _business_references(keys), _active_task_references(keys)
    )
    result = {str(category): set(values) for category, values in business.items()}
    if history:
        result["history"] = set(history)
    if active:
        result["active_task"] = set(active)
    return result


def _head(client, bucket: str, key: str) -> tuple[int, str | None]:
    response = client.head_object(Bucket=bucket, Key=key)
    metadata = {str(k).lower(): str(v) for k, v in (response.get("Metadata") or {}).items()}
    digest = metadata.get("sha256")
    return int(response["ContentLength"]), digest if digest and len(digest) == 64 else None


async def verify_flat_root_candidates(
    client,
    bucket: str,
    groups: dict[str, tuple[int, list[str]]],
    references: dict[str, set[str]],
    *,
    concurrency: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Use size/metadata to order candidates, but always compute both full SHA-256s."""
    from botocore.exceptions import ClientError
    from scripts.r2_temp_cleanup import _sha256_object

    semaphore = asyncio.Semaphore(concurrency)

    async def io(function, *args):
        async with semaphore:
            return await asyncio.to_thread(function, *args)

    blocked_keys = set().union(*references.values()) if references else set()

    async def verify(source: str, size: int, twins: list[str]):
        if source in blocked_keys:
            reasons = sorted(category for category, values in references.items() if source in values)
            return None, {"object_key": source, "size": size, "reason": "referenced:" + ",".join(reasons)}
        try:
            source_size, source_meta = await io(_head, client, bucket, source)
            if source_size != size:
                return None, {"object_key": source, "size": size, "reason": "source_head_size_mismatch"}
            twin_heads = []
            for twin in twins:
                twin_size, twin_meta = await io(_head, client, bucket, twin)
                if twin_size == size:
                    twin_heads.append((twin, twin_meta))
            if source_meta:
                twin_heads.sort(key=lambda item: item[1] != source_meta)
            source_sha = await io(_sha256_object, client, bucket, source)
            for twin, _metadata_sha in twin_heads:
                twin_sha = await io(_sha256_object, client, bucket, twin)
                if source_sha == twin_sha:
                    audit = {
                        "history": "clear", "gallery": "clear", "favorite": "clear",
                        "public": "clear", "template": "clear", "archive": "clear",
                        "active_task": "clear", "redis": "clear", "head": "verified",
                    }
                    return {
                        "object_key": source, "durable_twin": twin, "size": size,
                        "source_sha256": source_sha, "durable_sha256": twin_sha,
                        "reference_audit": audit,
                    }, None
            return None, {"object_key": source, "size": size, "reason": "no_full_sha256_twin"}
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None, {"object_key": source, "size": size, "reason": "object_missing"}
            raise

    verified: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    entries = list(groups.items())
    for offset in range(0, len(entries), 1000):
        results = await asyncio.gather(
            *(verify(source, value[0], value[1]) for source, value in entries[offset:offset + 1000])
        )
        verified.extend(item for item, _ in results if item is not None)
        blocked.extend(item for _, item in results if item is not None)
    return verified, blocked


async def verify_numeric_migration_plan(
    client, bucket: str, plan: dict[str, Any], *, concurrency: int = 8
) -> dict[str, Any]:
    """HEAD and fully hash sources/any existing targets without copying them."""
    from botocore.exceptions import ClientError
    from scripts.r2_temp_cleanup import _sha256_object

    semaphore = asyncio.Semaphore(concurrency)

    async def io(function, *args):
        async with semaphore:
            return await asyncio.to_thread(function, *args)

    async def probe(item: dict[str, Any]) -> dict[str, Any]:
        row = dict(item)
        source, target, expected = row["object_key"], row["durable_target"], int(row["size"])
        try:
            source_size, _ = await io(_head, client, bucket, source)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return {**row, "migration_status": "source_missing", "error": "source_missing"}
            raise
        if source_size != expected:
            return {**row, "migration_status": "blocked", "error": "source_size_changed"}
        source_sha = await io(_sha256_object, client, bucket, source)
        try:
            target_size, _ = await io(_head, client, bucket, target)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
            return {
                **row, "source_sha256": source_sha, "target_sha256": None,
                "migration_status": "copy_required", "error": None,
            }
        target_sha = await io(_sha256_object, client, bucket, target)
        status = (
            "target_existing_consistent"
            if target_size == expected and target_sha == source_sha
            else "target_conflict"
        )
        return {
            **row, "source_sha256": source_sha, "target_sha256": target_sha,
            "target_size": target_size, "migration_status": status,
            "error": None if status == "target_existing_consistent" else "target_content_conflict",
        }

    rows: list[dict[str, Any]] = []
    objects = list(plan.get("objects") or [])
    for offset in range(0, len(objects), 1000):
        rows.extend(await asyncio.gather(*(probe(item) for item in objects[offset:offset + 1000])))
    counts: dict[str, int] = {}
    bytes_by_status: dict[str, int] = {}
    for row in rows:
        status = str(row["migration_status"])
        counts[status] = counts.get(status, 0) + 1
        bytes_by_status[status] = bytes_by_status.get(status, 0) + int(row["size"])
    result = dict(plan)
    result["objects"] = rows
    result["status_counts"] = counts
    result["status_bytes"] = bytes_by_status
    result["migratable_count"] = counts.get("copy_required", 0) + counts.get("target_existing_consistent", 0)
    result["migratable_bytes"] = bytes_by_status.get("copy_required", 0) + bytes_by_status.get("target_existing_consistent", 0)
    result["estimated_full_sha_read_bytes"] = sum(
        int(row["size"]) + (int(row.get("target_size") or 0) if row.get("target_sha256") else 0)
        for row in rows if row.get("source_sha256")
    )
    result["plan_sha256"] = _canonical_sha(result)
    return result


def freeze_flat_root_campaign(
    index: Path,
    *,
    verified: Iterable[dict[str, Any]],
    blocked: Iterable[dict[str, Any]],
    output: Path,
    batch_id: str,
) -> dict[str, Any]:
    """Seal one complete flat-root campaign after external HEAD/SHA/reference probes."""
    db = sqlite3.connect(index)
    metadata = dict(db.execute("select key,value from governance_metadata"))
    safe: list[dict[str, Any]] = []
    for item in verified:
        row = dict(item)
        source = str(row.get("object_key") or "")
        twin = str(row.get("durable_twin") or "")
        source_sha = str(row.get("source_sha256") or "")
        twin_sha = str(row.get("durable_sha256") or "")
        audit = row.get("reference_audit") or {}
        required_clear = (
            "history", "gallery", "favorite", "public", "template", "archive",
            "active_task", "redis",
        )
        if (
            "/" in source
            or not twin.startswith(DURABLE_PREFIXES)
            or source_sha != twin_sha
            or len(source_sha) != 64
            or any(audit.get(name) != "clear" for name in required_clear)
            or audit.get("head") != "verified"
        ):
            raise ValueError("flat-root campaign contains an incompletely verified object")
        safe.append(row)
        db.execute(
            "update media_objects set sha256=?,durable_target=?,cleanup_status='planned',"
            "referenced_by=?,error=null where object_key=?",
            (source_sha, twin, json.dumps(audit, sort_keys=True), source),
        )
    blocked_rows = sorted((dict(item) for item in blocked), key=lambda item: item["object_key"])
    for item in blocked_rows:
        db.execute(
            "update media_objects set cleanup_status='blocked',error=? where object_key=?",
            (str(item.get("reason") or "blocked"), str(item["object_key"])),
        )
    db.commit()
    db.close()
    safe.sort(key=lambda item: item["object_key"])
    plan = {
        "mode": "flat-root-cleanup-campaign-dry-run",
        "batch_id": batch_id,
        "inventory_sha256": metadata["inventory_sha256"],
        "inventory_mtime_ns": int(metadata["inventory_mtime_ns"]),
        "inventory_object_count": int(metadata["inventory_object_count"]),
        "campaign_object_count": len(safe),
        "campaign_bytes": sum(int(item["size"]) for item in safe),
        "blocked_count": len(blocked_rows),
        "blocked_bytes": sum(int(item.get("size") or 0) for item in blocked_rows),
        "objects": safe,
        "blocked": blocked_rows,
        "limits": {"max_objects_per_run": 10_000, "max_bytes_per_run": 50 * 1024**3},
    }
    plan["campaign_sha256"] = _canonical_sha(plan)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    return plan


def validate_flat_root_delete_gate(
    *, bucket: str, enabled: bool, confirmation: str, campaign_sha256: str
) -> None:
    if bucket != "user-data-prod":
        raise ValueError("flat-root deletion is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_FLAT_ROOT_CLEANUP_ENABLED must be true")
    expected = f"DELETE_FLAT_ROOT_{bucket}:{campaign_sha256}"
    if confirmation != expected:
        raise ValueError("exact flat-root campaign authorization is required")


def load_flat_root_campaign(path: Path, expected_sha256: str) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    actual = _canonical_sha(plan)
    if (
        plan.get("mode") != "flat-root-cleanup-campaign-dry-run"
        or plan.get("campaign_sha256") != actual
        or actual != expected_sha256
    ):
        raise ValueError("flat-root campaign is invalid or has been modified")
    return plan


def _flat_root_receipt(plan: dict[str, Any], state, *, status: str, error: str = "") -> dict[str, Any]:
    summary = state.summary()
    return {
        "batch_id": plan["batch_id"],
        "campaign_sha256": plan["campaign_sha256"],
        "inventory_sha256": plan["inventory_sha256"],
        "status": status,
        "error": error,
        "pending_count": int(summary.get("pending_count", 0)),
        "pending_bytes": int(summary.get("pending_bytes", 0)),
        "deleted_count": int(summary.get("deleted_count", 0)),
        "deleted_bytes": int(summary.get("deleted_bytes", 0)),
        "blocked_count": int(summary.get("blocked_count", 0)),
        "blocked_bytes": int(summary.get("blocked_bytes", 0)),
    }


async def execute_flat_root_campaign(
    args,
    *,
    client=None,
    enabled: bool | None = None,
    reference_audit=flat_root_reference_audit,
) -> dict[str, Any]:
    """Consume at most one bounded batch from one exact frozen flat-root campaign."""
    from botocore.exceptions import ClientError
    from scripts.r2_temp_cleanup import _r2_client, _sha256_object
    from scripts.r2_temp_cleanup_campaign import CampaignState, _atomic_private_json

    max_objects = int(args.max_batch_objects)
    max_bytes = int(args.max_batch_bytes)
    if not 1 <= max_objects <= 10_000:
        raise ValueError("max batch objects must be between 1 and 10000")
    if not 1 <= max_bytes <= 50 * 1024**3:
        raise ValueError("max batch bytes must be between 1 and 50 GiB")
    plan = load_flat_root_campaign(Path(args.approved_campaign), args.campaign_sha256)
    validate_flat_root_delete_gate(
        bucket=args.bucket,
        enabled=(
            os.getenv("R2_FLAT_ROOT_CLEANUP_ENABLED", "").lower() == "true"
            if enabled is None else enabled
        ),
        confirmation=args.confirm,
        campaign_sha256=args.campaign_sha256,
    )
    state_objects = [
        {**item, "key": item["object_key"], "byte_size": int(item["size"])}
        for item in plan["objects"]
    ]
    state = CampaignState.open(
        Path(args.state),
        campaign_id=plan["batch_id"],
        plan_sha256=plan["campaign_sha256"],
        inventory_sha256=plan["inventory_sha256"],
        objects=state_objects,
    )
    receipt_path = Path(args.output)
    r2 = client or _r2_client()
    try:
        state.set_campaign_status("running")
        batch = state.next_batch(max_objects=max_objects, max_bytes=max_bytes)
        if not batch:
            oversized = state.first_pending()
            if oversized is not None:
                state.mark(oversized["key"], "blocked", reason="exceeds_batch_byte_limit")
        else:
            references = await reference_audit([item["key"] for item in batch])
            referenced = set().union(*references.values()) if references else set()
            for item in batch:
                key = str(item["key"])
                twin = str(item["durable_twin"])
                size = int(item["byte_size"])
                if key in referenced:
                    categories = sorted(
                        category for category, keys in references.items() if key in keys
                    )
                    state.mark(key, "blocked", reason="referenced:" + ",".join(categories))
                    continue
                try:
                    source_size, _ = await asyncio.to_thread(_head, r2, args.bucket, key)
                    twin_size, _ = await asyncio.to_thread(_head, r2, args.bucket, twin)
                except ClientError as exc:
                    code = str((exc.response or {}).get("Error", {}).get("Code", ""))
                    if code in {"404", "NoSuchKey", "NotFound"}:
                        state.mark(key, "blocked", reason="source_or_twin_missing")
                        continue
                    raise
                if source_size != size or twin_size != size:
                    state.mark(key, "blocked", reason="source_or_twin_size_changed")
                    continue
                source_sha = await asyncio.to_thread(_sha256_object, r2, args.bucket, key)
                twin_sha = await asyncio.to_thread(_sha256_object, r2, args.bucket, twin)
                if (
                    source_sha != item["source_sha256"]
                    or twin_sha != item["durable_sha256"]
                    or source_sha != twin_sha
                ):
                    state.mark(key, "blocked", reason="source_or_twin_sha256_changed")
                    continue
                await asyncio.to_thread(r2.delete_object, Bucket=args.bucket, Key=key)
                try:
                    await asyncio.to_thread(_head, r2, args.bucket, key)
                except ClientError as exc:
                    code = str((exc.response or {}).get("Error", {}).get("Code", ""))
                    if code not in {"404", "NoSuchKey", "NotFound"}:
                        raise
                else:
                    raise RuntimeError(f"deleted flat-root object still exists: {key}")
                post_size, _ = await asyncio.to_thread(_head, r2, args.bucket, twin)
                post_sha = await asyncio.to_thread(_sha256_object, r2, args.bucket, twin)
                if post_size != size or post_sha != item["durable_sha256"]:
                    raise RuntimeError(f"durable twin changed after deletion: {key}")
                state.mark(key, "deleted", reason="post_delete_verified")
        pending = int(state.summary().get("pending_count", 0))
        status = "running" if pending else "completed"
        state.set_campaign_status(status)
        receipt = _flat_root_receipt(plan, state, status=status)
        _atomic_private_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        state.set_campaign_status("paused", f"{type(exc).__name__}: {exc}")
        _atomic_private_json(
            receipt_path,
            _flat_root_receipt(
                plan, state, status="paused", error=f"{type(exc).__name__}: {exc}"
            ),
        )
        raise
    finally:
        state.close()


async def plan_flat_root(index: Path, output: Path, *, bucket: str, concurrency: int) -> dict[str, Any]:
    from scripts.r2_temp_cleanup import PRODUCTION_BUCKET, _r2_client

    if bucket != PRODUCTION_BUCKET:
        raise ValueError("flat-root governance is restricted to user-data-prod")
    if not 1 <= concurrency <= 16:
        raise ValueError("verification concurrency must be between 1 and 16")
    groups = select_flat_root_size_candidate_groups(index)
    references: dict[str, set[str]] = {}
    keys = list(groups)
    for offset in range(0, len(keys), 10_000):
        chunk = await flat_root_reference_audit(keys[offset:offset + 10_000])
        for category, values in chunk.items():
            references.setdefault(category, set()).update(values)
    verified, blocked = await verify_flat_root_candidates(
        _r2_client(), bucket, groups, references, concurrency=concurrency
    )
    return freeze_flat_root_campaign(
        index, verified=verified, blocked=blocked, output=output,
        batch_id=str(uuid.uuid4()),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-inventory")
    validate.add_argument("--inventory", required=True, type=Path)
    build = subparsers.add_parser("build-index")
    build.add_argument("--inventory", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    numeric = subparsers.add_parser("plan-numeric")
    numeric.add_argument("--index", required=True, type=Path)
    numeric.add_argument("--output", required=True, type=Path)
    numeric.add_argument("--bucket", default="user-data-prod")
    numeric.add_argument("--verification-concurrency", type=int, default=8)
    flat = subparsers.add_parser("plan-flat-root")
    flat.add_argument("--index", required=True, type=Path)
    flat.add_argument("--output", required=True, type=Path)
    flat.add_argument("--bucket", default="user-data-prod")
    flat.add_argument("--verification-concurrency", type=int, default=8)
    execute_flat = subparsers.add_parser("execute-flat-root")
    execute_flat.add_argument("--approved-campaign", required=True, type=Path)
    execute_flat.add_argument("--campaign-sha256", required=True)
    execute_flat.add_argument("--state", required=True, type=Path)
    execute_flat.add_argument("--output", required=True, type=Path)
    execute_flat.add_argument("--bucket", default="user-data-prod")
    execute_flat.add_argument("--confirm", required=True)
    execute_flat.add_argument("--max-batch-objects", type=int, default=10_000)
    execute_flat.add_argument("--max-batch-bytes", type=int, default=50 * 1024**3)
    args = parser.parse_args()
    if args.command == "validate-inventory":
        result = validate_inventory(args.inventory)
    elif args.command == "build-index":
        result = build_governance_index(args.inventory, args.output)
    elif args.command == "plan-numeric":
        from scripts.r2_temp_cleanup import PRODUCTION_BUCKET, _r2_client
        if args.bucket != PRODUCTION_BUCKET:
            raise SystemExit("numeric media migration is restricted to user-data-prod")
        draft = freeze_numeric_migration_plan(
            args.index, asyncio.run(load_numeric_history_references()), args.output
        )
        result = asyncio.run(verify_numeric_migration_plan(
            _r2_client(), args.bucket, draft,
            concurrency=args.verification_concurrency,
        ))
        index_db = sqlite3.connect(args.index)
        index_db.executemany(
            "update media_objects set sha256=?,migration_status=?,error=? where object_key=?",
            [
                (row.get("source_sha256"), row["migration_status"], row.get("error"), row["object_key"])
                for row in result["objects"]
            ],
        )
        index_db.commit()
        index_db.close()
        temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, args.output)
    elif args.command == "plan-flat-root":
        result = asyncio.run(plan_flat_root(
            args.index, args.output, bucket=args.bucket,
            concurrency=args.verification_concurrency,
        ))
    else:
        result = asyncio.run(execute_flat_root_campaign(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
