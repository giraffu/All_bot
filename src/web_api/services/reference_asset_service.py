from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from fastapi import HTTPException

from config import MINIO_BUCKET
from src.media_paths import normalize_owned_user_upload_key
from src.core.task_core_types import CoreDomainError
from src.database.models import (
    CharacterReference,
    CharacterReferenceView,
    OfficialCharacterAsset,
    OfficialEnvironmentAsset,
)
from src.services.storage import storage
from src.web_api.services.prompt_optimization_service import (
    PROMPT_MEDIA_MAX_BYTES,
    normalize_owned_prompt_media_key,
)


@dataclass(frozen=True, slots=True)
class ResolvedReferenceSet:
    character_sheets: tuple[str, str]
    character_descriptions: tuple[str, str]
    environment_object_key: str
    environment_description: str


@dataclass(frozen=True, slots=True)
class ResolvedH3ReferenceSet:
    images: tuple[str, ...]
    descriptions: tuple[str, ...]


_H3_REFERENCE_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "mp4", "ogg", "oga", "opus"}


async def resolve_h3_reference_audio_ref(
    *,
    user_id: int,
    reference_audio_ref: dict,
    object_size: Callable[
        [str, str], Awaitable[int | None]
    ] = storage.async_object_size,
) -> str:
    if not isinstance(reference_audio_ref, dict) or set(reference_audio_ref) != {
        "source",
        "object_key",
    }:
        raise CoreDomainError("主角参考语音引用格式无效。")
    if reference_audio_ref.get("source") != "upload":
        raise CoreDomainError("主角参考语音仅支持当前用户上传的文件。")
    try:
        object_key = normalize_owned_user_upload_key(
            str(reference_audio_ref.get("object_key") or ""),
            user_id=user_id,
            allowed_extensions=_H3_REFERENCE_AUDIO_EXTENSIONS,
        )
    except ValueError as exc:
        if str(exc) == "object key extension is not allowed":
            raise CoreDomainError("主角参考语音仅支持 MP3/WAV/M4A/OGG/OPUS。") from exc
        raise CoreDomainError("主角参考语音必须属于当前用户。") from exc
    size = await object_size(MINIO_BUCKET, object_key)
    if size is None:
        raise CoreDomainError("主角参考语音不存在或暂不可读取。")
    if size > PROMPT_MEDIA_MAX_BYTES:
        raise CoreDomainError("主角参考语音不能超过 20 MB。")
    return object_key


_H3_CHARACTER_VIEW_DESCRIPTIONS = {
    "face_front": "front face view",
    "body_front": "legacy full-body front view",
    "body_front_nude": "nude full-body front view",
    "body_front_clothed": "clothed full-body front view",
    "body_side": "full-body side view",
    "body_back": "full-body back view",
    "torso_front": "front torso detail",
    "genitals_front": "front genital anatomy close-up",
    "pelvis_back": "rear pelvis detail",
    "custom_1": "custom character detail 1",
    "custom_2": "custom character detail 2",
    "custom_3": "custom character detail 3",
    "custom_4": "custom character detail 4",
}

_H3_CHARACTER_VIEW_COMPOSITION_GUIDANCE = {
    "face_front": (
        "Identity evidence only; do not copy this close-up crop, camera framing, "
        "or plain background."
    ),
    "body_front": (
        "Identity and body-proportion evidence only; do not copy the reference "
        "pose, camera framing, or plain background."
    ),
    "body_front_nude": (
        "Identity and body-proportion evidence only; do not copy the reference "
        "pose, camera framing, or plain background."
    ),
    "body_front_clothed": (
        "Identity, body-proportion, and clothing evidence only; do not copy the "
        "reference pose, camera framing, or plain background."
    ),
    "body_side": (
        "Identity and body-proportion evidence only; do not copy the reference "
        "pose, camera framing, or plain background."
    ),
    "body_back": (
        "Identity and body-proportion evidence only; do not copy the reference "
        "pose, camera framing, or plain background."
    ),
    "genitals_front": (
        "Localized anatomy evidence only; never use this close-up as output "
        "framing and never create an inset, overlay, split screen, or collage."
    ),
    "torso_front": (
        "Localized torso evidence only; do not use this crop as output framing."
    ),
    "pelvis_back": (
        "Localized rear anatomy evidence only; do not use this crop as output "
        "framing and never create an inset, overlay, split screen, or collage."
    ),
    "custom_1": "User-defined character evidence only; follow its description.",
    "custom_2": "User-defined character evidence only; follow its description.",
    "custom_3": "User-defined character evidence only; follow its description.",
    "custom_4": "User-defined character evidence only; follow its description.",
}


