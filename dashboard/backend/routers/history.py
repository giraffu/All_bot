import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import HistoryListResponse, HistoryResponse
from dashboard.backend.services.history_service import (
    get_all_history_payload,
    get_user_history_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("dashboard.history")


@router.get("/all", response_model=HistoryListResponse)
async def get_all_history(
    page: int = 1,
    page_size: int = 20,
    type: Optional[str] = None,
    rating: Optional[int] = None,
    is_public: Optional[bool] = None,
    worker_id: Optional[str] = None,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all history with pagination and multiple optional filters"""
    return await get_all_history_payload(
        db=db,
        page=page,
        page_size=page_size,
        type=type,
        rating=rating,
        is_public=is_public,
        worker_id=worker_id,
        source=source,
        logger_override=logger,
    )


@router.get("/{user_id}", response_model=List[HistoryResponse])
async def get_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get history for a specific user"""
    return await get_user_history_payload(
        user_id=user_id,
        db=db,
        logger_override=logger,
    )
