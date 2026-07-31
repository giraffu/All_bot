from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from dashboard.backend.routers import referrals as referrals_router
from dashboard.backend.services import referral_admin_service


@pytest.mark.asyncio
async def test_get_referral_rewards_payload_routes_to_stats_query(monkeypatch):
    query_mock = AsyncMock(return_value=[{"inviter_id": 1}])
    monkeypatch.setattr(referral_admin_service, "query_referral_rewards", query_mock)
    db = object()

    result = await referral_admin_service.get_referral_rewards_payload(db=db)

    assert result == [{"inviter_id": 1}]
    query_mock.assert_awaited_once_with(db)


@pytest.mark.asyncio
async def test_get_affiliate_redeem_records_payload_routes_query_params(monkeypatch):
    query_mock = AsyncMock(return_value={"items": [], "total": 0, "page": 2, "page_size": 5})
    monkeypatch.setattr(
        referral_admin_service,
        "query_affiliate_redeem_records",
        query_mock,
    )
    db = object()

    result = await referral_admin_service.get_affiliate_redeem_records_payload(
        page=2,
        page_size=5,
        query="alice",
        redeem_type="membership",
        status=None,
        db=db,
    )

    assert result["page"] == 2
    query_mock.assert_awaited_once_with(
        db,
        page=2,
        page_size=5,
        query="alice",
        redeem_type="membership",
        status=None,
    )


@pytest.mark.asyncio
async def test_get_affiliate_redeem_records_router_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0, "page": 1, "page_size": 20}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        referrals_router,
        "get_affiliate_redeem_records_payload",
        service_mock,
    )
    db = object()

    result = await referrals_router.get_affiliate_redeem_records(
        page=1,
        page_size=20,
        query="bob",
        redeem_type="cash",
        status=None,
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        query="bob",
        redeem_type="cash",
        status=None,
        db=db,
    )


@pytest.mark.asyncio
async def test_get_referral_rewards_router_wraps_service_exception(monkeypatch):
    service_mock = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(referrals_router, "get_referral_rewards_payload", service_mock)

    with pytest.raises(HTTPException) as exc_info:
        await referrals_router.get_referral_rewards(db=object())

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "boom"


@pytest.mark.asyncio
async def test_complete_usdt_redeem_commits_before_notification(monkeypatch):
    events = []
    result = SimpleNamespace(redeem_id=8, status="SUCCESS", user_id=1)
    complete_mock = AsyncMock(return_value=result)
    side_effect_mock = AsyncMock(side_effect=lambda **_: events.append("notify"))
    db = SimpleNamespace(commit=AsyncMock(side_effect=lambda: events.append("commit")))
    monkeypatch.setattr(
        referral_admin_service,
        "complete_affiliate_usdt_redeem",
        complete_mock,
    )
    monkeypatch.setattr(
        referral_admin_service,
        "_post_commit_redeem_side_effects",
        side_effect_mock,
    )

    response = await referral_admin_service.complete_affiliate_usdt_redeem_payload(
        redeem_id=8,
        payout_tx_hash="a" * 64,
        admin_note=None,
        processed_by="admin",
        db=db,
    )

    assert response == {"redeem_id": 8, "status": "SUCCESS"}
    assert events == ["commit", "notify"]


@pytest.mark.asyncio
async def test_post_commit_notification_failure_does_not_change_admin_result(
    monkeypatch,
):
    invalidate = AsyncMock()
    notify = AsyncMock(side_effect=RuntimeError("telegram unavailable"))
    execute_result = SimpleNamespace(scalar_one_or_none=lambda: 5340735895)
    db = SimpleNamespace(execute=AsyncMock(return_value=execute_result))
    monkeypatch.setattr(
        referral_admin_service,
        "invalidate_affiliate_redeem_cache_after_commit",
        invalidate,
    )
    monkeypatch.setattr(
        referral_admin_service,
        "send_affiliate_usdt_redeem_notification",
        notify,
    )
    result = SimpleNamespace(
        redeem_id=8,
        user_id=2,
        amount_usdt=5,
        status="SUCCESS",
        rejection_reason=None,
    )

    await referral_admin_service._post_commit_redeem_side_effects(
        db=db,
        result=result,
    )

    invalidate.assert_awaited_once_with(2)
    notify.assert_awaited_once()
