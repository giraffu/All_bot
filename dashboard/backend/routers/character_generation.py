from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.auth import TokenData, get_current_user
from src.database.core import get_db
from src.web_api.services.character_view_prompt_config_service import (
    list_character_view_configs,
    save_character_view_config,
)
from src.web_api.services.character_view_template_service import (
    create_character_view_template,
    list_character_view_templates,
    update_character_view_template,
)

router = APIRouter(
    prefix="/api/character-generation/configs",
    tags=["character-generation"],
)


class CharacterViewConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    prompt_templates: dict[str, str]
    tag_groups: list[str]
    tag_options: dict[str, dict[str, str]]


class CharacterViewTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    gender: str | None = None
    sort_order: int | None = None
    status: str | None = None


@router.get("")
async def get_character_view_configs(
    _admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_character_view_configs(db)


@router.put("/{view_type}")
async def update_character_view_config(
    view_type: str,
    payload: CharacterViewConfigUpdate,
    admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_character_view_config(
            db,
            view_type=view_type,
            payload=payload,
            updated_by=admin.username or "admin",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/templates")
async def get_character_view_image_templates(
    _admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_character_view_templates(db, include_disabled=True)


@router.post("/templates")
async def create_character_view_image_template(
    view_type: str = Form(...),
    name: str = Form(...),
    gender: str = Form("neutral"),
    sort_order: int = Form(0),
    file: UploadFile = File(...),
    admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await file.read(20 * 1024 * 1024 + 1)
    if not image_bytes or len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(413, "图片必须小于 20 MB。")
    try:
        return await create_character_view_template(
            db,
            view_type=view_type,
            name=name,
            gender=gender,
            sort_order=sort_order,
            image_bytes=image_bytes,
            content_type=str(file.content_type or ""),
            created_by=admin.username or "admin",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.patch("/templates/{template_id}")
async def update_character_view_image_template(
    template_id: str,
    payload: CharacterViewTemplatePatch,
    _admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await update_character_view_template(
            db, template_id=template_id, payload=payload
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "图片模板不存在。")
    return result
