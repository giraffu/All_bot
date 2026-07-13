import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import (
    SiteNoticeCreateRequest,
    SiteNoticeListResponse,
    SiteNoticeResponse,
    SiteNoticeUpdateRequest,
)
from dashboard.backend.services.site_notice_admin_service import (
    create_site_notice_payload,
    delete_site_notice_payload,
    get_site_notice_payload,
    list_site_notice_payloads,
    update_site_notice_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api", tags=["site_notice"])
logger = logging.getLogger("dashboard.site_notice")


@router.get("/site-notices", response_model=SiteNoticeListResponse)
async def list_site_notices(db: AsyncSession = Depends(get_db)):
    return await list_site_notice_payloads(db=db, logger_override=logger)


@router.get("/site-notices/{notice_id}", response_model=SiteNoticeResponse)
async def get_site_notice(notice_id: int, db: AsyncSession = Depends(get_db)):
    return await get_site_notice_payload(
        notice_id=notice_id,
        db=db,
        logger_override=logger,
    )


@router.post("/site-notices", response_model=SiteNoticeResponse)
async def create_site_notice(
    payload: SiteNoticeCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await create_site_notice_payload(
        payload=payload,
        db=db,
        logger_override=logger,
    )


@router.put("/site-notices/{notice_id}", response_model=SiteNoticeResponse)
async def update_site_notice(
    notice_id: int,
    payload: SiteNoticeUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    return await update_site_notice_payload(
        notice_id=notice_id,
        payload=payload,
        db=db,
        logger_override=logger,
    )


@router.delete("/site-notices/{notice_id}")
async def delete_site_notice(notice_id: int, db: AsyncSession = Depends(get_db)):
    return await delete_site_notice_payload(
        notice_id=notice_id,
        db=db,
        logger_override=logger,
    )
