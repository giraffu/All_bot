from __future__ import annotations

import asyncio
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
from typing import Any

import asyncpg

from .analytics_common import _database_url
from .prompt_template_candidates import (
    prompt_template_arg_parser,
    refresh_prompt_template_candidates,
)


DEFAULT_TEMPLATE_CANDIDATE_DATA_DIR = "/app/data/prompt_template_candidates"


def _json_default(value: Any) -> str:
    return str(value)


@contextmanager
def _refresh_lock(data_dir: str = DEFAULT_TEMPLATE_CANDIDATE_DATA_DIR):
    lock_dir = Path(data_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".refresh_prompt_template_candidates.lock"
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


async def _run() -> None:
    parser = prompt_template_arg_parser()
    args = parser.parse_args()
    with _refresh_lock() as acquired:
        if not acquired:
            print(json.dumps({"status": "skipped_lock_held"}, ensure_ascii=False, sort_keys=True))
            return
        conn = await asyncpg.connect(dsn=_database_url())
        try:
            await conn.execute(f"set statement_timeout = {int(args.statement_timeout_ms)}")
            status = await refresh_prompt_template_candidates(conn, batch_size=args.batch_size)
            print(json.dumps(status, ensure_ascii=False, default=_json_default, sort_keys=True))
        finally:
            await conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
