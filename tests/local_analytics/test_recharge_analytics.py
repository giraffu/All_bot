import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_finance_returns_recharge_situation_details(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        assert args == (30,)
        if "finance_first_purchase" in query:
            return {
                "first_purchase_users": 4,
                "avg_hours_to_first_purchase": 12.5,
                "median_hours_to_first_purchase": 6.5,
                "first_day_payers": 2,
            }
        if "finance_invitation" in query:
            return {
                "invitee_payers": 3,
                "orders": 5,
                "rmb_amount": 100,
                "ton_amount": 2.5,
                "stars_amount": 200,
                "usdt_amount": 29.03,
            }
        if "finance_health" in query:
            return {
                "success_rate": 80,
                "pending_orders": 3,
                "pending_ratio": 12,
                "failure_rate": 8,
                "top_payer_share": 33,
                "internal_success_ratio": 5,
                "credits_per_usdt": 82.4,
            }
        return {
            "success_orders": 20,
            "pending_orders": 3,
            "failed_orders": 2,
            "non_success_orders": 5,
            "real_payers": 9,
            "new_payers": 4,
            "repeat_payers": 5,
            "rmb_amount": 1200,
            "ton_amount": 8.5,
            "stars_amount": 600,
            "usdt_amount": 228.36,
            "plan_reward_credits": 18000,
            "arppu_usdt": 25.37,
            "success_rate": 80,
            "rmb_avg_order": 100,
            "internal_success_orders": 1,
            "latest_success_at": "2026-06-25T12:00:00",
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "finance_daily" in query:
            assert args == (30,)
            return [
                {
                    "day": "2026-06-25",
                    "rmb_amount": 120,
                    "ton_amount": 1.5,
                    "stars_amount": 200,
                    "usdt_amount": 48.41,
                    "success_orders": 4,
                    "payers": 3,
                    "plan_reward_credits": 2400,
                    "inner_disciples": 1,
                    "core_disciples": 1,
                    "true_disciples": 0,
                    "pure_credit_orders": 2,
                }
            ]
        if "finance_hourly" in query:
            assert args == (30,)
            return [
                {
                    "hour": 12,
                    "success_orders": 3,
                    "plan_reward_credits": 1800,
                    "rmb_amount": 90,
                    "ton_amount": 0,
                    "stars_amount": 200,
                    "inner_disciples": 1,
                    "core_disciples": 0,
                    "true_disciples": 0,
                }
            ]
        if "finance_channels" in query:
            assert args == (30,)
            return [
                {
                    "channel": "RMB",
                    "success_orders": 12,
                    "pending_orders": 1,
                    "failed_orders": 1,
                    "payers": 6,
                    "amount": 1200,
                    "usdt_amount": 179.1,
                    "avg_order_amount": 100,
                    "plan_reward_credits": 7200,
                    "first_paid_at": "2026-06-01T00:00:00",
                    "last_paid_at": "2026-06-25T12:00:00",
                }
            ]
        if "finance_plans" in query:
            assert args == (30,)
            return [
                {
                    "plan_id": 5,
                    "plan_name": "200 Star 直购",
                    "identity_name": "纯灵石",
                    "duration_days": 0,
                    "configured_reward_credits": 600,
                    "success_orders": 8,
                    "all_orders": 10,
                    "payers": 5,
                    "rmb_amount": 300,
                    "ton_amount": 0,
                    "stars_amount": 1000,
                    "usdt_amount": 57.78,
                    "plan_reward_credits": 4800,
                    "success_rate": 80,
                    "first_paid_at": "2026-06-01T00:00:00",
                    "last_paid_at": "2026-06-25T12:00:00",
                }
            ]
        if "finance_segments" in query:
            assert args == ()
            return [{"segment": "首充用户", "users": 4, "orders": 4, "usdt_amount": 80, "avg_usdt_per_user": 20, "latest_paid_at": "2026-06-25T12:00:00"}]
        if "finance_top_payers" in query:
            assert args == (30, 12)
            return [{"id": 101, "username": "payer", "full_name": "Payer", "orders": 3, "rmb_amount": 300, "ton_amount": 2, "stars_amount": 0, "usdt_amount": 47.79, "plan_reward_credits": 3600, "latest_paid_at": "2026-06-25T12:00:00"}]
        if "finance_recent_orders" in query:
            assert args == (30, 12)
            return [{"id": 201, "order_id": "RMB_1", "business_order_id": "BIZ_1", "internal_user_id": 101, "username": "payer", "full_name": "Payer", "plan_name": "基础月卡", "payment_channel": "RMB", "status": "SUCCESS", "final_price": 30, "reward_credits": 400, "paid_at": "2026-06-25T12:00:00", "created_at": "2026-06-25T11:00:00", "is_internal_order": False}]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/finance?days=30&limit=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["limit"] == 12
    assert payload["summary"]["real_payers"] == 9
    assert payload["summary"]["internal_success_orders"] == 1
    assert payload["daily"][0]["plan_reward_credits"] == 2400
    assert payload["hourly"][0]["hour"] == 12
    assert payload["channels"][0]["channel"] == "RMB"
    assert payload["plans"][0]["identity_name"] == "纯灵石"
    assert payload["invitation"]["invitee_payers"] == 3
    assert payload["health"]["credits_per_usdt"] == 82.4
    assert payload["top_payers"][0]["username"] == "payer"
    assert payload["recent_orders"][0]["is_internal_order"] is False
    assert any(call[0] == "fetch" and call[2] == (30, 12) for call in calls)
