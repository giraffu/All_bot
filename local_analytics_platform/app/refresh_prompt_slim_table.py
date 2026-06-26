from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import asyncpg

from .main import _database_url
from .prompt_slim import refresh_prompt_slim_candidates


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh local analytics prompt slim candidate table.")
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=1_800_000,
        help="PostgreSQL statement timeout used during refresh.",
    )
    return parser


def _json_default(value: Any) -> str:
    return str(value)


async def _run(args: argparse.Namespace) -> None:
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
        status = await refresh_prompt_slim_candidates(conn)
        print(json.dumps(status, ensure_ascii=False, default=_json_default, sort_keys=True))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
