#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import subprocess


ENVIRONMENTS = {
    "test": ("allbot-do-sgp1-test-control", "/var/lib/allbot/test"),
    "prod": ("allbot-do-sgp1-control", "/var/lib/allbot/prod"),
}


class MaintenanceError(RuntimeError):
    pass


def environment_contract(environment: str) -> tuple[str, str]:
    try:
        return ENVIRONMENTS[environment]
    except KeyError as exc:
        raise MaintenanceError("unsupported maintenance environment") from exc


def _python_payload_script(payload: dict) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return "\n".join(
        [
            "import base64, json",
            f"payload = json.loads(base64.b64decode({encoded!r}))",
        ]
    )


def status_script(environment: str) -> str:
    _, root = environment_contract(environment)
    payload = {
        "environment": environment,
        "root": root,
        "deployment_root": (
            f"/var/lib/allbot/deployments/{environment}/control-plane"
        ),
    }
    return (
        "set -euo pipefail\npython3 - <<'PY'\n"
        + _python_payload_script(payload)
        + r"""
from pathlib import Path
root = Path(payload["root"])
marker = root / "runtime/GENERATION_MAINTENANCE"
metadata_path = root / "runtime/GENERATION_MAINTENANCE.owner.json"
metadata = {}
if metadata_path.is_file():
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        metadata = {}
deployment_root = Path(payload["deployment_root"])
current = {}
current_path = deployment_root / "current.json"
if current_path.is_file():
    try:
        current = json.loads(current_path.read_text())
    except (OSError, ValueError):
        current = {}
active = []
for transactions in (root / "transactions", deployment_root / "transactions"):
    if transactions.exists():
        for path in transactions.rglob("*.json"):
            if path.name.endswith(".state.json"):
                continue
            try:
                item = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if item.get("status") not in {"succeeded", "rolled_back", "recovered"}:
                active.append({"transaction": path.stem, "status": item.get("status")})
enabled = marker.exists()
owner = metadata.get("owner") if enabled else None
print(json.dumps({
    "environment": payload["environment"],
    "current_sha": current.get("git_sha"),
    "artifacts": current.get("artifacts") or {},
    "health": current.get("health") or {},
    "config_revision": current.get("config_revision"),
    "maintenance": {
        "enabled": enabled,
        "owner": owner or ("unknown" if enabled else None),
        "reason": metadata.get("reason") if enabled else None,
        "can_disable": enabled and owner == "lan-resource-manager" and not active,
    },
    "active_transaction": active[0] if active else None,
    "config_drift": bool(current.get("config_drift")),
}))
PY
"""
    )


def mutation_script(
    *,
    environment: str,
    enabled: bool,
    expected_enabled: bool,
    reason: str,
    operation_id: str,
) -> str:
    _, root = environment_contract(environment)
    payload = {
        "environment": environment,
        "root": root,
        "deployment_root": (
            f"/var/lib/allbot/deployments/{environment}/control-plane"
        ),
        "enabled": enabled,
        "expected_enabled": expected_enabled,
        "reason": reason,
        "operation_id": operation_id,
    }
    return (
        "set -euo pipefail\npython3 - <<'PY'\n"
        + _python_payload_script(payload)
        + r"""
import os
import tempfile
from pathlib import Path
root = Path(payload["root"])
runtime = root / "runtime"
marker = runtime / "GENERATION_MAINTENANCE"
metadata_path = runtime / "GENERATION_MAINTENANCE.owner.json"
current = marker.exists()
if current != payload["expected_enabled"]:
    raise SystemExit("maintenance state changed")
active = []
for transactions in (
    root / "transactions",
    Path(payload["deployment_root"]) / "transactions",
):
    if transactions.exists():
        for path in transactions.rglob("*.json"):
            if path.name.endswith(".state.json"):
                continue
            try:
                item = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if item.get("status") not in {"succeeded", "rolled_back", "recovered"}:
                active.append(path)
if active:
    raise SystemExit("active release transaction blocks maintenance change")
runtime.mkdir(parents=True, exist_ok=True)
if payload["enabled"]:
    marker.write_text("1\n")
    metadata = {
        "owner": "lan-resource-manager",
        "environment": payload["environment"],
        "reason": payload["reason"],
        "operation_id": payload["operation_id"],
    }
    fd, name = tempfile.mkstemp(dir=runtime)
    with os.fdopen(fd, "w") as handle:
        json.dump(metadata, handle)
        handle.write("\n")
    os.chmod(name, 0o600)
    os.replace(name, metadata_path)
else:
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        raise SystemExit("maintenance owner is unknown; use host operator CLI")
    if metadata.get("owner") != "lan-resource-manager":
        raise SystemExit("maintenance owner is unknown; use host operator CLI")
    marker.unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)
print(json.dumps({
    "environment": payload["environment"],
    "maintenance": {
        "enabled": payload["enabled"],
        "owner": "lan-resource-manager" if payload["enabled"] else None,
        "reason": payload["reason"] if payload["enabled"] else None,
        "can_disable": payload["enabled"],
    },
}))
PY
"""
    )


def _ssh(host: str, script: str) -> dict:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, "bash", "-s"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise MaintenanceError(detail[-1] if detail else "maintenance command failed")
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise MaintenanceError("maintenance response is invalid") from exc
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the fixed AllBot generation-maintenance marker."
    )
    parser.add_argument("action", choices=("status", "enable", "disable"))
    parser.add_argument("--env", choices=("test", "prod"), required=True)
    parser.add_argument("--expected-enabled", choices=("true", "false"))
    parser.add_argument("--reason", default="")
    parser.add_argument("--operation-id", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-prod", action="store_true")
    args = parser.parse_args()
    host, _ = environment_contract(args.env)
    if args.action == "status":
        payload = _ssh(host, status_script(args.env))
    else:
        if not args.execute:
            raise MaintenanceError("maintenance mutation requires --execute")
        if args.env == "prod" and not args.confirm_prod:
            raise MaintenanceError("production maintenance requires --confirm-prod")
        if args.expected_enabled is None or not args.reason or not args.operation_id:
            raise MaintenanceError("maintenance mutation arguments are incomplete")
        payload = _ssh(
            host,
            mutation_script(
                environment=args.env,
                enabled=args.action == "enable",
                expected_enabled=args.expected_enabled == "true",
                reason=args.reason,
                operation_id=args.operation_id,
            ),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MaintenanceError as exc:
        raise SystemExit(str(exc))
