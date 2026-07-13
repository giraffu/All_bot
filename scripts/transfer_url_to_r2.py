#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class TransferProgress:
    def __init__(self, label: str, total_size: int | None, *, step_bytes: int = 1024 * 1024 * 1024):
        self.label = label
        self.total_size = total_size
        self.step_bytes = step_bytes
        self.transferred = 0
        self.last_reported = 0

    def add(self, amount: int) -> None:
        self.transferred += amount
        if (
            self.transferred - self.last_reported >= self.step_bytes
            or (self.total_size is not None and self.transferred >= self.total_size)
        ):
            self.last_reported = self.transferred
            suffix = f"/{self.total_size}" if self.total_size is not None else ""
            print(
                f"[url-r2-transfer] {self.label}: {self.transferred}{suffix} bytes",
                file=sys.stderr,
                flush=True,
            )


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _endpoint_url(raw_endpoint: str, secure: bool) -> str:
    endpoint = raw_endpoint.strip()
    if not endpoint:
        raise RuntimeError("RUNPOD_MODEL_ENDPOINT/R2_ENDPOINT/MINIO_ENDPOINT is required")
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        if not parsed.netloc:
            raise RuntimeError("invalid R2 endpoint")
        return endpoint.rstrip("/")
    scheme = "https" if secure else "http"
    return f"{scheme}://{endpoint}"


def _r2_client():
    endpoint = (
        os.getenv("RUNPOD_MODEL_ENDPOINT")
        or os.getenv("R2_ENDPOINT")
        or os.getenv("MINIO_ENDPOINT")
        or ""
    )
    access_key = (
        os.getenv("RUNPOD_MODEL_ACCESS_KEY")
        or os.getenv("R2_ACCESS_KEY")
        or os.getenv("MINIO_ACCESS_KEY")
        or ""
    )
    secret_key = (
        os.getenv("RUNPOD_MODEL_SECRET_KEY")
        or os.getenv("R2_SECRET_KEY")
        or os.getenv("MINIO_SECRET_KEY")
        or ""
    )
    secure = _bool_env(
        os.getenv("RUNPOD_MODEL_SECURE") or os.getenv("MINIO_SECURE"),
        default=True,
    )
    if not access_key or not secret_key:
        raise RuntimeError("RUNPOD_MODEL_ACCESS_KEY/RUNPOD_MODEL_SECRET_KEY is required")
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(endpoint, secure),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("R2_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )


def _head_object(client, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        message = exc.response.get("Error", {}).get("Message", "")
        raise RuntimeError(f"head_object failed for {key}: {code}: {message}") from exc


def _read_source_url(*, env_name: str, url_stdin: bool) -> str:
    if env_name and os.getenv(env_name):
        return os.environ[env_name].strip()
    if url_stdin or not sys.stdin.isatty():
        return sys.stdin.readline().strip()
    raise RuntimeError(f"source URL is required via ${env_name} or --url-stdin")


def _content_size_from_headers(status: int, headers: dict[str, str]) -> int | None:
    content_range = headers.get("content-range", "")
    match = re.search(r"/(\d+)$", content_range)
    if match:
        return int(match.group(1))
    if status == 200 and headers.get("content-length"):
        return int(headers["content-length"])
    return None


def probe_url(source_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        source_url,
        method="GET",
        headers={"Range": "bytes=0-0", "User-Agent": "AllBotModelTransfer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        headers = {key.lower(): value for key, value in response.headers.items()}
        return {
            "status": response.status,
            "content_size": _content_size_from_headers(response.status, headers),
            "content_length": headers.get("content-length"),
            "content_range": headers.get("content-range"),
            "content_disposition_present": bool(headers.get("content-disposition")),
        }


def transfer_url_to_r2(
    *,
    source_url: str,
    bucket: str,
    key: str,
    expected_sha256: str,
    expected_size: int | None,
    relative_path: str,
    part_size: int,
    execute: bool,
    content_type: str,
) -> dict[str, Any]:
    client = _r2_client()
    existing = _head_object(client, bucket=bucket, key=key)
    existing_sha = ""
    if existing:
        existing_sha = str((existing.get("Metadata") or {}).get("sha256") or "")
    if (
        existing
        and expected_size is not None
        and int(existing.get("ContentLength") or 0) == expected_size
        and existing_sha == expected_sha256
    ):
        return {
            "ok": True,
            "dry_run": not execute,
            "skipped_existing": True,
            "bucket": bucket,
            "key": key,
            "size_bytes": expected_size,
            "sha256": expected_sha256,
        }

    probe = probe_url(source_url)
    remote_size = probe.get("content_size")
    if expected_size is not None and remote_size is not None and int(remote_size) != expected_size:
        raise RuntimeError(f"remote size mismatch: expected {expected_size}, got {remote_size}")

    if not execute:
        return {
            "ok": True,
            "dry_run": True,
            "skipped_existing": False,
            "bucket": bucket,
            "key": key,
            "expected_size_bytes": expected_size,
            "remote_size_bytes": remote_size,
            "sha256": expected_sha256,
        }

    upload_id = ""
    parts: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    transferred = 0
    progress = TransferProgress(relative_path or key, expected_size or remote_size)
    try:
        create_resp = client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=content_type,
            Metadata={
                "sha256": expected_sha256,
                "relative-path": relative_path,
                "source": "external-url",
            },
        )
        upload_id = create_resp["UploadId"]
        request = urllib.request.Request(
            source_url,
            method="GET",
            headers={"User-Agent": "AllBotModelTransfer/1.0"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            part_number = 1
            while True:
                chunk = response.read(part_size)
                if not chunk:
                    break
                transferred += len(chunk)
                digest.update(chunk)
                part_resp = client.upload_part(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": part_resp["ETag"]})
                progress.add(len(chunk))
                part_number += 1

        actual_sha = digest.hexdigest()
        if expected_size is not None and transferred != expected_size:
            raise RuntimeError(f"download size mismatch: expected {expected_size}, got {transferred}")
        if actual_sha != expected_sha256:
            raise RuntimeError(f"sha256 mismatch: expected {expected_sha256}, got {actual_sha}")

        client.complete_multipart_upload(
            Bucket=bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        return {
            "ok": True,
            "dry_run": False,
            "skipped_existing": False,
            "bucket": bucket,
            "key": key,
            "size_bytes": transferred,
            "sha256": actual_sha,
            "part_count": len(parts),
        }
    except BaseException:
        if upload_id:
            try:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
            except Exception:
                pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream an external model URL into R2 without local staging")
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument("--url-env", default="RUNPOD_MODEL_SOURCE_URL")
    parser.add_argument("--url-stdin", action="store_true")
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--key", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--size-bytes", type=int, default=None)
    parser.add_argument("--part-size-mib", type=int, default=64)
    parser.add_argument("--content-type", default="application/octet-stream")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_env_file(args.env_file)
    bucket = args.bucket or os.getenv("RUNPOD_MODEL_BUCKET") or "allbot-model-cache-test"
    try:
        source_url = _read_source_url(env_name=args.url_env, url_stdin=args.url_stdin)
        payload = transfer_url_to_r2(
            source_url=source_url,
            bucket=bucket,
            key=args.key,
            expected_sha256=args.sha256,
            expected_size=args.size_bytes,
            relative_path=args.relative_path,
            part_size=args.part_size_mib * 1024 * 1024,
            execute=args.execute,
            content_type=args.content_type,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
