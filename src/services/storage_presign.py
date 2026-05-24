from __future__ import annotations

from datetime import timedelta


def resolve_download_expiry(expires_hours: float) -> timedelta:
    # Compat: historical callers sometimes pass seconds even though the field is named hours.
    if expires_hours > 24:
        return timedelta(seconds=float(expires_hours))
    return timedelta(hours=float(expires_hours))


def resolve_upload_expiry(expires_minutes: int) -> timedelta:
    return timedelta(minutes=float(expires_minutes))


def build_download_response_headers(
    *,
    object_name: str,
    download: bool,
) -> dict[str, str]:
    if not download:
        return {}

    filename = object_name.split("/")[-1]
    return {
        "response-content-disposition": f'attachment; filename="{filename}"'
    }


def get_presign_client(service):
    return getattr(service, "public_client", None) or service.client


def generate_presigned_get_url(
    service,
    *,
    bucket_name: str,
    object_name: str,
    expires_hours: float,
    download: bool,
) -> str:
    client = get_presign_client(service)
    if not client:
        return ""

    return client.presigned_get_object(
        bucket_name,
        object_name,
        expires=resolve_download_expiry(expires_hours),
        response_headers=build_download_response_headers(
            object_name=object_name,
            download=download,
        ),
    )


def generate_presigned_put_url(
    service,
    *,
    bucket_name: str,
    object_name: str,
    expires_minutes: int,
) -> str:
    client = get_presign_client(service)
    if not client:
        return ""

    return client.presigned_put_object(
        bucket_name=bucket_name,
        object_name=object_name,
        expires=resolve_upload_expiry(expires_minutes),
    )
