from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from config import MINIO_BUCKET
from src.database.models import CharacterViewImageTemplate
from src.services.storage import storage


CHARACTER_TEMPLATE_VIEW_TYPES = {"torso_front", "genitals_front", "pelvis_back"}
CHARACTER_TEMPLATE_GENDERS = {"neutral", "female", "male"}


def serialize_character_view_template(row: CharacterViewImageTemplate) -> dict:
    object_key = str(row.object_key).removeprefix(f"{MINIO_BUCKET}/")
    return {
        "id": row.id,
        "view_type": row.view_type,
        "name": row.name,
        "gender": row.gender,
        "sort_order": row.sort_order,
        "status": row.status,
        "object_key": row.object_key,
        "preview_url": storage.get_presigned_url(object_key, bucket=MINIO_BUCKET) or "",
    }


async def list_character_view_templates(db, *, include_disabled: bool = False) -> list[dict]:
    statement = select(CharacterViewImageTemplate)
    if not include_disabled:
        statement = statement.where(CharacterViewImageTemplate.status == "active")
    rows = (
        (
            await db.execute(
                statement.order_by(
                    CharacterViewImageTemplate.view_type,
                    CharacterViewImageTemplate.sort_order,
                    CharacterViewImageTemplate.created_at,
                )
            )
        )
        .scalars()
        .all()
    )
    return [serialize_character_view_template(row) for row in rows]


async def get_active_character_view_template(db, template_id: str):
    row = await db.get(CharacterViewImageTemplate, template_id)
    if row is None or row.status != "active":
        return None
    return row


async def create_character_view_template(
    db,
    *,
    view_type: str,
    name: str,
    gender: str,
    sort_order: int,
    image_bytes: bytes,
    content_type: str,
    created_by: str,
) -> dict:
    if view_type not in CHARACTER_TEMPLATE_VIEW_TYPES:
        raise ValueError("只有胸部、正面私处和背面私处支持图片模板。")
    if gender not in CHARACTER_TEMPLATE_GENDERS:
        raise ValueError("模板性别无效。")
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 80:
        raise ValueError("模板名称无效。")
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
    extension = extensions.get(content_type.lower())
    if extension is None:
        raise ValueError("仅支持 PNG/JPEG/WebP。")
    template_id = str(uuid.uuid4())
    object_key = f"character_assets/view_templates/{template_id}.{extension}"
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        image_bytes,
        object_key,
        content_type,
        MINIO_BUCKET,
    )
    if not uploaded:
        raise RuntimeError("模板图片保存失败。")
    row = CharacterViewImageTemplate(
        id=template_id,
        view_type=view_type,
        name=clean_name,
        gender=gender,
        object_key=f"{MINIO_BUCKET}/{object_key}",
        sort_order=sort_order,
        status="active",
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    return serialize_character_view_template(row)


async def update_character_view_template(db, *, template_id: str, payload) -> dict | None:
    row = await db.get(CharacterViewImageTemplate, template_id)
    if row is None:
        return None
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.gender is not None:
        if payload.gender not in CHARACTER_TEMPLATE_GENDERS:
            raise ValueError("模板性别无效。")
        row.gender = payload.gender
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise ValueError("模板状态无效。")
        row.status = payload.status
    await db.commit()
    return serialize_character_view_template(row)
