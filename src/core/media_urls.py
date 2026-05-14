from src.core.media_paths import (
    build_history_r2_media_key,
    build_history_r2_thumbnail_key,
    build_legacy_r2_key,
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
    candidates.append(build_legacy_r2_key(output_file))

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
    candidates.append(build_legacy_r2_key(thumb_file))

    seen = set()
    deduped = [key for key in candidates if key and not (key in seen or seen.add(key))]
    return thumb_file, deduped


def build_public_r2_url(
    *,
    output_file: str | None,
    public_url_builder,
    task_id: str | None = None,
    preferred_r2_object_name: str | None = None,
) -> str:
    if not output_file:
        return ""

    for object_key in build_r2_media_key_candidates(
        output_file=output_file,
        task_id=task_id,
        preferred_r2_object_name=preferred_r2_object_name,
    ):
        url = public_url_builder(object_key)
        if url:
            return url
    return output_file
