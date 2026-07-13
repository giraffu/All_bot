#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import yaml
from botocore.config import Config
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "ops/gpu_pool_controller/config/model_bundles.yml"
DEFAULT_BUNDLE = "pornmaster_flux2_edit_baseline"
DEFAULT_PREFIX = "pornmaster_flux2_edit/2026-06-27"
DEFAULT_BUCKET = "allbot-model-cache"


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
        raise RuntimeError("RUNPOD_MODEL_ENDPOINT, R2_ENDPOINT, or MINIO_ENDPOINT is required")
    if "://" in endpoint:
        parsed = urlparse(endpoint)
        if not parsed.netloc:
            raise RuntimeError("invalid model endpoint")
        return endpoint.rstrip("/")
    return f"{'https' if secure else 'http'}://{endpoint}"


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
    if not access_key or not secret_key:
        raise RuntimeError(
            "RUNPOD_MODEL_ACCESS_KEY/RUNPOD_MODEL_SECRET_KEY or R2/MINIO credentials are required"
        )
    secure = _bool_env(
        os.getenv("RUNPOD_MODEL_SECURE") or os.getenv("MINIO_SECURE"),
        default=True,
    )
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


def _load_bundle(config_path: Path, bundle_id: str) -> dict[str, Any]:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    bundles = payload.get("bundles") or {}
    bundle = bundles.get(bundle_id)
    if not isinstance(bundle, dict):
        raise RuntimeError(f"model bundle not found: {bundle_id}")
    files = bundle.get("files") or []
    if not files:
        raise RuntimeError(f"model bundle has no files: {bundle_id}")
    return dict(bundle)


def _manifest_from_bundle(
    *,
    bundle_id: str,
    bundle: dict[str, Any],
    prefix: str,
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    total_size = 0
    for item in bundle.get("files") or []:
        relative_path = str(item["relative_path"]).lstrip("/")
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
        "bundle": bundle_id,
        "version": str(bundle.get("version") or ""),
        "profiles": bundle.get("profiles") or [],
        "source": bundle.get("source") or {},
        "total_size_bytes": total_size,
        "file_count": len(files),
        "files": files,
    }


def _metadata_value(metadata: dict[str, Any] | None, key: str) -> str:
    if not metadata:
        return ""
    for metadata_key, value in metadata.items():
        if str(metadata_key).lower() == key.lower():
            return str(value)
    return ""


def _head_object(client: Any, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise RuntimeError(f"head_object failed for {key}: {_safe_client_error(exc)}") from exc


def validate_manifest_objects(
    client: Any,
    *,
    bucket: str,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for item in manifest["files"]:
        key = str(item["key"])
        expected_size = int(item["size_bytes"])
        expected_sha256 = str(item["sha256"])
        head = _head_object(client, bucket=bucket, key=key)
        if head is None:
            checks.append(
                {
                    "key": key,
                    "ok": False,
                    "reason": "missing",
                    "expected_size_bytes": expected_size,
                    "expected_sha256": expected_sha256,
                }
            )
            continue
        actual_size = int(head.get("ContentLength") or 0)
        actual_sha256 = _metadata_value(head.get("Metadata") or {}, "sha256")
        reason = ""
        if actual_size != expected_size:
            reason = "size_mismatch"
        elif actual_sha256.lower() != expected_sha256.lower():
            reason = "sha256_metadata_mismatch"
        checks.append(
            {
                "key": key,
                "ok": not bool(reason),
                "reason": reason or "ok",
                "expected_size_bytes": expected_size,
                "actual_size_bytes": actual_size,
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
            }
        )
    return checks


def publish_manifest(
    client: Any,
    *,
    bucket: str,
    manifest_key: str,
    manifest: dict[str, Any],
) -> None:
    body = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")
    metadata = {
        "bundle": str(manifest.get("bundle") or ""),
        "version": str(manifest.get("version") or ""),
        "profile": ",".join(str(item) for item in manifest.get("profiles") or []),
    }
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=body,
        ContentType="application/json",
        Metadata=metadata,
    )


def build_summary(
    *,
    bucket: str,
    prefix: str,
    manifest_key: str,
    manifest: dict[str, Any],
    checks: list[dict[str, Any]],
    execute: bool,
    uploaded: bool,
) -> dict[str, Any]:
    return {
        "ok": all(item["ok"] for item in checks),
        "dry_run": not execute,
        "uploaded": uploaded,
        "bucket": bucket,
        "prefix": prefix,
        "manifest_key": manifest_key,
        "file_count": manifest["file_count"],
        "total_size_bytes": manifest["total_size_bytes"],
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and publish the PornMaster Flux2 edit R2 model manifest."
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.test"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--manifest-key", default=f"{DEFAULT_PREFIX}/manifest.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_env_file(args.env_file)
    try:
        bundle = _load_bundle(args.config, args.bundle)
        manifest = _manifest_from_bundle(
            bundle_id=args.bundle,
            bundle=bundle,
            prefix=args.prefix,
        )
        client = _r2_client()
        checks = validate_manifest_objects(
            client,
            bucket=args.bucket,
            manifest=manifest,
        )
        if args.execute and all(item["ok"] for item in checks):
            publish_manifest(
                client,
                bucket=args.bucket,
                manifest_key=args.manifest_key,
                manifest=manifest,
            )
            uploaded = True
        else:
            uploaded = False
        print(
            json.dumps(
                build_summary(
                    bucket=args.bucket,
                    prefix=args.prefix,
                    manifest_key=args.manifest_key,
                    manifest=manifest,
                    checks=checks,
                    execute=args.execute,
                    uploaded=uploaded,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    return 0 if all(item["ok"] for item in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
