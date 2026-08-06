#!/usr/bin/env python3
"""Resumable exact-key migration and verified retirement for the legacy R2 bucket."""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


SOURCE_BUCKET = "user-data"
TARGET_BUCKET = "user-data-prod"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("pragma journal_mode=wal")
    db.execute(
        """
        create table if not exists migration_objects(
          key text primary key,
          byte_size integer not null,
          source_etag text not null,
          source_last_modified text,
          status text not null,
          sha256 text,
          attempts integer not null default 0,
          error text,
          updated_at text not null
        ) without rowid
        """
    )
    columns = {row[1] for row in db.execute("pragma table_info(migration_objects)")}
    for name in ("source_head_json", "target_head_json"):
        if name not in columns:
            db.execute(f"alter table migration_objects add column {name} text")
    db.commit()
    return db


def initialize_state(
    state_path: Path, source_inventory: Path, target_inventory: Path
) -> None:
    db = _connect(state_path)
    try:
        db.execute("attach database ? as source", (str(source_inventory),))
        db.execute("attach database ? as target", (str(target_inventory),))
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            """
            insert into migration_objects(
              key,byte_size,source_etag,source_last_modified,status,updated_at
            )
            select s.key,s.size,s.etag,s.last_modified,
                   case
                     when t.key is null then 'pending'
                     when t.size=s.size then 'present'
                     else 'conflict'
                   end,
                   ?
            from source.objects s left join target.objects t using(key)
            on conflict(key) do update set
              status=case
                when migration_objects.status in ('copied','verified')
                  and migration_objects.byte_size=excluded.byte_size
                  and migration_objects.source_etag=excluded.source_etag
                  then migration_objects.status
                else excluded.status
              end,
              byte_size=excluded.byte_size,
              source_etag=excluded.source_etag,
              source_last_modified=excluded.source_last_modified,
              updated_at=excluded.updated_at
            """,
            (now,),
        )
        db.execute(
            "delete from migration_objects where key not in (select key from source.objects)"
        )
        db.commit()
    finally:
        db.close()
    os.chmod(state_path, 0o600)


def retirement_summary(state_path: Path) -> dict[str, int]:
    db = _connect(state_path)
    try:
        counts = dict(
            db.execute(
                "select status,count(*) from migration_objects group by status"
            ).fetchall()
        )
        total, total_bytes = db.execute(
            "select count(*),coalesce(sum(byte_size),0) from migration_objects"
        ).fetchone()
        bytes_pending = db.execute(
            "select coalesce(sum(byte_size),0) from migration_objects where status='pending'"
        ).fetchone()[0]
        return {
            "total": int(total),
            "total_bytes": int(total_bytes),
            "bytes_pending": int(bytes_pending),
            **{name: int(counts.get(name, 0)) for name in (
                "pending", "present", "copied", "verified", "conflict", "failed"
            )},
        }
    finally:
        db.close()


def validate_copy_gate(*, enabled: bool, confirmation: str) -> None:
    if not enabled:
        raise ValueError("R2_LEGACY_MIGRATION_ENABLED must be true")
    if confirmation != f"COPY_{SOURCE_BUCKET}_TO_{TARGET_BUCKET}":
        raise ValueError("exact legacy copy confirmation is required")


def validate_delete_gate(
    *,
    enabled: bool,
    source_bucket: str,
    target_bucket: str,
    verified: int,
    total: int,
    confirmation: str,
) -> None:
    if source_bucket != SOURCE_BUCKET or target_bucket != TARGET_BUCKET:
        raise ValueError("legacy retirement bucket identity mismatch")
    if not enabled:
        raise ValueError("R2_LEGACY_RETIRE_ENABLED must be true")
    if total < 1 or verified != total:
        raise ValueError("every legacy object must be SHA-256 verified")
    if confirmation != f"DELETE_LEGACY_BUCKET_{source_bucket}_{total}":
        raise ValueError("exact legacy bucket deletion confirmation is required")


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
        config=Config(signature_version="s3v4", max_pool_connections=32),
    )


def _copy_one(client, key: str, expected_size: int) -> dict:
    preserved_fields = (
        "ContentType",
        "CacheControl",
        "ContentDisposition",
        "ContentEncoding",
        "ContentLanguage",
        "Metadata",
    )
    try:
        source_head = client.head_object(Bucket=SOURCE_BUCKET, Key=key)
        try:
            target_head = client.head_object(Bucket=TARGET_BUCKET, Key=key)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
            target_head = None
        if target_head is None:
            client.copy_object(
                Bucket=TARGET_BUCKET,
                Key=key,
                CopySource={"Bucket": SOURCE_BUCKET, "Key": key},
                MetadataDirective="COPY",
            )
            target_head = client.head_object(Bucket=TARGET_BUCKET, Key=key)
        if int(target_head.get("ContentLength", -1)) != int(expected_size):
            raise RuntimeError("TARGET_SIZE_MISMATCH")
        if any(
            source_head.get(field) != target_head.get(field)
            for field in preserved_fields
        ):
            raise RuntimeError("TARGET_METADATA_MISMATCH")
        return {
            "key": key,
            "status": "copied",
            "source_head_json": json.dumps(
                {field: source_head.get(field) for field in preserved_fields},
                sort_keys=True,
                default=str,
            ),
            "target_head_json": json.dumps(
                {field: target_head.get(field) for field in preserved_fields},
                sort_keys=True,
                default=str,
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "key": key,
            "status": "failed",
            "source_head_json": None,
            "target_head_json": None,
            "error": type(exc).__name__,
        }


def _copy_batch(client, rows: list[tuple[str, int]], *, workers: int) -> list[dict]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda row: _copy_one(client, *row), rows))


