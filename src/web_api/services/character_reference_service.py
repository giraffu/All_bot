from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from config import MINIO_BUCKET
from shared.character_reference_sheet import (
    INGREDIENTS_CHARACTER_PANEL_VERSION,
    compose_ingredients_character_panel,
)
from src.core.billing_core import get_concurrent_task_limit_for_identity
from src.core.task_core import process_and_submit_task
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.database.models import CharacterReference, CharacterReferenceView
from src.domain_config.ltx_t2v import (
    CHARACTER_REFERENCE_BUILD_COST,
    CHARACTER_REFERENCE_BUILD_TASK_TYPE,
)
from src.quota import QuotaManager
from src.services.storage import storage
from src.web_api.common.utils import release_read_transaction
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services.task_submission_service import submit_generation_task

ALLOWED_CHARACTER_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CHARACTER_IMAGE_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
CHARACTER_READY_LIMIT = 20
CHARACTER_SOURCE_MAX_BYTES = 20 * 1024 * 1024
CHARACTER_VIEW_TASK_TYPES = {
    "free_edit": "edit",
    "free_edit_v2_5": "free_edit_v2_5",
    "free_edit_v3": "pornmaster_flux2_edit_bf16",
}

CHARACTER_VIEW_CATALOG = (
    {
        "type": "face_front",
        "label": "正脸图",
        "index": 1,
        "default_prompt": (
            "生成与源图为同一位成年人的正面脸部近景，严格保持身份、五官、发型、"
            "肤色和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何配饰，"
            "直视镜头，画面包括完整头部、裸露肩部和上胸。仅一个人物，纯白背景，"
            "不要文字、标签、边框或拼贴。"
        ),
    },
    {
        "type": "body_front",
        "label": "全身正面图",
        "index": 4,
        "default_prompt": (
            "生成与源图为同一位成年人的全身正面站立图，严格保持身份、五官、发型、"
            "肤色、身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何"
            "配饰，正对镜头自然站立，从头顶到双脚完整可见。仅一个人物，纯白背景，"
            "不要文字、标签、边框或拼贴。"
        ),
    },
    {
        "type": "body_side",
        "label": "全身侧面图",
        "index": 5,
        "default_prompt": (
            "生成与源图为同一位成年人的全身侧面站立图，严格保持身份、五官、发型、"
            "肤色、身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何"
            "配饰，身体与头部均向左旋转九十度，呈严格侧面，从头顶到双脚完整可见。"
            "仅一个人物，纯白背景，不要文字、标签、边框或拼贴。"
        ),
    },
    {
        "type": "body_back",
        "label": "全身背面图",
        "index": 6,
        "default_prompt": (
            "生成与源图为同一位成年人的全身背面站立图，严格保持身份、发型、肤色、"
            "身材比例和身体特征一致。人物完全裸体，不穿任何衣物，不佩戴任何配饰，"
            "背对镜头自然站立，不回头，从头顶到双脚完整可见。仅一个人物，纯白背景，"
            "不要文字、标签、边框或拼贴。"
        ),
    },
)


@dataclass(frozen=True, slots=True)
class ReadyCharacterIngredient:
    sheet_object_key: str
    description: str


CHARACTER_VIEW_BY_TYPE = {item["type"]: item for item in CHARACTER_VIEW_CATALOG}
CHARACTER_VIEW_ORDER = {
    item["type"]: int(item["index"]) for item in CHARACTER_VIEW_CATALOG
}
CHARACTER_REQUIRED_VIEW_TYPES = tuple(item["type"] for item in CHARACTER_VIEW_CATALOG)


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


def _presigned_object_url(value: str | None) -> str | None:
    if not value:
        return None
    object_key = value.removeprefix(f"{MINIO_BUCKET}/")
    return storage.get_presigned_url(object_key, bucket=MINIO_BUCKET) or None


