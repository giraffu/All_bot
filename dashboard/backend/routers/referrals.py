import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.routers.utils import run_dashboard_route
from dashboard.backend.services.referral_admin_service import (
    get_affiliate_redeem_records_payload,
    get_referral_rewards_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/referrals", tags=["referrals"])
logger = logging.getLogger("dashboard.referrals")


@router.get("/rewards")
async def get_referral_rewards(db: AsyncSession = Depends(get_db)):
    return await run_dashboard_route(
        lambda: get_referral_rewards_payload(db=db),
        logger=logger,
        error_message="Error getting referral rewards",
    )


@router.get("/redeems")
async def get_affiliate_redeem_records(
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    redeem_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await run_dashboard_route(
        lambda: get_affiliate_redeem_records_payload(
            page=page,
            page_size=page_size,
            query=query,
            redeem_type=redeem_type,
            db=db,
        ),
        logger=logger,
        error_message="Error getting affiliate redeem records",
    )
