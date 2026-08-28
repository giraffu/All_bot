from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from observer_bot.repository import _asyncpg_url


async def apply_schema(database_url: str) -> None:
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        await connection.execute(sql)
    finally:
        await connection.close()


def main() -> None:
    database_url = os.environ.get("OBSERVER_DATABASE_ADMIN_URL", "").strip()
    if not database_url:
        raise SystemExit("OBSERVER_DATABASE_ADMIN_URL is required")
    asyncio.run(apply_schema(database_url))


if __name__ == "__main__":
    main()
