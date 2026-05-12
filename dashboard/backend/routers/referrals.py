import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core import get_db
from src.services.referral_stats_service import query_referral_rewards

router = APIRouter(prefix="/api/referrals", tags=["referrals"])
logger = logging.getLogger("dashboard.referrals")


@router.get("/rewards")
async def get_referral_rewards(db: AsyncSession = Depends(get_db)):
    try:
        return await query_referral_rewards(db)

    except Exception as e:
        logger.error(f"Error getting referral rewards: {e}")
        raise HTTPException(status_code=500, detail=str(e))
