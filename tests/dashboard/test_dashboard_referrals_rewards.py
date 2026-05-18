from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend.auth import ADMIN_USERNAME, create_access_token
from dashboard.backend.main import app
from dashboard.backend.routers import referrals as referrals_router


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("unexpected execute call")
        return _FakeResult(self._results.pop(0))


@pytest.mark.asyncio
async def test_referrals_rewards_route_preserves_commission_sum_precision(monkeypatch):
    async def _fake_rates():
        return {
            "ton_to_usdt": 1.4,
            "rmb_to_usdt": 1.0 / 6.7,
            "stars_to_usdt": 0.013,
        }

    monkeypatch.setattr("src.services.referral_stats_service.get_exchange_rates", _fake_rates)

    inviter = SimpleNamespace(
        id=1,
        telegram_id=1001,
        full_name="Inviter",
        username="inviter",
    )
    invitee = SimpleNamespace(
        id=2,
        telegram_id=2002,
        full_name="Invitee",
        username="invitee",
    )
    paid_at = datetime(2026, 5, 18, 12, 0, 0)
    order_1 = SimpleNamespace(
        order_id="ORD-1",
        final_price=Decimal("10.00"),
        payment_channel="RMB",
        commission_usdt=Decimal("0.0149"),
        paid_at=paid_at,
        created_at=paid_at,
    )
    order_2 = SimpleNamespace(
        order_id="ORD-2",
        final_price=Decimal("10.00"),
        payment_channel="RMB",
        commission_usdt=Decimal("0.0149"),
        paid_at=paid_at,
        created_at=paid_at,
    )
    fake_db = _FakeSession(
        results=[
            [
                (order_1, inviter, invitee),
                (order_2, inviter, invitee),
            ],
            [(1, 1)],
        ]
    )

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[referrals_router.get_db] = _override_get_db
    token = create_access_token({"sub": ADMIN_USERNAME})

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/api/referrals/rewards",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(referrals_router.get_db, None)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["inviter_id"] == 1
    assert payload[0]["total_invitees"] == 1
    assert payload[0]["total_rmb"] == 20.0
    assert payload[0]["commission_usdt"] == 0.03
    assert payload[0]["invitees"][0]["commission_usdt"] == 0.03
    assert payload[0]["total_invitations"] == 1
