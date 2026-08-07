from pathlib import Path
from urllib.parse import unquote, urlparse

from config import MINIO_BUCKET, MINIO_RESULT_BUCKET
from src.constants import VIDEO_TASK_TYPES


_VIDEO_TASK_TYPE_SET = {task_type.lower() for task_type in VIDEO_TASK_TYPES}


def normalize_storage_object_key(reference: str) -> str:
    """Return a stable object key for plain, bucket-prefixed, or HTTP references."""
    raw = str(reference or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        raw = unquote(parsed.path)
    raw = raw.lstrip("/")
    bucket_names = (
        MINIO_BUCKET,
        MINIO_RESULT_BUCKET,
        "bot-data",
        "comfyui-temp",
        "user-data",
        "user-data-prod",
    )
    for bucket_name in dict.fromkeys(bucket_names):
        prefix = f"{bucket_name}/"
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def normalize_owned_user_upload_key(
    reference: str,
    *,
    user_id: int,
    allowed_extensions: set[str] | None = None,
) -> str:
    """Accept staged user uploads while keeping legacy web_uploads readable."""
    object_key = normalize_storage_object_key(reference)
    user_segment = str(int(user_id))
    allowed_prefixes = (
        f"staging/user-uploads/{user_segment}/",
        f"web_uploads/{user_segment}/",
    )
    if not any(object_key.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError("object key is not owned by the current user")
    if allowed_extensions is not None:
        extension = object_key.rsplit(".", 1)[-1].lower() if "." in object_key else ""
        if extension not in allowed_extensions:
            raise ValueError("object key extension is not allowed")
    return object_key


def resolve_storage_object(
    output_file: str,
) -> tuple[str, str]:
    compatibility_bucket_aliases = {
        "bot-data": MINIO_BUCKET,
        "comfyui-temp": MINIO_RESULT_BUCKET,
    }
    current_bucket_aliases = {
        MINIO_BUCKET: MINIO_BUCKET,
        MINIO_RESULT_BUCKET: MINIO_RESULT_BUCKET,
    }

    for bucket_name, resolved_bucket in {
        **compatibility_bucket_aliases,
        **current_bucket_aliases,
    }.items():
        prefix = f"{bucket_name}/"
        if output_file.startswith(prefix):
            return resolved_bucket, output_file[len(prefix) :]

    if "/" not in output_file:
        return MINIO_RESULT_BUCKET, output_file

    return MINIO_BUCKET, output_file


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


def build_flat_r2_compatibility_key(object_name: str) -> str:
    return object_name.split("/")[-1]
