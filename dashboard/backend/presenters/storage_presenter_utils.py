def build_storage_url(
    *,
    storage_service,
    object_name: str | None,
    bucket: str | None = None,
    fallback_url: str | None = None,
) -> str | None:
    if not object_name:
        return fallback_url

    if hasattr(storage_service, "get_file_url") and bucket is None:
        return storage_service.get_file_url(object_name)
    if hasattr(storage_service, "get_presigned_url"):
        return storage_service.get_presigned_url(object_name, bucket=bucket)
    if hasattr(storage_service, "get_presigned_download_url") and bucket is None:
        return storage_service.get_presigned_download_url(object_name)
    return fallback_url
