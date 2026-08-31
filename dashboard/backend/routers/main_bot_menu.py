import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    MainBotMenuConfigRequest,
    MainBotMenuConfigResponse,
    TaskPricingConfigRequest,
    TaskPricingConfigResponse,
)
from src.database.core import get_db
from src.services.main_bot_menu_config_service import (
    MainBotMenuConfigValidationError,
    load_main_bot_menu_config_payload,
    save_main_bot_menu_config_payload,
)
from src.services.task_pricing_config_service import (
    TaskPricingConfigValidationError,
    load_task_pricing_config_payload,
    save_task_pricing_config_payload,
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


@router.get("/task-pricing", response_model=TaskPricingConfigResponse)
async def get_task_pricing_config(db: AsyncSession = Depends(get_db)):
    return await load_task_pricing_config_payload(db)


@router.put("/task-pricing", response_model=TaskPricingConfigResponse)
async def update_task_pricing_config(
    payload: TaskPricingConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await save_task_pricing_config_payload(
            db,
            payload.model_dump(),
        )
    except TaskPricingConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
