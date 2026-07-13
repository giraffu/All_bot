#!/usr/bin/env python3
"""Import legacy/cold media into a local complete MinIO bucket.

The legacy buckets contain non-standard MinIO StorageClass metadata such as
ARCHIVE_18T. A plain S3-to-S3 copy can preserve that system metadata and make
the target MinIO reject PutObject/CopyObject with InvalidStorageClass. This
tool streams object bytes and writes them to the target without StorageClass.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import mimetypes
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


DEFAULT_COLD_ENDPOINT = "http://192.168.1.88:9002"
DEFAULT_TARGET_BUCKET = "user-data-complete-shadow"


@dataclass(frozen=True)
class S3Config:
    endpoint_url: str
    access_key: str
    secret_key: str
    secure: bool = False


@dataclass
class Counters:
    scanned: int = 0
    copied: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_copied: int = 0


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def bool_value(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_endpoint(endpoint: str, *, secure: bool) -> str:
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    scheme = "https" if secure else "http"
    return f"{scheme}://{endpoint}"


def build_s3_client(config: S3Config):
    return boto3.client(
        "s3",
        endpoint_url=normalize_endpoint(config.endpoint_url, secure=config.secure),
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name="us-east-1",
        config=Config(
            connect_timeout=10,
            read_timeout=120,
            retries={"max_attempts": 3, "mode": "standard"},
            max_pool_connections=64,
        ),
    )


def local_config(values: dict[str, str]) -> S3Config:
    return S3Config(
        endpoint_url=values["LOCAL_MINIO_ENDPOINT"],
        access_key=values["LOCAL_MINIO_ACCESS_KEY"],
        secret_key=values["LOCAL_MINIO_SECRET_KEY"],
        secure=bool_value(values.get("LOCAL_MINIO_SECURE"), default=False),
    )


def cold_config(values: dict[str, str]) -> S3Config:
    access_key = values.get("COLD_MINIO_ACCESS_KEY") or values.get("LEGACY_MINIO_ACCESS_KEY")
    secret_key = values.get("COLD_MINIO_SECRET_KEY") or values.get("LEGACY_MINIO_SECRET_KEY")
    if not access_key or not secret_key:
        raise SystemExit("Cold MinIO credentials are missing.")
    return S3Config(
        endpoint_url=values.get("COLD_MINIO_ENDPOINT", DEFAULT_COLD_ENDPOINT),
        access_key=access_key,
        secret_key=secret_key,
        secure=bool_value(values.get("COLD_MINIO_SECURE"), default=False),
    )


def object_exists(client, *, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError:
        client.create_bucket(Bucket=bucket)


def iter_s3_objects(client, bucket: str) -> Iterable[dict]:
    kwargs: dict[str, object] = {"Bucket": bucket, "MaxKeys": 1000}
    while True:
        response = client.list_objects_v2(**kwargs)
        for item in response.get("Contents", []):
            yield item
        if not response.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = response["NextContinuationToken"]


def iter_filesystem_objects(root: Path) -> Iterable[tuple[str, Path, int]]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        key = path.relative_to(root).as_posix()
        yield key, path, path.stat().st_size


def put_s3_object(
    *,
    source_client,
    target_client,
    source_bucket: str,
    target_bucket: str,
    key: str,
    skip_existing: bool,
) -> tuple[str, int]:
    if skip_existing and object_exists(target_client, bucket=target_bucket, key=key):
        return "skipped", 0
    source = source_client.get_object(Bucket=source_bucket, Key=key)
    length = int(source.get("ContentLength") or 0)
    content_type = source.get("ContentType") or "application/octet-stream"
    body = source["Body"]
    try:
        with tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024) as spool:
            shutil.copyfileobj(body, spool, length=1024 * 1024)
            spool.seek(0)
            target_client.put_object(
                Bucket=target_bucket,
                Key=key,
                Body=spool,
                ContentLength=length,
                ContentType=content_type,
            )
    finally:
        body.close()
    return "copied", length


def put_filesystem_object(
    *,
    target_client,
    target_bucket: str,
    key: str,
    path: Path,
    size: int,
    skip_existing: bool,
) -> tuple[str, int]:
    if skip_existing and object_exists(target_client, bucket=target_bucket, key=key):
        return "skipped", 0
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        target_client.put_object(
            Bucket=target_bucket,
            Key=key,
            Body=handle,
            ContentLength=size,
            ContentType=content_type,
        )
    return "copied", size


def print_progress(label: str, counters: Counters, start: float) -> None:
    elapsed = max(time.monotonic() - start, 0.001)
    gib = counters.bytes_copied / (1024**3)
    rate_mib = counters.bytes_copied / elapsed / (1024**2)
    print(
        f"{label}: scanned={counters.scanned} copied={counters.copied} "
        f"skipped={counters.skipped} failed={counters.failed} "
        f"copied_gib={gib:.3f} rate_mib_s={rate_mib:.2f}",
        flush=True,
    )


def run_s3_import(args, source_config: S3Config, target_config: S3Config) -> int:
    source_client = build_s3_client(source_config)
    target_client = build_s3_client(target_config)
    ensure_bucket(target_client, args.target_bucket)

    counters = Counters()
    start = time.monotonic()
    last_progress = start
    pending: set[concurrent.futures.Future] = set()
    failed_keys: list[str] = []

    def submit(pool, item):
        key = item["Key"]
        return pool.submit(
            put_s3_object,
            source_client=source_client,
            target_client=target_client,
            source_bucket=args.source_bucket,
            target_bucket=args.target_bucket,
            key=key,
            skip_existing=not args.overwrite,
        )

    def drain(done: Iterable[concurrent.futures.Future]) -> None:
        nonlocal last_progress
        for future in done:
            try:
                status, copied_bytes = future.result()
                if status == "copied":
                    counters.copied += 1
                    counters.bytes_copied += copied_bytes
                elif status == "skipped":
                    counters.skipped += 1
            except Exception as exc:  # noqa: BLE001 - keep import resumable.
                counters.failed += 1
                failed_keys.append(str(exc))
        now = time.monotonic()
        if now - last_progress >= args.progress_interval:
            print_progress(args.label, counters, start)
            last_progress = now

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for item in iter_s3_objects(source_client, args.source_bucket):
            counters.scanned += 1
            if args.limit and counters.scanned > args.limit:
                break
            if args.dry_run:
                counters.skipped += 1
                continue
            pending.add(submit(pool, item))
            if len(pending) >= max(args.workers * 4, 1):
                done, pending = concurrent.futures.wait(
                    pending,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                drain(done)
        while pending:
            done, pending = concurrent.futures.wait(
                pending,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            drain(done)

    print_progress(args.label, counters, start)
    if failed_keys:
        print(f"{args.label}: failed samples={failed_keys[:5]}", file=sys.stderr)
    return 1 if counters.failed else 0


def run_filesystem_import(args, target_config: S3Config) -> int:
    target_client = build_s3_client(target_config)
    ensure_bucket(target_client, args.target_bucket)

    counters = Counters()
    start = time.monotonic()
    last_progress = start
    pending: set[concurrent.futures.Future] = set()
    root = args.source_path.resolve()

    def drain(done: Iterable[concurrent.futures.Future]) -> None:
        nonlocal last_progress
        for future in done:
            try:
                status, copied_bytes = future.result()
                if status == "copied":
                    counters.copied += 1
                    counters.bytes_copied += copied_bytes
                elif status == "skipped":
                    counters.skipped += 1
            except Exception as exc:  # noqa: BLE001
                counters.failed += 1
                print(f"{args.label}: failed object: {exc}", file=sys.stderr, flush=True)
        now = time.monotonic()
        if now - last_progress >= args.progress_interval:
            print_progress(args.label, counters, start)
            last_progress = now

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, path, size in iter_filesystem_objects(root):
            counters.scanned += 1
            if args.limit and counters.scanned > args.limit:
                break
            if args.dry_run:
                counters.skipped += 1
                continue
            pending.add(
                pool.submit(
                    put_filesystem_object,
                    target_client=target_client,
                    target_bucket=args.target_bucket,
                    key=key,
                    path=path,
                    size=size,
                    skip_existing=not args.overwrite,
                )
            )
            if len(pending) >= max(args.workers * 4, 1):
                done, pending = concurrent.futures.wait(
                    pending,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                drain(done)
        while pending:
            done, pending = concurrent.futures.wait(
                pending,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            drain(done)

    print_progress(args.label, counters, start)
    return 1 if counters.failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-env-file", type=Path, default=Path(".env.cloud-prod-shadow-sync.local"))
    parser.add_argument("--cold-env-file", type=Path, default=Path(".env.cloud.prod"))
    parser.add_argument("--source", choices=["local", "cold", "filesystem"], required=True)
    parser.add_argument("--source-bucket", default="bot-data")
    parser.add_argument("--source-path", type=Path)
    parser.add_argument("--target-bucket", default=DEFAULT_TARGET_BUCKET)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--progress-interval", type=int, default=60)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--label", default="import")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    args.dry_run = not args.execute
    if args.source == "filesystem" and args.source_path is None:
        parser.error("--source-path is required for filesystem imports")
    return args


def main() -> int:
    args = parse_args()
    target_values = load_env(args.target_env_file)
    target_config = local_config(target_values)
    if args.source == "filesystem":
        return run_filesystem_import(args, target_config)
    if args.source == "local":
        source_config = target_config
    else:
        source_config = cold_config(load_env(args.cold_env_file))
    return run_s3_import(args, source_config, target_config)


if __name__ == "__main__":
    raise SystemExit(main())
