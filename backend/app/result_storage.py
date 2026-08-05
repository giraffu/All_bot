"""Promote transient Worker assets before Central records task completion."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from minio.commonconfig import CopySource
from minio.error import S3Error

from shared.r2_retention_contract import build_task_result_key


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResultPromotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotedCompletion:
    result_path: str
    extra_outputs: dict[str, Any] | None


def _metadata_sha256(stat: Any) -> str:
    metadata = getattr(stat, "metadata", None) or {}
    for key in ("sha256", "x-amz-meta-sha256", "X-Amz-Meta-Sha256"):
        value = str(metadata.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def _is_not_found(exc: Exception) -> bool:
    if isinstance(exc, S3Error):
        return exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}
    return "not found" in str(exc).lower()


def _stat_optional(client, bucket: str, key: str):
    try:
        return client.stat_object(bucket, key)
    except Exception as exc:
        if _is_not_found(exc):
            return None
        raise ResultPromotionError(f"failed to stat R2 object {key}") from exc


def _validate_asset(asset: dict[str, Any], *, task_id: str) -> tuple[str, str, int]:
    staging_key = str(asset.get("staging_key") or "").strip()
    expected_prefix = f"staging/worker-results/{task_id}/"
    if not staging_key.startswith(expected_prefix):
        raise ResultPromotionError("completion asset is outside the task staging prefix")
    sha256 = str(asset.get("sha256") or "").strip().lower()
    if not _SHA256.fullmatch(sha256):
        raise ResultPromotionError("completion asset has an invalid SHA-256")
    try:
        byte_size = int(asset.get("byte_size"))
    except (TypeError, ValueError) as exc:
        raise ResultPromotionError("completion asset has an invalid byte size") from exc
    if byte_size < 0:
        raise ResultPromotionError("completion asset has an invalid byte size")
    return staging_key, sha256, byte_size


def _matches(stat: Any, *, sha256: str, byte_size: int) -> bool:
    return int(getattr(stat, "size", -1)) == byte_size and _metadata_sha256(stat) == sha256


def _object_sha256(client, bucket: str, key: str) -> str:
    response = client.get_object(bucket, key)
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: response.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    finally:
        response.close()
        release = getattr(response, "release_conn", None)
        if callable(release):
            release()
    return digest.hexdigest()


def _promote_one(
    *,
    client,
    bucket: str,
    staging_key: str,
    durable_key: str,
    sha256: str,
    byte_size: int,
) -> None:
    durable_stat = _stat_optional(client, bucket, durable_key)
    if durable_stat is not None:
        if _matches(
            durable_stat, sha256=sha256, byte_size=byte_size
        ) and _object_sha256(client, bucket, durable_key) == sha256:
            return
        raise ResultPromotionError("durable result exists with different content")

    staging_stat = _stat_optional(client, bucket, staging_key)
    if staging_stat is None or not _matches(
        staging_stat, sha256=sha256, byte_size=byte_size
    ):
        raise ResultPromotionError("staging result integrity validation failed")
    if _object_sha256(client, bucket, staging_key) != sha256:
        raise ResultPromotionError("staging result SHA-256 validation failed")
    try:
        client.copy_object(
            bucket,
            durable_key,
            CopySource(bucket, staging_key),
        )
    except Exception as exc:
        raise ResultPromotionError("R2 staging promotion copy failed") from exc
    durable_stat = _stat_optional(client, bucket, durable_key)
    if durable_stat is None or not _matches(
        durable_stat, sha256=sha256, byte_size=byte_size
    ):
        raise ResultPromotionError("durable result verification failed after copy")
    if _object_sha256(client, bucket, durable_key) != sha256:
        raise ResultPromotionError("durable result SHA-256 validation failed after copy")


async def promote_completion_assets(
    *,
    task_id: str,
    result_path: str,
    extra_outputs: dict[str, Any] | None,
    result_asset: dict[str, Any] | None,
    extra_output_assets: dict[str, Any] | None,
    minio_client,
    bucket: str,
) -> PromotedCompletion:
    """Return legacy payload unchanged or promote a complete new asset contract."""
    if not result_asset:
        return PromotedCompletion(
            result_path=result_path,
            extra_outputs=(dict(extra_outputs) if extra_outputs is not None else None),
        )
    if minio_client is None or not bucket:
        raise ResultPromotionError("result storage is unavailable")

    staging_key, sha256, byte_size = _validate_asset(result_asset, task_id=task_id)
    if result_path != staging_key:
        raise ResultPromotionError("result path does not match its staging asset")
    durable_result = build_task_result_key(
        task_id=task_id,
        source_name=staging_key,
        role="primary",
    )
    await asyncio.to_thread(
        _promote_one,
        client=minio_client,
        bucket=bucket,
        staging_key=staging_key,
        durable_key=durable_result,
        sha256=sha256,
        byte_size=byte_size,
    )

    original_extras = dict(extra_outputs or {})
    asset_extras = dict(extra_output_assets or {})
    if set(original_extras) != set(asset_extras):
        raise ResultPromotionError("extra output asset contract is incomplete")
    promoted_extras: dict[str, Any] = {}
    for name, original in original_extras.items():
        asset = asset_extras[name]
        extra_staging, extra_sha, extra_size = _validate_asset(
            asset, task_id=task_id
        )
        if str((original or {}).get("path") or "") != extra_staging:
            raise ResultPromotionError("extra output path does not match staging asset")
        ordinal = int(asset.get("ordinal", 0))
        durable_extra = build_task_result_key(
            task_id=task_id,
            source_name=extra_staging,
            role=name,
            ordinal=ordinal,
        )
        await asyncio.to_thread(
            _promote_one,
            client=minio_client,
            bucket=bucket,
            staging_key=extra_staging,
            durable_key=durable_extra,
            sha256=extra_sha,
            byte_size=extra_size,
        )
        promoted_extras[name] = {
            **dict(original or {}),
            "path": durable_extra,
        }
    return PromotedCompletion(
        result_path=durable_result,
        extra_outputs=promoted_extras,
    )
