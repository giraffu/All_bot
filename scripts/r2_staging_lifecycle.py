#!/usr/bin/env python3
"""Audit or apply the production-only 24 hour R2 staging lifecycle rule."""

from __future__ import annotations

import argparse
import json
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


STAGING_RULE_ID = "AllBot Staging 24h Expiration"
PRODUCTION_BUCKET = "user-data-prod"


def build_lifecycle_rules(existing_rules: list[dict]) -> list[dict]:
    retained = [
        dict(rule) for rule in existing_rules if rule.get("ID") != STAGING_RULE_ID
    ]
    retained.append(
        {
            "ID": STAGING_RULE_ID,
            "Status": "Enabled",
            "Filter": {"Prefix": "staging/"},
            "Expiration": {"Days": 1},
        }
    )
    return retained


def validate_apply_gate(*, bucket: str, enabled: bool, confirmation: str) -> None:
    if bucket != PRODUCTION_BUCKET:
        raise ValueError("staging lifecycle is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMP_CLEANUP_ENABLED must be true")
    if confirmation != f"APPLY_STAGING_24H_{bucket}":
        raise ValueError("exact staging lifecycle confirmation is required")


def _client():
    required = ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit(f"missing R2 configuration: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _read_rules(client, bucket: str) -> list[dict]:
    try:
        return list(
            client.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
        )
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in {"NoSuchLifecycleConfiguration", "NoSuchLifecycle"}:
            return []
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default=PRODUCTION_BUCKET)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    client = _client()
    existing = _read_rules(client, args.bucket)
    planned = build_lifecycle_rules(existing)
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "bucket": args.bucket,
                "existing_rule_ids": [rule.get("ID") for rule in existing],
                "planned_rules": planned,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not args.apply:
        return
    validate_apply_gate(
        bucket=args.bucket,
        enabled=os.getenv("R2_TEMP_CLEANUP_ENABLED", "").lower() == "true",
        confirmation=args.confirm,
    )
    client.put_bucket_lifecycle_configuration(
        Bucket=args.bucket,
        LifecycleConfiguration={"Rules": planned},
    )
    applied = _read_rules(client, args.bucket)
    if applied != planned:
        raise SystemExit("lifecycle read-back did not match the requested rules")


if __name__ == "__main__":
    main()
