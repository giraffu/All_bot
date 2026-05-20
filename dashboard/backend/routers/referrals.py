import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.services.referral_stats_service import (
    query_affiliate_redeem_records,
    query_referral_rewards,
)

router = APIRouter(prefix="/api/referrals", tags=["referrals"])
logger = logging.getLogger("dashboard.referrals")


@router.get("/rewards")
async def get_referral_rewards(db: AsyncSession = Depends(get_db)):
    try:
        return await query_referral_rewards(db)

    except Exception as e:
        logger.error(f"Error getting referral rewards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/redeems")
async def get_affiliate_redeem_records(
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    redeem_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await query_affiliate_redeem_records(
            db,
            page=page,
            page_size=page_size,
            query=query,
            redeem_type=redeem_type,
        )
    except Exception as e:
        logger.error(f"Error getting affiliate redeem records: {e}")
        raise HTTPException(status_code=500, detail=str(e))
