from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.referral_stats_service import (
    query_affiliate_redeem_records,
    query_referral_rewards,
)


async def get_referral_rewards_payload(*, db: AsyncSession):
    return await query_referral_rewards(db)


async def get_affiliate_redeem_records_payload(
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    redeem_type: str | None = None,
    db: AsyncSession,
):
    return await query_affiliate_redeem_records(
        db,
        page=page,
        page_size=page_size,
        query=query,
        redeem_type=redeem_type,
    )
