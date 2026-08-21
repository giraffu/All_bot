from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.auth import TokenData, get_current_user
from src.database.core import get_db
from src.web_api.services.character_view_prompt_config_service import (
    list_character_view_configs,
    save_character_view_config,
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
