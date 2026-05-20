from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.routers import users as dashboard_users
from dashboard.backend.schemas import AdminGiftRequest


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.added = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return _ScalarResult(self.execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_admin_gift_plan_uses_unified_membership_settlement_when_enabled(
    monkeypatch,
):
    user = SimpleNamespace(
        id=2002,
        username="gift_user",
        credits=5,
        current_identity="外门弟子",
        identity_expire_at=None,
    )
    plan = SimpleNamespace(
        id=1,
        name="Gift Plan",
        identity_name="内门弟子",
        duration_days=30,
        reward_credits=100,
    )
    db = _FakeSession([user, plan])
    settle_mock = AsyncMock(return_value={"current_credits": 105})

    monkeypatch.setattr(
        dashboard_users, "is_membership_settlement_v2_enabled", lambda: True
    )
    monkeypatch.setattr(
        dashboard_users, "settle_membership_plan_in_session", settle_mock
    )

    result = await dashboard_users.admin_gift_plan(
        2002,
        AdminGiftRequest(plan_id=1, note="test"),
        db=db,
    )

    settle_mock.assert_awaited_once()
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert result["status"] == "ok"
