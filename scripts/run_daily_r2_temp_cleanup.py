#!/usr/bin/env python3
"""Run one bounded, evidence-producing R2 temporary cleanup batch."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from scripts.r2_temp_cleanup import DEFAULT_MAX_DELETE_BYTES, PRODUCTION_BUCKET, run


def build_args_from_env() -> SimpleNamespace:
    inventory = os.getenv("R2_TEMP_CLEANUP_INVENTORY", "").strip()
    if not inventory or not Path(inventory).is_file():
        raise SystemExit("R2_TEMP_CLEANUP_INVENTORY must reference a current inventory")
    max_inventory_age = max(
        1, int(os.getenv("R2_TEMP_CLEANUP_MAX_INVENTORY_AGE_HOURS", "36"))
    )
    inventory_age = time.time() - Path(inventory).stat().st_mtime
    if inventory_age > max_inventory_age * 3600:
        raise SystemExit("R2_TEMP_CLEANUP_INVENTORY is stale")
    state_root = Path(
        os.getenv(
            "R2_TEMP_CLEANUP_STATE_ROOT",
            "/var/lib/allbot-r2-temp-cleanup",
        )
    )
    now = datetime.now(timezone.utc)
    output = state_root / now.strftime("%Y%m%d") / now.strftime("cleanup-%H%M%S.json")
    return SimpleNamespace(
        inventory=inventory,
        output=str(output),
        bucket=PRODUCTION_BUCKET,
        limit=min(10_000, max(1, int(os.getenv("R2_TEMP_CLEANUP_DAILY_LIMIT", "10000")))),
        min_age_hours=max(24, int(os.getenv("R2_TEMP_CLEANUP_MIN_AGE_HOURS", "24"))),
        verification_concurrency=min(
            16, max(1, int(os.getenv("R2_TEMP_CLEANUP_VERIFICATION_CONCURRENCY", "8")))
        ),
        max_delete_bytes=min(
            DEFAULT_MAX_DELETE_BYTES,
            max(1, int(os.getenv("R2_TEMP_CLEANUP_DAILY_MAX_BYTES", str(DEFAULT_MAX_DELETE_BYTES)))),
        ),
        execute=True,
        confirm=os.getenv("R2_TEMP_CLEANUP_CONFIRMATION", ""),
    )


def main() -> None:
    args = build_args_from_env()
    report = asyncio.run(run(args))
    print(
        json.dumps(
            {
                "output": args.output,
                "delete_count": report["delete_count"],
                "delete_bytes": report["delete_bytes"],
                "blocked": report["referenced_blocked_count"],
                "probe_failures": len(report["probe_failures"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
