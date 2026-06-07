from pathlib import Path

from config import (
    LEGACY_MINIO_BUCKET,
    LEGACY_MINIO_RESULT_BUCKET,
    MINIO_BUCKET,
    MINIO_RESULT_BUCKET,
)
from src.constants import VIDEO_TASK_TYPES


_VIDEO_TASK_TYPE_SET = {task_type.lower() for task_type in VIDEO_TASK_TYPES}


def resolve_storage_object(
    output_file: str,
) -> tuple[str, str]:
    legacy_bucket_aliases = {
        "bot-data": MINIO_BUCKET,
        "comfyui-temp": MINIO_RESULT_BUCKET,
    }
    current_bucket_aliases = {
        MINIO_BUCKET: MINIO_BUCKET,
        MINIO_RESULT_BUCKET: MINIO_RESULT_BUCKET,
    }

    for bucket_name, resolved_bucket in {
        **legacy_bucket_aliases,
        **current_bucket_aliases,
    }.items():
        prefix = f"{bucket_name}/"
        if output_file.startswith(prefix):
            return resolved_bucket, output_file[len(prefix) :]

    if "/" not in output_file:
        return MINIO_RESULT_BUCKET, output_file

    return MINIO_BUCKET, output_file


def resolve_legacy_storage_object(output_file: str) -> tuple[str, str]:
    legacy_bucket_aliases = {
        "bot-data": LEGACY_MINIO_BUCKET,
        "comfyui-temp": LEGACY_MINIO_RESULT_BUCKET,
    }

    for bucket_name, resolved_bucket in legacy_bucket_aliases.items():
        prefix = f"{bucket_name}/"
        if output_file.startswith(prefix):
            return resolved_bucket, output_file[len(prefix) :]

    if "/" not in output_file:
        return LEGACY_MINIO_RESULT_BUCKET, output_file

    return LEGACY_MINIO_BUCKET, output_file


def get_media_type_from_history(history_type: str | None) -> str:
    if not history_type:
        return "image"

    normalized_history_type = history_type.lower()
    if (
        normalized_history_type in _VIDEO_TASK_TYPE_SET
        or "video" in normalized_history_type
    ):
        return "video"
    return "image"


def build_thumbnail_object_name(object_name: str, media_type: str) -> str:
    base_name = object_name.rsplit(".", 1)[0]
    thumb_ext = "_thumb.jpg" if media_type == "video" else "_thumb.webp"
    return f"{base_name}{thumb_ext}"


def build_history_r2_media_key(task_id: str, output_file: str) -> str:
    suffix = Path(output_file).suffix
    return f"history/{task_id}/original{suffix}"


def build_history_r2_thumbnail_key(task_id: str, media_type: str) -> str:
    ext = ".jpg" if media_type == "video" else ".webp"
    return f"history/{task_id}/thumb{ext}"


def build_storage_r2_object_key(output_file: str) -> str:
    _, object_name = resolve_storage_object(output_file)
    return object_name


def build_legacy_r2_key(object_name: str) -> str:
    return object_name.split("/")[-1]
