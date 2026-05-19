from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.database.models import User
from src.services.affiliate_redeem_service import (
    AffiliateCreditsRedeemResult,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
)
from src.web_api.routers.users import redeem_current_user_affiliate_credits
from src.web_api.schemas.affiliate_redeem_schema import AffiliateCreditsRedeemRequest


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_success():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.2345"),
        idempotency_key="idem-1",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = False

    with patch(
        "src.web_api.routers.users.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            return_value=AffiliateCreditsRedeemResult(
                redeem_id=1,
                redeem_type="CREDITS",
                amount_usdt=Decimal("1.2345"),
                credits_granted=111,
                status="SUCCESS",
                idempotency_key="idem-1",
                available_balance_usdt=Decimal("8.7655"),
                current_credits=222,
                exchange_rate_snapshot="1.0000 USDT = 90 credits",
                rounding_mode="ROUND_HALF_UP",
            )
        ),
    ):
        response = await redeem_current_user_affiliate_credits(payload, current_user, db)

    assert response.redeem_id == 1
    assert response.credits_granted == 111
    assert response.available_balance_usdt == 8.7655
    assert response.current_credits == 222


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_succeeds_even_when_post_commit_side_effects_fail():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.0000"),
        idempotency_key="idem-side-effects-fail",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = True

    with patch(
        "src.web_api.routers.users.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            return_value=AffiliateCreditsRedeemResult(
                redeem_id=9,
                redeem_type="CREDITS",
                amount_usdt=Decimal("1.0000"),
                credits_granted=90,
                status="SUCCESS",
                idempotency_key="idem-side-effects-fail",
                available_balance_usdt=Decimal("0.5000"),
                current_credits=90,
                exchange_rate_snapshot="1.0000 USDT = 90 credits",
                rounding_mode="ROUND_HALF_UP",
            )
        ),
    ) as mock_redeem:
        response = await redeem_current_user_affiliate_credits(payload, current_user, db)

    db.commit.assert_awaited_once()
    mock_redeem.assert_awaited_once()
    assert response.redeem_id == 9
    assert response.status == "SUCCESS"
    assert response.credits_granted == 90


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_invalidates_cache_after_commit():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.0000"),
        idempotency_key="idem-after-commit",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = True
    events: list[str] = []

    async def _commit():
        events.append("commit")

    async def _invalidate(user_id: int):
        assert user_id == current_user.id
        events.append("invalidate")

    db.commit.side_effect = _commit

    with (
        patch(
            "src.web_api.routers.users.redeem_affiliate_balance_to_credits",
            new=AsyncMock(
                return_value=AffiliateCreditsRedeemResult(
                    redeem_id=10,
                    redeem_type="CREDITS",
                    amount_usdt=Decimal("1.0000"),
                    credits_granted=90,
                    status="SUCCESS",
                    idempotency_key="idem-after-commit",
                    available_balance_usdt=Decimal("0.5000"),
                    current_credits=90,
                    exchange_rate_snapshot="1.0000 USDT = 90 credits",
                    rounding_mode="ROUND_HALF_UP",
                )
            ),
        ),
        patch(
            "src.web_api.routers.users.invalidate_affiliate_redeem_cache_after_commit",
            new=AsyncMock(side_effect=_invalidate),
        ),
    ):
        response = await redeem_current_user_affiliate_credits(payload, current_user, db)

    assert response.redeem_id == 10
    assert events == ["commit", "invalidate"]


def test_redeem_current_user_affiliate_credits_request_normalizes_amount_usdt():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.23456"),
        idempotency_key="idem-normalized-request",
    )

    assert payload.amount_usdt == Decimal("1.2346")


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_conflict():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("1.0000"),
        idempotency_key="idem-conflict",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = False

    with patch(
        "src.web_api.routers.users.redeem_affiliate_balance_to_credits",
        new=AsyncMock(side_effect=AffiliateRedeemConflictError("conflict")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await redeem_current_user_affiliate_credits(payload, current_user, db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "同一幂等键已被不同兑换参数占用"


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_insufficient_balance():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("2.0000"),
        idempotency_key="idem-balance",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = False

    with patch(
        "src.web_api.routers.users.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            side_effect=AffiliateRedeemInsufficientBalanceError(
                available_balance_usdt=Decimal("1.5000"),
                requested_amount_usdt=Decimal("2.0000"),
            )
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await redeem_current_user_affiliate_credits(payload, current_user, db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "message": "返佣可用余额不足",
        "available_balance_usdt": 1.5,
        "requested_amount_usdt": 2.0,
    }
