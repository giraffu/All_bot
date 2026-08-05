#!/usr/bin/env python3
"""Lease History media, copy it to NAS MinIO, verify, and post receipts.

The worker has no R2 delete operation by design.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import httpx


ARCHIVE_BUCKET = "allbot-media-archive-v1"
PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def clear_proxy_environment() -> None:
    for key in PROXY_KEYS:
        os.environ.pop(key, None)


def validate_direct_route(hostname: str) -> None:
    addresses = {
        item[4][0]
        for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    }
    if not addresses:
        raise RuntimeError(f"cannot resolve {hostname}")
    for address in addresses:
        route = subprocess.run(
            ["ip", "route", "get", address], capture_output=True, text=True, check=True
        ).stdout.lower()
        if any(marker in route for marker in ("tailscale", "tun0", "wg0", "127.0.0.1")):
            raise RuntimeError(
                f"non-physical route rejected for {hostname}: {route.strip()}"
            )


def _client(config: dict):
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config.get("region", "auto"),
        verify=config.get("ca_file", True),
        config=Config(
            signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}
        ),
    )


def _candidate_keys(source_ref: str, task_id: str | None) -> list[str]:
    parsed = urlparse(source_ref)
    raw = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    names = []
    if task_id:
        names.append(f"history/{task_id}/{Path(raw).name}")
    names.extend((raw, Path(raw).name))
    seen = set()
    return [name for name in names if name and not (name in seen or seen.add(name))]


def _extension(source_ref: str, content_type: str | None) -> str:
    suffix = Path(urlparse(source_ref).path).suffix.lower().lstrip(".")
    if suffix:
        return "jpg" if suffix == "jpeg" else suffix
    guessed = mimetypes.guess_extension(content_type or "") or ".bin"
    return guessed.lstrip(".")


def _blob_key(digest: str, extension: str) -> str:
    return f"blobs/sha256/{digest[:2]}/{digest[2:4]}/{digest}.{extension}"


class RateLimiter:
    def __init__(self, bytes_per_second: int):
        self.bytes_per_second = max(1, bytes_per_second)
        self.started = time.monotonic()
        self.bytes = 0

    def account(self, size: int) -> None:
        self.bytes += size
        expected = self.bytes / self.bytes_per_second
        delay = expected - (time.monotonic() - self.started)
        if delay > 0:
            time.sleep(delay)


def archive_one_asset(
    asset: dict,
    task_id: str | None,
    sources: list[dict],
    nas: dict,
    spool: Path,
    limit_bps: int,
) -> dict:
    nas_client = _client(nas)
    limiter = RateLimiter(limit_bps)
    last_error = "not found in any online source"
    with tempfile.NamedTemporaryFile(dir=spool, suffix=".part", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        found = None
        for source in sources:
            source_client = _client(source)
            for key in _candidate_keys(asset["source_ref"], task_id):
                try:
                    response = source_client.get_object(
                        Bucket=source["bucket"], Key=key
                    )
                except ClientError as exc:
                    code = str(exc.response.get("Error", {}).get("Code", ""))
                    if code in {"404", "NoSuchKey", "NotFound"}:
                        continue
                    last_error = f"{source['name']}:{code}"
                    break
                digest = hashlib.sha256()
                size = 0
                with temp_path.open("wb") as handle:
                    while chunk := response["Body"].read(8 * 1024 * 1024):
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                        limiter.account(len(chunk))
                found = (
                    source,
                    key,
                    digest.hexdigest(),
                    size,
                    response.get("ContentType"),
                )
                break
            if found:
                break
        if not found:
            raise FileNotFoundError(last_error)

        _source, _key, digest, size, content_type = found
        blob_key = _blob_key(digest, _extension(asset["source_ref"], content_type))
        nas_client.upload_file(
            str(temp_path),
            ARCHIVE_BUCKET,
            blob_key,
            ExtraArgs={
                "ContentType": content_type or "application/octet-stream",
                "Metadata": {"sha256": digest},
            },
        )
        verify = nas_client.get_object(Bucket=ARCHIVE_BUCKET, Key=blob_key)
        verified_hash = hashlib.sha256()
        verified_size = 0
        while chunk := verify["Body"].read(8 * 1024 * 1024):
            verified_hash.update(chunk)
            verified_size += len(chunk)
        if verified_size != size or verified_hash.hexdigest() != digest:
            raise RuntimeError("NAS read-back checksum mismatch")
        return {
            "role": asset["role"],
            "ordinal": asset["ordinal"],
            "source_ref": asset["source_ref"],
            "sha256": digest,
            "byte_size": size,
            "mime_type": content_type,
            "nas_bucket": ARCHIVE_BUCKET,
            "nas_key": blob_key,
            "verified_at": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
        }
    finally:
        temp_path.unlink(missing_ok=True)


async def run(args) -> int:
    clear_proxy_environment()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    for source in config["sources"]:
        validate_direct_route(urlparse(source["endpoint"]).hostname)
    spool = Path(config.get("spool_path", "/var/lib/allbot-media-archive/spool"))
    spool.mkdir(parents=True, exist_ok=True)
    max_spool = int(config.get("max_spool_bytes", 100 * 1024**3))
    if shutil.disk_usage(spool).free < min(max_spool, 10 * 1024**3):
        raise RuntimeError("archive spool has insufficient free space")

    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    async with httpx.AsyncClient(
        base_url=config["central_api"], headers=headers, timeout=60, trust_env=False
    ) as client:
        response = await client.get(
            "/api/internal/media-archive/jobs",
            params={"worker_id": args.worker_id, "limit": args.limit},
        )
        response.raise_for_status()
        jobs = response.json()["jobs"]
        semaphore = asyncio.Semaphore(args.concurrency)

        async def process(job):
            try:
                receipts = []
                for asset in job["assets"]:
                    async with semaphore:
                        receipts.append(
                            await asyncio.to_thread(
                                archive_one_asset,
                                asset,
                                job.get("task_id"),
                                config["sources"],
                                config["nas"],
                                spool,
                                int(
                                    config.get(
                                        "bandwidth_bytes_per_second", 20 * 1024**2
                                    )
                                )
                                // max(1, args.concurrency),
                            )
                        )
                result = await client.post(
                    "/api/internal/media-archive/receipts",
                    json={
                        "history_id": job["history_id"],
                        "worker_id": args.worker_id,
                        "receipts": receipts,
                    },
                )
                result.raise_for_status()
            except Exception as exc:
                await client.post(
                    "/api/internal/media-archive/failures",
                    json={
                        "history_id": job["history_id"],
                        "worker_id": args.worker_id,
                        "error_code": type(exc).__name__,
                        "message": str(exc)[:1000],
                        "retryable": not isinstance(exc, FileNotFoundError),
                    },
                )

        await asyncio.gather(*(process(job) for job in jobs))
    return len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        required=True,
        help="0600 JSON config containing source/NAS credentials",
    )
    parser.add_argument("--worker-id", default=socket.gethostname())
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    print(f"processed {asyncio.run(run(args))} archive jobs")


if __name__ == "__main__":
    main()
