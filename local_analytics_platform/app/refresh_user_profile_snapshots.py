from __future__ import annotations

import argparse
import asyncio
from datetime import date
import json
from typing import Sequence

import asyncpg

from .user_profile_snapshots import (
    database_url_from_env,
    refresh_user_profile_daily_snapshot,
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


async def _run(args: argparse.Namespace) -> dict[str, object]:
    conn = await asyncpg.connect(database_url_from_env())
    try:
        return await refresh_user_profile_daily_snapshot(
            conn,
            snapshot_date=_parse_date(args.snapshot_date),
            statement_timeout_ms=int(args.statement_timeout_ms),
        )
    finally:
        await conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh AllBot user profile daily snapshot.")
    parser.add_argument("--snapshot-date", help="snapshot date in YYYY-MM-DD; defaults to today")
    parser.add_argument("--statement-timeout-ms", type=int, default=3_600_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

