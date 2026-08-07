"""Promote short-lived user uploads into task-owned durable input keys."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Iterable

from minio.commonconfig import CopySource

from shared.r2_retention_contract import build_task_input_key, normalize_r2_object_key


class StagedInputPromotionError(RuntimeError):
    pass


def _strip_bucket(ref: str, bucket: str) -> str:
    return normalize_r2_object_key(ref, buckets=(bucket,))


def _stat(client, bucket: str, key: str):
    try:
        return client.stat_object(bucket, key)
    except Exception as exc:
        raise StagedInputPromotionError(f"R2 input object is unavailable: {key}") from exc


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


def _promote_one(*, client, bucket: str, source_key: str, durable_key: str) -> None:
    source_stat = _stat(client, bucket, source_key)
    source_sha256 = _sha256(client, bucket, source_key)
    try:
        durable_stat = client.stat_object(bucket, durable_key)
    except Exception:
        durable_stat = None
    if durable_stat is not None:
        if (
            int(durable_stat.size) == int(source_stat.size)
            and _sha256(client, bucket, durable_key) == source_sha256
        ):
            return
        raise StagedInputPromotionError("durable input exists with different content")
    try:
        client.copy_object(
            bucket,
            durable_key,
            CopySource(bucket, source_key),
        )
    except Exception as exc:
        raise StagedInputPromotionError("R2 input promotion copy failed") from exc
    copied = _stat(client, bucket, durable_key)
    if int(copied.size) != int(source_stat.size):
        raise StagedInputPromotionError("R2 input promotion verification failed")
    if _sha256(client, bucket, durable_key) != source_sha256:
        raise StagedInputPromotionError("R2 input SHA-256 differs after promotion")


async def promote_staged_user_inputs(
    *,
    input_refs: Iterable[str],
    task_id: str,
    user_id: int,
    bucket: str,
    client,
) -> list[str]:
    expected_prefix = f"staging/user-uploads/{int(user_id)}/"
    promoted: list[str] = []
    for ordinal, ref in enumerate(input_refs):
        key = _strip_bucket(str(ref), bucket)
        if not key.startswith("staging/user-uploads/"):
            promoted.append(str(ref))
            continue
        if not key.startswith(expected_prefix):
            raise StagedInputPromotionError("staged upload belongs to another user")
        durable_key = build_task_input_key(
            task_id=task_id,
            ordinal=ordinal,
            source_name=key,
        )
        await asyncio.to_thread(
            _promote_one,
            client=client,
            bucket=bucket,
            source_key=key,
            durable_key=durable_key,
        )
        promoted.append(durable_key)
    return promoted
