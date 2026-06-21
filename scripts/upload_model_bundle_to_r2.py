#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402


class UploadProgress:
    def __init__(self, label: str, total_size: int, *, step_bytes: int = 1024 * 1024 * 1024):
        self.label = label
        self.total_size = total_size
        self.step_bytes = step_bytes
        self.transferred = 0
        self.last_reported = 0

    def __call__(self, amount: int) -> None:
        self.transferred += amount
        if (
            self.transferred - self.last_reported >= self.step_bytes
            or self.transferred >= self.total_size
        ):
            self.last_reported = self.transferred
            print(
                f"[model-r2-upload] {self.label}: {self.transferred}/{self.total_size} bytes",
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
        raise RuntimeError("R2_ENDPOINT or MINIO_ENDPOINT is required")
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
        raise RuntimeError("R2_ACCESS_KEY/R2_SECRET_KEY or MINIO_ACCESS_KEY/MINIO_SECRET_KEY is required")
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(endpoint, secure),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.getenv("R2_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )


def _safe_client_error(exc: ClientError) -> str:
    code = exc.response.get("Error", {}).get("Code", "unknown")
    message = exc.response.get("Error", {}).get("Message", "")
    return f"{code}: {message}".strip()


def _head_bucket(client, bucket: str) -> bool:
    try:
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchBucket", "NotFound"}:
            return False
        raise RuntimeError(f"head_bucket failed for {bucket}: {_safe_client_error(exc)}") from exc


def _head_object(client, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise RuntimeError(f"head_object failed for {key}: {_safe_client_error(exc)}") from exc


def _metadata_value(metadata: dict[str, Any] | None, key: str) -> str:
    if not metadata:
        return ""
    for metadata_key, value in metadata.items():
        if str(metadata_key).lower() == key.lower():
            return str(value)
    return ""


def _build_r2_manifest(
    *,
    manifest: dict[str, Any],
    prefix: str,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict[str, Any]:
    files = []
    total_size = 0
    for item in manifest.get("files", []):
        relative_path = str(item["relative_path"]).lstrip("/")
        if not _path_included(
            relative_path,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        ):
            continue
        size_bytes = int(item["size_bytes"])
        total_size += size_bytes
        files.append(
            {
                "relative_path": relative_path,
                "sha256": str(item["sha256"]),
                "size_bytes": size_bytes,
                "key": f"{prefix.rstrip('/')}/models/{relative_path}",
            }
        )
    return {
        "bundle": manifest.get("bundle"),
        "version": manifest.get("version"),
        "profiles": manifest.get("profiles") or [],
        "source": manifest.get("source") or {},
        "total_size_bytes": total_size,
        "file_count": len(files),
        "files": files,
    }


def _build_r2_manifest_from_manifests(
    *,
    manifests: list[dict[str, Any]],
    prefix: str,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict[str, Any]:
    files_by_path: dict[str, dict[str, Any]] = {}
    bundle_refs = []
    sources = []
    for manifest in manifests:
        bundle_refs.append(
            {
                "bundle": manifest.get("bundle"),
                "version": manifest.get("version"),
                "profiles": manifest.get("profiles") or [],
            }
        )
        if manifest.get("source"):
            sources.append(manifest["source"])
        for item in manifest.get("files", []):
            relative_path = str(item["relative_path"]).lstrip("/")
            if not _path_included(
                relative_path,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
            ):
                continue
            size_bytes = int(item["size_bytes"])
            sha256 = str(item["sha256"])
            existing = files_by_path.get(relative_path)
            if existing:
                if existing["sha256"] != sha256 or int(existing["size_bytes"]) != size_bytes:
                    raise RuntimeError(
                        "conflicting model bundle entries for "
                        f"{relative_path}: {existing['sha256']} vs {sha256}"
                    )
                continue
            files_by_path[relative_path] = {
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "key": f"{prefix.rstrip('/')}/models/{relative_path}",
            }
    files = sorted(files_by_path.values(), key=lambda item: item["relative_path"])
    return {
        "bundle": "union",
        "version": ",".join(
            sorted({str(item.get("version") or "") for item in bundle_refs if item.get("version")})
        ),
        "bundles": bundle_refs,
        "source": {"sources": sources},
        "total_size_bytes": sum(int(item["size_bytes"]) for item in files),
        "file_count": len(files),
        "files": files,
    }


def _split_patterns(patterns: list[str] | None) -> list[str]:
    result: list[str] = []
    for raw in patterns or []:
        result.extend(part.strip() for part in raw.split(",") if part.strip())
    return result


def _path_included(
    relative_path: str,
    *,
    include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
) -> bool:
    includes = _split_patterns(include_patterns)
    excludes = _split_patterns(exclude_patterns)
    if includes and not any(fnmatch.fnmatch(relative_path, pattern) for pattern in includes):
        return False
    return not any(fnmatch.fnmatch(relative_path, pattern) for pattern in excludes)


def upload_bundle(
    *,
    repo_root: Path,
    bundle: str | None = None,
    bundles: list[str] | None = None,
    version: str,
    bucket: str,
    prefix: str,
    execute: bool,
    create_bucket: bool,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    skip_manifest: bool = False,
    max_concurrency: int = 4,
    max_bandwidth_mbps: float | None = None,
    allow_missing_local: bool = False,
    client=None,
) -> dict[str, Any]:
    registry = ModelRegistry(repo_root)
    selected_bundles = list(bundles or ([bundle] if bundle else []))
    if not selected_bundles:
        raise RuntimeError("at least one model bundle is required")
    manifests = [
        registry.load_manifest(selected_bundle, version)
        for selected_bundle in selected_bundles
    ]
    r2_manifest = _build_r2_manifest_from_manifests(
        manifests=manifests,
        prefix=prefix,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )
    manifest_key = f"{prefix.rstrip('/')}/manifest.json"
    client = client or _r2_client()

    bucket_exists = _head_bucket(client, bucket)
    created_bucket = False
    if not bucket_exists:
        if not create_bucket:
            raise RuntimeError(f"R2 bucket does not exist: {bucket}")
        if execute:
            client.create_bucket(Bucket=bucket)
        created_bucket = execute

    uploads: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    missing_local_blobs: list[dict[str, Any]] = []
    transfer_config = TransferConfig(
        max_concurrency=max_concurrency,
        max_bandwidth=(
            int(max_bandwidth_mbps * 1024 * 1024 / 8)
            if max_bandwidth_mbps and max_bandwidth_mbps > 0
            else None
        ),
    )
    for item in r2_manifest["files"]:
        key = item["key"]
        size_bytes = int(item["size_bytes"])
        sha256 = str(item["sha256"])
        source = registry.blob_path(sha256)
        existing = _head_object(client, bucket=bucket, key=key) if bucket_exists or created_bucket else None
        existing_sha = ""
        if existing:
            existing_sha = _metadata_value(existing.get("Metadata"), "sha256")
        if existing and int(existing.get("ContentLength") or 0) == size_bytes and existing_sha == sha256:
            skipped.append({"key": key, "relative_path": item["relative_path"], "size_bytes": size_bytes})
            continue
        if not source.exists():
            missing_local_blobs.append(
                {
                    "key": key,
                    "relative_path": item["relative_path"],
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "local_blob": str(source),
                }
            )
            continue
        uploads.append(
            {
                "key": key,
                "relative_path": item["relative_path"],
                "sha256": sha256,
                "size_bytes": size_bytes,
                "source": str(source),
            }
        )

    if missing_local_blobs and execute and not allow_missing_local:
        raise RuntimeError(
            "missing local registry blobs for "
            f"{len(missing_local_blobs)} model object(s); use transfer pods first"
        )
    if missing_local_blobs and execute and allow_missing_local and not skip_manifest:
        raise RuntimeError("missing local blobs require --skip-manifest before partial execute")

    if execute:
        for item in uploads:
            client.upload_file(
                item["source"],
                bucket,
                item["key"],
                ExtraArgs={
                    "ContentType": "application/octet-stream",
                    "Metadata": {
                        "sha256": item["sha256"],
                        "relative-path": str(item["relative_path"]),
                    },
                },
                Callback=UploadProgress(str(item["relative_path"]), int(item["size_bytes"])),
                Config=transfer_config,
            )

    manifest_needs_upload = False
    if not skip_manifest:
        manifest_bytes = json.dumps(r2_manifest, ensure_ascii=False, indent=2).encode("utf-8")
        manifest_existing = _head_object(client, bucket=bucket, key=manifest_key) if bucket_exists or created_bucket else None
        manifest_needs_upload = True
        if manifest_existing and int(manifest_existing.get("ContentLength") or 0) == len(manifest_bytes):
            manifest_needs_upload = False
        if execute and manifest_needs_upload:
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=manifest_bytes,
                ContentType="application/json",
                Metadata={"bundle": ",".join(selected_bundles), "version": version},
            )

    return {
        "ok": True,
        "dry_run": not execute,
        "bucket": bucket,
        "bucket_exists": bucket_exists,
        "bucket_created": created_bucket,
        "prefix": prefix,
        "manifest_key": manifest_key,
        "bundles": selected_bundles,
        "bundle_count": len(selected_bundles),
        "file_count": r2_manifest["file_count"],
        "total_size_bytes": r2_manifest["total_size_bytes"],
        "upload_count": len(uploads),
        "skipped_existing_count": len(skipped),
        "missing_local_blob_count": len(missing_local_blobs),
        "skip_manifest": skip_manifest,
        "manifest_upload": manifest_needs_upload,
        "max_concurrency": max_concurrency,
        "max_bandwidth_mbps": max_bandwidth_mbps,
        "uploads": uploads,
        "skipped_existing": skipped,
        "missing_local_blobs": missing_local_blobs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload an AllBot model bundle manifest/blobs to R2")
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    parser.add_argument(
        "--bundle",
        action="append",
        default=None,
        help="Model bundle to include. Repeat for a union manifest.",
    )
    parser.add_argument("--version", default="2026-06-10")
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument(
        "--include-pattern",
        action="append",
        default=[],
        help="Only include relative model paths matching this glob; can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=[],
        help="Exclude relative model paths matching this glob; can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--skip-manifest",
        action="store_true",
        help="Upload matching objects only. Use this for partial uploads before the full bundle is complete.",
    )
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-bandwidth-mbps", type=float, default=None)
    parser.add_argument(
        "--allow-missing-local",
        action="store_true",
        help="Allow execute to upload available local blobs only; requires --skip-manifest.",
    )
    parser.add_argument("--create-bucket", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_env_file(args.env_file)
    bundles = args.bundle or ["img2img_lora_baseline"]
    bucket = args.bucket or os.getenv("RUNPOD_MODEL_BUCKET") or "allbot-model-cache-test"
    prefix = args.prefix or os.getenv("RUNPOD_MODEL_PREFIX") or "img2img_lora/2026-06-10"
    try:
        payload = upload_bundle(
            repo_root=args.repo_root,
            bundles=bundles,
            version=args.version,
            bucket=bucket,
            prefix=prefix,
            execute=args.execute,
            create_bucket=args.create_bucket,
            include_patterns=args.include_pattern,
            exclude_patterns=args.exclude_pattern,
            skip_manifest=args.skip_manifest,
            max_concurrency=args.max_concurrency,
            max_bandwidth_mbps=args.max_bandwidth_mbps,
            allow_missing_local=args.allow_missing_local,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
