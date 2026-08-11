#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ops.gpu_pool_controller.model_repo import ModelRegistry  # noqa: E402
from ops.gpu_pool_controller.runpod_video_manifests import (  # noqa: E402
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    split_wan22_aio_manifest,
)  # noqa: E402
from upload_model_bundle_to_r2 import UploadProgress  # noqa: E402


DEFAULT_ENDPOINT = "http://192.168.1.115:9010"
DEFAULT_BUCKET = "allbot-model-cache"
DEFAULT_ENV_FILE = Path(".env.lan.model-cache")
SHARED_OBJECT_PREFIX = "models/by-sha256"


@dataclass(frozen=True)
class TargetSpec:
    name: str
    prefix: str
    manifest_key: str
    bundle_versions: tuple[tuple[str, str], ...]
    version: str | None = None


DEFAULT_BASE_TARGETS: tuple[TargetSpec, ...] = (
    TargetSpec(
        name="img2img_lora",
        prefix="img2img_lora/2026-06-10",
        manifest_key="img2img_lora/2026-06-10/manifest.json",
        bundle_versions=(("img2img_lora_baseline", "2026-06-10"),),
    ),
    TargetSpec(
        name="i2i_pro",
        prefix="i2i_pro/2026-06-14-test",
        manifest_key="i2i_pro/2026-06-14-test/manifest.json",
        bundle_versions=(("i2i_pro_baseline", "2026-06-14-test"),),
    ),
    TargetSpec(
        name="pornmaster_flux2_edit_bf16",
        prefix="pornmaster_flux2_edit_bf16/2026-07-12",
        manifest_key="pornmaster_flux2_edit_bf16/2026-07-12/manifest.json",
        bundle_versions=(("pornmaster_flux2_edit_bf16_baseline", "2026-07-12"),),
    ),
    TargetSpec(
        name="ltx_video",
        prefix="ltx_video/2026-06-10",
        manifest_key="ltx_video/2026-06-10/manifest.json",
        bundle_versions=(("ltx_video_baseline", "2026-06-10"),),
    ),
    TargetSpec(
        name="face_i2i_t2i",
        prefix="face_i2i_t2i/2026-06-10",
        manifest_key="face_i2i_t2i/2026-06-10/manifest.json",
        bundle_versions=(
            ("face_i2i_t2i_baseline", "2026-06-10"),
            ("video_basic_baseline", "2026-06-10"),
        ),
    ),
    TargetSpec(
        name="wan22_aio_video",
        prefix="wan22_aio_video/2026-07-18-lora5",
        manifest_key=RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
        bundle_versions=(
            ("video_basic_baseline", "2026-06-10"),
            ("wan22_video_v2_baseline", "2026-06-10"),
            ("wan22_explicit_lora_library", "2026-07-18"),
        ),
        version="2026-07-18-lora5",
    ),
)

OPTIONAL_TARGETS: tuple[TargetSpec, ...] = (
    TargetSpec(
        name="face_swap",
        prefix="face_swap_v2/2026-07-25",
        manifest_key="face_swap_v2/2026-07-25/manifest.json",
        bundle_versions=(("face_swap_v2_baseline", "2026-07-25"),),
    ),
    TargetSpec(
        name="ltx_t2v",
        prefix="ltx_t2v/2026-08-01-comfy-fast",
        manifest_key="ltx_t2v/2026-08-01-comfy-fast/manifest.json",
        bundle_versions=(("ltx_t2v_runtime", "2026-08-01-comfy-fast"),),
    ),
    TargetSpec(
        name="ltx_unified",
        prefix="ltx_unified/2026-08-03-10eros-v14-runexx-msr",
        manifest_key="ltx_unified/2026-08-03-10eros-v14-runexx-msr/manifest.json",
        bundle_versions=(("ltx_unified_runtime", "2026-08-03-10eros-v14-runexx-msr"),),
    ),
    TargetSpec(
        name="minimax_h3",
        prefix="minimax_h3/2026-08-11-hmnsfw-v2-anatomy-v05-lightx2v4",
        manifest_key="minimax_h3/2026-08-11-hmnsfw-v2-anatomy-v05-lightx2v4/manifest.json",
        bundle_versions=(("minimax_h3_runtime", "2026-08-11-hmnsfw-v2-anatomy-v05-lightx2v4"),),
    ),
)
TARGETS_BY_NAME = {
    target.name: target for target in (*DEFAULT_BASE_TARGETS, *OPTIONAL_TARGETS)
}


