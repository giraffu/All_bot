from urllib.parse import quote

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters.storage_presenter_utils import build_storage_url
from src.media_paths import build_thumbnail_object_name, resolve_storage_object
from src.services.minimax_h3_history_context_service import (
    resolve_valid_minimax_h3_history_context,
)
from src.services.qqcc_regenerate_metadata import has_qqcc_regenerate_context


def _input_media_type(file_name: str) -> str:
    normalized = file_name.lower().split("?", 1)[0]
    if normalized.endswith((".mp3", ".wav", ".m4a", ".oga", ".opus", ".aac", ".flac")):
        return "audio"
    if normalized.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".ogg")):
        return "video"
    return "image"


def build_history_input_media_payload(*, history, storage_service) -> list[dict]:
    input_files = [
        item.strip()
        for item in str(getattr(history, "input_file", None) or "").split("|")
        if item.strip()
    ]
    input_urls = (
        build_history_input_file_url(
            input_file="|".join(input_files),
            storage_service=storage_service,
        )
        or ""
    ).split("|")
    preview_urls = (
        build_history_input_file_preview_url(
            input_file="|".join(input_files),
            storage_service=storage_service,
        )
        or ""
    ).split("|")
    is_h3_ref2v = getattr(history, "type", None) == "minimax_h3_ref2v"
    context = (
        resolve_valid_minimax_h3_history_context(
            task_type=history.type,
            extra_outputs=getattr(history, "extra_outputs", None),
        )
        if is_h3_ref2v
        else {}
    )
    reference_audio = str(context.get("reference_audio") or "").strip()
    previous_task_id = str(context.get("prev_task_id") or "").strip()
    is_h3_tail_anchor = (
        is_h3_ref2v
        and context.get("execution_mode") == "i2v"
        and bool(previous_task_id)
    )
    media = []
    reference_image_index = 0
    for index, file_name in enumerate(input_files):
        kind = (
            "audio"
            if is_h3_ref2v and file_name == reference_audio
            else _input_media_type(file_name)
        )
        label = ""
        if is_h3_ref2v and kind == "image":
            if is_h3_tail_anchor:
                label = "上一段尾帧"
            else:
                reference_image_index += 1
                label = f"参考图 {reference_image_index}"
        elif is_h3_ref2v and kind == "video":
            label = "输入视频"
        elif is_h3_ref2v and kind == "audio":
            label = "参考音频"
        media.append(
            {
                "file": file_name,
                "url": input_urls[index] if index < len(input_urls) else "",
                "preview_url": (
                    preview_urls[index] if index < len(preview_urls) else ""
                ),
                "kind": kind,
                "label": label,
            }
        )
    if not is_h3_ref2v:
        return media

    if previous_task_id and not any(item["kind"] == "video" for item in media):
        media.append(
            {
                "file": f"{previous_task_id}.mp4",
                "url": "",
                "preview_url": "",
                "resolve_url": (
                    f"/api/history/media/{quote(previous_task_id, safe='')}"
                ),
                "kind": "video",
                "label": "父段视频" if is_h3_tail_anchor else "输入视频",
            }
        )

    if reference_audio and reference_audio not in input_files:
        media.append(
            {
                "file": reference_audio,
                "url": build_history_input_file_url(
                    input_file=reference_audio,
                    storage_service=storage_service,
                )
                or "",
                "preview_url": "",
                "kind": "audio",
                "label": "参考音频",
            }
        )
    return media


def build_history_input_file_url(
    *, input_file: str | None, storage_service
) -> str | None:
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


def build_history_output_file_url(
    *, output_file: str | None, storage_service
) -> str | None:
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
    item_dict = {
        column.name: getattr(history, column.name)
        for column in history.__table__.columns
    }
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
    item_dict["input_media"] = build_history_input_media_payload(
        history=history,
        storage_service=storage_service,
    )

    resolved_output_url = output_file_url or build_history_output_file_url(
        output_file=history.output_file,
        storage_service=storage_service,
    )
    if resolved_output_url:
        item_dict["output_file_url"] = resolved_output_url
    if output_file_preview_url:
        item_dict["output_file_preview_url"] = output_file_preview_url

    return item_dict
