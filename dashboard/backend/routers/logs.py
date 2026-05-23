import logging
from typing import Optional

from fastapi import APIRouter

from dashboard.backend.schemas import LogListResponse
from dashboard.backend.routers.utils import run_dashboard_route
from dashboard.backend.services.log_admin_service import get_logs_payload

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = logging.getLogger("dashboard.logs")


@router.get("", response_model=LogListResponse)
async def get_logs(
    user_id: Optional[int] = None,
    operation_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get user operation logs with filtering and pagination.
    Dates should be in YYYY-MM-DD format.
    """
    return await run_dashboard_route(
        lambda: get_logs_payload(
            user_id=user_id,
            operation_type=operation_type,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        ),
        logger=logger,
        error_message="Error getting logs",
    )
