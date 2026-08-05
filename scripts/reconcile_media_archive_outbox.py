#!/usr/bin/env python3
"""Find History rows missing archive outbox entries; writes only with --execute."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_history_ids(path: str | None) -> tuple[int, ...]:
    if not path:
        return ()
    values = []
    for line_number, raw in enumerate(Path(path).read_text().splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if not value.isdigit() or int(value) < 1:
            raise ValueError(f"invalid History ID on line {line_number}")
        values.append(int(value))
    result = tuple(sorted(set(values)))
    if not result:
        raise ValueError("History ID file contains no IDs")
    if len(result) > 10000:
        raise ValueError("History ID file is limited to 10000 IDs")
    return result


async def run(args) -> None:
    from sqlalchemy import select, text

    from src.database.core import AsyncSessionLocal
    from src.database.models import History, MediaArchiveOutbox
    from src.services.media_archive_service import enqueue_history_media_archive

    selected_ids = load_history_ids(args.history_id_file)
    last_id = (selected_ids[0] if selected_ids else args.start_id) - 1
    end_id = selected_ids[-1] if selected_ids else args.end_id
    total = 0
    while True:
        async with AsyncSessionLocal() as session:
            rows = (
                (
                    await session.execute(
                        select(History)
                        .outerjoin(
                            MediaArchiveOutbox,
                            MediaArchiveOutbox.history_id == History.id,
                        )
                        .where(
                            History.id > last_id,
                            History.id <= end_id,
                            *([History.id.in_(selected_ids)] if selected_ids else []),
                            MediaArchiveOutbox.id.is_(None),
                        )
                        .order_by(History.id)
                        .limit(args.batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            last_id = rows[-1].id
            total += len(rows)
            if args.execute:
                ids = [history.id for history in rows]
                hot_ids = set(
                    (
                        await session.execute(
                            text(
                                """
                                with users_in_batch as (
                                  select distinct user_id from history where id = any(:ids)
                                ), ranked as (
                                  select h.id,row_number() over(partition by h.user_id order by h.id desc) rn
                                  from history h join users_in_batch u on u.user_id=h.user_id
                                )
                                select h.id from history h left join ranked r on r.id=h.id
                                where h.id = any(:ids) and (
                                  (r.rn<=8 and h.is_visible is true) or h.is_favorited is true or h.is_public is true
                                  or exists(select 1 from gallery_posts gp where gp.task_id=h.task_id and gp.is_active is true)
                                )
                                """
                            ),
                            {"ids": ids},
                        )
                    ).scalars()
                )
                recent_cutoff = datetime.now() - timedelta(days=30)
                for history in rows:
                    priority = (
                        0
                        if history.id in hot_ids
                        else 10
                        if history.created_at and history.created_at >= recent_cutoff
                        else 20
                    )
                    await enqueue_history_media_archive(
                        session, history, priority=priority
                    )
                await session.commit()
            print(
                f"cursor={last_id} candidates={total} mode={'execute' if args.execute else 'dry-run'}"
            )
    print(
        f"complete candidates={total} mode={'execute' if args.execute else 'dry-run'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--end-id", type=int)
    parser.add_argument(
        "--history-id-file",
        help="newline-delimited exact History IDs (maximum 10000)",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.end_id is None and not args.history_id_file:
        parser.error("--end-id or --history-id-file is required")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
