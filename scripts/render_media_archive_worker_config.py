#!/usr/bin/env python3
"""Render a private 0600 archive Worker config from env:NAME placeholders."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _resolve(value):
    if isinstance(value, dict):
        return {key: _resolve(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item) for item in value]
    if isinstance(value, str) and value.startswith("env:"):
        name = value[4:]
        resolved = os.getenv(name)
        if not resolved:
            raise ValueError(f"required environment value is missing: {name}")
        return resolved
    return value


def validate_worker_config(config: dict) -> None:
    required = ("central_api", "agent_token", "catalog_database_url", "nas", "sources")
    missing = [name for name in required if not config.get(name)]
    if missing:
        raise ValueError(f"worker config is missing: {', '.join(missing)}")
    sources = config["sources"]
    names = [str(item.get("name") or "") for item in sources]
    if len(names) != len(set(names)) or any(not name for name in names):
        raise ValueError("archive source names must be unique and non-empty")
    if "r2-user-data" in names or any(item.get("bucket") == "user-data" for item in sources):
        raise ValueError("retired user-data bucket cannot be an enabled archive source")
    if int(config.get("bandwidth_bytes_per_second", 0)) > 50 * 1024**2:
        raise ValueError("archive bandwidth must not exceed 50 MiB/s")
    if int(config.get("max_spool_bytes", 0)) > 100 * 1024**3:
        raise ValueError("archive spool capacity must not exceed 100 GiB")
    if int(config.get("pause_spool_bytes", 0)) > 90 * 1024**3:
        raise ValueError("archive spool pause threshold must not exceed 90 GiB")


def render(template: Path) -> tuple[dict, dict]:
    config = _resolve(json.loads(template.read_text(encoding="utf-8")))
    validate_worker_config(config)
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    summary = {
        "source_names": [item["name"] for item in config["sources"]],
        "nas_name": config["nas"]["name"],
        "restore_target_name": (config.get("restore_target") or {}).get("name"),
        "fingerprint": hashlib.sha256(canonical).hexdigest()[:16],
    }
    return config, summary


def write_private_config(output: Path, config: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temporary.chmod(0o600)
        temporary.replace(output)
        output.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    config, summary = render(Path(args.template))
    if args.apply:
        write_private_config(Path(args.output), config)
    print(json.dumps({"mode": "apply" if args.apply else "check", **summary}))


if __name__ == "__main__":
    main()
