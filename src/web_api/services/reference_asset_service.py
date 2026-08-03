from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import select
from fastapi import HTTPException

from config import MINIO_BUCKET
from src.core.task_core_types import CoreDomainError
from src.database.models import OfficialCharacterAsset, OfficialEnvironmentAsset
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