def _picture_labels(indices: list[int]) -> str:
    labels = [f"<Picture {index}>" for index in indices]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return " and ".join(labels)
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def build_h3_character_reference_binding(reference_refs: list[dict]) -> str:
    """Bind trusted character refs to target subjects without exposing object keys."""
    grouped_positions: dict[str, list[int]] = {}
    for index, raw in enumerate(reference_refs, start=1):
        if not isinstance(raw, dict) or raw.get("source") != "private_character_view":
            continue
        character_id = str(raw.get("character_id") or "").strip()
        if character_id:
            grouped_positions.setdefault(character_id, []).append(index)
    if not grouped_positions:
        return ""

    groups = list(grouped_positions.values())
    clauses: list[str] = []
    if len(groups) == 1:
        labels = _picture_labels(groups[0])
        if len(groups[0]) == 1:
            clauses.append(
                "The one and only person in the target video is the person from "
                f"{labels}. Render exactly one instance of this person."
            )
        else:
            clauses.append(
                f"{labels} are different views of the same one target character. "
                "The one and only person in the target video is the person shown in "
                "these pictures. Render exactly one instance of this character."
            )
    else:
        for positions in groups:
            labels = _picture_labels(positions)
            view_word = "is" if len(positions) == 1 else "are"
            clauses.append(
                f"{labels} {view_word} identity and appearance evidence for one target "
                "character. Render exactly one instance of this character."
            )

    return (
        "Reference-to-target binding (mandatory): "
        f"{' '.join(clauses)} Use character reference pictures only as identity and "
        "appearance evidence; do not show the reference pictures themselves. The output "
        "must be one full-frame continuous scene, never comparison views, contact sheets, "
        "split screens, grids, panels, inset images, or repeated bodies."
    )


async def resolve_h3_reference_refs(
    *,
    db,
    user_id: int,
    reference_refs: list[dict],
    object_size: Callable[
        [str, str], Awaitable[int | None]
    ] = storage.async_object_size,
    explicit_views_enabled: bool,
) -> ResolvedH3ReferenceSet:
    if not isinstance(reference_refs, list) or not 1 <= len(reference_refs) <= 4:
        raise CoreDomainError("H3 参考图必须包含 1 至 4 项。")

    images: list[str] = []
    descriptions: list[str] = []
    identities: set[tuple[str, ...]] = set()
    for raw in reference_refs:
        if not isinstance(raw, dict):
            raise CoreDomainError("H3 参考图引用格式无效。")
        source = str(raw.get("source") or "").strip()
        if source == "upload":
            if set(raw) != {"source", "object_key"}:
                raise CoreDomainError("上传参考图字段无效。")
            object_key = normalize_owned_prompt_media_key(
                str(raw.get("object_key") or ""), user_id
            )
            identity = (source, object_key)
            description = (
                "User-uploaded visual reference; use only visible identity, "
                "appearance, prop, or style evidence."
            )
        elif source == "private_character_view":
            if set(raw) != {"source", "character_id", "view_type"}:
                raise CoreDomainError("人物参考图字段无效。")
            character_id = str(raw.get("character_id") or "").strip()
            view_type = str(raw.get("view_type") or "").strip()
            if not character_id or view_type not in _H3_CHARACTER_VIEW_DESCRIPTIONS:
                raise CoreDomainError("人物参考图类型无效。")
            if (
                view_type in {"genitals_front", "pelvis_back"}
                and not explicit_views_enabled
            ):
                raise CoreDomainError("人物特写功能当前未开放。")
            character = (
                await db.execute(
                    select(CharacterReference).where(
                        CharacterReference.id == character_id,
                        CharacterReference.user_id == user_id,
                        CharacterReference.status != "deleted",
                    )
                )
            ).scalar_one_or_none()
            if character is None or character.status != "ready":
                raise CoreDomainError("人物不存在或尚未完成。")
            if getattr(character, "moderation_status", "active") != "active":
                raise CoreDomainError("人物已被停用。")
            view = (
                await db.execute(
                    select(CharacterReferenceView).where(
                        CharacterReferenceView.character_id == character_id,
                        CharacterReferenceView.view_type == view_type,
                    )
                )
            ).scalar_one_or_none()
            if view is None or view.status != "ready" or not view.object_key:
                raise CoreDomainError("所选人物视图尚未完成或已失效。")
            object_key = str(view.object_key).removeprefix(f"{MINIO_BUCKET}/")
            identity = (source, character_id, view_type)
            character_description = str(character.description or "").strip()
            view_description = str(getattr(view, "description", None) or "").strip()
            description = (
                f"Adult character {character.name}; "
                f"{_H3_CHARACTER_VIEW_DESCRIPTIONS[view_type]}; "
                f"same identity and appearance. "
                f"{_H3_CHARACTER_VIEW_COMPOSITION_GUIDANCE[view_type]} "
                f"{character_description} {view_description}"
            ).strip()
        else:
            raise CoreDomainError("H3 参考图来源无效。")

        if identity in identities:
            raise CoreDomainError("H3 参考图不能重复。")
        identities.add(identity)
        size = await object_size(MINIO_BUCKET, object_key)
        if size is None:
            raise CoreDomainError("H3 参考图不存在或暂不可读取。")
        if size > PROMPT_MEDIA_MAX_BYTES:
            raise CoreDomainError("单张 H3 参考图不能超过 20 MB。")
        images.append(object_key)
        descriptions.append(description)

    return ResolvedH3ReferenceSet(tuple(images), tuple(descriptions))


def _url(object_key: str | None) -> str | None:
    if not object_key:
        return None
    return (
        storage.get_presigned_url(
            object_key.removeprefix(f"{MINIO_BUCKET}/"), bucket=MINIO_BUCKET
        )
        or None
    )


