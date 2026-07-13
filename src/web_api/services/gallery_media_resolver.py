from src.services import gallery_media_resolver as _service_resolver
from src.web_api.presenters.media_presenter import resolve_thumbnail_url

build_storage_media_url = _service_resolver.build_storage_media_url
build_r2_presigned_url = _service_resolver.build_r2_presigned_url


async def build_gallery_media_url(
    output_file: str | None,
    *,
    task_id: str | None,
    async_r2_object_exists_fn=None,
    get_r2_public_url_fn=None,
    build_r2_presigned_url_fn=None,
) -> str:
    return await _service_resolver.build_gallery_media_url(
        output_file,
        task_id=task_id,
        async_r2_object_exists_fn=async_r2_object_exists_fn,
        get_r2_public_url_fn=get_r2_public_url_fn,
        build_r2_presigned_url_fn=build_r2_presigned_url_fn or build_r2_presigned_url,
    )


async def build_gallery_thumbnail_url(
    output_file: str | None,
    media_type: str,
    *,
    task_id: str | None,
    fast_list_mode: bool = True,
    async_r2_object_exists_fn=None,
    get_r2_public_url_fn=None,
    build_r2_presigned_url_fn=None,
    resolve_thumbnail_url_fn=None,
    async_object_exists_fn=None,
    get_presigned_url_fn=None,
) -> str:
    kwargs = {
        "task_id": task_id,
        "fast_list_mode": fast_list_mode,
        "async_r2_object_exists_fn": async_r2_object_exists_fn,
        "get_r2_public_url_fn": get_r2_public_url_fn,
        "build_r2_presigned_url_fn": build_r2_presigned_url_fn
        or build_r2_presigned_url,
        "resolve_thumbnail_url_fn": resolve_thumbnail_url_fn or resolve_thumbnail_url,
    }
    if async_object_exists_fn is not None:
        kwargs["async_object_exists_fn"] = async_object_exists_fn
    if get_presigned_url_fn is not None:
        kwargs["get_presigned_url_fn"] = get_presigned_url_fn
    return await _service_resolver.build_gallery_thumbnail_url(
        output_file,
        media_type,
        **kwargs,
    )


async def pick_gallery_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
    build_media_url_fn=None,
    build_thumbnail_url_fn=None,
    resolve_gallery_media_urls_fn=None,
    logger=None,
    logger_override=None,
) -> tuple[str, str]:
    return await _service_resolver.pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
        build_media_url_fn=build_media_url_fn or build_gallery_media_url,
        build_thumbnail_url_fn=build_thumbnail_url_fn or build_gallery_thumbnail_url,
        resolve_gallery_media_urls_fn=resolve_gallery_media_urls_fn,
        logger=logger,
        logger_override=logger_override,
    )


async def resolve_gallery_post_media_urls(
    *,
    task_id: str | None,
    output_file: str | None,
    media_type: str,
) -> tuple[str, str]:
    return await pick_gallery_media_urls(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
    )


__all__ = [
    "build_gallery_media_url",
    "build_gallery_thumbnail_url",
    "build_r2_presigned_url",
    "build_storage_media_url",
    "pick_gallery_media_urls",
    "resolve_gallery_post_media_urls",
]
