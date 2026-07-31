import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.routers.utils import run_dashboard_route
from dashboard.backend.services.referral_admin_service import (
    complete_affiliate_usdt_redeem_payload,
    get_affiliate_redeem_records_payload,
    get_referral_rewards_payload,
    reject_affiliate_usdt_redeem_payload,
)
from dashboard.backend.auth import TokenData, get_current_user
from src.services.affiliate_usdt_redeem_service import (
    AffiliateUsdtRedeemConflictError,
    AffiliateUsdtRedeemNotFoundError,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/referrals", tags=["referrals"])
logger = logging.getLogger("dashboard.referrals")


class CompleteUsdtRedeemRequest(BaseModel):
    payout_tx_hash: str = Field(min_length=1, max_length=128)
    admin_note: str | None = Field(default=None, max_length=500)


class RejectUsdtRedeemRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


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
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await run_dashboard_route(
        lambda: get_affiliate_redeem_records_payload(
            page=page,
            page_size=page_size,
            query=query,
            redeem_type=redeem_type,
            status=status,
            db=db,
        ),
        logger=logger,
        error_message="Error getting affiliate redeem records",
    )


def _raise_admin_redeem_error(exc: Exception):
    if isinstance(exc, AffiliateUsdtRedeemNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AffiliateUsdtRedeemConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.post("/redeems/{redeem_id}/complete")
async def complete_usdt_redeem(
    redeem_id: int,
    payload: CompleteUsdtRedeemRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    try:
        return await complete_affiliate_usdt_redeem_payload(
            redeem_id=redeem_id,
            payout_tx_hash=payload.payout_tx_hash,
            admin_note=payload.admin_note,
            processed_by=admin.username or "dashboard-admin",
            db=db,
        )
    except Exception as exc:
        _raise_admin_redeem_error(exc)


@router.post("/redeems/{redeem_id}/reject")
async def reject_usdt_redeem(
    redeem_id: int,
    payload: RejectUsdtRedeemRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    try:
        return await reject_affiliate_usdt_redeem_payload(
            redeem_id=redeem_id,
            reason=payload.reason,
            processed_by=admin.username or "dashboard-admin",
            db=db,
        )
    except Exception as exc:
        _raise_admin_redeem_error(exc)
