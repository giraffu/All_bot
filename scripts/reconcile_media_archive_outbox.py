#!/usr/bin/env python3
"""Find History rows missing archive outbox entries; writes only with --execute."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def run(args) -> None:
    from sqlalchemy import select

    from src.database.core import AsyncSessionLocal
    from src.database.models import History, MediaArchiveOutbox
    from src.services.media_archive_service import enqueue_history_media_archive

    last_id = args.start_id - 1
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
                            History.id <= args.end_id,
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
                for history in rows:
                    await enqueue_history_media_archive(session, history)
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
    parser.add_argument("--end-id", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--execute", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
