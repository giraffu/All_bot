from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User
from src.web_api.dependencies import get_current_user, get_db
from src.web_api.schemas.character_schema import (
    CharacterBuildRequest,
    CharacterBuildResponse,
    CharacterPatchRequest,
    CharacterResponse,
)
from src.web_api.services.character_reference_service import (
    build_character,
    delete_character,
    list_characters,
    patch_character,
)

router = APIRouter()


@router.post("/build", response_model=CharacterBuildResponse)
async def create_character(
    payload: CharacterBuildRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_character(db=db, current_user=current_user, payload=payload)


@router.get("", response_model=list[CharacterResponse])
async def get_characters(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await list_characters(db=db, user_id=current_user.id)


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: str,
    payload: CharacterPatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await patch_character(
        db=db, user_id=current_user.id, character_id=character_id, payload=payload
    )


@router.delete("/{character_id}", status_code=204)
async def remove_character(
    character_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_character(db=db, user_id=current_user.id, character_id=character_id)
    return Response(status_code=204)
