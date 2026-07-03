import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import QqccBotConfigRequest, QqccBotConfigResponse
from src.database.core import get_db
from src.services.qqcc_config_service import (
    load_qqcc_config_payload,
    save_qqcc_config_payload,
)

router = APIRouter(prefix="/api/qqcc", tags=["qqcc"])
logger = logging.getLogger("dashboard.qqcc")


@router.get("/config", response_model=QqccBotConfigResponse)
async def get_qqcc_config(db: AsyncSession = Depends(get_db)):
    return await load_qqcc_config_payload(db)


@router.put("/config", response_model=QqccBotConfigResponse)
async def update_qqcc_config(
    payload: QqccBotConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    return await save_qqcc_config_payload(db, payload.model_dump(exclude_unset=True))
