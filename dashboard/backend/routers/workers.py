from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import WorkerHistoryListResponse
from dashboard.backend.services.worker_admin_service import (
    get_worker_history_payload,
    get_worker_list_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("/list")
async def get_worker_list(db: AsyncSession = Depends(get_db)):
    """Get a list of all unique worker IDs"""
    return await get_worker_list_payload(db=db)


@router.get("/history", response_model=WorkerHistoryListResponse)
async def get_worker_history(
    worker_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get worker history with pagination and optional filtering by worker_id"""
    return await get_worker_history_payload(
        worker_id=worker_id,
        page=page,
        size=size,
        db=db,
    )
