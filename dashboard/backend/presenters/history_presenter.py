from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters.storage_presenter_utils import build_storage_url
from src.media_paths import build_thumbnail_object_name, resolve_storage_object
from src.services.qqcc_regenerate_metadata import has_qqcc_regenerate_context


def _input_media_type(file_name: str) -> str:
    normalized = file_name.lower().split("?", 1)[0]
    if normalized.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".ogg")):
        return "video"
    return "image"


def build_history_input_file_url(*, input_file: str | None, storage_service) -> str | None:
    if not input_file:
        return None

    urls: list[str] = []
    for file_name in input_file.split("|"):
        if file_name.startswith("template:"):
            template_path = file_name[9:]
            urls.append(
                build_storage_url(
                    storage_service=storage_service,
                    object_name=template_path,
                    bucket=MINIO_TEMPLATE_BUCKET,
                )
            )
        else:
            urls.append(
                build_storage_url(
                    storage_service=storage_service,
                    object_name=file_name,
                )
            )
    return "|".join(urls)


def build_history_input_file_preview_url(
    *,
    input_file: str | None,
    storage_service,
) -> str | None:
    """Build cheap file-specific thumbnail candidates without probing storage."""

    if not input_file:
        return None

    urls: list[str] = []
    for file_name in input_file.split("|"):
        if file_name.startswith("template:"):
            bucket = MINIO_TEMPLATE_BUCKET
            object_name = file_name[9:]
        else:
            bucket, object_name = resolve_storage_object(file_name)
        thumbnail_name = build_thumbnail_object_name(
            object_name,
            _input_media_type(file_name),
        )
        urls.append(
            build_storage_url(
                storage_service=storage_service,
                object_name=thumbnail_name,
                bucket=bucket,
            )
            or ""
        )
    return "|".join(urls)


def build_history_output_file_url(*, output_file: str | None, storage_service) -> str | None:
    if not output_file:
        return None
    if "/" not in output_file:
        return build_storage_url(
            storage_service=storage_service,
            object_name=output_file,
            bucket="comfyui-temp",
        )
    return build_storage_url(storage_service=storage_service, object_name=output_file)


def build_history_item_payload(
    *,
    history,
    storage_service,
    username: str | None = None,
    full_name: str | None = None,
    worker_id: str | None = None,
    private_client_type: str | None = None,
    output_file_url: str | None = None,
    output_file_preview_url: str | None = None,
) -> dict:
    item_dict = {column.name: getattr(history, column.name) for column in history.__table__.columns}
    if username is not None:
        item_dict["username"] = username
    if full_name is not None:
        item_dict["full_name"] = full_name
    item_dict["worker_id"] = worker_id
    if private_client_type:
        item_dict["source"] = private_client_type
    elif history.source == "bot" and has_qqcc_regenerate_context(
        getattr(history, "extra_outputs", None)
    ):
        item_dict["source"] = "bot:qqcc"

    input_file_url = build_history_input_file_url(
        input_file=history.input_file,
        storage_service=storage_service,
    )
    if input_file_url:
        item_dict["input_file_url"] = input_file_url

    input_file_preview_url = build_history_input_file_preview_url(
        input_file=history.input_file,
        storage_service=storage_service,
    )
    if input_file_preview_url:
        item_dict["input_file_preview_url"] = input_file_preview_url

    resolved_output_url = output_file_url or build_history_output_file_url(
        output_file=history.output_file,
        storage_service=storage_service,
    )
    if resolved_output_url:
        item_dict["output_file_url"] = resolved_output_url
    if output_file_preview_url:
        item_dict["output_file_preview_url"] = output_file_preview_url

    return item_dict