def _view_response(row: CharacterReferenceView) -> dict:
    config = CHARACTER_VIEW_BY_TYPE[row.view_type]
    return {
        "type": row.view_type,
        "label": config["label"],
        "prompt": row.prompt,
        "default_prompt": config["default_prompt"],
        "status": row.status,
        "task_id": row.task_id,
        "object_key": row.object_key,
        "preview_url": _presigned_object_url(row.object_key),
    }


def _response(
    row: CharacterReference,
    views: list[CharacterReferenceView] | None = None,
) -> dict:
    preview = None
    if row.sheet_object_key:
        preview = _presigned_object_url(row.sheet_object_key)
    resolved_views = list(views if views is not None else getattr(row, "views", []))
    resolved_views.sort(key=lambda item: CHARACTER_VIEW_ORDER.get(item.view_type, 99))
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "task_id": row.task_id,
        "source_object_key": row.source_object_key,
        "sheet_object_key": row.sheet_object_key,
        "preview_url": preview,
        "views": [_view_response(view) for view in resolved_views],
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


async def get_character_batch_capacity(
    *,
    current_user,
    get_active_count_func=None,
    get_identity_func=None,
) -> dict[str, int]:
    if get_active_count_func is None:
        from src.services.redis_client import redis_client

        get_active_count_func = redis_client.get_user_concurrency
    if get_identity_func is None:
        from src.services.permission_service import permission_service

        get_identity_func = permission_service.get_user_identity
    identity = await get_identity_func(current_user.id)
    limit = get_concurrent_task_limit_for_identity(identity)
    active = max(int(await get_active_count_func(current_user.id)), 0)
    return {
        "limit": limit,
        "active": active,
        "available": max(limit - active, 0),
    }


async def _validate_character_source(*, user_id: int, source_object_key: str) -> str:
    object_key = _normalize_owned_upload_key(source_object_key, user_id)
    if not await storage.async_object_exists(MINIO_BUCKET, object_key):
        raise HTTPException(status_code=400, detail="源图不存在或上传尚未完成。")
    object_size = await storage.async_object_size(MINIO_BUCKET, object_key)
    if object_size is None:
        raise HTTPException(status_code=400, detail="无法校验源图大小，请重新上传。")
    if object_size > CHARACTER_SOURCE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="源图不能超过 20MB。")
    return object_key


async def _ensure_character_limit(*, db, user_id: int) -> None:
    ready_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(CharacterReference)
                .where(
                    CharacterReference.user_id == user_id,
                    CharacterReference.status.in_(("draft", "ready")),
                )
            )
        ).scalar_one()
    )
    if ready_count >= CHARACTER_READY_LIMIT:
        raise HTTPException(status_code=409, detail="每位用户最多保留 20 个人物。")


async def create_character_draft(*, db, current_user, payload) -> dict:
    object_key = await _validate_character_source(
        user_id=current_user.id,
        source_object_key=payload.source_object_key,
    )
    await _ensure_character_limit(db=db, user_id=current_user.id)
    row = CharacterReference(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        source_object_key=f"{MINIO_BUCKET}/{object_key}",
        task_id=str(uuid.uuid4()),
        status="draft",
    )
    db.add(row)
    await db.commit()
    return _response(row, [])


