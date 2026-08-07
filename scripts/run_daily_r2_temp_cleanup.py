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


def validate_canary_evidence(path_value: str) -> None:
    path = Path(path_value)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise SystemExit("daily cleanup requires private canary evidence")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("daily cleanup canary evidence is invalid") from exc
    stages = document.get("stages") if isinstance(document, dict) else None
    for stage in ("100", "1000", "10000"):
        evidence = stages.get(stage) if isinstance(stages, dict) else None
        if not isinstance(evidence, dict) or evidence.get("status") != "completed":
            raise SystemExit(f"daily cleanup canary {stage} is not accepted")
        digest = str(evidence.get("receipt_sha256") or "")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise SystemExit(f"daily cleanup canary {stage} receipt SHA-256 is invalid")


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
        execute=False,
        confirm=os.getenv("R2_TEMP_CLEANUP_CONFIRMATION", ""),
        approved_plan="",
        plan_sha256="",
    )


def main() -> None:
    args = build_args_from_env()
    execution_output = args.output
    args.output = execution_output.replace("cleanup-", "plan-", 1)
    args.execute = False
    report = asyncio.run(run(args))
    automation_enabled = (
        os.getenv("R2_TEMP_CLEANUP_AUTOMATION_ENABLED", "").lower() == "true"
    )
    delete_enabled = os.getenv("R2_TEMP_CLEANUP_ENABLED", "").lower() == "true"
    if automation_enabled and delete_enabled:
        validate_canary_evidence(
            os.getenv("R2_TEMP_CLEANUP_CANARY_EVIDENCE", "").strip()
        )
        base_confirmation = f"DELETE_VERIFIED_TEMP_R2_{PRODUCTION_BUCKET}"
        if args.confirm != base_confirmation:
            raise SystemExit("daily cleanup base confirmation is invalid")
        args.execute = True
        args.approved_plan = args.output
        args.plan_sha256 = report["plan_sha256"]
        args.confirm = f"{base_confirmation}:{args.plan_sha256}"
        args.output = execution_output
        report = asyncio.run(run(args))
    elif automation_enabled:
        raise SystemExit(
            "R2 temp cleanup automation requires R2_TEMP_CLEANUP_ENABLED=true"
        )
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