def _copy_pending(
    state_path: Path,
    *,
    limit: int,
    workers: int,
    execute: bool,
    confirm: str,
) -> None:
    if not execute:
        print(json.dumps({"mode": "dry-run", **retirement_summary(state_path)}))
        return
    if limit < 1 or limit > 10_000:
        raise SystemExit("copy limit must be between 1 and 10000")
    if workers < 1 or workers > 32:
        raise SystemExit("copy workers must be between 1 and 32")
    validate_copy_gate(
        enabled=os.getenv("R2_LEGACY_MIGRATION_ENABLED", "").lower() == "true",
        confirmation=confirm,
    )
    client = _client()
    db = _connect(state_path)
    try:
        rows = db.execute(
            "select key,byte_size from migration_objects where status in ('pending','failed') order by key limit ?",
            (limit,),
        ).fetchall()
        for result in _copy_batch(client, rows, workers=workers):
            now = datetime.now(timezone.utc).isoformat()
            if result["status"] == "copied":
                db.execute(
                    """update migration_objects set status='copied',
                       source_head_json=?,target_head_json=?,attempts=attempts+1,
                       error=null,updated_at=? where key=?""",
                    (
                        result["source_head_json"],
                        result["target_head_json"],
                        now,
                        result["key"],
                    ),
                )
            else:
                db.execute(
                    "update migration_objects set status='failed',attempts=attempts+1,error=?,updated_at=? where key=?",
                    (result["error"], now, result["key"]),
                )
            db.commit()
    finally:
        db.close()


def _sha256(client, bucket: str, key: str) -> str:
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: body.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


def _verify_one(client, key: str) -> tuple[str, str, str | None]:
    try:
        source_sha = _sha256(client, SOURCE_BUCKET, key)
        target_sha = _sha256(client, TARGET_BUCKET, key)
        if source_sha != target_sha:
            return key, "conflict", None
        return key, "verified", source_sha
    except Exception:
        return key, "failed", None


def _verify(state_path: Path, *, limit: int, workers: int) -> None:
    client = _client()
    db = _connect(state_path)
    try:
        keys = [
            row[0]
            for row in db.execute(
                "select key from migration_objects where status in ('present','copied','failed') order by key limit ?",
                (limit,),
            ).fetchall()
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for key, status, sha256 in pool.map(
                lambda item: _verify_one(client, item), keys
            ):
                db.execute(
                    "update migration_objects set status=?,sha256=?,error=?,updated_at=? where key=?",
                    (
                        status,
                        sha256,
                        None if status == "verified" else "SHA256_VERIFY_FAILED",
                        datetime.now(timezone.utc).isoformat(),
                        key,
                    ),
                )
                db.commit()
    finally:
        db.close()


def _delete_verified_bucket(state_path: Path, *, execute: bool, confirm: str) -> None:
    summary = retirement_summary(state_path)
    print(json.dumps({"mode": "delete" if execute else "dry-run", **summary}))
    if not execute:
        return
    validate_delete_gate(
        enabled=os.getenv("R2_LEGACY_RETIRE_ENABLED", "").lower() == "true",
        source_bucket=SOURCE_BUCKET,
        target_bucket=TARGET_BUCKET,
        verified=summary["verified"],
        total=summary["total"],
        confirmation=confirm,
    )
    client = _client()
    while True:
        page = client.list_objects_v2(Bucket=SOURCE_BUCKET, MaxKeys=1000)
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if not objects:
            break
        response = client.delete_objects(
            Bucket=SOURCE_BUCKET,
            Delete={"Objects": objects, "Quiet": True},
        )
        if response.get("Errors"):
            raise RuntimeError("legacy bucket batch deletion failed")
    if client.list_objects_v2(Bucket=SOURCE_BUCKET, MaxKeys=1).get("KeyCount", 0):
        raise RuntimeError("legacy bucket is not empty after deletion")
    client.delete_bucket(Bucket=SOURCE_BUCKET)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--source-inventory", required=True, type=Path)
    init.add_argument("--target-inventory", required=True, type=Path)
    copy = sub.add_parser("copy")
    copy.add_argument("--limit", type=int, default=1000)
    copy.add_argument("--workers", type=int, default=16)
    copy.add_argument("--execute", action="store_true")
    copy.add_argument("--confirm", default="")
    verify = sub.add_parser("verify")
    verify.add_argument("--limit", type=int, default=1000)
    verify.add_argument("--workers", type=int, default=8)
    sub.add_parser("summary")
    delete = sub.add_parser("delete")
    delete.add_argument("--execute", action="store_true")
    delete.add_argument("--confirm", default="")
    args = parser.parse_args()

    if args.command == "init":
        initialize_state(args.state, args.source_inventory, args.target_inventory)
    elif args.command == "copy":
        _copy_pending(
            args.state,
            limit=args.limit,
            workers=args.workers,
            execute=args.execute,
            confirm=args.confirm,
        )
    elif args.command == "verify":
        _verify(args.state, limit=args.limit, workers=args.workers)
    elif args.command == "delete":
        _delete_verified_bucket(
            args.state, execute=args.execute, confirm=args.confirm
        )
    print(json.dumps(retirement_summary(args.state), indent=2))


if __name__ == "__main__":
    main()
