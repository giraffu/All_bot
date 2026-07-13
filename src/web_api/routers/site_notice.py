from fastapi import APIRouter

from src.web_api.dependencies import CurrentUserDep, DbSessionDep
from src.web_api.schemas.site_notice_schema import SiteNoticeResponse
from src.web_api.services.site_notice_service import get_active_site_notice_payload

router = APIRouter(prefix="/api/app", tags=["app"])
__all__ = ["router"]


@router.get("/site-notice", response_model=SiteNoticeResponse)
async def get_site_notice(
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> SiteNoticeResponse:
    return await get_active_site_notice_payload(db=db, current_user=current_user)


@router.get("/site-notices", response_model=SiteNoticeResponse)
async def get_site_notice_center(
    current_user: CurrentUserDep,
    db: DbSessionDep,
) -> SiteNoticeResponse:
    return await get_active_site_notice_payload(db=db, current_user=current_user)
