#!/usr/bin/env python3
"""Read-only health probe for every configured archive source and NAS target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config

from scripts.media_archive_worker import load_secure_config, validate_endpoint_route


def _s3_client(item: dict):
    return boto3.client(
        "s3",
        endpoint_url=item["endpoint"],
        aws_access_key_id=item["access_key"],
        aws_secret_access_key=item["secret_key"],
        region_name=item.get("region", "auto"),
        verify=item.get("ca_file", True),
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 1},
        ),
    )


def probe_item(item: dict) -> dict:
    name = str(item.get("name") or "unnamed")
    try:
        if item.get("type", "s3") == "filesystem":
            roots = [Path(value) for value in item.get("roots", [])]
            if not roots or not all(root.is_dir() for root in roots):
                raise RuntimeError("configured filesystem root is offline")
        else:
            validate_endpoint_route(item)
            _s3_client(item).list_objects_v2(Bucket=item["bucket"], MaxKeys=1)
        return {"name": name, "status": "healthy"}
    except Exception as exc:
        return {"name": name, "status": "source_offline", "error": type(exc).__name__}


def build_report(config: dict) -> dict:
    sources = [probe_item(item) for item in config["sources"]]
    nas = probe_item(config["nas"])
    offline = [item["name"] for item in [*sources, nas] if item["status"] != "healthy"]
    return {"sources": sources, "nas": nas, "offline": offline, "healthy": not offline}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    report = build_report(load_secure_config(Path(args.config)))
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        output.chmod(0o600)
    print(payload)
    if args.require_all and not report["healthy"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
