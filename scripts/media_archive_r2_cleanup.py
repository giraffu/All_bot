#!/usr/bin/env python3
"""Generate a verified-cold R2 cleanup report; delete only with two explicit gates."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

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


async def run(args) -> None:
    from scripts.media_archive_worker import (
        _client,
        clear_proxy_environment,
        load_secure_config,
        validate_endpoint_route,
    )
    from src.database.core import AsyncSessionLocal
    from src.services.storage import storage
    from src.services.storage_r2_cleanup import build_archive_asset_cleanup_keys

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(CANDIDATE_SQL), {"limit": args.limit})).all()
        hot_rows = (await session.execute(text(HOT_REFERENCE_SQL))).all()
    archive_config = (
        load_secure_config(Path(args.archive_worker_config))
        if args.archive_worker_config
        else None
    )
    if archive_config:
        clear_proxy_environment()
        validate_endpoint_route(archive_config["nas"])
    nas_client = _client(archive_config["nas"]) if archive_config else None
    nas_failures = []
    objects = {}
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
        nas_verified = False
        if nas_client:
            try:
                head = await asyncio.to_thread(
                    nas_client.head_object, Bucket=nas_bucket, Key=nas_key
                )
                nas_verified = (
                    int(head.get("ContentLength") or -1) == int(byte_size)
                    and (head.get("Metadata") or {}).get("sha256") == sha256
                )
                if not nas_verified:
                    nas_failures.append(
                        {
                            "history_id": history_id,
                            "role": role,
                            "error": "NAS_METADATA_MISMATCH",
                        }
                    )
            except Exception as exc:
                nas_failures.append(
                    {
                        "history_id": history_id,
                        "role": role,
                        "error": type(exc).__name__,
                    }
                )
        for key in build_archive_asset_cleanup_keys(
            task_id, source_ref, history_type, role
        ):
            item = objects.setdefault(
                key,
                {
                    "key": key,
                    "history_ids": [],
                    "roles": [],
                    "archive_assets": [],
                    "nas_verified": True,
                },
            )
            item["history_ids"].append(history_id)
            item["roles"].append(f"{role}:{ordinal}")
            item["archive_assets"].append(
                {"sha256": sha256, "nas_bucket": nas_bucket, "nas_key": nas_key}
            )
            item["nas_verified"] = item["nas_verified"] and nas_verified
    hot_keys = set()
    for task_id, history_type, role, source_ref in hot_rows:
        hot_keys.update(
            build_archive_asset_cleanup_keys(task_id, source_ref, history_type, role)
        )
    shared_hot_blocked_keys = sorted(set(objects).intersection(hot_keys))
    for key in shared_hot_blocked_keys:
        objects.pop(key, None)
    total_bytes = 0
    for item in objects.values():
        try:
            head = await asyncio.to_thread(
                storage.r2_client.head_object, Bucket=storage.r2_bucket, Key=item["key"]
            )
            item["exists"] = True
            item["byte_size"] = int(head.get("ContentLength") or 0)
            total_bytes += item["byte_size"]
        except Exception as exc:
            item["exists"] = False
            item["byte_size"] = 0
            item["probe_error"] = type(exc).__name__
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "history_count": len(rows),
        "object_count": len(objects),
        "total_bytes": total_bytes,
        "nas_revalidated": bool(nas_client),
        "nas_failures": nas_failures,
        "shared_hot_blocked_keys": shared_hot_blocked_keys,
        "objects": list(objects.values()),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"dry-run report: {output} histories={len(rows)} objects={len(objects)} bytes={total_bytes}"
    )
    if not args.execute:
        return
    if (
        not nas_client
        or nas_failures
        or any(not item["nas_verified"] for item in objects.values())
    ):
        raise SystemExit("execute rejected: every NAS blob must be revalidated")
    if (
        args.confirm != "DELETE_VERIFIED_COLD_R2"
        or os.getenv("R2_ARCHIVE_DELETE_ENABLED", "").lower() != "true"
        or os.getenv("R2_ARCHIVE_RESTORE_GATE_VERIFIED", "").lower() != "true"
    ):
        raise SystemExit(
            "execute rejected: confirmation, delete gate, and restore gate are required"
        )
    failures = []
    for item in objects.values():
        if not item["exists"]:
            continue
        try:
            await asyncio.to_thread(
                storage.r2_client.delete_object,
                Bucket=storage.r2_bucket,
                Key=item["key"],
            )
        except Exception as exc:
            failures.append({"key": item["key"], "error": str(exc)[:300]})
    if failures:
        raise RuntimeError(f"R2 cleanup had {len(failures)} failures; see {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--archive-worker-config")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 1000:
        raise SystemExit("cleanup batch limit must be between 1 and 1000")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
