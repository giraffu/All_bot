import inspect

from fastapi import HTTPException

from src.services.affiliate_redeem_service import (
    AffiliateMembershipRedeemResult,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
    invalidate_affiliate_redeem_cache_after_commit,
    is_affiliate_membership_redeem_enabled,
    is_membership_settlement_v2_enabled,
    redeem_affiliate_balance_to_credits,
    redeem_affiliate_balance_to_membership,
)
from src.web_api.schemas.affiliate_redeem_schema import (
    AffiliateCreditsRedeemResponse,
    AffiliateMembershipRedeemResponse,
)


async def _commit_if_needed(db) -> bool:
    in_transaction = db.in_transaction()
    if inspect.isawaitable(in_transaction):
        in_transaction = await in_transaction
    if not in_transaction:
        return False
    await db.commit()
    return True


async def _invalidate_redeem_cache_if_needed(*, user_id: int, committed_here: bool) -> None:
    if committed_here:
        await invalidate_affiliate_redeem_cache_after_commit(user_id)


def _raise_affiliate_redeem_http_error(exc: Exception) -> None:
    if isinstance(exc, AffiliateRedeemConflictError):
        raise HTTPException(
            status_code=409,
            detail="同一幂等键已被不同兑换参数占用",
        ) from exc
    if isinstance(exc, AffiliateRedeemInsufficientBalanceError):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "返佣可用余额不足",
                "available_balance_usdt": float(exc.available_balance_usdt),
                "requested_amount_usdt": float(exc.requested_amount_usdt),
            },
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def build_affiliate_membership_redeem_response(
    result: AffiliateMembershipRedeemResult,
) -> AffiliateMembershipRedeemResponse:
    return AffiliateMembershipRedeemResponse(
        redeem_id=result.redeem_id,
        redeem_type=result.redeem_type,
        option_key=result.option_key,
        target_plan_id=result.target_plan_id,
        target_identity=result.target_identity,
        duration_days=result.duration_days,
        amount_usdt=f"{result.amount_usdt:.4f}",
        credits_granted=result.credits_granted,
        status=result.status,
        idempotency_key=result.idempotency_key,
        available_balance_usdt=f"{result.available_balance_usdt:.4f}",
        current_identity=result.current_identity,
        identity_expire_at=result.identity_expire_at,
        current_credits=result.current_credits,
        converted_days=result.converted_days,
        settlement_reason=result.settlement_reason,
    )


async def redeem_user_affiliate_credits_payload(
    *,
    db,
    user_id: int,
    amount_usdt,
    idempotency_key: str,
) -> AffiliateCreditsRedeemResponse:
    try:
        result = await redeem_affiliate_balance_to_credits(
            db,
            user_id=user_id,
            amount_usdt=amount_usdt,
            idempotency_key=idempotency_key,
        )
        committed_here = await _commit_if_needed(db)
    except Exception as exc:
        _raise_affiliate_redeem_http_error(exc)

    await _invalidate_redeem_cache_if_needed(
        user_id=user_id,
        committed_here=committed_here,
    )
    return AffiliateCreditsRedeemResponse(
        redeem_id=result.redeem_id,
        redeem_type=result.redeem_type,
        amount_usdt=float(result.amount_usdt),
        credits_granted=result.credits_granted,
        status=result.status,
        idempotency_key=result.idempotency_key,
        available_balance_usdt=float(result.available_balance_usdt),
        current_credits=result.current_credits,
        exchange_rate_snapshot=result.exchange_rate_snapshot,
        rounding_mode=result.rounding_mode,
    )


async def redeem_user_affiliate_membership_payload(
    *,
    db,
    user_id: int,
    option_key: str,
    idempotency_key: str,
) -> AffiliateMembershipRedeemResponse:
    if not (
        is_membership_settlement_v2_enabled()
        and is_affiliate_membership_redeem_enabled()
    ):
        raise HTTPException(status_code=404, detail="返佣兑换身份功能未开启")

    try:
        result = await redeem_affiliate_balance_to_membership(
            db,
            user_id=user_id,
            option_key=option_key,
            idempotency_key=idempotency_key,
        )
        committed_here = await _commit_if_needed(db)
    except Exception as exc:
        _raise_affiliate_redeem_http_error(exc)

    await _invalidate_redeem_cache_if_needed(
        user_id=user_id,
        committed_here=committed_here,
    )
    return build_affiliate_membership_redeem_response(result)
