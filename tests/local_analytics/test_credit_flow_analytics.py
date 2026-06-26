import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_credit_flow_analytics_returns_flow_health_and_risk_users(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
        if "credit_flow_health" in query:
            return {
                "paid_recharge_ratio": 25,
                "non_paid_grant_ratio": 50,
                "refund_to_generation_ratio": 7.69,
                "expense_coverage_ratio": 70,
                "top_income_user_share": 12.5,
                "checkin_pressure_ratio": 30,
            }
        return {
            "gross_income": 1000,
            "gross_expense": 700,
            "net_change": 300,
            "paid_recharge_income": 250,
            "non_paid_grant_income": 500,
            "refund_income": 50,
            "generation_expense": 650,
            "current_total_credits": 9000,
            "avg_daily_expense": 23.33,
            "balance_burn_days": 385.71,
            "internal_transfer_income": 20,
            "internal_transfer_expense": 20,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "credit_flow_daily" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
            return [
                {
                    "day": "2026-06-25",
                    "income": 100,
                    "expense": 70,
                    "net_change": 30,
                    "recharge_income": 25,
                    "checkin_income": 40,
                    "generation_expense": 65,
                    "refund_income": 5,
                }
            ]
        if "credit_flow_category" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES)
            return [
                {"category": "充值/套餐发放", "direction": "income", "events": 3, "users": 2, "income": 250, "expense": 0, "net_change": 250},
                {"category": "签到", "direction": "income", "events": 20, "users": 20, "income": 300, "expense": 0, "net_change": 300},
                {"category": "退款/补偿", "direction": "income", "events": 2, "users": 1, "income": 50, "expense": 0, "net_change": 50},
                {"category": "Gallery 解锁收入", "direction": "income", "events": 1, "users": 1, "income": 20, "expense": 0, "net_change": 20},
                {"category": "Gallery 解锁支出", "direction": "expense", "events": 1, "users": 1, "income": 0, "expense": 20, "net_change": -20},
            ]
        if "composition_identity" in query:
            assert args == (30,)
            return [{"label": "外门弟子", "users": 10, "events": 30, "income": 500}]
        if "composition_user_group" in query:
            assert args == (30,)
            return [{"label": "凡人", "users": 12, "events": 32, "income": 520}]
        if "composition_channel_member" in query:
            assert args == (30,)
            return [{"label": "入宗门", "users": 8, "events": 20, "income": 400}]
        if "composition_payer" in query:
            assert args == (30,)
            return [{"label": "未付费用户", "users": 9, "events": 25, "income": 480}]
        if "risk_user_rank" in query:
            assert args == (30, analytics_main.GENERATION_OPERATION_TYPES, 12)
            return [
                {
                    "id": 101,
                    "username": "risk_user",
                    "full_name": "Risk User",
                    "current_identity": "外门弟子",
                    "user_group": "凡人",
                    "risk_score": 75,
                    "risk_reasons": ["签到高且低消耗", "非付费净增高"],
                    "income": 500,
                    "expense": 25,
                    "net_change": 475,
                    "checkin_income": 300,
                    "referral_income": 120,
                    "refund_income": 50,
                    "recharge_income": 0,
                    "generation_expense": 20,
                    "current_balance": 900,
                    "is_channel_member": False,
                }
            ]
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/credit-flow-analytics?days=30&limit=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 30
    assert payload["limit"] == 12
    assert payload["summary"]["gross_income"] == 1000
    assert payload["categories"][0]["category"] == "充值/套餐发放"
    assert {row["category"] for row in payload["categories"]} >= {"签到", "退款/补偿", "Gallery 解锁收入", "Gallery 解锁支出"}
    assert payload["composition"]["identity"][0]["label"] == "外门弟子"
    assert payload["health"]["flags"]
    assert payload["risk_users"][0]["username"] == "risk_user"
    assert any(call[0] == "fetch" and call[2] == (30, analytics_main.GENERATION_OPERATION_TYPES, 12) for call in calls)
