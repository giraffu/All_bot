"""Infrastructure-neutral media archive contracts and invariants."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from shared.r2_retention_contract import normalize_durable_media_key
from src.constants import VIDEO_TASK_TYPES


ARCHIVE_BUCKET = "allbot-media-archive-v1"
DERIVED_BUCKET = "allbot-media-derived-v1"
QUARANTINE_BUCKET = "allbot-media-quarantine-v1"

ASSET_STATUSES = frozenset(
    {
        "pending_probe",
        "source_offline",
        "found",
        "archived_verified",
        "provisional_missing",
        "confirmed_lost",
        "checksum_error",
        "external_unmanaged",
    }
)
_VIDEO_TASK_TYPE_SET = {task_type.lower() for task_type in VIDEO_TASK_TYPES}


@dataclass(frozen=True)
class MediaAssetSpec:
    history_id: int
    role: str
    ordinal: int
    source_ref: str

    @property
    def identity(self) -> tuple[str, int]:
        return self.role, self.ordinal


def _clean_ref(value: Any) -> str:
    return str(value or "").strip()


def _extra_paths(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        path = _clean_ref(value.get("path"))
        if path:
            yield path
        for key, nested in value.items():
            if key != "path":
                yield from _extra_paths(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _extra_paths(nested)


def extract_history_media_assets(history: Any) -> list[MediaAssetSpec]:
    """Return stable logical assets without deduplicating repeated references."""
    history_id = int(history.id)
    assets: list[MediaAssetSpec] = []
    inputs = [_clean_ref(item) for item in _clean_ref(history.input_file).split("|")]
    for ordinal, source_ref in enumerate(item for item in inputs if item):
        assets.append(MediaAssetSpec(history_id, "input", ordinal, source_ref))

    output_ref = _clean_ref(history.output_file)
    if output_ref:
        assets.append(MediaAssetSpec(history_id, "output", 0, output_ref))

    extra_outputs = (
        history.extra_outputs if isinstance(history.extra_outputs, dict) else {}
    )
    for name, value in extra_outputs.items():
        for ordinal, source_ref in enumerate(_extra_paths(value)):
            assets.append(
                MediaAssetSpec(history_id, f"extra:{name}", ordinal, source_ref)
            )
    return assets


def archive_blob_key(sha256: str, extension: str) -> str:
    digest = sha256.strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("sha256 must be a 64-character hexadecimal digest")
    ext = extension.strip().lower().lstrip(".") or "bin"
    if ext == "jpeg":
        ext = "jpg"
    ext = "".join(char for char in ext if char.isalnum()) or "bin"
    return str(
        PurePosixPath("blobs", "sha256", digest[:2], digest[2:4], f"{digest}.{ext}")
    )


def get_archive_media_type(history_type: str | None) -> str:
    normalized = str(history_type or "").lower()
    if normalized in _VIDEO_TASK_TYPE_SET or "video" in normalized:
        return "video"
    return "image"


def plan_archive_asset_restore_keys(
    *, task_id: str, source_ref: str
) -> set[str]:
    """Plan original R2 compatibility keys without loading runtime configuration."""
    if not task_id or not source_ref:
        return set()
    durable_key = normalize_durable_media_key(source_ref)
    if durable_key:
        return {durable_key}
    parsed = urlparse(source_ref)
    raw_key = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    basename = PurePosixPath(raw_key).name
    suffix = PurePosixPath(parsed.path if parsed.scheme else source_ref).suffix
    return {
        key
        for key in {
            f"history/{task_id}/original{suffix}",
            raw_key,
            basename,
            f"history/{task_id}/{basename}" if basename else "",
        }
        if key
    }


def plan_archive_thumbnail_restore_keys(
    *, task_id: str, source_ref: str, history_type: str | None
) -> set[str]:
    """Plan rebuilt thumbnail keys without loading storage or database adapters."""
    if not task_id or not source_ref:
        return set()
    media_type = get_archive_media_type(history_type)
    durable_key = normalize_durable_media_key(source_ref)
    if durable_key and durable_key.startswith("task-results/"):
        stem = durable_key.rsplit(".", 1)[0]
        return {
            f"{stem}{'_thumb.jpg' if media_type == 'video' else '_thumb.webp'}"
        }
    parsed = urlparse(source_ref)
    raw_key = (
        unquote(parsed.path.lstrip("/"))
        if parsed.scheme in {"http", "https"}
        else source_ref.lstrip("/")
    )
    stem = raw_key.rsplit(".", 1)[0]
    thumb_name = PurePosixPath(
        f"{stem}{'_thumb.jpg' if media_type == 'video' else '_thumb.webp'}"
    ).name
    return {
        f"history/{task_id}/{'thumb.jpg' if media_type == 'video' else 'thumb.webp'}",
        thumb_name,
    }


def receipts_cover_assets(
    assets: Iterable[MediaAssetSpec], receipts: Iterable[Any]
) -> bool:
    expected = {asset.identity for asset in assets}
    verified = {
        (str(receipt.role), int(receipt.ordinal))
        for receipt in receipts
        if receipt.status == "archived_verified"
        and len(str(receipt.sha256 or "")) == 64
    }
    return bool(expected) and expected.issubset(verified)


def media_manifest_hash(assets: Iterable[MediaAssetSpec]) -> str:
    manifest = [
        {"role": asset.role, "ordinal": asset.ordinal, "source_ref": asset.source_ref}
        for asset in assets
    ]
    payload = json.dumps(
        manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
