from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from config import MINIO_BUCKET
from src.core.task_core import process_and_submit_task
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.database.models import CharacterReference
from src.domain_config.ltx_t2v import (
    CHARACTER_REFERENCE_BUILD_COST,
    CHARACTER_REFERENCE_BUILD_TASK_TYPE,
)
from src.quota import QuotaManager
from src.services.storage import storage
from src.web_api.common.utils import release_read_transaction

ALLOWED_CHARACTER_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CHARACTER_READY_LIMIT = 20
CHARACTER_SOURCE_MAX_BYTES = 20 * 1024 * 1024


def character_features_enabled() -> bool:
    return os.getenv("LTX_T2V_BACKEND_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_owned_upload_key(value: str, user_id: int) -> str:
    raw = str(value or "").strip().lstrip("/")
    bucket_prefix = f"{MINIO_BUCKET}/"
    object_key = raw[len(bucket_prefix) :] if raw.startswith(bucket_prefix) else raw
    prefix = f"web_uploads/{user_id}/"
    extension = object_key.rsplit(".", 1)[-1].lower() if "." in object_key else ""
    if (
        not object_key.startswith(prefix)
        or extension not in ALLOWED_CHARACTER_EXTENSIONS
    ):
        raise HTTPException(
            status_code=400, detail="源图必须是当前用户上传的 PNG/JPEG/WebP。"
        )
    return object_key


def _response(row: CharacterReference) -> dict:
    preview = None
    if row.sheet_object_key:
        object_key = row.sheet_object_key.removeprefix(f"{MINIO_BUCKET}/")
        preview = storage.get_presigned_url(object_key, bucket=MINIO_BUCKET) or None
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "task_id": row.task_id,
        "source_object_key": row.source_object_key,
        "sheet_object_key": row.sheet_object_key,
        "preview_url": preview,
    }


async def list_characters(*, db, user_id: int) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(CharacterReference)
                .where(
                    CharacterReference.user_id == user_id,
                    CharacterReference.status != "deleted",
                )
                .order_by(CharacterReference.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_response(row) for row in rows]


async def resolve_ready_character_sheet(*, db, user_id: int, character_id: str) -> str:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None or row.status != "ready" or not row.sheet_object_key:
        raise HTTPException(status_code=400, detail="人物不存在、未就绪或已删除。")
    sheet = row.sheet_object_key
    await release_read_transaction(db)
    return sheet


async def build_character(*, db, current_user, payload) -> dict:
    object_key = _normalize_owned_upload_key(payload.source_object_key, current_user.id)
    if not await storage.async_object_exists(MINIO_BUCKET, object_key):
        raise HTTPException(status_code=400, detail="源图不存在或上传尚未完成。")
    object_size = await storage.async_object_size(MINIO_BUCKET, object_key)
    if object_size is None:
        raise HTTPException(status_code=400, detail="无法校验源图大小，请重新上传。")
    if object_size > CHARACTER_SOURCE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="源图不能超过 20MB。")
    ready_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(CharacterReference)
                .where(
                    CharacterReference.user_id == current_user.id,
                    CharacterReference.status == "ready",
                )
            )
        ).scalar_one()
    )
    if ready_count >= CHARACTER_READY_LIMIT:
        raise HTTPException(
            status_code=409, detail="每位用户最多保留 20 个已就绪人物。"
        )

    character_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    row = CharacterReference(
        id=character_id,
        user_id=current_user.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        source_object_key=f"{MINIO_BUCKET}/{object_key}",
        task_id=task_id,
        status="pending",
    )
    db.add(row)
    await db.commit()
    try:
        result = await process_and_submit_task(
            user_id=current_user.id,
            username=current_user.username,
            task_type=CHARACTER_REFERENCE_BUILD_TASK_TYPE,
            inputs={
                "images": [f"{MINIO_BUCKET}/{object_key}"],
                "character_id": character_id,
                "prompt": "Generate six separate consistent adult character reference views on pure black backgrounds: front close-up face, three-quarter face, front waist-up, front full body, side full body, back full body. Preserve identity, face, hairstyle, skin tone, body, clothing and accessories. No text, labels, borders or collage.",
            },
            task_id=task_id,
            submission_side_effect_plan=TaskSubmissionSideEffectPlan(
                attach_web_monitor=True
            ),
            cost_override=CHARACTER_REFERENCE_BUILD_COST,
            user_cancel_allowed=True,
            registry_metadata={"character_id": character_id},
            allow_contribute_override=False,
        )
    except Exception:
        row.status = "failed"
        row.updated_at = datetime.now()
        await db.commit()
        raise
    balance = await QuotaManager().get_credits(current_user.id)
    return {
        "character_id": character_id,
        "task_id": result["task_id"],
        "status": "pending",
        "cost": result["cost"],
        "balance_remaining": balance,
    }


async def patch_character(*, db, user_id: int, character_id: str, payload) -> dict:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.description is not None:
        row.description = payload.description.strip() or None
    row.updated_at = datetime.now()
    await db.commit()
    return _response(row)


async def delete_character(*, db, user_id: int, character_id: str) -> None:
    row = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == user_id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    if row.status == "pending":
        raise HTTPException(status_code=409, detail="人物仍在构建，请先取消任务。")
    row.status = "deleted"
    row.deleted_at = datetime.now()
    row.updated_at = datetime.now()
    await db.commit()


async def finalize_character_reference(
    *, task_id: str, status: str, result_path: str | None
) -> None:
    from src.database.core import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(CharacterReference).where(CharacterReference.task_id == task_id)
            )
        ).scalar_one_or_none()
        if row is None or row.status in {"ready", "deleted"}:
            return
        row.status = "ready" if status == "done" and result_path else "failed"
        if row.status == "ready":
            row.sheet_object_key = result_path
        row.updated_at = datetime.now()
        await db.commit()
