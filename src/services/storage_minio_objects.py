from __future__ import annotations

import asyncio
import io

from config import MINIO_BUCKET
from minio.error import S3Error


def _resolve_bucket_name(*, bucket_name: str | None, bucket: str | None) -> str:
    return bucket or bucket_name or MINIO_BUCKET


def upload_file(
    service,
    *,
    file_path: str,
    object_name: str,
    logger,
    bucket_name: str | None = None,
    bucket: str | None = None,
) -> bool:
    resolved_bucket = _resolve_bucket_name(bucket_name=bucket_name, bucket=bucket)
    if not service.client:
        logger.error("MinIO client not initialized")
        return False

    try:
        service.client.fput_object(resolved_bucket, object_name, file_path)
        return True
    except Exception as exc:
        logger.error(
            "Failed to upload file %s to %s/%s: %s",
            file_path,
            resolved_bucket,
            object_name,
            exc,
        )
        return False


def upload_bytes(
    service,
    *,
    data: bytes,
    object_name: str,
    content_type: str,
    logger,
    bucket_name: str | None = None,
    bucket: str | None = None,
) -> str:
    resolved_bucket = _resolve_bucket_name(bucket_name=bucket_name, bucket=bucket)
    if not service.client:
        logger.error("MinIO client not initialized")
        return ""

    try:
        service.client.put_object(
            resolved_bucket,
            object_name,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )
        return object_name
    except Exception as exc:
        logger.error(
            "Failed to upload bytes to %s in %s: %s",
            object_name,
            resolved_bucket,
            exc,
        )
        return ""


def get_file_bytes(
    service,
    *,
    object_name: str,
    logger,
    bucket_name: str | None = None,
    bucket: str | None = None,
) -> bytes | None:
    resolved_bucket = _resolve_bucket_name(bucket_name=bucket_name, bucket=bucket)
    if not service.client:
        logger.error("MinIO client not initialized")
        return None

    response = None
    try:
        response = service.client.get_object(resolved_bucket, object_name)
        return response.read()
    except Exception as exc:
        logger.error(
            "Failed to download %s from %s: %s",
            object_name,
            resolved_bucket,
            exc,
        )
        return None
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def list_objects(
    service,
    *,
    prefix: str,
    logger,
    bucket_name: str | None = None,
    bucket: str | None = None,
) -> list[str]:
    resolved_bucket = _resolve_bucket_name(bucket_name=bucket_name, bucket=bucket)
    if not service.client:
        logger.error("MinIO client not initialized")
        return []

    try:
        objects = service.client.list_objects(
            resolved_bucket,
            prefix=prefix,
            recursive=True,
        )
        return [obj.object_name for obj in objects if not obj.is_dir]
    except Exception as exc:
        logger.error(
            "Failed to list objects in %s with prefix %s: %s",
            resolved_bucket,
            prefix,
            exc,
        )
        return []


def object_exists(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
) -> bool:
    try:
        service.client.stat_object(bucket_name, object_name)
        return True
    except S3Error as exc:
        code = getattr(exc, "code", "")
        if code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return False
        logger.warning(
            "MinIO stat_object failed for %s/%s: %s",
            bucket_name,
            object_name,
            exc,
        )
        return False
    except Exception as exc:
        logger.warning(
            "Unexpected object_exists failure for %s/%s: %s",
            bucket_name,
            object_name,
            exc,
        )
        return False


def object_size(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
) -> int | None:
    """Return the object size, or ``None`` when it cannot be inspected."""
    try:
        return int(service.client.stat_object(bucket_name, object_name).size)
    except Exception as exc:
        logger.warning(
            "Unable to inspect object size for %s/%s: %s",
            bucket_name,
            object_name,
            exc,
        )
        return None


async def async_object_exists(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
) -> bool:
    return await asyncio.to_thread(
        object_exists,
        service,
        bucket_name=bucket_name,
        object_name=object_name,
        logger=logger,
    )


async def async_object_size(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
) -> int | None:
    return await asyncio.to_thread(
        object_size,
        service,
        bucket_name=bucket_name,
        object_name=object_name,
        logger=logger,
    )


def download_file(
    service,
    *,
    bucket_name: str,
    object_name: str,
    file_path: str,
):
    service.client.fget_object(bucket_name, object_name, file_path)