async def list_published_characters(db) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(OfficialCharacterAsset)
                .where(OfficialCharacterAsset.status == "published")
                .order_by(
                    OfficialCharacterAsset.sort_order, OfficialCharacterAsset.created_at
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "source": "official",
            "name": row.name,
            "description": row.description or "",
            "tags": row.tags or [],
            "preview_url": _url(row.sheet_object_key),
        }
        for row in rows
    ]


async def list_published_environments(db) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(OfficialEnvironmentAsset)
                .where(OfficialEnvironmentAsset.status == "published")
                .order_by(
                    OfficialEnvironmentAsset.sort_order,
                    OfficialEnvironmentAsset.created_at,
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "source": "official",
            "name": row.name,
            "description": row.description or "",
            "category": row.category,
            "tags": row.tags or [],
            "preview_url": _url(row.object_key),
        }
        for row in rows
    ]


def normalize_reference_inputs(
    inputs: dict,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    refs = inputs.get("character_refs")
    env_ref = inputs.get("environment_ref")
    legacy_ids = inputs.get("character_ids")
    legacy_background = inputs.get("background_object_key")
    if refs is not None and legacy_ids is not None:
        raise CoreDomainError("新旧角色引用不能同时提交。")
    if env_ref is not None and legacy_background is not None:
        raise CoreDomainError("上传环境和环境引用不能同时提交。")
    if refs is None:
        refs = [{"source": "private", "id": str(value)} for value in (legacy_ids or [])]
    if env_ref is None and legacy_background:
        env_ref = {"source": "upload", "object_key": str(legacy_background)}
    if not isinstance(refs, list) or len(refs) != 2:
        raise CoreDomainError("请选择恰好 2 个角色。")
    normalized_refs: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for raw in refs:
        if not isinstance(raw, dict) or raw.get("source") not in {
            "private",
            "official",
        }:
            raise CoreDomainError("角色引用来源无效。")
        item = {"source": str(raw["source"]), "id": str(raw.get("id") or "").strip()}
        if not item["id"] or (item["source"], item["id"]) in identities:
            raise CoreDomainError("两个角色不能重复。")
        identities.add((item["source"], item["id"]))
        normalized_refs.append(item)
    if not isinstance(env_ref, dict) or env_ref.get("source") not in {
        "official",
        "upload",
    }:
        raise CoreDomainError("请选择一张官方环境图或上传环境图。")
    normalized_env = {"source": str(env_ref["source"])}
    key = "id" if normalized_env["source"] == "official" else "object_key"
    normalized_env[key] = str(env_ref.get(key) or "").strip()
    if not normalized_env[key]:
        raise CoreDomainError("环境引用不能为空。")
    return normalized_refs, normalized_env


async def resolve_reference_set(
    *,
    db,
    user_id: int,
    character_refs: list[dict],
    environment_ref: dict,
    object_size: Callable[[str, str], Awaitable[int | None]] | None = None,
) -> ResolvedReferenceSet:
    sheets: list[str] = []
    descriptions: list[str] = []
    for ref in character_refs:
        if ref["source"] == "private":
            from src.web_api.services.character_reference_service import (
                resolve_ready_character_sheet,
            )

            try:
                ingredient = await resolve_ready_character_sheet(
                    db=db, user_id=user_id, character_id=ref["id"]
                )
            except HTTPException as exc:
                raise CoreDomainError(str(exc.detail)) from exc
            sheets.append(ingredient.sheet_object_key)
            descriptions.append(ingredient.description)
            continue
        else:
            row = (
                await db.execute(
                    select(OfficialCharacterAsset).where(
                        OfficialCharacterAsset.id == ref["id"],
                        OfficialCharacterAsset.status == "published",
                    )
                )
            ).scalar_one_or_none()
        if row is None or not row.sheet_object_key:
            raise CoreDomainError("角色不存在、未就绪或已下架。")
        sheets.append(row.sheet_object_key)
        descriptions.append(str(row.description or "").strip())
    if environment_ref["source"] == "official":
        environment = (
            await db.execute(
                select(OfficialEnvironmentAsset).where(
                    OfficialEnvironmentAsset.id == environment_ref["id"],
                    OfficialEnvironmentAsset.status == "published",
                )
            )
        ).scalar_one_or_none()
        if environment is None or not environment.object_key:
            raise CoreDomainError("官方环境不存在或已下架。")
        environment_key = environment.object_key
        environment_description = str(environment.description or "").strip()
    else:
        environment_key = normalize_owned_prompt_media_key(
            environment_ref["object_key"], user_id
        )
        size_func = object_size or storage.async_object_size
        size = await size_func(MINIO_BUCKET, environment_key)
        if size is None:
            raise CoreDomainError("上传环境不存在或暂不可读取。")
        if size > PROMPT_MEDIA_MAX_BYTES:
            raise CoreDomainError("环境图不能超过 20 MB。")
        environment_description = ""
    return ResolvedReferenceSet(
        tuple(sheets), tuple(descriptions), environment_key, environment_description
    )
