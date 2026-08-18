from __future__ import annotations

import asyncio
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import MINIO_BUCKET
from dashboard.backend.auth import TokenData, get_current_user
from shared.character_reference_sheet import compose_ingredients_character_panel
from src.core.task_core_types import (
    TaskSubmissionCommand,
    TaskSubmissionPolicy,
    TaskSubmissionSideEffectPlan,
)
from src.database.core import get_db
from src.database.models import (
    CharacterReference,
    OfficialCharacterAsset,
    OfficialCharacterAssetView,
    OfficialEnvironmentAsset,
)
from src.services.storage import storage
from src.task_application_runtime import get_task_application
from src.web_api.services.character_reference_service import (
    CHARACTER_REQUIRED_VIEW_TYPES,
    CHARACTER_VIEW_BY_TYPE,
    CHARACTER_VIEW_ORDER,
)

router = APIRouter(prefix="/api/reference-assets", tags=["reference-assets"])
ALLOWED_IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_BYTES = 20 * 1024 * 1024


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    sort_order: int = 0


class AssetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    status: str | None = None


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    engine: str = "free_edit_v3"


def _url(value: str | None) -> str | None:
    if not value:
        return None
    return (
        storage.get_presigned_url(
            value.removeprefix(f"{MINIO_BUCKET}/"), bucket=MINIO_BUCKET
        )
        or None
    )


def _character_payload(row) -> dict:
    views = sorted(
        row.views, key=lambda view: CHARACTER_VIEW_ORDER.get(view.view_type, 99)
    )
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "tags": row.tags or [],
        "sort_order": row.sort_order,
        "status": row.status,
        "preview_url": _url(row.sheet_object_key),
        "views": [
            {
                "type": view.view_type,
                "status": view.status,
                "prompt": view.prompt,
                "task_id": view.task_id,
                "preview_url": _url(view.object_key),
            }
            for view in views
        ],
    }


def _environment_payload(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "category": row.category or "",
        "tags": row.tags or [],
        "sort_order": row.sort_order,
        "status": row.status,
        "task_id": row.task_id,
        "preview_url": _url(row.object_key),
    }


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    extension = ALLOWED_IMAGE_TYPES.get(str(file.content_type or "").lower())
    if extension is None:
        raise HTTPException(415, "仅支持 PNG/JPEG/WebP。")
    payload = await file.read(MAX_BYTES + 1)
    if not payload or len(payload) > MAX_BYTES:
        raise HTTPException(413, "图片必须小于 20 MB。")
    return payload, extension


@router.get("/characters")
async def list_characters(db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(OfficialCharacterAsset).order_by(
                    OfficialCharacterAsset.sort_order
                )
            )
        )
        .scalars()
        .all()
    )
    return [_character_payload(row) for row in rows]


