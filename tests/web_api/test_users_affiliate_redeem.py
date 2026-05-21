from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.database.models import User
from src.services.affiliate_redeem_service import (
    AffiliateCreditsRedeemResult,
    AffiliateMembershipRedeemResult,
    AffiliateRedeemConflictError,
    AffiliateRedeemInsufficientBalanceError,
)
from src.web_api.schemas.affiliate_redeem_schema import (
    AffiliateCreditsRedeemRequest,
    AffiliateMembershipRedeemRequest,
)
from src.web_api.services.user_affiliate_redeem_api_service import (
    build_affiliate_membership_redeem_response,
    redeem_user_affiliate_credits_payload,
    redeem_user_affiliate_membership_payload,
)


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_success():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("3.0000"),
        idempotency_key="idem-1",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = False

    with patch(
        "src.web_api.services.user_affiliate_redeem_api_service.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            return_value=AffiliateCreditsRedeemResult(
                redeem_id=1,
                redeem_type="CREDITS",
                amount_usdt=Decimal("3.0000"),
                credits_granted=390,
                status="SUCCESS",
                idempotency_key="idem-1",
                available_balance_usdt=Decimal("7.0000"),
                current_credits=390,
                exchange_rate_snapshot="3.0000 USDT = 390 credits",
                rounding_mode="FIXED_PACKAGE",
            )
        ),
    ):
        response = await redeem_user_affiliate_credits_payload(
            db=db,
            user_id=current_user.id,
            amount_usdt=payload.amount_usdt,
            idempotency_key=payload.idempotency_key,
        )

    assert response.redeem_id == 1
    assert response.credits_granted == 390
    assert response.available_balance_usdt == 7.0
    assert response.current_credits == 390


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
        "src.web_api.services.user_affiliate_redeem_api_service.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            return_value=AffiliateCreditsRedeemResult(
                redeem_id=9,
                redeem_type="CREDITS",
                amount_usdt=Decimal("1.0000"),
                credits_granted=130,
                status="SUCCESS",
                idempotency_key="idem-side-effects-fail",
                available_balance_usdt=Decimal("0.5000"),
                current_credits=130,
                exchange_rate_snapshot="1.0000 USDT = 130 credits",
                rounding_mode="FIXED_PACKAGE",
            )
        ),
    ) as mock_redeem:
        response = await redeem_user_affiliate_credits_payload(
            db=db,
            user_id=current_user.id,
            amount_usdt=payload.amount_usdt,
            idempotency_key=payload.idempotency_key,
        )

    db.commit.assert_awaited_once()
    mock_redeem.assert_awaited_once()
    assert response.redeem_id == 9
    assert response.status == "SUCCESS"
    assert response.credits_granted == 130


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
            "src.web_api.services.user_affiliate_redeem_api_service.redeem_affiliate_balance_to_credits",
            new=AsyncMock(
                return_value=AffiliateCreditsRedeemResult(
                    redeem_id=10,
                    redeem_type="CREDITS",
                    amount_usdt=Decimal("1.0000"),
                    credits_granted=130,
                    status="SUCCESS",
                    idempotency_key="idem-after-commit",
                    available_balance_usdt=Decimal("0.5000"),
                    current_credits=130,
                    exchange_rate_snapshot="1.0000 USDT = 130 credits",
                    rounding_mode="FIXED_PACKAGE",
                )
            ),
        ),
        patch(
            "src.web_api.services.user_affiliate_redeem_api_service.invalidate_affiliate_redeem_cache_after_commit",
            new=AsyncMock(side_effect=_invalidate),
        ),
    ):
        response = await redeem_user_affiliate_credits_payload(
            db=db,
            user_id=current_user.id,
            amount_usdt=payload.amount_usdt,
            idempotency_key=payload.idempotency_key,
        )

    assert response.redeem_id == 10
    assert events == ["commit", "invalidate"]


def test_redeem_current_user_affiliate_credits_request_rejects_non_package_amount():
    with pytest.raises(ValueError, match="固定套餐"):
        AffiliateCreditsRedeemRequest(
            amount_usdt=Decimal("1.23456"),
            idempotency_key="idem-invalid-package-request",
        )


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
        "src.web_api.services.user_affiliate_redeem_api_service.redeem_affiliate_balance_to_credits",
        new=AsyncMock(side_effect=AffiliateRedeemConflictError("conflict")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await redeem_user_affiliate_credits_payload(
                db=db,
                user_id=current_user.id,
                amount_usdt=payload.amount_usdt,
                idempotency_key=payload.idempotency_key,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "同一幂等键已被不同兑换参数占用"


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_insufficient_balance():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt=Decimal("3.0000"),
        idempotency_key="idem-balance",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    db.in_transaction.return_value = False

    with patch(
        "src.web_api.services.user_affiliate_redeem_api_service.redeem_affiliate_balance_to_credits",
        new=AsyncMock(
            side_effect=AffiliateRedeemInsufficientBalanceError(
                available_balance_usdt=Decimal("1.5000"),
                requested_amount_usdt=Decimal("3.0000"),
            )
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await redeem_user_affiliate_credits_payload(
                db=db,
                user_id=current_user.id,
                amount_usdt=payload.amount_usdt,
                idempotency_key=payload.idempotency_key,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "message": "返佣可用余额不足",
        "available_balance_usdt": 1.5,
        "requested_amount_usdt": 3.0,
    }


def test_build_affiliate_membership_redeem_response_formats_decimal_fields():
    response = build_affiliate_membership_redeem_response(
        AffiliateMembershipRedeemResult(
            redeem_id=1,
            redeem_type="MEMBERSHIP",
            option_key="inner_30d",
            target_plan_id=1,
            target_identity="内门弟子",
            duration_days=30,
            amount_usdt=Decimal("3.0000"),
            credits_granted=0,
            status="SUCCESS",
            idempotency_key="idem-membership",
            available_balance_usdt=Decimal("7.5000"),
            current_identity="内门弟子",
            identity_expire_at=None,
            current_credits=10,
            converted_days=30,
            settlement_reason="AFFILIATE_REDEEM",
        )
    )

    assert response.amount_usdt == "3.0000"
    assert response.available_balance_usdt == "7.5000"
    assert response.target_identity == "内门弟子"


@pytest.mark.asyncio
async def test_redeem_user_affiliate_membership_payload_returns_404_when_feature_disabled():
    payload = AffiliateMembershipRedeemRequest(
        option_key="inner_30d",
        idempotency_key="idem-membership-disabled",
    )
    db = AsyncMock()

    with (
        patch(
            "src.web_api.services.user_affiliate_redeem_api_service.is_membership_settlement_v2_enabled",
            return_value=False,
        ),
        patch(
            "src.web_api.services.user_affiliate_redeem_api_service.is_affiliate_membership_redeem_enabled",
            return_value=True,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await redeem_user_affiliate_membership_payload(
                db=db,
                user_id=123,
                option_key=payload.option_key,
                idempotency_key=payload.idempotency_key,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "返佣兑换身份功能未开启"
