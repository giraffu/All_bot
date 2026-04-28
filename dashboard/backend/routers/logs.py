import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from dashboard.backend.schemas import LogListResponse
from src.services.log_service import LogService

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = logging.getLogger("dashboard.logs")

@router.get("", response_model=LogListResponse)
async def get_logs(
    user_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """
    Get user operation logs with filtering and pagination.
    Dates should be in YYYY-MM-DD format.
    """
    try:
        start_dt = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
        
        end_dt = None
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass

        result = await LogService.get_logs(
            user_id=user_id,
            operation_type=operation_type,
            start_date=start_dt,
            end_date=end_dt,
            page=page,
            page_size=page_size
        )
        return result
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
