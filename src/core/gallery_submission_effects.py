from src.media_paths import (
    build_r2_media_materialization_plan,
    resolve_storage_object,
)
from src.media_processor import generate_and_upload_thumbnail

from src.gallery_core_dependencies import get_gallery_storage_service


async def async_copy_to_r2_background(
    bucket_name: str,
    object_name: str,
    r2_object_name: str,
    *,
    copy_to_r2_func=None,
    storage_service=None,
    logger=None,
):
    """Background task to copy file to R2."""
    if copy_to_r2_func is None:
        storage_service = storage_service or get_gallery_storage_service()
        copy_to_r2_func = storage_service.async_copy_to_r2
    try:
        await copy_to_r2_func(bucket_name, object_name, r2_object_name)
    except Exception as exc:
        if logger is not None:
            logger.error(f"Background task failed to copy {object_name} to R2: {exc}")


def build_gallery_submit_side_effects(
    *,
    task_id: str,
    output_file: str,
    media_type: str,
    copy_to_r2_background_func=None,
    generate_thumbnail_func=None,
    resolve_storage_object_func=None,
) -> list[tuple[object, tuple[object, ...]]]:
    copy_to_r2_background_func = (
        copy_to_r2_background_func or async_copy_to_r2_background
    )
    generate_thumbnail_func = (
        generate_thumbnail_func or generate_and_upload_thumbnail
    )
    resolve_storage_object_func = resolve_storage_object_func or resolve_storage_object
    plan = build_r2_media_materialization_plan(
        task_id=task_id,
        output_file=output_file,
        media_type=media_type,
    )
    effects = []
    if plan.original_copy_key:
        bucket_name, object_name = resolve_storage_object_func(output_file)
        effects.append(
            (
                copy_to_r2_background_func,
                (bucket_name, object_name, plan.original_copy_key),
            )
        )
    effects.append(
        (
            generate_thumbnail_func,
            (output_file, media_type, plan.thumbnail_key),
        )
    )
    return effects
