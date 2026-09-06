#!/usr/bin/env python3
"""Plan, probe, then execute verified-cold R2 media cleanup."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from botocore.exceptions import ClientError  # noqa: E402
from sqlalchemy import text  # noqa: E402

PLAN_KIND = "media_archive_r2_cleanup_plan"
PROBE_KIND = "media_archive_r2_cleanup_probe"
RECEIPT_KIND = "media_archive_r2_cleanup_receipt"
DELETE_CONFIRMATION = "DELETE_VERIFIED_COLD_R2"

CANDIDATE_SQL = """
with ranked as (
  select id, row_number() over(partition by user_id order by id desc) rn from history
), hot as (
  select h.id from history h join ranked r on r.id=h.id where r.rn<=8 and h.is_visible is true
  union select id from history where is_favorited is true or is_public is true
  union select h.id from history h join gallery_posts gp on gp.task_id=h.task_id where gp.is_active is true
), hot_refs as (
  select distinct ref from (
    select btrim(x.ref) ref from history h join hot on hot.id=h.id
      cross join lateral unnest(string_to_array(coalesce(h.input_file,''),'|')) x(ref)
    union all select btrim(h.output_file) from history h join hot on hot.id=h.id
    union all select trim(both '"' from p.path::text)
      from history h join hot on hot.id=h.id
      cross join lateral jsonb_path_query(coalesce(h.extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path') p(path)
  ) refs where ref<>''
), verified as (
  select h.id,h.task_id,h.type,r.role,r.ordinal,r.source_ref,r.sha256,
         r.byte_size,r.nas_bucket,r.nas_key
  from history h join media_archive_outbox o on o.history_id=h.id and o.status='archived'
  join media_archive_receipts r on r.history_id=h.id
    and r.status='archived_verified' and length(r.sha256)=64
  where r.source_ref<>'' and h.task_id is not null
)
select v.id,v.task_id,v.source_ref,v.type,v.role,v.ordinal,v.sha256,
       v.byte_size,v.nas_bucket,v.nas_key
from verified v where not exists(select 1 from hot where hot.id=v.id)
and not exists(select 1 from hot_refs where hot_refs.ref=v.source_ref)
order by v.id,v.role,v.ordinal limit :limit
"""

HOT_REFERENCE_SQL = """
with ranked as (
  select id,row_number() over(partition by user_id order by id desc) rn from history
), hot as (
  select h.* from history h join ranked r on r.id=h.id
  where (r.rn<=8 and h.is_visible is true) or h.is_favorited is true or h.is_public is true
     or exists(select 1 from gallery_posts gp where gp.task_id=h.task_id and gp.is_active is true)
)
select task_id,type,'input' role,btrim(x.ref) source_ref from hot
cross join lateral unnest(string_to_array(coalesce(input_file,''),'|')) x(ref)
where task_id is not null and btrim(x.ref)<>''
union all select task_id,type,'output',btrim(output_file) from hot
where task_id is not null and btrim(coalesce(output_file,''))<>''
union all select task_id,type,'extra',trim(both '"' from p.path::text) from hot
cross join lateral jsonb_path_query(coalesce(extra_outputs::jsonb,'{}'::jsonb),'strict $.**.path') p(path)
where task_id is not null
"""


def _canonical_sha256(payload: dict[str, Any], hash_field: str) -> str:
    canonical = dict(payload)
    canonical.pop(hash_field, None)
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _freeze(payload: dict[str, Any], hash_field: str) -> dict[str, Any]:
    frozen = dict(payload)
    frozen[hash_field] = _canonical_sha256(frozen, hash_field)
    return frozen


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_frozen_artifact(
    path: Path, *, expected_kind: str, hash_field: str, expected_sha256: str
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = _canonical_sha256(payload, hash_field)
    if payload.get("kind") != expected_kind:
        raise ValueError(f"unexpected artifact kind: {payload.get('kind')}")
    if payload.get(hash_field) != actual or expected_sha256 != actual:
        raise ValueError(f"{hash_field} mismatch")
    return payload


def _build_cleanup_objects(rows, hot_rows, build_keys) -> tuple[list[dict], list[str]]:
    objects: dict[str, dict[str, Any]] = {}
    for (
        history_id,
        task_id,
        source_ref,
        history_type,
        role,
        ordinal,
        sha256,
        byte_size,
        nas_bucket,
        nas_key,
    ) in rows:
        for key in build_keys(task_id, source_ref, history_type, role):
            item = objects.setdefault(
                key,
                {"key": key, "history_ids": [], "roles": [], "archive_assets": []},
            )
            item["history_ids"].append(history_id)
            item["roles"].append(f"{role}:{ordinal}")
            item["archive_assets"].append(
                {
                    "sha256": sha256,
                    "byte_size": int(byte_size),
                    "nas_bucket": nas_bucket,
                    "nas_key": nas_key,
                }
            )
    hot_keys: set[str] = set()
    for task_id, history_type, role, source_ref in hot_rows:
        hot_keys.update(build_keys(task_id, source_ref, history_type, role))
    blocked = sorted(set(objects).intersection(hot_keys))
    for key in blocked:
        objects.pop(key, None)
    return [objects[key] for key in sorted(objects)], blocked


async def _load_candidate_rows(limit: int):
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(CANDIDATE_SQL), {"limit": limit})).all()
        hot_rows = (await session.execute(text(HOT_REFERENCE_SQL))).all()
    return rows, hot_rows


def _load_nas_client(config_path: str | None):
    if not config_path:
        raise ValueError("archive worker config is required for probe and execute")
    from scripts.media_archive_worker import (
        _client,
        clear_proxy_environment,
        load_secure_config,
        validate_endpoint_route,
    )

    config = load_secure_config(Path(config_path))
    clear_proxy_environment()
    validate_endpoint_route(config["nas"])
    return _client(config["nas"])


def _is_not_found(exc: BaseException) -> bool:
    if not isinstance(exc, ClientError):
        return False
    code = str((exc.response or {}).get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


async def _probe_objects(
    *, plan: dict[str, Any], r2_client, nas_client
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    bucket = str(plan["bucket"])
    for item in plan["objects"]:
        key = str(item["key"])
        nas_verified = True
        for asset in item["archive_assets"]:
            try:
                head = await asyncio.to_thread(
                    nas_client.head_object,
                    Bucket=asset["nas_bucket"],
                    Key=asset["nas_key"],
                )
                matches = (
                    int(head.get("ContentLength") or -1) == int(asset["byte_size"])
                    and (head.get("Metadata") or {}).get("sha256") == asset["sha256"]
                )
            except Exception as exc:
                matches = False
                failures.append(
                    {"key": key, "scope": "nas", "error": type(exc).__name__}
                )
            if not matches:
                nas_verified = False
                if not any(
                    failure["key"] == key and failure["scope"] == "nas"
                    for failure in failures
                ):
                    failures.append(
                        {"key": key, "scope": "nas", "error": "IDENTITY_MISMATCH"}
                    )
        try:
            head = await asyncio.to_thread(
                r2_client.head_object, Bucket=bucket, Key=key
            )
            exists = True
            byte_size = int(head.get("ContentLength") or 0)
        except Exception as exc:
            exists = False
            byte_size = 0
            if not _is_not_found(exc):
                failures.append(
                    {"key": key, "scope": "r2", "error": type(exc).__name__}
                )
        results.append(
            {
                "key": key,
                "exists": exists,
                "byte_size": byte_size,
                "nas_verified": nas_verified,
            }
        )
    return results, failures


def validate_execute_artifacts(
    *,
    plan: dict[str, Any],
    probe: dict[str, Any],
    plan_sha256: str,
    probe_sha256: str,
    confirmation: str,
    now: datetime | None = None,
    max_probe_age_seconds: int = 3600,
) -> None:
    if plan.get("plan_sha256") != plan_sha256:
        raise ValueError("execute plan SHA mismatch")
    if probe.get("probe_sha256") != probe_sha256:
        raise ValueError("execute probe SHA mismatch")
    if probe.get("plan_sha256") != plan_sha256:
        raise ValueError("probe does not belong to plan")
    if probe.get("bucket") != plan.get("bucket"):
        raise ValueError("probe bucket identity mismatch")
    if not probe.get("probe_ok") or probe.get("failures"):
        raise ValueError("probe contains blockers")
    generated_at = datetime.fromisoformat(str(probe["generated_at"]))
    current = now or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        raise ValueError("probe timestamp must be timezone-aware")
    age = (current - generated_at).total_seconds()
    if age < 0 or age > max_probe_age_seconds:
        raise ValueError("probe is stale")
    if confirmation != DELETE_CONFIRMATION:
        raise ValueError("exact delete confirmation is required")


async def command_plan(args) -> None:
    from src.services.storage import storage
    from src.services.storage_r2_cleanup import build_archive_asset_cleanup_keys

    if args.limit < 1 or args.limit > 1000:
        raise ValueError("cleanup batch limit must be between 1 and 1000")
    if not storage.r2_bucket:
        raise ValueError("R2 bucket is not configured")
    rows, hot_rows = await _load_candidate_rows(args.limit)
    objects, blocked = _build_cleanup_objects(
        rows, hot_rows, build_archive_asset_cleanup_keys
    )
    plan = _freeze(
        {
            "kind": PLAN_KIND,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bucket": storage.r2_bucket,
            "history_count": len(rows),
            "object_count": len(objects),
            "shared_hot_blocked_keys": blocked,
            "objects": objects,
        },
        "plan_sha256",
    )
    _write_private_json(args.output, plan)
    print(
        json.dumps(
            {
                "kind": PLAN_KIND,
                "output": str(args.output),
                "plan_sha256": plan["plan_sha256"],
                "history_count": plan["history_count"],
                "object_count": plan["object_count"],
                "shared_hot_blocked_count": len(blocked),
            }
        )
    )


async def command_probe(args) -> None:
    from src.services.storage import storage

    plan = load_frozen_artifact(
        args.plan,
        expected_kind=PLAN_KIND,
        hash_field="plan_sha256",
        expected_sha256=args.plan_sha256,
    )
    if storage.r2_bucket != plan.get("bucket") or storage.r2_client is None:
        raise ValueError("runtime R2 identity does not match plan")
    results, failures = await _probe_objects(
        plan=plan,
        r2_client=storage.r2_client,
        nas_client=_load_nas_client(args.archive_worker_config),
    )
    probe = _freeze(
        {
            "kind": PROBE_KIND,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "plan_sha256": plan["plan_sha256"],
            "bucket": plan["bucket"],
            "probe_ok": not failures and all(item["nas_verified"] for item in results),
            "failures": failures,
            "objects": results,
        },
        "probe_sha256",
    )
    _write_private_json(args.output, probe)
    print(
        json.dumps(
            {
                "kind": PROBE_KIND,
                "output": str(args.output),
                "plan_sha256": probe["plan_sha256"],
                "probe_sha256": probe["probe_sha256"],
                "probe_ok": probe["probe_ok"],
                "object_count": len(results),
                "failure_count": len(failures),
            }
        )
    )


async def _current_hot_keys(build_keys) -> set[str]:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        hot_rows = (await session.execute(text(HOT_REFERENCE_SQL))).all()
    keys: set[str] = set()
    for task_id, history_type, role, source_ref in hot_rows:
        keys.update(build_keys(task_id, source_ref, history_type, role))
    return keys


async def command_execute(args) -> None:
    from src.services.storage import storage
    from src.services.storage_r2_cleanup import build_archive_asset_cleanup_keys

    plan = load_frozen_artifact(
        args.plan,
        expected_kind=PLAN_KIND,
        hash_field="plan_sha256",
        expected_sha256=args.plan_sha256,
    )
    probe = load_frozen_artifact(
        args.probe,
        expected_kind=PROBE_KIND,
        hash_field="probe_sha256",
        expected_sha256=args.probe_sha256,
    )
    validate_execute_artifacts(
        plan=plan,
        probe=probe,
        plan_sha256=args.plan_sha256,
        probe_sha256=args.probe_sha256,
        confirmation=args.confirm,
        max_probe_age_seconds=args.max_probe_age_seconds,
    )
    if (
        os.getenv("R2_ARCHIVE_DELETE_ENABLED", "").lower() != "true"
        or os.getenv("R2_ARCHIVE_RESTORE_GATE_VERIFIED", "").lower() != "true"
    ):
        raise ValueError("delete and restore gates are required")
    if storage.r2_bucket != plan.get("bucket") or storage.r2_client is None:
        raise ValueError("runtime R2 identity does not match plan")
    planned_keys = {str(item["key"]) for item in plan["objects"]}
    newly_hot = sorted(planned_keys.intersection(await _current_hot_keys(build_archive_asset_cleanup_keys)))
    if newly_hot:
        raise ValueError(f"planned objects became hot: {len(newly_hot)}")

    current_results, failures = await _probe_objects(
        plan=plan,
        r2_client=storage.r2_client,
        nas_client=_load_nas_client(args.archive_worker_config),
    )
    frozen_results = {item["key"]: item for item in probe["objects"]}
    if failures or {item["key"]: item for item in current_results} != frozen_results:
        raise ValueError("execute-time probe drifted from frozen probe")

    deleted: list[str] = []
    for item in current_results:
        if not item["exists"]:
            continue
        await asyncio.to_thread(
            storage.r2_client.delete_object,
            Bucket=plan["bucket"],
            Key=item["key"],
        )
        try:
            await asyncio.to_thread(
                storage.r2_client.head_object,
                Bucket=plan["bucket"],
                Key=item["key"],
            )
        except Exception as exc:
            if not _is_not_found(exc):
                raise
        else:
            raise RuntimeError(f"deleted object still exists: {item['key']}")
        deleted.append(item["key"])
    receipt = _freeze(
        {
            "kind": RECEIPT_KIND,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "plan_sha256": plan["plan_sha256"],
            "probe_sha256": probe["probe_sha256"],
            "bucket": plan["bucket"],
            "deleted_count": len(deleted),
            "deleted_keys": deleted,
        },
        "receipt_sha256",
    )
    _write_private_json(args.output, receipt)
    print(
        json.dumps(
            {
                "kind": RECEIPT_KIND,
                "output": str(args.output),
                "plan_sha256": receipt["plan_sha256"],
                "probe_sha256": receipt["probe_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "deleted_count": receipt["deleted_count"],
            }
        )
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--limit", type=int, default=1000)
    plan.add_argument("--output", required=True, type=Path)
    probe = sub.add_parser("probe")
    probe.add_argument("--plan", required=True, type=Path)
    probe.add_argument("--plan-sha256", required=True)
    probe.add_argument("--archive-worker-config", required=True)
    probe.add_argument("--output", required=True, type=Path)
    execute = sub.add_parser("execute")
    execute.add_argument("--plan", required=True, type=Path)
    execute.add_argument("--plan-sha256", required=True)
    execute.add_argument("--probe", required=True, type=Path)
    execute.add_argument("--probe-sha256", required=True)
    execute.add_argument("--archive-worker-config", required=True)
    execute.add_argument("--max-probe-age-seconds", type=int, default=3600)
    execute.add_argument("--confirm", required=True)
    execute.add_argument("--output", required=True, type=Path)
    return parser


async def _main_async(args) -> None:
    if args.command == "plan":
        await command_plan(args)
    elif args.command == "probe":
        await command_probe(args)
    else:
        await command_execute(args)


def main() -> None:
    asyncio.run(_main_async(build_argument_parser().parse_args()))


if __name__ == "__main__":
    main()
