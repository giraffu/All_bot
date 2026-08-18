from src.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_flat_r2_compatibility_key,
    build_storage_r2_object_key,
    resolve_storage_object,
)


def build_thumbnail_file_path(output_file: str, media_type: str) -> str:
    if not output_file:
        return ""
    base_path = output_file.rsplit(".", 1)[0]
    thumb_ext = "_thumb.jpg" if media_type == "video" else "_thumb.webp"
    return f"{base_path}{thumb_ext}"


def build_r2_media_key_candidates(
    *,
    output_file: str | None,
    task_id: str | None = None,
    preferred_r2_object_name: str | None = None,
) -> list[str]:
    if not output_file:
        return []

    candidates: list[str] = []
    if preferred_r2_object_name:
        candidates.append(preferred_r2_object_name)
    elif task_id:
        candidates.append(build_history_r2_media_key(task_id, output_file))
    candidates.append(build_storage_r2_object_key(output_file))
    candidates.append(output_file)
    candidates.append(build_flat_r2_compatibility_key(output_file))

    seen = set()
    return [key for key in candidates if key and not (key in seen or seen.add(key))]


def build_r2_thumbnail_info(
    *,
    output_file: str | None,
    media_type: str,
    task_id: str | None = None,
    preferred_r2_object_name: str | None = None,
) -> tuple[str, list[str]]:
    thumb_file = build_thumbnail_file_path(output_file or "", media_type)
    if not thumb_file:
        return "", []

    candidates: list[str] = []
    if preferred_r2_object_name:
        candidates.append(preferred_r2_object_name)
    elif task_id:
        candidates.append(build_history_r2_thumbnail_key(task_id, media_type))
    candidates.append(build_storage_r2_object_key(thumb_file))
    candidates.append(thumb_file)
    candidates.append(build_flat_r2_compatibility_key(thumb_file))

    seen = set()
    deduped = [key for key in candidates if key and not (key in seen or seen.add(key))]
    return thumb_file, deduped


def build_storage_presigned_url(
    output_file: str | None,
    presigned_url_builder,
) -> str | None:
    if not output_file:
        return None

    bucket_name, object_name = resolve_storage_object(output_file)
    return presigned_url_builder(object_name, bucket_name)
