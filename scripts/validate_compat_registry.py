#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "compat_registry.json"
REQUIRED_FIELDS = {
    "id",
    "status",
    "entrypoint",
    "owner",
    "telemetry_key",
    "telemetry_source",
    "replacement",
    "exit_condition",
    "minimum_zero_hit_days",
    "historical_data",
}
VALID_STATUSES = {"active-compat", "runtime-verification-required"}


def validate_registry() -> list[str]:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return [*errors, "entries must be a non-empty list"]

    ids: set[str] = set()
    telemetry_keys: set[str] = set()
    production_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (ROOT / "src", ROOT / "backend")
        for path in root.rglob("*.py")
        if path.name != "compat_telemetry.py"
    )
    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = REQUIRED_FIELDS - entry.keys()
        if missing:
            errors.append(f"{label} missing fields: {sorted(missing)}")
            continue
        if entry["id"] in ids:
            errors.append(f"duplicate id: {entry['id']}")
        ids.add(entry["id"])
        if entry["telemetry_key"] in telemetry_keys:
            errors.append(f"duplicate telemetry_key: {entry['telemetry_key']}")
        telemetry_keys.add(entry["telemetry_key"])
        if entry["status"] not in VALID_STATUSES:
            errors.append(f"{label} has invalid status")
        if not str(entry["telemetry_key"]).startswith("compat."):
            errors.append(f"{label} telemetry_key must start with compat.")
        if int(entry["minimum_zero_hit_days"]) < 7:
            errors.append(f"{label} observation window must be at least 7 days")
        if entry["telemetry_source"] == "compat_hit_log" and entry["telemetry_key"] not in production_text:
            errors.append(f"{label} declares compat_hit_log without instrumentation")
    return errors


def main() -> int:
    errors = validate_registry()
    if errors:
        print("Compat registry validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Compat registry validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
