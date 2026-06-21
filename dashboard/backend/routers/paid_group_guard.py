import logging
from typing import Optional

from fastapi import APIRouter

from dashboard.backend.routers.utils import run_dashboard_route
from dashboard.backend.schemas import (
    PaidGroupGuardConfigRequest,
    PaidGroupGuardConfigResponse,
    PaidGroupGuardLogListResponse,
)
from dashboard.backend.services.paid_group_guard_admin_service import (
    get_paid_group_guard_config_payload,
    get_paid_group_guard_logs_payload,
    update_paid_group_guard_config_payload,
)

router = APIRouter(prefix="/api/paid-group-guard", tags=["paid_group_guard"])
logger = logging.getLogger("dashboard.paid_group_guard")


@router.get("/config", response_model=PaidGroupGuardConfigResponse)
async def get_paid_group_guard_config():
    return await run_dashboard_route(
        get_paid_group_guard_config_payload,
        logger=logger,
        error_message="Error getting paid group guard config",
    )


@router.put("/config", response_model=PaidGroupGuardConfigResponse)
async def update_paid_group_guard_config(payload: PaidGroupGuardConfigRequest):
    return await run_dashboard_route(
        lambda: update_paid_group_guard_config_payload(payload),
        logger=logger,
        error_message="Error updating paid group guard config",
    )


@router.get("/logs", response_model=PaidGroupGuardLogListResponse)
async def get_paid_group_guard_logs(
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    return await run_dashboard_route(
        lambda: get_paid_group_guard_logs_payload(
            reason=reason,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        ),
        logger=logger,
        error_message="Error getting paid group guard logs",
    )
