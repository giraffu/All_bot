import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_user_analytics_returns_profile_distributions_and_leaderboards(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        assert args == (30,)
        return {
            "total_users": 100,
            "new_users": 12,
            "active_users": 34,
            "channel_members": 56,
            "password_users": 7,
            "submission_banned_users": 2,
            "generation_users": 45,
            "paying_users": 8,
            "total_credits": 999,
            "active_credits": 888,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "as new_users" in query and "checkin_history" in query:
            assert args == (30,)
            return [
                {
                    "day": "2026-06-24",
                    "new_users": 3,
                    "active_users": 9,
                    "checkins": 4,
                }
            ]
        if "identity_label" in query:
            return [{"label": "外门弟子", "count": 70}, {"label": "内门弟子", "count": 30}]
        if "user_group_label" in query:
            return [{"label": "凡人", "count": 60}, {"label": "练气期", "count": 40}]
        if "credit_bucket" in query:
            return [{"label": "1-10", "count": 64}]
        if "generation_bucket" in query:
            return [{"label": "11-20", "count": 18}]
        if "activity_segment" in query:
            assert args == (30,)
            return [{"label": "近周期活跃", "count": 34}]
        if "generation_rank" in query:
            assert args == (12,)
            return [
                {
                    "id": 101,
                    "username": "maker",
                    "full_name": "Maker",
                    "current_identity": "核心弟子",
                    "user_group": "筑基期",
                    "generation_count": 222,
                    "last_activity": "2026-06-25T10:00:00",
                }
            ]
        if "credits_rank" in query:
            assert args == (12,)
            return [{"id": 102, "username": None, "full_name": None, "credits": 1000}]
        if "referrals_rank" in query:
            assert args == (12,)
            return [{"id": 103, "username": "inviter", "full_name": "Inviter", "referral_count": 20}]
        if "recent_active_rank" in query:
            assert args == (12,)
            return [{"id": 104, "username": "fresh", "full_name": "Fresh", "last_activity": "2026-06-25T11:00:00"}]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/user-analytics?days=30&limit=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["limit"] == 12
    assert payload["summary"]["total_users"] == 100
    assert payload["distributions"]["identity"][0] == {"label": "外门弟子", "count": 70}
    assert payload["leaderboards"]["generation"][0]["username"] == "maker"
    assert payload["leaderboards"]["credits"][0]["full_name"] is None
    assert ("fetchrow",) == tuple(calls[0][:1])
