import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import HistoryListResponse, UserHistoryListResponse
from dashboard.backend.services.history_service import (
    HistoryCountCache,
    get_all_history_payload,
    get_user_history_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("dashboard.history")
history_count_cache = HistoryCountCache(ttl_seconds=300)


@router.get("/all", response_model=HistoryListResponse)
async def get_all_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    rating: Optional[int] = None,
    is_public: Optional[bool] = None,
    worker_id: Optional[str] = None,
    source: Optional[str] = None,
    username: Annotated[Optional[str], Query(max_length=100)] = None,
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
        username=username,
        count_cache=history_count_cache,
        logger_override=logger,
    )


@router.get("/{user_id}", response_model=UserHistoryListResponse)
async def get_user_history(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get history for a specific user"""
    return await get_user_history_payload(
        user_id=user_id,
        page=page,
        page_size=page_size,
        db=db,
        logger_override=logger,
    )
