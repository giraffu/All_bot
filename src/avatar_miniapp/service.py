from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from config import MINIO_BUCKET
from src.database.models import (
    CharacterModelAsset,
    CharacterModelInputView,
    CharacterReference,
    CharacterRenderJob,
)
from src.services.storage import storage
from src.web_api.services.character_reference_service import list_characters

from .providers import LocalFixtureModelBuildProvider
from .schemas import RenderCreateRequest

NON_TERMINAL_BUILD_STATUSES = (
    "queued",
    "preparing_views",
    "reconstructing",
    "rigging",
)


def ensure_fixture_mode(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(
            status_code=404,
            detail={"reason": "FIXTURE_MODE_DISABLED"},
        )


def ensure_owned_asset(asset, *, user_id: int):
    if asset is None or int(asset.user_id) != int(user_id):
        raise HTTPException(
            status_code=404,
            detail={"reason": "MODEL_ASSET_NOT_FOUND"},
        )
    return asset


def ensure_render_job_can_cancel(job) -> None:
    if job.status not in {"queued", "rendering"}:
        raise HTTPException(
            status_code=409,
            detail={"reason": "RENDER_ALREADY_TERMINAL"},
        )


def fixture_mode_enabled() -> bool:
    return os.getenv("MINIAPP_FIXTURE_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _presigned_url(object_key: str | None) -> str | None:
    if not object_key:
        return None
    normalized = object_key.removeprefix(f"{MINIO_BUCKET}/")
    return storage.get_presigned_url(normalized, bucket=MINIO_BUCKET) or None


def serialize_asset(asset: CharacterModelAsset) -> dict:
    views = sorted(asset.input_views, key=lambda view: view.view_type)
    return {
        "id": asset.id,
        "character_id": asset.character_id,
        "version": asset.version,
        "provider": asset.provider,
        "status": asset.status,
        "error_code": asset.error_code,
        "model_url": _presigned_url(asset.model_object_key),
        "thumbnail_url": _presigned_url(asset.thumbnail_object_key),
        "rig_type": asset.rig_type,
        "animation_ids": list(asset.animation_ids or []),
        "metadata": dict(asset.model_metadata or {}),
        "views": [
            {
                "view_type": view.view_type,
                "status": view.status,
                "width": view.width,
                "height": view.height,
                "preview_url": _presigned_url(view.object_key),
            }
            for view in views
        ],
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def serialize_render_job(job: CharacterRenderJob) -> dict:
    return {
        "id": job.id,
        "asset_id": job.asset_id,
        "status": job.status,
        "recipe": dict(job.render_recipe),
        "error_code": job.error_code,
        "output_url": _presigned_url(job.output_object_key),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


async def list_mini_characters(*, db, user_id: int) -> list[dict]:
    characters = await list_characters(db=db, user_id=user_id)
    assets = (
        (
            await db.execute(
                select(CharacterModelAsset)
                .options(selectinload(CharacterModelAsset.input_views))
                .where(CharacterModelAsset.user_id == user_id)
                .order_by(
                    CharacterModelAsset.character_id,
                    CharacterModelAsset.version.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    latest_by_character: dict[str, CharacterModelAsset] = {}
    for asset in assets:
        latest_by_character.setdefault(asset.character_id, asset)
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "status": item["status"],
            "source_object_key": item["source_object_key"],
            "preview_url": item["preview_url"],
            "latest_model": (
                serialize_asset(latest_by_character[item["id"]])
                if item["id"] in latest_by_character
                else None
            ),
        }
        for item in characters
    ]


async def create_fixture_build(*, db, user_id: int, character_id: str) -> dict:
    ensure_fixture_mode(fixture_mode_enabled())
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(
            status_code=404,
            detail={"reason": "CHARACTER_NOT_FOUND"},
        )
    active = (
        await db.execute(
            select(CharacterModelAsset).where(
                CharacterModelAsset.character_id == character_id,
                CharacterModelAsset.status.in_(NON_TERMINAL_BUILD_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "MODEL_BUILD_ALREADY_ACTIVE",
                "asset_id": active.id,
            },
        )
    version = (
        int(
            (
                await db.execute(
                    select(
                        func.coalesce(func.max(CharacterModelAsset.version), 0)
                    ).where(CharacterModelAsset.character_id == character_id)
                )
            ).scalar_one()
        )
        + 1
    )
    now = datetime.now()
    asset = CharacterModelAsset(
        id=str(uuid.uuid4()),
        user_id=user_id,
        character_id=character_id,
        version=version,
        provider=LocalFixtureModelBuildProvider.provider_name,
        status="queued",
        animation_ids=[],
        model_metadata={},
        created_at=now,
        updated_at=now,
    )
    asset.input_views = [
        CharacterModelInputView(
            id=str(uuid.uuid4()),
            view_type=view_type,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        for view_type in LocalFixtureModelBuildProvider.view_types
    ]
    db.add(asset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"reason": "MODEL_BUILD_ALREADY_ACTIVE"},
        ) from exc
    return {"asset_id": asset.id, "status": asset.status}


async def get_owned_asset(*, db, user_id: int, asset_id: str) -> CharacterModelAsset:
    asset = (
        await db.execute(
            select(CharacterModelAsset)
            .options(selectinload(CharacterModelAsset.input_views))
            .where(CharacterModelAsset.id == asset_id)
        )
    ).scalar_one_or_none()
    return ensure_owned_asset(asset, user_id=user_id)


async def create_render_job(*, db, user_id: int, payload: RenderCreateRequest) -> dict:
    asset = await get_owned_asset(db=db, user_id=user_id, asset_id=payload.asset_id)
    if asset.status != "ready":
        raise HTTPException(
            status_code=409,
            detail={"reason": "MODEL_NOT_READY"},
        )
    now = datetime.now()
    job = CharacterRenderJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        asset_id=asset.id,
        status="queued",
        render_recipe=payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    await db.commit()
    return serialize_render_job(job)


async def get_owned_render_job(*, db, user_id: int, render_id: str):
    job = (
        await db.execute(
            select(CharacterRenderJob).where(CharacterRenderJob.id == render_id)
        )
    ).scalar_one_or_none()
    if job is None or int(job.user_id) != int(user_id):
        raise HTTPException(
            status_code=404,
            detail={"reason": "RENDER_JOB_NOT_FOUND"},
        )
    return job


async def cancel_render_job(*, db, user_id: int, render_id: str) -> dict:
    job = await get_owned_render_job(db=db, user_id=user_id, render_id=render_id)
    ensure_render_job_can_cancel(job)
    job.status = "cancelled"
    job.lease_owner = None
    job.lease_expires_at = None
    job.updated_at = datetime.now()
    await db.commit()
    return serialize_render_job(job)
