from unittest.mock import AsyncMock, patch

import pytest

from src.database.models import User
from src.web_api.routers.users import (
    redeem_current_user_affiliate_credits,
    redeem_current_user_affiliate_membership,
)
from src.web_api.schemas.affiliate_redeem_schema import (
    AffiliateCreditsRedeemRequest,
    AffiliateCreditsRedeemResponse,
    AffiliateMembershipRedeemRequest,
    AffiliateMembershipRedeemResponse,
)


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_credits_routes_to_service():
    payload = AffiliateCreditsRedeemRequest(
        amount_usdt="1.0000",
        idempotency_key="idem-router-credits",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    expected = AffiliateCreditsRedeemResponse(
        redeem_id=1,
        redeem_type="CREDITS",
        amount_usdt=1.0,
        credits_granted=130,
        status="SUCCESS",
        idempotency_key=payload.idempotency_key,
        available_balance_usdt=9.0,
        current_credits=130,
        exchange_rate_snapshot="1.0000 USDT = 130 credits",
        rounding_mode="FIXED_PACKAGE",
    )

    with patch(
        "src.web_api.routers.users.redeem_current_user_affiliate_credits_payload",
        new=AsyncMock(return_value=expected),
    ) as mock_service:
        response = await redeem_current_user_affiliate_credits(payload, current_user, db)

    assert response == expected
    mock_service.assert_awaited_once_with(
        payload=payload,
        current_user=current_user,
        db=db,
    )


@pytest.mark.asyncio
async def test_redeem_current_user_affiliate_membership_routes_to_service():
    payload = AffiliateMembershipRedeemRequest(
        option_key="inner_30d",
        idempotency_key="idem-router-membership",
    )
    current_user = User(id=123, username="tester")
    db = AsyncMock()
    expected = AffiliateMembershipRedeemResponse(
        redeem_id=2,
        redeem_type="MEMBERSHIP",
        option_key="inner_30d",
        target_plan_id=1,
        target_identity="内门弟子",
        duration_days=30,
        amount_usdt="3.0000",
        credits_granted=0,
        status="SUCCESS",
        idempotency_key=payload.idempotency_key,
        available_balance_usdt="7.0000",
        current_identity="内门弟子",
        identity_expire_at=None,
        current_credits=50,
        converted_days=30,
        settlement_reason="AFFILIATE_REDEEM",
    )

    with patch(
        "src.web_api.routers.users.redeem_current_user_affiliate_membership_payload",
        new=AsyncMock(return_value=expected),
    ) as mock_service:
        response = await redeem_current_user_affiliate_membership(
            payload,
            current_user,
            db,
        )

    assert response == expected
    mock_service.assert_awaited_once_with(
        payload=payload,
        current_user=current_user,
        db=db,
    )
