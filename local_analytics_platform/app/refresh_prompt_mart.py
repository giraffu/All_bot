from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import asyncpg

from .main import _builtin_prompt_template_args, _database_url
from .prompt_mart import refresh_prompt_mart


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh local analytics prompt mart tables.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Rebuild prompt mart tables from all eligible history rows.",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=7,
        help="For incremental refresh, also re-read recent history rows to catch mutable flags.",
    )
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
        await conn.execute("set work_mem = '512MB'")
        builtin_template_keys, builtin_template_prompts = _builtin_prompt_template_args()
        status = await refresh_prompt_mart(
            conn,
            builtin_template_keys=builtin_template_keys,
            builtin_template_prompts=builtin_template_prompts,
            full=bool(args.full),
            recent_days=max(1, int(args.recent_days)),
        )
        print(json.dumps(status, ensure_ascii=False, default=_json_default, sort_keys=True))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
