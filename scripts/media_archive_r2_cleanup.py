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

from sqlalchemy import text

CANDIDATE_SQL = """
with ranked as (
  select id, row_number() over(partition by user_id order by id desc) rn from history
), hot as (
  select h.id from history h join ranked r on r.id=h.id where r.rn<=8 and h.is_visible is true
  union select id from history where is_favorited is true or is_public is true
  union select h.id from history h join gallery_posts gp on gp.task_id=h.task_id where gp.is_active is true
), verified as (
  select distinct h.id,h.task_id,h.output_file,h.type
  from history h join media_archive_outbox o on o.history_id=h.id and o.status='archived'
  join media_archive_receipts r on r.history_id=h.id and r.role='output' and r.ordinal=0
    and r.status='archived_verified' and length(r.sha256)=64
  where h.output_file is not null and h.output_file<>'' and h.task_id is not null
)
select v.id,v.task_id,v.output_file,v.type
from verified v where not exists(select 1 from hot where hot.id=v.id)
and not exists(
  select 1 from history shared join hot on hot.id=shared.id
  where shared.output_file=v.output_file
)
order by v.id limit :limit
"""


async def run(args) -> None:
    from src.database.core import AsyncSessionLocal
    from src.services.storage import storage
    from src.services.storage_r2_cleanup import build_history_r2_cleanup_keys

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(CANDIDATE_SQL), {"limit": args.limit})).all()
    objects = {}
    for history_id, task_id, output_file, history_type in rows:
        for key in build_history_r2_cleanup_keys(task_id, output_file, history_type):
            objects.setdefault(key, {"key": key, "history_ids": []})[
                "history_ids"
            ].append(history_id)
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
        args.confirm != "DELETE_VERIFIED_COLD_R2"
        or os.getenv("R2_ARCHIVE_DELETE_ENABLED", "").lower() != "true"
    ):
        raise SystemExit(
            "execute rejected: confirmation and R2_ARCHIVE_DELETE_ENABLED=true are required"
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
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
