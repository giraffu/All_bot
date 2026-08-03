from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User
from src.web_api.dependencies import get_current_user, get_db
from src.web_api.services.reference_asset_service import (
    list_published_characters,
    list_published_environments,
)

router = APIRouter()


@router.get("/characters")
async def get_official_characters(
    _current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await list_published_characters(db)


@router.get("/environments")
async def get_official_environments(
    _current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await list_published_environments(db)
