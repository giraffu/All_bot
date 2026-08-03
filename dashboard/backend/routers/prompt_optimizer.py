from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.auth import TokenData, get_current_user
from src.database.core import get_db
from src.web_api.services.prompt_optimizer_config_service import (
    list_configs,
    save_config,
)

router = APIRouter(prefix="/api/prompt-optimizer/configs", tags=["prompt-optimizer"])


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    system_template: str = Field(min_length=1, max_length=50000)
    user_template: str = Field(min_length=1, max_length=10000)


@router.get("")
async def get_configs(db: AsyncSession = Depends(get_db)):
    return await list_configs(db)


@router.put("/{scene_key}")
async def update_config(
    scene_key: str,
    payload: ConfigUpdate,
    admin: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_config(
            db,
            scene_key=scene_key,
            payload=payload,
            updated_by=admin.username or "admin",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{scene_key}/preview")
async def preview_config(scene_key: str, payload: ConfigUpdate):
    from src.prompt_optimizer.config_snapshot import validate_config_templates

    try:
        validate_config_templates(payload.system_template, payload.user_template)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "scene_key": scene_key,
        "valid": True,
        "variables": [
            "profile_ref",
            "duration_seconds",
            "media_frame_instructions",
            "original_prompt",
            "character_descriptions",
            "environment_description",
        ],
    }
