#!/usr/bin/env python3
"""Enqueue verified hot History for asynchronous NAS-to-R2 restoration."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconcile_media_archive_outbox import load_history_ids  # noqa: E402


async def run(args) -> None:
    from sqlalchemy import select, text

    from src.database.core import AsyncSessionLocal
    from src.database.models import History
    from src.services.media_archive_service import enqueue_history_media_restore

    selected_ids = load_history_ids(args.history_id_file)
    async with AsyncSessionLocal() as session:
        ids = (
            (
                await session.execute(
                    text(
                        """with ranked as (
                      select id,row_number() over(partition by user_id order by id desc) rn
                      from history
                    )
                    select h.id from history h join ranked r on r.id=h.id
                    join media_archive_outbox a on a.history_id=h.id and a.status='archived'
                    left join media_archive_restore_outbox x on x.history_id=h.id
                    where ((r.rn<=8 and h.is_visible is true)
                      or h.is_favorited is true or h.is_public is true
                      or exists(select 1 from gallery_posts gp
                        where gp.task_id=h.task_id and gp.is_active is true))
                      and (x.id is null or x.status='manual_review')
                      and (:selected is false or h.id=any(:ids))
                    order by h.id limit :limit"""
                    ),
                    {
                        "selected": bool(selected_ids),
                        "ids": list(selected_ids) or [0],
                        "limit": args.limit,
                    },
                )
            )
            .scalars()
            .all()
        )
        histories = (
            (
                await session.execute(
                    select(History).where(History.id.in_(ids)).order_by(History.id)
                )
            )
            .scalars()
            .all()
            if ids
            else []
        )
        enqueued = 0
        if args.execute:
            for history in histories:
                enqueued += int(
                    await enqueue_history_media_restore(session, history, priority=0)
                )
            await session.commit()
    print(
        f"restore candidates={len(histories)} enqueued={enqueued} "
        f"mode={'execute' if args.execute else 'dry-run'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--history-id-file")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10000:
        parser.error("--limit must be between 1 and 10000")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
