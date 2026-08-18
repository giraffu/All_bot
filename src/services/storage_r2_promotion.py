"""Promote short-lived user uploads into task-owned durable input keys."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from typing import Iterable

from minio.commonconfig import CopySource, REPLACE
from minio.error import S3Error

from shared.r2_retention_contract import build_task_input_key, normalize_r2_object_key


class StagedInputPromotionError(RuntimeError):
    pass


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _strip_bucket(ref: str, bucket: str) -> str:
    return normalize_r2_object_key(ref, buckets=(bucket,))


def _stat(client, bucket: str, key: str):
    try:
        return client.stat_object(bucket, key)
    except Exception as exc:
        raise StagedInputPromotionError(f"R2 input object is unavailable: {key}") from exc


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
        raise StagedInputPromotionError(
            f"R2 durable input status is unavailable: {key}"
        ) from exc


def _sha256(client, bucket: str, key: str) -> str:
    try:
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
    except Exception as exc:
        raise StagedInputPromotionError(f"R2 input SHA-256 failed: {key}") from exc


def _metadata_sha256(stat) -> str:
    metadata = getattr(stat, "metadata", None) or {}
    for key in ("sha256", "x-amz-meta-sha256", "X-Amz-Meta-Sha256"):
        value = str(metadata.get(key) or "").strip().lower()
        if _SHA256.fullmatch(value):
            return value
    return ""


def _native_sha256(stat) -> str:
    metadata = getattr(stat, "metadata", None) or {}
    for candidate in (
        getattr(stat, "checksum_sha256", None),
        metadata.get("x-amz-checksum-sha256"),
        metadata.get("X-Amz-Checksum-Sha256"),
    ):
        value = str(candidate or "").strip()
        if _SHA256.fullmatch(value.lower()):
            return value.lower()
        try:
            decoded = base64.b64decode(value, validate=True)
        except (TypeError, ValueError):
            continue
        if len(decoded) == 32:
            return decoded.hex()
    return ""


def _promote_one(*, client, bucket: str, source_key: str, durable_key: str) -> None:
    source_stat = _stat(client, bucket, source_key)
    source_sha256 = _native_sha256(source_stat) or _sha256(
        client,
        bucket,
        source_key,
    )
    durable_stat = _stat_optional(client, bucket, durable_key)
    if durable_stat is not None:
        if (
            int(durable_stat.size) == int(source_stat.size)
            and _metadata_sha256(durable_stat) == source_sha256
        ):
            return
        raise StagedInputPromotionError("durable input exists with different content")
    metadata = {"sha256": source_sha256}
    source_content_type = str(getattr(source_stat, "content_type", "") or "").strip()
    if source_content_type:
        metadata["Content-Type"] = source_content_type
    try:
        client.copy_object(
            bucket,
            durable_key,
            CopySource(bucket, source_key),
            metadata=metadata,
            metadata_directive=REPLACE,
        )
    except Exception as exc:
        raise StagedInputPromotionError("R2 input promotion copy failed") from exc
    copied = _stat(client, bucket, durable_key)
    if (
        int(copied.size) != int(source_stat.size)
        or _metadata_sha256(copied) != source_sha256
    ):
        raise StagedInputPromotionError("R2 input promotion verification failed")


async def promote_staged_user_inputs(
    *,
    input_refs: Iterable[str],
    task_id: str,
    user_id: int,
    bucket: str,
    client,
    max_concurrency: int = 3,
) -> list[str]:
    expected_prefix = f"staging/user-uploads/{int(user_id)}/"
    refs = list(input_refs)
    promoted: list[str | None] = [None] * len(refs)
    semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def promote_ref(ordinal: int, ref: str) -> None:
        key = _strip_bucket(str(ref), bucket)
        if not key.startswith("staging/user-uploads/"):
            promoted[ordinal] = str(ref)
            return
        if not key.startswith(expected_prefix):
            raise StagedInputPromotionError("staged upload belongs to another user")
        durable_key = build_task_input_key(
            task_id=task_id,
            ordinal=ordinal,
            source_name=key,
        )
        async with semaphore:
            await asyncio.to_thread(
                _promote_one,
                client=client,
                bucket=bucket,
                source_key=key,
                durable_key=durable_key,
            )
        promoted[ordinal] = durable_key

    await asyncio.gather(
        *(promote_ref(ordinal, str(ref)) for ordinal, ref in enumerate(refs))
    )
    return [str(value) for value in promoted]