def _bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_client_error(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") if isinstance(response, dict) else {}
    code = error.get("Code", "unknown") if isinstance(error, dict) else "unknown"
    message = error.get("Message", "") if isinstance(error, dict) else ""
    return f"{code}: {message}".strip()


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") if isinstance(response, dict) else {}
    if isinstance(error, dict):
        return str(error.get("Code") or "")
    return ""


def _load_lan_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    allowed = {"LAN_MODEL_CACHE_ACCESS_KEY", "LAN_MODEL_CACHE_SECRET_KEY"}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("\"'")


def _lan_client(*, endpoint: str):
    access_key = os.getenv("LAN_MODEL_CACHE_ACCESS_KEY", "")
    secret_key = os.getenv("LAN_MODEL_CACHE_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise RuntimeError(
            "LAN_MODEL_CACHE_ACCESS_KEY/LAN_MODEL_CACHE_SECRET_KEY is required"
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint.rstrip("/"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _head_bucket(client, bucket: str) -> bool:
    try:
        client.head_bucket(Bucket=bucket)
        return True
    except ClientError as exc:
        code = _client_error_code(exc)
        if code in {"404", "NoSuchBucket", "NotFound"}:
            return False
        raise RuntimeError(
            f"head_bucket failed for {bucket}: {_safe_client_error(exc)}"
        ) from exc


def _head_object(client, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = _client_error_code(exc)
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise RuntimeError(
            f"head_object failed for {key}: {_safe_client_error(exc)}"
        ) from exc


def _metadata_value(metadata: dict[str, Any] | None, key: str) -> str:
    for metadata_key, value in (metadata or {}).items():
        if str(metadata_key).lower() == key.lower():
            return str(value)
    return ""


def _list_objects(client, *, bucket: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    token = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        objects.extend(page.get("Contents") or [])
        if not page.get("IsTruncated"):
            return objects
        token = page.get("NextContinuationToken")


def _read_json_object(client, *, bucket: str, key: str) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    return json.loads(body.decode("utf-8") if isinstance(body, bytes) else str(body))


def _shared_object_key(sha256: str) -> str:
    return f"{SHARED_OBJECT_PREFIX}/{sha256[:2]}/{sha256}"


def _gib(size_bytes: int) -> float:
    return round(size_bytes / 1024**3, 2)


def _build_union_manifest(
    *,
    registry: ModelRegistry,
    target: TargetSpec,
) -> dict[str, Any]:
    bundle_refs = []
    sources = []
    files_by_path: dict[str, dict[str, Any]] = {}
    for bundle, version in target.bundle_versions:
        manifest = registry.load_manifest(bundle, version)
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
            size_bytes = int(item["size_bytes"])
            sha256 = str(item["sha256"])
            existing = files_by_path.get(relative_path)
            if existing:
                if (
                    existing["sha256"] != sha256
                    or int(existing["size_bytes"]) != size_bytes
                ):
                    raise RuntimeError(
                        "conflicting model bundle entries for "
                        f"{relative_path}: {existing['sha256']} vs {sha256}"
                    )
                continue
            files_by_path[relative_path] = {
                "relative_path": relative_path,
                "sha256": sha256,
                "size_bytes": size_bytes,
            }
    files = sorted(files_by_path.values(), key=lambda item: item["relative_path"])
    version = target.version or ",".join(
        sorted({item["version"] for item in bundle_refs if item.get("version")})
    )
    return {
        "bundle": "union",
        "version": version,
        "bundles": bundle_refs,
        "source": {"sources": sources},
        "total_size_bytes": sum(int(item["size_bytes"]) for item in files),
        "file_count": len(files),
        "files": files,
    }


def _load_existing_sha_index(client, *, bucket: str) -> dict[str, str]:
    existing_by_sha: dict[str, str] = {}
    for item in _list_objects(client, bucket=bucket):
        key = str(item.get("Key") or "")
        if not key.endswith("/manifest.json"):
            continue
        try:
            manifest = _read_json_object(client, bucket=bucket, key=key)
        except Exception:
            continue
        for file_info in manifest.get("files") or []:
            object_key = str(
                file_info.get("key") or file_info.get("object_key") or ""
            ).strip("/")
            sha256 = str(file_info.get("sha256") or "")
            size_bytes = int(file_info.get("size_bytes") or 0)
            if not object_key or not sha256 or sha256 in existing_by_sha:
                continue
            head = _head_object(client, bucket=bucket, key=object_key)
            if not head:
                continue
            metadata_sha = _metadata_value(head.get("Metadata"), "sha256")
            if (
                int(head.get("ContentLength") or 0) == size_bytes
                and metadata_sha == sha256
            ):
                existing_by_sha[sha256] = object_key
    return existing_by_sha


def _assign_object_keys(
    manifest: dict[str, Any], *, existing_by_sha: dict[str, str]
) -> dict[str, Any]:
    updated = dict(manifest)
    files = []
    for file_info in manifest.get("files") or []:
        item = dict(file_info)
        sha256 = str(item["sha256"])
        item["key"] = existing_by_sha.get(sha256) or _shared_object_key(sha256)
        files.append(item)
    updated["files"] = files
    return updated


def build_target_manifests(
    *,
    registry: ModelRegistry,
    existing_by_sha: dict[str, str],
    targets: tuple[TargetSpec, ...] = DEFAULT_BASE_TARGETS,
) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for target in targets:
        manifest = _build_union_manifest(registry=registry, target=target)
        manifests[target.manifest_key] = _assign_object_keys(
            manifest,
            existing_by_sha=existing_by_sha,
        )

    aio = manifests.get(RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY)
    if aio is not None:
        split_manifests = split_wan22_aio_manifest(aio)
        manifests[RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY] = split_manifests[
            "image_to_video"
        ]
        manifests[RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY] = split_manifests[
            "wan22_video_v2"
        ]
    return dict(sorted(manifests.items()))


def _unique_model_entries(
    manifests: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for manifest_key, manifest in manifests.items():
        for item in manifest.get("files") or []:
            sha256 = str(item["sha256"])
            existing = entries.get(sha256)
            if existing:
                if int(existing["size_bytes"]) != int(item["size_bytes"]):
                    raise RuntimeError(f"conflicting size for model sha256 {sha256}")
                existing["manifest_keys"].append(manifest_key)
                existing["relative_paths"].append(str(item["relative_path"]))
                continue
            entries[sha256] = {
                "sha256": sha256,
                "size_bytes": int(item["size_bytes"]),
                "key": str(item["key"]),
                "relative_paths": [str(item["relative_path"])],
                "manifest_keys": [manifest_key],
            }
    return entries


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle": manifest.get("bundle"),
        "version": manifest.get("version"),
        "file_count": manifest.get("file_count"),
        "total_size_bytes": manifest.get("total_size_bytes"),
        "total_gib": _gib(int(manifest.get("total_size_bytes") or 0)),
        "models": [item["relative_path"] for item in manifest.get("files") or []],
    }


def upload_all_task_models(
    *,
    repo_root: Path,
    bucket: str,
    execute: bool,
    create_bucket: bool,
    client,
    max_concurrency: int = 4,
    max_bandwidth_mbps: float | None = None,
    targets: tuple[TargetSpec, ...] = DEFAULT_BASE_TARGETS,
) -> dict[str, Any]:
    registry = ModelRegistry(repo_root)
    bucket_exists = _head_bucket(client, bucket)
    created_bucket = False
    if not bucket_exists:
        if not create_bucket:
            raise RuntimeError(f"LAN model cache bucket does not exist: {bucket}")
        if execute:
            client.create_bucket(Bucket=bucket)
        created_bucket = execute

    existing_by_sha = (
        _load_existing_sha_index(client, bucket=bucket) if bucket_exists else {}
    )
    manifests = build_target_manifests(
        registry=registry,
        existing_by_sha=existing_by_sha,
        targets=targets,
    )
    unique_entries = _unique_model_entries(manifests)

    uploads: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    missing_local_blobs: list[dict[str, Any]] = []
    for entry in sorted(unique_entries.values(), key=lambda item: item["key"]):
        sha256 = str(entry["sha256"])
        size_bytes = int(entry["size_bytes"])
        key = str(entry["key"])
        head = (
            _head_object(client, bucket=bucket, key=key)
            if bucket_exists or created_bucket
            else None
        )
        metadata_sha = _metadata_value(head.get("Metadata"), "sha256") if head else ""
        if (
            head
            and int(head.get("ContentLength") or 0) == size_bytes
            and metadata_sha == sha256
        ):
            skipped_existing.append(
                {
                    "key": key,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "relative_paths": sorted(set(entry["relative_paths"])),
                }
            )
            continue
        source = registry.blob_path(sha256)
        if not source.exists():
            missing_local_blobs.append(
                {
                    "key": key,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                    "relative_paths": sorted(set(entry["relative_paths"])),
                    "local_blob": str(source),
                }
            )
            continue
        uploads.append(
            {
                "key": key,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "relative_paths": sorted(set(entry["relative_paths"])),
                "source": str(source),
            }
        )

    if missing_local_blobs and execute:
        raise RuntimeError(
            "missing local registry blobs for "
            f"{len(missing_local_blobs)} model object(s)"
        )

    transfer_config = TransferConfig(
        max_concurrency=max_concurrency,
        max_bandwidth=(
            int(max_bandwidth_mbps * 1024 * 1024 / 8)
            if max_bandwidth_mbps and max_bandwidth_mbps > 0
            else None
        ),
    )
    if execute:
        for item in uploads:
            label = ",".join(item["relative_paths"][:2])
            if len(item["relative_paths"]) > 2:
                label = f"{label},..."
            client.upload_file(
                item["source"],
                bucket,
                item["key"],
                ExtraArgs={
                    "ContentType": "application/octet-stream",
                    "Metadata": {
                        "sha256": item["sha256"],
                        "relative-path": item["relative_paths"][0],
                    },
                },
                Callback=UploadProgress(label, int(item["size_bytes"])),
                Config=transfer_config,
            )

        verification_failures = []
        for entry in unique_entries.values():
            head = _head_object(client, bucket=bucket, key=str(entry["key"]))
            metadata_sha = (
                _metadata_value(head.get("Metadata"), "sha256") if head else ""
            )
            if (
                not head
                or int(head.get("ContentLength") or 0) != int(entry["size_bytes"])
                or metadata_sha != str(entry["sha256"])
            ):
                verification_failures.append(str(entry["key"]))
        if verification_failures:
            raise RuntimeError(
                "LAN object HEAD verification failed before manifest publish for "
                f"{len(verification_failures)} object(s)"
            )

    manifest_uploads: list[dict[str, Any]] = []
    manifest_skips: list[dict[str, Any]] = []
    manifest_checksums: dict[str, str] = {}
    for manifest_key, manifest in manifests.items():
        body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        checksum = hashlib.sha256(body).hexdigest()
        manifest_checksums[manifest_key] = checksum
        existing = (
            _head_object(client, bucket=bucket, key=manifest_key)
            if bucket_exists or created_bucket
            else None
        )
        if (
            existing
            and int(existing.get("ContentLength") or 0) == len(body)
            and _metadata_value(existing.get("Metadata"), "sha256") == checksum
        ):
            manifest_skips.append({"key": manifest_key, "bytes": len(body)})
            continue
        manifest_uploads.append({"key": manifest_key, "bytes": len(body)})
        if execute:
            client.put_object(
                Bucket=bucket,
                Key=manifest_key,
                Body=body,
                ContentType="application/json",
                Metadata={
                    "generated-by": "upload_all_task_models_to_lan_cache",
                    "sha256": checksum,
                },
            )
        if execute:
            manifest_head = _head_object(client, bucket=bucket, key=manifest_key)
            if (
                not manifest_head
                or int(manifest_head.get("ContentLength") or 0) != len(body)
                or _metadata_value(manifest_head.get("Metadata"), "sha256") != checksum
            ):
                raise RuntimeError(
                    f"LAN manifest HEAD verification failed: {manifest_key}"
                )

    total_upload_size = sum(int(item["size_bytes"]) for item in uploads)
    unique_model_total = sum(
        int(item["size_bytes"]) for item in unique_entries.values()
    )
    return {
        "ok": True,
        "dry_run": not execute,
        "bucket": bucket,
        "bucket_exists": bucket_exists,
        "bucket_created": created_bucket,
        "shared_object_prefix": SHARED_OBJECT_PREFIX,
        "targets": [target.name for target in targets],
        "existing_cached_unique_model_count": len(existing_by_sha),
        "target_unique_model_count": len(unique_entries),
        "target_unique_total_size_bytes": unique_model_total,
        "target_unique_total_gib": _gib(unique_model_total),
        "upload_count": len(uploads),
        "upload_total_size_bytes": total_upload_size,
        "upload_total_gib": _gib(total_upload_size),
        "skipped_existing_count": len(skipped_existing),
        "missing_local_blob_count": len(missing_local_blobs),
        "manifest_upload_count": len(manifest_uploads),
        "manifest_skip_count": len(manifest_skips),
        "manifest_checksums": manifest_checksums,
        "verified_object_count": len(unique_entries) if execute else 0,
        "target_manifests": {
            key: _manifest_summary(manifest) for key, manifest in manifests.items()
        },
        "uploads": uploads,
        "skipped_existing": skipped_existing,
        "missing_local_blobs": missing_local_blobs,
        "manifest_uploads": manifest_uploads,
        "manifest_skips": manifest_skips,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload all AllBot runtime model manifests/blobs to the LAN model cache"
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--repo-root", type=Path, default=ModelRegistry().root)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-bandwidth-mbps", type=float, default=None)
    parser.add_argument("--create-bucket", action="store_true")
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(sorted(TARGETS_BY_NAME)),
        help=(
            "Upload only the named target; repeat for multiple targets. "
            "Without this option the established base target set is used."
        ),
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    _load_lan_env_file(args.env_file)
    client = _lan_client(endpoint=args.endpoint)
    targets = (
        tuple(TARGETS_BY_NAME[name] for name in dict.fromkeys(args.target))
        if args.target
        else DEFAULT_BASE_TARGETS
    )
    try:
        payload = upload_all_task_models(
            repo_root=args.repo_root,
            bucket=args.bucket,
            execute=args.execute,
            create_bucket=args.create_bucket,
            client=client,
            max_concurrency=args.max_concurrency,
            max_bandwidth_mbps=args.max_bandwidth_mbps,
            targets=targets,
        )
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
