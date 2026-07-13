import asyncio


def sync_upload_to_r2(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
    r2_object_name: str = None,
):
    if not service.r2_client:
        logger.error("R2 client not initialized")
        return False

    r2_key = r2_object_name or object_name.split("/")[-1]
    try:
        response = service.client.get_object(bucket_name, object_name)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        extra_args = {"ContentType": content_type} if content_type else None
        service.r2_client.upload_fileobj(
            response,
            service.r2_bucket,
            r2_key,
            ExtraArgs=extra_args,
        )
        service.mark_r2_object_exists(r2_key)
        logger.info(
            "Successfully copied %s to R2 bucket %s as %s",
            object_name,
            service.r2_bucket,
            r2_key,
        )
        return True
    except Exception as exc:
        service.invalidate_r2_exists_cache(r2_key)
        logger.error("Failed to copy %s to R2: %s", object_name, exc)
        return False
    finally:
        if "response" in locals():
            response.close()
            response.release_conn()


async def async_copy_to_r2(
    service,
    *,
    bucket_name: str,
    object_name: str,
    logger,
    r2_object_name: str = None,
):
    if not service.r2_client:
        return False

    return await asyncio.to_thread(
        sync_upload_to_r2,
        service,
        bucket_name=bucket_name,
        object_name=object_name,
        logger=logger,
        r2_object_name=r2_object_name,
    )


def get_r2_public_url(*, object_name: str, public_domain: str | None) -> str:
    if not public_domain or not object_name:
        return ""
    return f"{public_domain.rstrip('/')}/{object_name.lstrip('/')}"
