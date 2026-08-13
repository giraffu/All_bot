from typing import Optional

from fastapi import APIRouter

from dashboard.backend.schemas import (
    GroupManageConfigRequest,
    GroupManageConfigResponse,
    PaidGroupGuardLogListResponse,
)
from dashboard.backend.services.group_manage_admin_service import (
    get_group_manage_config_payload,
    get_group_manage_logs_payload,
    update_group_manage_config_payload,
)

router = APIRouter(prefix="/api/group-manage", tags=["group_manage"])


@router.get("/config", response_model=GroupManageConfigResponse)
async def get_config():
    return await get_group_manage_config_payload()


@router.put("/config", response_model=GroupManageConfigResponse)
async def update_config(payload: GroupManageConfigRequest):
    return await update_group_manage_config_payload(payload)


@router.get("/logs", response_model=PaidGroupGuardLogListResponse)
async def get_logs(
    reason: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    return await get_group_manage_logs_payload(
        reason=reason, user_id=user_id, start_date=start_date, end_date=end_date,
        page=page, page_size=page_size,
    )
