import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    MainBotMenuConfigRequest,
    MainBotMenuConfigResponse,
)
from src.database.core import get_db
from src.services.main_bot_menu_config_service import (
    MainBotMenuConfigValidationError,
    load_main_bot_menu_config_payload,
    save_main_bot_menu_config_payload,
)


router = APIRouter(prefix="/api/main-bot", tags=["main_bot_menu"])
logger = logging.getLogger("dashboard.main_bot_menu")


@router.get("/menu-config", response_model=MainBotMenuConfigResponse)
async def get_main_bot_menu_config(db: AsyncSession = Depends(get_db)):
    return await load_main_bot_menu_config_payload(db)


@router.put("/menu-config", response_model=MainBotMenuConfigResponse)
async def update_main_bot_menu_config(
    payload: MainBotMenuConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_main_bot_menu_config_payload(
            db,
            payload.model_dump(),
        )
    except MainBotMenuConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