async def generate_character_view(
    *, db, current_user, character_id: str, view_type: str, payload
) -> dict:
    if view_type not in CHARACTER_VIEW_BY_TYPE:
        raise HTTPException(status_code=404, detail="未知的人物子图类型。")
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == current_user.id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    view = (
        await db.execute(
            select(CharacterReferenceView).where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
            )
        )
    ).scalar_one_or_none()
    if view is not None and view.status == "pending":
        raise HTTPException(status_code=409, detail="该子图正在生成，请稍候。")

    task_id = str(uuid.uuid4())
    if view is None:
        view = CharacterReferenceView(
            id=str(uuid.uuid4()),
            character_id=character_id,
            view_type=view_type,
            prompt=payload.prompt.strip(),
            task_id=task_id,
            status="pending",
        )
        db.add(view)
    else:
        view.prompt = payload.prompt.strip()
        view.task_id = task_id
        view.status = "pending"
        view.updated_at = datetime.now()
    await db.commit()
    try:
        task_type = CHARACTER_VIEW_TASK_TYPES[payload.engine]
        result = await submit_generation_task(
            req=TaskGenerateRequest(
                task_type=task_type,
                inputs={
                    "images": [character.source_object_key],
                    "record_history": False,
                },
                prompt=payload.prompt.strip(),
            ),
            current_user=current_user,
            get_balance=QuotaManager().get_credits,
            task_id_override=task_id,
            registry_metadata_extra={
                "_character_reference_view": {
                    "version": 1,
                    "character_id": character_id,
                    "view_type": view_type,
                },
                "record_history": False,
            },
            allow_contribute_override=False,
        )
    except Exception:
        view.status = "failed"
        view.updated_at = datetime.now()
        await db.commit()
        raise
    return {
        "character_id": character_id,
        "view_type": view_type,
        "task_id": result.task_id,
        "task_type": task_type,
        "status": "pending",
        "cost": result.cost,
        "balance_remaining": result.balance_remaining,
    }


