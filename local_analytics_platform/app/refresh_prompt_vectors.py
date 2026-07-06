from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
from typing import Any

import asyncpg

from .analytics_common import _database_url
from .prompt_vectors import config_from_args, prompt_vector_arg_parser, refresh_prompt_vectors


def _json_default(value: Any) -> str:
    return str(value)


@contextmanager
def _refresh_lock(data_dir: str):
    lock_dir = Path(data_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".refresh_prompt_vectors.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _is_closed_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncpg.PostgresConnectionError):
        return True
    message = str(exc).lower()
    return isinstance(exc, asyncpg.InterfaceError) and (
        "connection is closed" in message
        or "connection was closed" in message
        or "connection lost" in message
    )


async def _run() -> None:
    parser = prompt_vector_arg_parser()
    args = parser.parse_args()
    config = config_from_args(args)
    with _refresh_lock(config.data_dir) as acquired:
        if not acquired:
            print(json.dumps({"status": "skipped_lock_held"}, ensure_ascii=False, sort_keys=True))
            return
        attempts = 0
        while True:
            conn = await asyncpg.connect(dsn=_database_url())
            try:
                await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
                status = await refresh_prompt_vectors(conn, config)
                print(json.dumps(status, ensure_ascii=False, default=_json_default, sort_keys=True))
                return
            except Exception as exc:
                if _is_closed_connection_error(exc) and attempts < 3:
                    attempts += 1
                    continue
                raise
            finally:
                try:
                    await conn.close()
                except asyncpg.InterfaceError:
                    pass


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
