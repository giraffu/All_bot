from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .providers.runpod import (
    RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
    RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
    redact_text,
)


COMMON_RELATIVE_PATHS = {
    "clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae/wan_2.1_vae.safetensors",
}
LEGACY_WAN22_AIO_MANIFEST_KEY = "wan22_aio_video/2026-06-12-test/manifest.json"
WAN22_EXPLICIT_LORA_MANIFEST_KEY = (
    "wan22_explicit_lora_library/2026-07-18/manifest.json"
)
IMAGE_TO_VIDEO_MARKERS = ("FASTMOVE",)
WAN22_VIDEO_V2_MARKERS = ("DasiwaWAN22I2V14B",)


def split_wan22_aio_manifest(
    source_manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    files = list(source_manifest.get("files") or [])
    if not files:
        raise ValueError("source Wan22 AIO manifest has no files")

    image_to_video_files = _selected_files(
        files,
        lambda rel: (
            rel in COMMON_RELATIVE_PATHS
            or rel.startswith("loras/")
            or _contains_marker(rel, IMAGE_TO_VIDEO_MARKERS)
        ),
    )
    wan22_v2_files = _selected_files(
        files,
        lambda rel: (
            rel in COMMON_RELATIVE_PATHS
            or rel.startswith("loras/")
            or _contains_marker(rel, WAN22_VIDEO_V2_MARKERS)
        ),
    )
    return {
        "image_to_video": _build_split_manifest(
            source_manifest,
            profile="image_to_video",
            prefix=RUNPOD_IMAGE_TO_VIDEO_MODEL_PREFIX,
            files=image_to_video_files,
        ),
        "wan22_video_v2": _build_split_manifest(
            source_manifest,
            profile="wan22_video_v2",
            prefix=RUNPOD_WAN22_VIDEO_V2_MODEL_PREFIX,
            files=wan22_v2_files,
        ),
    }


def prepare_wan22_lora5_manifests(
    *,
    client: Any,
    bucket: str,
    base_source_key: str = LEGACY_WAN22_AIO_MANIFEST_KEY,
    explicit_source_key: str = WAN22_EXPLICIT_LORA_MANIFEST_KEY,
    execute: bool = False,
) -> dict[str, Any]:
    base_manifest = read_json_object(client, bucket=bucket, key=base_source_key)
    explicit_manifest = read_json_object(
        client, bucket=bucket, key=explicit_source_key
    )
    files_by_path: dict[str, dict[str, Any]] = {}
    for manifest in (base_manifest, explicit_manifest):
        for raw_entry in manifest.get("files") or []:
            entry = dict(raw_entry)
            relative_path = str(entry.get("relative_path") or "")
            if not relative_path or not (entry.get("key") or entry.get("objectKey")):
                raise ValueError("source manifest entry is missing relative_path or key")
            existing = files_by_path.get(relative_path)
            if existing and (
                str(existing.get("sha256")) != str(entry.get("sha256"))
                or int(existing.get("size_bytes") or 0)
                != int(entry.get("size_bytes") or 0)
            ):
                raise ValueError(f"conflicting Wan22 manifest entry: {relative_path}")
            files_by_path[relative_path] = entry
    aio_files = sorted(files_by_path.values(), key=lambda item: item["relative_path"])
    aio_manifest = {
        "bundle": "wan22_aio_video",
        "profile": "wan22_aio_video",
        "version": "2026-07-18-lora5",
        "prefix": RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY.removesuffix(
            "/manifest.json"
        ),
        "source": {
            "base_manifest_key": base_source_key,
            "explicit_lora_manifest_key": explicit_source_key,
        },
        "file_count": len(aio_files),
        "total_size_bytes": sum(
            int(item.get("size_bytes") or item.get("size") or 0)
            for item in aio_files
        ),
        "files": aio_files,
    }
    split = split_wan22_aio_manifest(aio_manifest)
    manifests = {
        "wan22_aio_video": aio_manifest,
        "image_to_video": split["image_to_video"],
        "wan22_video_v2": split["wan22_video_v2"],
    }
    targets = {
        "wan22_aio_video": RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
        "image_to_video": RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        "wan22_video_v2": RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    }
    missing = []
    for profile, manifest in manifests.items():
        for entry in manifest["files"]:
            key = str(entry.get("key") or entry.get("objectKey") or "")
            matches, reason = head_object_matches_manifest_entry(
                client, bucket=bucket, key=key, entry=entry
            )
            if not matches:
                missing.append(
                    {
                        "profile": profile,
                        "relative_path": entry["relative_path"],
                        "key": key,
                        "reason": reason,
                    }
                )
    if missing:
        return {
            "ok": False,
            "dry_run": not execute,
            "missing_count": len(missing),
            "missing": missing,
            "verified_file_counts": {
                profile: len(manifest["files"])
                for profile, manifest in manifests.items()
            },
        }

    uploads = []
    if execute:
        for profile, manifest in manifests.items():
            target_key = targets[profile]
            body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            checksum = hashlib.sha256(body).hexdigest()
            client.put_object(
                Bucket=bucket,
                Key=target_key,
                Body=body,
                ContentType="application/json",
                Metadata={"sha256": checksum},
            )
            head = client.head_object(Bucket=bucket, Key=target_key)
            if (
                int(head.get("ContentLength") or 0) != len(body)
                or _metadata_value(head.get("Metadata"), "sha256") != checksum
            ):
                raise RuntimeError(
                    f"published manifest HEAD verification failed: {target_key}"
                )
            uploads.append(
                {
                    "profile": profile,
                    "key": target_key,
                    "bytes": len(body),
                    "sha256": checksum,
                }
            )
    return {
        "ok": True,
        "dry_run": not execute,
        "base_source_key": base_source_key,
        "explicit_source_key": explicit_source_key,
        "missing_count": 0,
        "verified_file_counts": {
            profile: len(manifest["files"])
            for profile, manifest in manifests.items()
        },
        "uploads": uploads,
        "manifests": _manifest_summaries(manifests, targets),
    }


def prepare_split_video_manifests(
    *,
    client: Any,
    bucket: str,
    source_key: str = RUNPOD_WAN22_AIO_VIDEO_MODEL_MANIFEST_KEY,
    execute: bool = False,
) -> dict[str, Any]:
    source_manifest = read_json_object(client, bucket=bucket, key=source_key)
    manifests = split_wan22_aio_manifest(source_manifest)
    targets = {
        "image_to_video": RUNPOD_IMAGE_TO_VIDEO_MODEL_MANIFEST_KEY,
        "wan22_video_v2": RUNPOD_WAN22_VIDEO_V2_MODEL_MANIFEST_KEY,
    }
    missing = []
    for profile, manifest in manifests.items():
        for entry in manifest["files"]:
            key = entry.get("key") or entry.get("objectKey")
            if not key:
                missing.append(
                    {
                        "profile": profile,
                        "relative_path": entry["relative_path"],
                        "key": "",
                    }
                )
                continue
            matches, reason = head_object_matches_manifest_entry(
                client,
                bucket=bucket,
                key=str(key),
                entry=entry,
            )
            if not matches:
                missing.append(
                    {
                        "profile": profile,
                        "relative_path": entry["relative_path"],
                        "key": key,
                        "reason": reason,
                    }
                )
    if missing:
        return {
            "ok": False,
            "dry_run": not execute,
            "source_key": source_key,
            "missing_count": len(missing),
            "missing": missing,
            "manifests": _manifest_summaries(manifests, targets),
        }

    uploads = []
    if execute:
        for profile, manifest in manifests.items():
            target_key = targets[profile]
            body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            checksum = hashlib.sha256(body).hexdigest()
            client.put_object(
                Bucket=bucket,
                Key=target_key,
                Body=body,
                ContentType="application/json",
                Metadata={"sha256": checksum},
            )
            head = client.head_object(Bucket=bucket, Key=target_key)
            metadata_sha = _metadata_value(head.get("Metadata"), "sha256")
            if (
                int(head.get("ContentLength") or 0) != len(body)
                or metadata_sha != checksum
            ):
                raise RuntimeError(
                    f"published manifest HEAD verification failed: {target_key}"
                )
            uploads.append(
                {
                    "profile": profile,
                    "key": target_key,
                    "bytes": len(body),
                    "sha256": checksum,
                }
            )

    return {
        "ok": True,
        "dry_run": not execute,
        "source_key": source_key,
        "missing_count": 0,
        "uploads": uploads,
        "manifests": _manifest_summaries(manifests, targets),
    }


def create_model_r2_client_from_env() -> Any:
    try:
        import boto3
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            f"boto3 is required for R2 model manifest preparation: {exc}"
        ) from exc
    endpoint = (
        os.getenv("RUNPOD_MODEL_ENDPOINT")
        or os.getenv("R2_ENDPOINT")
        or os.getenv("MINIO_ENDPOINT")
    )
    access_key = (
        os.getenv("RUNPOD_MODEL_ACCESS_KEY")
        or os.getenv("R2_ACCESS_KEY")
        or os.getenv("R2_ACCESS_KEY_ID")
        or os.getenv("MINIO_ACCESS_KEY")
    )
    secret_key = (
        os.getenv("RUNPOD_MODEL_SECRET_KEY")
        or os.getenv("R2_SECRET_KEY")
        or os.getenv("R2_SECRET_ACCESS_KEY")
        or os.getenv("MINIO_SECRET_KEY")
    )
    if not endpoint:
        raise RuntimeError(
            "RUNPOD_MODEL_ENDPOINT/R2_ENDPOINT/MINIO_ENDPOINT is required"
        )
    if not access_key or not secret_key:
        raise RuntimeError(
            "RUNPOD_MODEL_ACCESS_KEY and RUNPOD_MODEL_SECRET_KEY are required"
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def read_json_object(client: Any, *, bucket: str, key: str) -> dict[str, Any]:
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise RuntimeError(
            f"get_object failed for {key}: {_safe_client_error(exc)}"
        ) from exc
    body = response["Body"].read()
    if isinstance(body, bytes):
        text = body.decode("utf-8")
    else:
        text = str(body)
    return json.loads(text)


def head_object_matches_manifest_entry(
    client: Any,
    *,
    bucket: str,
    key: str,
    entry: dict[str, Any],
) -> tuple[bool, str]:
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = _client_error_code(exc)
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False, "missing"
        raise RuntimeError(
            f"head_object failed for {key}: {_safe_client_error(exc)}"
        ) from exc
    reasons = []
    expected_size = int(entry.get("size_bytes") or entry.get("size") or 0)
    if int(head.get("ContentLength") or 0) != expected_size:
        reasons.append("size_mismatch")
    expected_sha = str(entry.get("sha256") or "")
    if _metadata_value(head.get("Metadata"), "sha256") != expected_sha:
        reasons.append("sha256_metadata_mismatch")
    return not reasons, ",".join(reasons)


def _metadata_value(metadata: dict[str, Any] | None, key: str) -> str:
    for metadata_key, value in (metadata or {}).items():
        if str(metadata_key).lower() == key.lower():
            return str(value)
    return ""


def _selected_files(files: list[dict[str, Any]], predicate) -> list[dict[str, Any]]:
    selected = [
        dict(entry)
        for entry in files
        if predicate(str(entry.get("relative_path") or ""))
    ]
    if not selected:
        raise ValueError("split manifest selection produced no files")
    for entry in selected:
        if not entry.get("relative_path"):
            raise ValueError("manifest file entry is missing relative_path")
        if not entry.get("key") and not entry.get("objectKey"):
            raise ValueError(f"manifest entry is missing key: {entry['relative_path']}")
    return sorted(selected, key=lambda item: str(item["relative_path"]))


def _build_split_manifest(
    source_manifest: dict[str, Any],
    *,
    profile: str,
    prefix: str,
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    total_size = sum(
        int(entry.get("size_bytes") or entry.get("size") or 0) for entry in files
    )
    return {
        "bundle": profile,
        "profile": profile,
        "version": "2026-07-18-lora5",
        "prefix": prefix,
        "source": {
            "split_from": source_manifest.get("bundle") or "wan22_aio_video",
            "source_version": source_manifest.get("version"),
        },
        "file_count": len(files),
        "total_size_bytes": total_size,
        "files": files,
    }


def _manifest_summaries(
    manifests: dict[str, dict[str, Any]],
    targets: dict[str, str],
) -> dict[str, dict[str, Any]]:
    return {
        profile: {
            "key": targets[profile],
            "file_count": manifest["file_count"],
            "total_size_bytes": manifest["total_size_bytes"],
            "relative_paths": [entry["relative_path"] for entry in manifest["files"]],
        }
        for profile, manifest in manifests.items()
    }


def _contains_marker(relative_path: str, markers: tuple[str, ...]) -> bool:
    return any(marker in relative_path for marker in markers)


def _client_error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    error = response.get("Error") if isinstance(response, dict) else {}
    return str(error.get("Code") or "")


def _safe_client_error(exc: Exception) -> str:
    return redact_text(str(exc))