async def upload_character_view(
    *, db, current_user, character_id: str, view_type: str, payload
) -> dict:
    config = CHARACTER_VIEW_BY_TYPE.get(view_type)
    if config is None:
        raise HTTPException(status_code=404, detail="未知的人物子图类型。")
    character = (
        await db.execute(
            select(CharacterReference).where(
                CharacterReference.id == character_id,
                CharacterReference.user_id == current_user.id,
                CharacterReference.status != "deleted",
            )
        )
    ).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="人物不存在。")
    view = (
        await db.execute(
            select(CharacterReferenceView).where(
                CharacterReferenceView.character_id == character_id,
                CharacterReferenceView.view_type == view_type,
            )
        )
    ).scalar_one_or_none()
    if view is not None and view.status == "pending":
        raise HTTPException(status_code=409, detail="该子图正在生成，不能上传替换。")

    source_key = await _validate_character_source(
        user_id=current_user.id,
        source_object_key=payload.source_object_key,
    )
    image_bytes = await asyncio.to_thread(
        storage.get_file_bytes,
        source_key,
        MINIO_BUCKET,
    )
    if not image_bytes:
        raise HTTPException(status_code=400, detail="无法读取上传图片，请重新上传。")
    extension = source_key.rsplit(".", 1)[-1].lower()
    durable_key = (
        f"character_references/{current_user.id}/{character_id}/views/"
        f"{view_type}-{uuid.uuid4().hex}.{extension}"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        image_bytes,
        durable_key,
        CHARACTER_IMAGE_CONTENT_TYPES[extension],
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物子图保存失败，请重试。")

    if view is None:
        view = CharacterReferenceView(
            id=str(uuid.uuid4()),
            character_id=character_id,
            view_type=view_type,
            prompt=config["default_prompt"],
            task_id=None,
            object_key=f"{MINIO_BUCKET}/{durable_key}",
            status="ready",
        )
        db.add(view)
    else:
        view.prompt = config["default_prompt"]
        view.task_id = None
        view.object_key = f"{MINIO_BUCKET}/{durable_key}"
        view.status = "ready"
        view.updated_at = datetime.now()
    await db.commit()
    return _view_response(view)


def _read_character_view_bytes(
    views: list[CharacterReferenceView],
) -> list[tuple[int, bytes]]:
    payloads: list[tuple[int, bytes]] = []
    for view in views:
        if not view.object_key:
            continue
        object_key = view.object_key.removeprefix(f"{MINIO_BUCKET}/")
        payload = storage.get_file_bytes(object_key, bucket=MINIO_BUCKET)
        if not payload:
            raise RuntimeError(
                f"character view object is unavailable: {view.view_type}"
            )
        payloads.append((CHARACTER_VIEW_ORDER[view.view_type] - 1, payload))
    return payloads


def _compose_character_sheet(payloads: list[tuple[int, bytes]]) -> bytes:
    return compose_ingredients_character_panel(payloads)


async def _materialize_saved_character_sheet(
    *, db, character: CharacterReference, views: list[CharacterReferenceView]
) -> dict:
    ready_by_type = {
        view.view_type: view
        for view in views
        if view.status == "ready" and view.object_key
    }
    missing_types = [
        view_type
        for view_type in CHARACTER_REQUIRED_VIEW_TYPES
        if view_type not in ready_by_type
    ]
    if missing_types:
        raise HTTPException(
            status_code=409,
            detail="请生成或上传并完成全部 4 张子图后再保存人物参考图。",
        )
    ready_views = [
        ready_by_type[view_type] for view_type in CHARACTER_REQUIRED_VIEW_TYPES
    ]
    payloads = await asyncio.to_thread(_read_character_view_bytes, ready_views)
    sheet = await asyncio.to_thread(_compose_character_sheet, payloads)
    object_key = (
        f"character_references/{character.user_id}/{character.id}/"
        f"{INGREDIENTS_CHARACTER_PANEL_VERSION}.png"
    )
    uploaded = await asyncio.to_thread(
        storage.upload_bytes,
        sheet,
        object_key,
        "image/png",
        MINIO_BUCKET,
    )
    if not uploaded:
        raise HTTPException(status_code=503, detail="人物参考图保存失败，请重试。")
    character.sheet_object_key = f"{MINIO_BUCKET}/{object_key}"
    character.status = "ready"
    character.updated_at = datetime.now()
    await db.commit()
    return _response(character, views)


async def save_character(*, db, user_id: int, character_id: str) -> dict:
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
        raise HTTPException(status_code=404, detail="人物不存在。")
    if not str(character.description or "").strip():
        raise HTTPException(status_code=409, detail="请先填写人物描述。")
    views = (
        (
            await db.execute(
                select(CharacterReferenceView).where(
                    CharacterReferenceView.character_id == character_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return await _materialize_saved_character_sheet(
        db=db,
        character=character,
        views=list(views),
    )


async def resolve_ready_character_sheet(
    *, db, user_id: int, character_id: str
) -> ReadyCharacterIngredient:
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
    if not row.sheet_object_key.endswith(f"/{INGREDIENTS_CHARACTER_PANEL_VERSION}.png"):
        raise HTTPException(
            status_code=400,
            detail="人物参考图版本已失效，请完成四张子图后重新保存。",
        )
    description = str(row.description or "").strip()
    if not description:
        raise HTTPException(
            status_code=400,
            detail="请先在人物图库填写人物描述。",
        )
    sheet = row.sheet_object_key
    await release_read_transaction(db)
    return ReadyCharacterIngredient(
        sheet_object_key=sheet,
        description=description,
    )


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
        description=payload.description.strip(),
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
        row.description = payload.description.strip()
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
        candidate = (
            await db.execute(
                select(CharacterReferenceView).where(
                    CharacterReferenceView.task_id == task_id
                )
            )
        ).scalar_one_or_none()
        if candidate is not None and hasattr(candidate, "view_type"):
            if candidate.status == "ready" and candidate.object_key:
                return
            candidate.status = "ready" if status == "done" and result_path else "failed"
            if candidate.status == "ready":
                candidate.object_key = result_path
            candidate.updated_at = datetime.now()
            await db.commit()
            return

        # Legacy all-at-once builds stored the task directly on the character row.
        row = candidate
        if row is None:
            row = (
                await db.execute(
                    select(CharacterReference).where(
                        CharacterReference.task_id == task_id
                    )
                )
            ).scalar_one_or_none()
        if row is None or row.status in {"ready", "deleted"}:
            return
        row.status = "ready" if status == "done" and result_path else "failed"
        if row.status == "ready":
            row.sheet_object_key = result_path
        row.updated_at = datetime.now()
        await db.commit()
