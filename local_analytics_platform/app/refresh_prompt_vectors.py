from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg

from .main import _database_url
from .prompt_vectors import config_from_args, prompt_vector_arg_parser, refresh_prompt_vectors


def _json_default(value: Any) -> str:
    return str(value)


async def _run() -> None:
    parser = prompt_vector_arg_parser()
    args = parser.parse_args()
    config = config_from_args(args)
    conn = await asyncpg.connect(dsn=_database_url())
    try:
        await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
        status = await refresh_prompt_vectors(conn, config)
        print(json.dumps(status, ensure_ascii=False, default=_json_default, sort_keys=True))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
