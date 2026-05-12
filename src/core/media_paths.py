from pathlib import Path


def resolve_storage_object(output_file: str) -> tuple[str, str]:
    if output_file.startswith("bot-data/"):
        return "bot-data", output_file[len("bot-data/") :]
    if output_file.startswith("comfyui-temp/"):
        return "comfyui-temp", output_file[len("comfyui-temp/") :]
    bucket_name = "bot-data" if "/" in output_file else "comfyui-temp"
    return bucket_name, output_file


def get_media_type_from_history(history_type: str | None) -> str:
    if history_type and "video" in history_type.lower():
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


def build_legacy_r2_key(object_name: str) -> str:
    return object_name.split("/")[-1]