@router.post("/characters")
async def create_character(
    payload: AssetCreate,
    admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = OfficialCharacterAsset(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        description=payload.description.strip(),
        tags=payload.tags,
        sort_order=payload.sort_order,
        status="draft",
        created_by=admin.username or "admin",
    )
    db.add(row)
    for view_type in CHARACTER_REQUIRED_VIEW_TYPES:
        db.add(
            OfficialCharacterAssetView(
                id=str(uuid.uuid4()),
                character_id=row.id,
                view_type=view_type,
                prompt=CHARACTER_VIEW_BY_TYPE[view_type]["default_prompt"],
                status="pending",
            )
        )
    await db.commit()
    await db.refresh(row)
    return _character_payload(row)


@router.patch("/characters/{asset_id}")
async def patch_character(
    asset_id: str, payload: AssetPatch, db: AsyncSession = Depends(get_db)
):
    row = await db.get(OfficialCharacterAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方角色不存在。")
    for key in ("name", "description", "tags", "sort_order"):
        value = getattr(payload, key)
        if value is not None:
            setattr(row, key, value.strip() if isinstance(value, str) else value)
    if payload.status is not None:
        if payload.status not in {"draft", "ready", "published", "archived"}:
            raise HTTPException(400, "状态无效。")
        if payload.status == "published" and not row.sheet_object_key:
            raise HTTPException(409, "请先合成角色面板。")
        row.status = payload.status
    await db.commit()
    return _character_payload(row)


@router.post("/characters/{asset_id}/views/{view_type}/upload")
async def upload_character_view(
    asset_id: str, view_type: str, file: UploadFile, db: AsyncSession = Depends(get_db)
):
    if view_type not in CHARACTER_VIEW_BY_TYPE:
        raise HTTPException(404, "未知视图。")
    row = await db.get(OfficialCharacterAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方角色不存在。")
    payload, extension = await _read_upload(file)
    object_key = f"official_assets/characters/{asset_id}/views/{view_type}.{extension}"
    await asyncio.to_thread(
        storage.upload_bytes, payload, object_key, str(file.content_type), MINIO_BUCKET
    )
    view = next(item for item in row.views if item.view_type == view_type)
    view.object_key, view.status, view.task_id = (
        f"{MINIO_BUCKET}/{object_key}",
        "ready",
        None,
    )
    row.status = (
        "ready" if all(item.status == "ready" for item in row.views) else "draft"
    )
    await db.commit()
    return _character_payload(row)


@router.post("/characters/{asset_id}/source/upload")
async def upload_character_source(
    asset_id: str, file: UploadFile, db: AsyncSession = Depends(get_db)
):
    row = await db.get(OfficialCharacterAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方角色不存在。")
    payload, extension = await _read_upload(file)
    object_key = f"official_assets/characters/{asset_id}/source.{extension}"
    await asyncio.to_thread(
        storage.upload_bytes, payload, object_key, str(file.content_type), MINIO_BUCKET
    )
    row.source_object_key = f"{MINIO_BUCKET}/{object_key}"
    await db.commit()
    return _character_payload(row)


@router.post("/characters/{asset_id}/compose")
async def compose_character(asset_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(OfficialCharacterAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方角色不存在。")
    if any(view.status != "ready" or not view.object_key for view in row.views):
        raise HTTPException(409, "四张视图全部 ready 后才能合成。")
    payloads = [
        (
            CHARACTER_VIEW_ORDER[view.view_type] - 1,
            await asyncio.to_thread(
                storage.get_file_bytes,
                view.object_key.removeprefix(f"{MINIO_BUCKET}/"),
                MINIO_BUCKET,
            ),
        )
        for view in row.views
    ]
    panel = await asyncio.to_thread(compose_ingredients_character_panel, payloads)
    object_key = f"official_assets/characters/{asset_id}/panel.png"
    await asyncio.to_thread(
        storage.upload_bytes, panel, object_key, "image/png", MINIO_BUCKET
    )
    row.sheet_object_key, row.status = f"{MINIO_BUCKET}/{object_key}", "ready"
    await db.commit()
    return _character_payload(row)


@router.get("/environments")
async def list_environments(db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(OfficialEnvironmentAsset).order_by(
                    OfficialEnvironmentAsset.sort_order
                )
            )
        )
        .scalars()
        .all()
    )
    return [_environment_payload(row) for row in rows]


@router.post("/environments")
async def create_environment(
    payload: AssetCreate,
    admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = OfficialEnvironmentAsset(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        description=payload.description.strip(),
        category=payload.category.strip(),
        tags=payload.tags,
        sort_order=payload.sort_order,
        status="draft",
        created_by=admin.username or "admin",
    )
    db.add(row)
    await db.commit()
    return _environment_payload(row)


@router.patch("/environments/{asset_id}")
async def patch_environment(
    asset_id: str, payload: AssetPatch, db: AsyncSession = Depends(get_db)
):
    row = await db.get(OfficialEnvironmentAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方环境不存在。")
    for key in ("name", "description", "category", "tags", "sort_order"):
        value = getattr(payload, key)
        if value is not None:
            setattr(row, key, value.strip() if isinstance(value, str) else value)
    if payload.status is not None:
        if payload.status not in {"draft", "ready", "published", "archived"}:
            raise HTTPException(400, "状态无效。")
        if payload.status == "published" and not row.object_key:
            raise HTTPException(409, "请先上传或生成环境图。")
        row.status = payload.status
    await db.commit()
    return _environment_payload(row)


@router.post("/environments/{asset_id}/upload")
async def upload_environment(
    asset_id: str, file: UploadFile, db: AsyncSession = Depends(get_db)
):
    row = await db.get(OfficialEnvironmentAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方环境不存在。")
    payload, extension = await _read_upload(file)
    object_key = f"official_assets/environments/{asset_id}/image.{extension}"
    await asyncio.to_thread(
        storage.upload_bytes, payload, object_key, str(file.content_type), MINIO_BUCKET
    )
    row.object_key, row.status, row.task_id = (
        f"{MINIO_BUCKET}/{object_key}",
        "ready",
        None,
    )
    await db.commit()
    return _environment_payload(row)


@router.get("/private-characters")
async def list_private_characters(db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(CharacterReference)
                .where(CharacterReference.status != "deleted")
                .order_by(CharacterReference.created_at.desc())
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "status": row.status,
            "moderation_status": row.moderation_status,
            "moderation_reason": row.moderation_reason,
            "preview_url": _url(row.sheet_object_key),
        }
        for row in rows
    ]


class ModerationRequest(BaseModel):
    disabled: bool
    reason: str = Field(default="", max_length=255)


@router.put("/private-characters/{asset_id}/moderation")
async def moderate_private_character(
    asset_id: str, payload: ModerationRequest, db: AsyncSession = Depends(get_db)
):
    row = await db.get(CharacterReference, asset_id)
    if row is None:
        raise HTTPException(404, "用户角色不存在。")
    row.moderation_status = "disabled" if payload.disabled else "active"
    row.moderation_reason = payload.reason.strip() if payload.disabled else None
    await db.commit()
    return {"id": row.id, "moderation_status": row.moderation_status}


async def _submit_operator_task(
    *, task_type: str, inputs: dict, prompt: str, marker: dict
) -> dict:
    operator_id = int(os.getenv("DASHBOARD_OFFICIAL_ASSET_OPERATOR_USER_ID", "0"))
    task_id = str(uuid.uuid4())
    result = await get_task_application().submit(
        TaskSubmissionCommand(
            internal_user_id=operator_id,
            username="dashboard:official-assets",
            task_type=task_type,
            inputs={**inputs, "prompt": prompt},
            task_id=task_id,
            registry_metadata={"record_history": False, "_official_asset": marker},
        ),
        TaskSubmissionPolicy(
            client_type="dashboard:official-assets",
            cost_override=0,
            deduct_quota=False,
            check_lock=False,
            user_cancel_allowed=True,
            side_effect_plan=TaskSubmissionSideEffectPlan(
                attach_web_monitor=True
            ),
            allow_contribute_override=False,
        ),
    )
    return {"task_id": result["task_id"], "status": "pending", "cost": 0}


@router.post("/characters/{asset_id}/views/{view_type}/generate")
async def generate_character_view(
    asset_id: str,
    view_type: str,
    payload: GenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(OfficialCharacterAsset, asset_id)
    if row is None or view_type not in CHARACTER_VIEW_BY_TYPE:
        raise HTTPException(404, "角色或视图不存在。")
    if not row.source_object_key:
        raise HTTPException(409, "生成子图前需要上传角色源图。")
    view = next(item for item in row.views if item.view_type == view_type)
    result = await _submit_operator_task(
        task_type="pornmaster_flux2_edit_bf16",
        inputs={"images": [row.source_object_key]},
        prompt=payload.prompt,
        marker={"kind": "character_view", "asset_id": asset_id, "view_type": view_type},
    )
    view.prompt, view.task_id, view.status = (
        payload.prompt,
        result["task_id"],
        "pending",
    )
    await db.commit()
    return result


@router.post("/environments/{asset_id}/generate")
async def generate_environment(
    asset_id: str, payload: GenerateRequest, db: AsyncSession = Depends(get_db)
):
    row = await db.get(OfficialEnvironmentAsset, asset_id)
    if row is None:
        raise HTTPException(404, "官方环境不存在。")
    result = await _submit_operator_task(
        task_type="t2i-pornmaster-turbo",
        inputs={},
        prompt=payload.prompt,
        marker={"kind": "environment", "asset_id": asset_id},
    )
    row.task_id, row.status = result["task_id"], "draft"
    await db.commit()
    return result
