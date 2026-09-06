from __future__ import annotations

from config import MINIO_BUCKET
from src.core.task_core_types import CoreDomainError
from src.media_paths import normalize_owned_user_upload_key


PROMPT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def normalize_owned_prompt_media_key(value: str, user_id: int) -> str:
    try:
        return normalize_owned_user_upload_key(
            value,
            user_id=user_id,
            allowed_extensions=_ALLOWED_EXTENSIONS,
        )
    except ValueError as exc:
        if str(exc) == "object key extension is not allowed":
            raise CoreDomainError("优化素材仅支持 PNG/JPEG/WebP。") from exc
        raise CoreDomainError("优化素材必须属于当前用户。") from exc


def normalize_prompt_media_object_key(value: str) -> str:
    raw = str(value or "").strip().lstrip("/")
    return raw.removeprefix(f"{MINIO_BUCKET}/")
