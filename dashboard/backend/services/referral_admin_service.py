from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.referral_stats_service import (
    query_affiliate_redeem_records,
    query_referral_rewards,
)
from sqlalchemy import select

from src.database.models import User
from src.services.affiliate_redeem_service import (
    invalidate_affiliate_redeem_cache_after_commit,
)
from src.services.affiliate_usdt_notification_service import (
    send_affiliate_usdt_redeem_notification,
)
from src.services.affiliate_usdt_redeem_service import (
    complete_affiliate_usdt_redeem,
    reject_affiliate_usdt_redeem,
)

logger = logging.getLogger(__name__)


async def get_referral_rewards_payload(*, db: AsyncSession):
    return await query_referral_rewards(db)


async def get_affiliate_redeem_records_payload(
    *,
    page: int = 1,
    page_size: int = 20,
    query: str | None = None,
    redeem_type: str | None = None,
    status: str | None = None,
    db: AsyncSession,
):
    return await query_affiliate_redeem_records(
        db,
        page=page,
        page_size=page_size,
        query=query,
        redeem_type=redeem_type,
        status=status,
    )


async def _post_commit_redeem_side_effects(*, db, result) -> None:
    await invalidate_affiliate_redeem_cache_after_commit(result.user_id)
    try:
        telegram_id = (
            await db.execute(select(User.telegram_id).where(User.id == result.user_id))
        ).scalar_one_or_none()
        await send_affiliate_usdt_redeem_notification(
            telegram_id=telegram_id,
            redeem_id=result.redeem_id,
            amount_usdt=f"{result.amount_usdt:.4f}",
            status=result.status,
            rejection_reason=result.rejection_reason,
        )
    except Exception:
        logger.warning(
            "Post-commit affiliate USDT notification failed: redeem_id=%s",
            result.redeem_id,
            exc_info=True,
        )


async def complete_affiliate_usdt_redeem_payload(
    *,
    redeem_id: int,
    payout_tx_hash: str,
    admin_note: str | None,
    processed_by: str,
    db: AsyncSession,
):
    result = await complete_affiliate_usdt_redeem(
        db,
        redeem_id=redeem_id,
        payout_tx_hash=payout_tx_hash,
        admin_note=admin_note,
        processed_by=processed_by,
    )
    await db.commit()
    await _post_commit_redeem_side_effects(db=db, result=result)
    return {"redeem_id": result.redeem_id, "status": result.status}


async def reject_affiliate_usdt_redeem_payload(
    *,
    redeem_id: int,
    reason: str,
    processed_by: str,
    db: AsyncSession,
):
    result = await reject_affiliate_usdt_redeem(
        db,
        redeem_id=redeem_id,
        reason=reason,
        processed_by=processed_by,
    )
    await db.commit()
    await _post_commit_redeem_side_effects(db=db, result=result)
    return {"redeem_id": result.redeem_id, "status": result.status}
