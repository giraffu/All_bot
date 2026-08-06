#!/usr/bin/env python3
"""Resumable same-bucket migration from temps/ to template-submissions/."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


BUCKET = "user-data-prod"
SOURCE_PREFIX = "temps/"
TARGET_PREFIX = "template-submissions/"


def destination_key(source_key: str) -> str:
    if not source_key.startswith(SOURCE_PREFIX) or source_key == SOURCE_PREFIX:
        raise ValueError("source key must be a non-empty temps/ object")
    return f"{TARGET_PREFIX}{source_key[len(SOURCE_PREFIX):]}"


def validate_execute_gate(*, bucket: str, enabled: bool, confirmation: str) -> None:
    if bucket != BUCKET:
        raise ValueError("template migration is restricted to user-data-prod")
    if not enabled:
        raise ValueError("R2_TEMPLATE_SUBMISSION_MIGRATION_ENABLED must be true")
    if confirmation != f"COPY_VERIFIED_TEMPLATE_SUBMISSIONS_{bucket}":
        raise ValueError("exact template migration confirmation is required")


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("pragma journal_mode=wal")
    db.execute(
        """create table if not exists objects(
          source_key text primary key,target_key text not null,byte_size integer not null,
          status text not null,sha256 text,error text,updated_at text not null
        ) without rowid"""
    )
    db.commit()
    os.chmod(path, 0o600)
    return db


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
        config=Config(signature_version="s3v4", max_pool_connections=8),
    )


def _sha256(client, bucket: str, key: str) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    try:
        while chunk := body.read(4 * 1024 * 1024):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def _head_optional(client, bucket: str, key: str):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def _scan(client, db: sqlite3.Connection, bucket: str) -> int:
    paginator = client.get_paginator("list_objects_v2")
    now = datetime.now(timezone.utc).isoformat()
    seen = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=SOURCE_PREFIX):
        for item in page.get("Contents", []):
            source_key = str(item["Key"])
            if source_key == SOURCE_PREFIX:
                continue
            db.execute(
                """insert into objects(source_key,target_key,byte_size,status,updated_at)
                   values(?,?,?,'pending',?) on conflict(source_key) do update set
                   target_key=excluded.target_key,byte_size=excluded.byte_size,
                   status=case when objects.status='verified' then objects.status else 'pending' end,
                   updated_at=excluded.updated_at""",
                (source_key, destination_key(source_key), int(item.get("Size") or 0), now),
            )
            seen += 1
    db.commit()
    return seen


def _copy_and_verify(client, bucket: str, source_key: str, target_key: str, size: int) -> str:
    source_head = client.head_object(Bucket=bucket, Key=source_key)
    if int(source_head.get("ContentLength", -1)) != size:
        raise RuntimeError("SOURCE_SIZE_CHANGED")
    source_sha = _sha256(client, bucket, source_key)
    target_head = _head_optional(client, bucket, target_key)
    if target_head is None:
        client.copy_object(
            Bucket=bucket,
            Key=target_key,
            CopySource={"Bucket": bucket, "Key": source_key},
            MetadataDirective="COPY",
        )
        target_head = client.head_object(Bucket=bucket, Key=target_key)
    if int(target_head.get("ContentLength", -1)) != size:
        raise RuntimeError("TARGET_SIZE_MISMATCH")
    if _sha256(client, bucket, target_key) != source_sha:
        raise RuntimeError("TARGET_SHA256_MISMATCH")
    return source_sha


def run(args) -> dict:
    client = _client()
    state_path = Path(args.state)
    db = _connect(state_path)
    try:
        scanned = _scan(client, db, args.bucket)
        if args.execute:
            validate_execute_gate(
                bucket=args.bucket,
                enabled=os.getenv("R2_TEMPLATE_SUBMISSION_MIGRATION_ENABLED", "").lower() == "true",
                confirmation=args.confirm,
            )
            rows = db.execute(
                """select source_key,target_key,byte_size from objects
                   where status<>'verified' order by source_key limit ?""",
                (args.limit,),
            ).fetchall()
            for source_key, target_key, size in rows:
                try:
                    digest = _copy_and_verify(client, args.bucket, source_key, target_key, int(size))
                    db.execute(
                        "update objects set status='verified',sha256=?,error=null,updated_at=? where source_key=?",
                        (digest, datetime.now(timezone.utc).isoformat(), source_key),
                    )
                except Exception as exc:
                    db.execute(
                        "update objects set status='failed',error=?,updated_at=? where source_key=?",
                        (type(exc).__name__, datetime.now(timezone.utc).isoformat(), source_key),
                    )
                    db.commit()
                    raise
                db.commit()
        total, verified, failed, total_bytes = db.execute(
            """select count(*),count(*) filter(where status='verified'),
               count(*) filter(where status='failed'),coalesce(sum(byte_size),0) from objects"""
        ).fetchone()
        return {
            "mode": "execute" if args.execute else "dry-run",
            "bucket": args.bucket,
            "scanned": scanned,
            "total": int(total),
            "verified": int(verified),
            "failed": int(failed),
            "bytes": int(total_bytes),
            "state": str(state_path),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10_000:
        raise SystemExit("limit must be between 1 and 10000")
    print(json.dumps(run(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
