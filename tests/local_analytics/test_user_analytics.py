from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_user_analytics_returns_profile_distributions_and_leaderboards(monkeypatch):
    calls = []

    async def fake_fetchrow(query, *args):
        calls.append(("fetchrow", query, args))
        if "to_regclass('public.analytics_user_profile_daily_snapshots')" in query:
            assert args == ()
            return {"table_name": "analytics_user_profile_daily_snapshots"}
        assert args == (
            30,
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
        )
        assert "coalesce(users.checkin_count, 0) > 7" in query
        assert "orders.status = 'SUCCESS'" in query
        assert "payment_channel in ('RMB', 'TON', 'XTR')" in query
        assert "real_success_payers as" in query
        assert "coalesce(final_price, 0) > 0" in query
        assert "high_quality_referral_exempt_users" in query
        assert "low_trust_exempt_users as" in query
        assert "period_generation_users as" in query
        assert "successful_invitees_count * 100 > referral_relations * 3" in query
        assert "avg(invitee_recharge_rate)" in query
        assert "else 0" in query
        assert "from affiliate_transactions" in query
        return {
            "total_users": 100,
            "new_users": 12,
            "active_users": 34,
            "channel_members": 56,
            "password_users": 7,
            "submission_banned_users": 2,
            "generation_users": 45,
            "paying_users": 8,
            "paying_channel_members": 6,
            "paying_generation_users": 5,
            "active_paying_users": 4,
            "recharge_rate_total_users": 8.0,
            "recharge_rate_channel_members": 10.71,
            "recharge_rate_generation_users": 11.11,
            "recharge_rate_active_users": 11.76,
            "avg_inviter_invitee_recharge_rate": 12.34,
            "inviter_recharge_rate_sample_size": 9,
            "total_credits": 999,
            "active_credits": 888,
            "low_trust_free_tier_users": 6,
            "low_trust_active_users": 4,
            "low_trust_generation_users": 5,
            "low_trust_total_credits": 321,
            "low_trust_exempt_users": 3,
            "low_trust_inviters_count": 4,
            "low_trust_non_low_trust_invitees_count": 13,
            "low_trust_recharged_invitees_count": 2,
            "referral_relations": 44,
            "inviters_count": 9,
            "invitee_channel_members": 18,
            "invitee_generation_users": 16,
            "recharged_invitees_count": 7,
            "invitee_recharge_orders": 11,
            "invitee_recharge_total_rmb": 88.0,
            "invitee_recharge_total_ton": 2.5,
            "invitee_recharge_total_stars": 120,
            "invitee_recharge_total_usdt": 35.6,
            "affiliate_total_commission_usdt": 9.99,
            "affiliate_spent_commission_usdt": 1.11,
            "affiliate_available_balance_usdt": 8.88,
        }

    async def fake_fetch(query, *args):
        calls.append(("fetch", query, args))
        if "as new_users" in query and "checkin_history" in query:
            assert args == (30, None, None)
            return [
                {
                    "day": "2026-06-24",
                    "new_users": 3,
                    "new_channel_members": 2,
                    "new_generation_users": 5,
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
            assert args == (30, None, None)
            return [{"label": "近周期活跃", "count": 34}]
        if "from analytics_user_profile_daily_snapshots" in query:
            assert args == (30, None, None)
            return [
                {
                    "day": "2026-06-30",
                    "total_users": 90,
                    "active_users_7d": 20,
                    "active_users_30d": 30,
                    "channel_members": 50,
                    "generation_users": 40,
                    "real_payers": 7,
                    "low_trust_free_tier_users": 5,
                    "low_trust_exempt_users": 2,
                    "submission_banned_users": 1,
                },
                {
                    "day": "2026-07-01",
                    "total_users": 100,
                    "active_users_7d": 24,
                    "active_users_30d": 34,
                    "channel_members": 56,
                    "generation_users": 45,
                    "real_payers": 8,
                    "low_trust_free_tier_users": 6,
                    "low_trust_exempt_users": 3,
                    "submission_banned_users": 2,
                },
            ]
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
            assert args == (
                12,
                analytics_main.RMB_TO_USDT,
                analytics_main.TON_TO_USDT,
                analytics_main.STARS_TO_USDT,
            )
            assert "orders.status = 'SUCCESS'" in query
            assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" not in query
            assert "coalesce(orders.final_price, 0) > 0" not in query
            assert "invitee_recharge_rate" in query
            assert "from affiliate_transactions" in query
            return [
                {
                    "id": 103,
                    "username": "inviter",
                    "full_name": "Inviter",
                    "referral_count": 20,
                    "referral_relations": 20,
                    "invitee_channel_members": 12,
                    "invitee_generation_users": 10,
                    "recharged_invitees_count": 3,
                    "invitee_recharge_rate": 15.0,
                    "invitee_recharge_orders": 4,
                    "invitee_recharge_total_usdt": 22.2,
                    "affiliate_total_commission_usdt": 6.66,
                    "affiliate_spent_commission_usdt": 1.23,
                    "affiliate_available_balance_usdt": 5.43,
                }
            ]
        if "low_trust_rank" in query:
            assert args == (
                12,
                analytics_main.RMB_TO_USDT,
                analytics_main.TON_TO_USDT,
                analytics_main.STARS_TO_USDT,
            )
            assert "coalesce(users.checkin_count, 0) > 7" in query
            assert "high_quality_referral_exempt_users" in query
            assert "successful_invitees_count * 100 > referral_relations * 3" in query
            assert "orders" in query
            assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" not in query
            assert "coalesce(orders.final_price, 0) > 0" not in query
            assert "non_low_trust_invitees_count" in query
            assert "non_low_trust_invitee_rate" in query
            assert "invitee_recharge_rate" in query
            assert "invitee_recharge_total_usdt" in query
            return [
                {
                    "id": 105,
                    "username": "lowtrust",
                    "full_name": "Low Trust",
                    "checkin_count": 42,
                    "generation_count": 3,
                    "credits": 66,
                    "referral_relations": 8,
                    "non_low_trust_invitees_count": 6,
                    "non_low_trust_invitee_rate": 75.0,
                    "low_trust_invitees_count": 2,
                    "invitee_channel_members": 4,
                    "invitee_generation_users": 3,
                    "recharged_invitees_count": 1,
                    "invitee_recharge_rate": 12.5,
                    "invitee_recharge_orders": 2,
                    "invitee_recharge_total_usdt": 9.9,
                    "is_low_trust_free_tier": True,
                }
            ]
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
    assert payload["summary"]["low_trust_free_tier_users"] == 6
    assert payload["summary"]["low_trust_exempt_users"] == 3
    assert payload["summary"]["low_trust_non_low_trust_invitees_count"] == 13
    assert payload["summary"]["recharged_invitees_count"] == 7
    assert payload["summary"]["affiliate_available_balance_usdt"] == 8.88
    assert payload["summary"]["paying_channel_members"] == 6
    assert payload["summary"]["paying_generation_users"] == 5
    assert payload["summary"]["active_paying_users"] == 4
    assert payload["summary"]["recharge_rate_total_users"] == 8.0
    assert payload["summary"]["recharge_rate_channel_members"] == 10.71
    assert payload["summary"]["recharge_rate_generation_users"] == 11.11
    assert payload["summary"]["recharge_rate_active_users"] == 11.76
    assert payload["summary"]["avg_inviter_invitee_recharge_rate"] == 12.34
    assert payload["summary"]["inviter_recharge_rate_sample_size"] == 9
    assert payload["daily"][0]["new_channel_members"] == 2
    assert payload["daily"][0]["new_generation_users"] == 5
    assert payload["visualizations"]["metrics"][0]["key"] == "total_users"
    assert payload["visualizations"]["metrics"][0]["share_percent"] == 100
    assert payload["visualizations"]["metrics"][0]["delta"]["value"] == 10
    assert payload["visualizations"]["metrics"][6]["key"] == "low_trust_exempt_users"
    assert payload["visualizations"]["trust_composition"] == [
        {"label": "常规用户", "count": 91, "share_percent": 91.0},
        {"label": "低信任免费层", "count": 6, "share_percent": 6.0},
        {"label": "豁免低信任", "count": 3, "share_percent": 3.0},
    ]
    assert payload["visualizations"]["conversion_funnel"][-1] == {"label": "真实付费", "count": 8}
    assert payload["visualizations"]["recharge_rates"][0]["rate"] == 8.0
    assert payload["visualizations"]["trend"][-1]["low_trust_exempt_users"] == 3
    assert payload["distributions"]["identity"][0] == {"label": "外门弟子", "count": 70}
    assert payload["leaderboards"]["generation"][0]["username"] == "maker"
    assert payload["leaderboards"]["credits"][0]["full_name"] is None
    assert payload["leaderboards"]["referrals"][0]["recharged_invitees_count"] == 3
    assert payload["leaderboards"]["referrals"][0]["invitee_recharge_rate"] == 15.0
    assert payload["leaderboards"]["low_trust"][0]["non_low_trust_invitees_count"] == 6
    assert payload["leaderboards"]["low_trust"][0]["non_low_trust_invitee_rate"] == 75.0
    assert payload["leaderboards"]["low_trust"][0]["invitee_recharge_rate"] == 12.5
    assert payload["leaderboards"]["low_trust"][0]["invitee_recharge_total_usdt"] == 9.9
    assert payload["leaderboards"]["low_trust"][0]["is_low_trust_free_tier"] is True
    assert ("fetchrow",) == tuple(calls[0][:1])


@pytest.mark.asyncio
async def test_user_analytics_accepts_date_range_and_missing_snapshot_table(monkeypatch):
    start = date(2026, 6, 24)
    end = date(2026, 7, 1)

    async def fake_fetchrow(query, *args):
        if "to_regclass('public.analytics_user_profile_daily_snapshots')" in query:
            return {"table_name": None}
        assert "period_generation_users as" in query
        assert args == (
            8,
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            start,
            end,
        )
        return {
            "total_users": 20,
            "new_users": 4,
            "active_users": 9,
            "channel_members": 10,
            "generation_users": 11,
            "paying_users": 2,
            "paying_channel_members": 1,
            "paying_generation_users": 2,
            "active_paying_users": 1,
            "submission_banned_users": 1,
            "low_trust_free_tier_users": 3,
            "low_trust_exempt_users": 2,
            "recharge_rate_total_users": 10,
            "recharge_rate_channel_members": 10,
            "recharge_rate_generation_users": 18.18,
            "recharge_rate_active_users": 11.11,
        }

    async def fake_fetch(query, *args):
        if "as new_users" in query and "checkin_history" in query:
            assert args == (8, start, end)
            return [{"day": "2026-06-24", "new_users": 1, "active_users": 2, "checkins": 3}]
        if "activity_segment" in query:
            assert args == (8, start, end)
            return []
        if "identity_label" in query or "user_group_label" in query or "credit_bucket" in query or "generation_bucket" in query:
            return []
        if "generation_rank" in query or "credits_rank" in query or "referrals_rank" in query or "low_trust_rank" in query or "recent_active_rank" in query:
            return []
        raise AssertionError(f"unexpected query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics",
            params={"start_date": "2026-06-24", "end_date": "2026-07-01"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 8
    assert payload["filters"] == {"start_date": "2026-06-24", "end_date": "2026-07-01"}
    assert payload["visualizations"]["trend"] == [
        {"day": "2026-06-24", "new_users": 1, "active_users": 2, "checkins": 3}
    ]
    assert payload["visualizations"]["metrics"][0]["delta"] == {"value": None, "percent": None}


@pytest.mark.asyncio
async def test_user_analytics_rejects_reversed_date_range():
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics?start_date=2026-07-01&end_date=2026-06-24"
        )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]


@pytest.mark.asyncio
async def test_user_profile_users_returns_paginated_cross_table_rollups(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "user_profile_count" in query
        assert "gallery_prompt_unlocks" in query
        assert "user_follows" in query
        assert "user_logs" in query
        assert "orders.status = 'SUCCESS'" in query
        assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" in query
        assert "coalesce(final_price, 0) > 0" in query
        assert "high_quality_referral_exempt_users" in query
        assert "real_success_orders > 0" in query
        assert "is_in_period_scope is true" in query
        assert "bounds.start_at" in query
        assert "bounds.end_at" in query
        assert args == (
            30,
            "%maker%",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
        )
        return {"total": 6}

    async def fake_fetch(query, *args):
        assert "user_profile_rows" in query
        assert "gallery_signal" in query
        assert "prompt_unlocks_bought" in query
        assert "followers_count" in query
        assert "order by coalesce(recharge_usdt, 0) desc" in query
        assert "is_in_period_scope is true" in query
        assert args == (
            30,
            "%maker%",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
            5,
            5,
        )
        return [
            {
                "user_id": 202,
                "id": 202,
                "username": "maker",
                "full_name": "Maker",
                "current_identity": "核心弟子",
                "user_group": "筑基期",
                "credits": 120,
                "generation_count": 44,
                "checkin_count": 12,
                "is_channel_member": True,
                "is_low_trust_free_tier": False,
                "real_success_orders": 3,
                "recharge_usdt": 18.8,
                "credit_income": 300,
                "credit_expense": 90,
                "referral_relations": 2,
                "gallery_posts": 4,
                "gallery_signal": 33,
                "prompt_unlocks_bought": 5,
                "prompt_unlocks_sold": 6,
                "followers_count": 7,
                "following_count": 8,
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics/users",
            params={
                "days": 30,
                "page": 2,
                "size": 5,
                "search": "Maker",
                "segment": "real_payer",
                "sort": "recharge_usdt",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"] == {"page": 2, "size": 5, "total": 6}
    assert payload["items"][0]["user_id"] == 202
    assert payload["items"][0]["id"] == 202
    assert payload["items"][0]["recharge_usdt"] == 18.8
    assert payload["items"][0]["prompt_unlocks_sold"] == 6
    assert payload["filters"]["segment"] == "real_payer"
    assert payload["filters"]["sort"] == "recharge_usdt"


@pytest.mark.asyncio
async def test_user_profile_groups_returns_dimension_rollups(monkeypatch):
    async def fake_fetch(query, *args):
        assert "user_profile_groups" in query
        assert "gallery_prompt_unlocks" in query
        assert "user_follows" in query
        assert "user_logs" in query
        assert "orders.status = 'SUCCESS'" in query
        assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" in query
        assert "coalesce(final_price, 0) > 0" in query
        assert "high_quality_referral_exempt_users" in query
        assert "real_success_orders > 0" in query
        assert "paying_rate" in query
        assert "gallery_signal" in query
        assert "prompt_unlocks" in query
        assert "followers_count" in query
        assert "period_checkins" in query
        assert "is_in_period_scope is true" in query
        assert "order by recharge_usdt desc" in query
        assert args == (
            30,
            "",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
            7,
        )
        return [
            {
                "group_key": "real_payer",
                "group_label": "真实付费",
                "users": 8,
                "share_percent": 100,
                "active_users": 5,
                "active_rate": 62.5,
                "channel_members": 6,
                "channel_member_rate": 75,
                "low_trust_users": 0,
                "real_payers": 8,
                "paying_rate": 100,
                "real_success_orders": 12,
                "recharge_usdt": 88.8,
                "generation_count": 120,
                "period_generations": 34,
                "credit_income": 900,
                "credit_expense": 450,
                "credit_net_change": 450,
                "referral_relations": 10,
                "invitee_channel_members": 4,
                "invitee_generation_users": 3,
                "recharged_invitees_count": 2,
                "invitee_recharge_rate": 20,
                "gallery_posts": 5,
                "gallery_signal": 44,
                "prompt_unlocks": 9,
                "followers_count": 13,
                "following_count": 11,
                "checkin_users": 7,
                "period_checkins": 21,
            }
        ]

    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics/groups",
            params={
                "days": 30,
                "dimension": "payer",
                "segment": "real_payer",
                "sort": "recharge_usdt",
                "limit": 7,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"] == {
        "dimension": "payer",
        "segment": "real_payer",
        "search": "",
        "sort": "recharge_usdt",
        "limit": 7,
        "start_date": "",
        "end_date": "",
    }
    assert payload["dimension"]["key"] == "payer"
    assert payload["rows"][0]["group_key"] == "real_payer"
    assert payload["rows"][0]["paying_rate"] == 100
    assert payload["rows"][0]["prompt_unlocks"] == 9
    assert "payer" in payload["available_dimensions"]
    assert "recharge_usdt" in payload["available_sorts"]


@pytest.mark.asyncio
async def test_user_profile_date_range_filters_users_and_group_scope(monkeypatch):
    start = date(2026, 6, 24)
    end = date(2026, 7, 1)

    async def fake_fetchrow(query, *args):
        assert "user_profile_count" in query
        assert "is_in_period_scope is true" in query
        assert "lower(coalesce(username, '')) like $2::text" in query
        assert args == (
            8,
            "%maker%",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            start,
            end,
        )
        return {"total": 0}

    async def fake_fetch(query, *args):
        assert "is_in_period_scope is true" in query
        assert "bounds.start_at" in query
        assert "bounds.end_at" in query
        if "user_profile_groups" in query:
            assert "is_period_active is true" in query
            assert args == (
                8,
                "%maker%",
                analytics_main.RMB_TO_USDT,
                analytics_main.TON_TO_USDT,
                analytics_main.STARS_TO_USDT,
                start,
                end,
                3,
            )
            return [{"group_key": "standard", "group_label": "常规用户", "users": 0}]
        assert "user_profile_rows" in query
        assert "is_period_active is true" in query
        assert args == (
            8,
            "%maker%",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            start,
            end,
            2,
            0,
        )
        return []

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        users_response = await client.get(
            "/api/user-analytics/users",
            params={
                "start_date": "2026-06-24",
                "end_date": "2026-07-01",
                "search": "Maker",
                "segment": "active",
                "size": 2,
            },
        )
        groups_response = await client.get(
            "/api/user-analytics/groups",
            params={
                "start_date": "2026-06-24",
                "end_date": "2026-07-01",
                "search": "Maker",
                "segment": "active",
                "dimension": "trust",
                "limit": 3,
            },
        )

    assert users_response.status_code == 200
    assert groups_response.status_code == 200
    users_payload = users_response.json()
    groups_payload = groups_response.json()
    assert users_payload["days"] == 8
    assert users_payload["filters"]["start_date"] == "2026-06-24"
    assert users_payload["filters"]["end_date"] == "2026-07-01"
    assert groups_payload["days"] == 8
    assert groups_payload["filters"]["search"] == "Maker"
    assert groups_payload["filters"]["segment"] == "active"
    assert groups_payload["filters"]["start_date"] == "2026-06-24"
    assert groups_payload["filters"]["end_date"] == "2026-07-01"


@pytest.mark.asyncio
async def test_user_profile_groups_rejects_unknown_whitelisted_params():
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        bad_dimension = await client.get("/api/user-analytics/groups?dimension=ghost")
        bad_segment = await client.get("/api/user-analytics/groups?segment=ghost")
        bad_sort = await client.get("/api/user-analytics/groups?sort=ghost")

    assert bad_dimension.status_code == 400
    assert bad_segment.status_code == 400
    assert bad_sort.status_code == 400


@pytest.mark.asyncio
async def test_user_profile_users_can_drill_down_by_group_key(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "user_profile_count" in query
        assert "= $8::text" in query
        assert args == (
            30,
            "",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
            "real_payer",
        )
        return {"total": 1}

    async def fake_fetch(query, *args):
        assert "user_profile_rows" in query
        assert "= $8::text" in query
        assert "order by coalesce(generation_count, 0) desc" in query
        assert args == (
            30,
            "",
            analytics_main.RMB_TO_USDT,
            analytics_main.TON_TO_USDT,
            analytics_main.STARS_TO_USDT,
            None,
            None,
            "real_payer",
            10,
            0,
        )
        return [{"user_id": 202, "id": 202, "username": "maker", "real_success_orders": 1}]

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics/users",
            params={
                "days": 30,
                "page": 1,
                "size": 10,
                "dimension": "payer",
                "group_key": "real_payer",
                "sort": "generation_count",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters"]["dimension"] == "payer"
    assert payload["filters"]["group_key"] == "real_payer"
    assert payload["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_user_profile_users_rejects_unknown_segment_and_sort():
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        bad_segment = await client.get("/api/user-analytics/users?segment=ghost")
        bad_sort = await client.get("/api/user-analytics/users?sort=ghost")
        bad_dimension = await client.get("/api/user-analytics/users?dimension=ghost&group_key=whatever")

    assert bad_segment.status_code == 400
    assert bad_sort.status_code == 400
    assert bad_dimension.status_code == 400


@pytest.mark.asyncio
async def test_user_profile_date_range_rejects_reversed_dates():
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/user-analytics/users?start_date=2026-07-01&end_date=2026-06-24"
        )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]


@pytest.mark.asyncio
async def test_user_profile_groups_returns_empty_rows(monkeypatch):
    async def fake_fetch(query, *args):
        assert "user_profile_groups" in query
        return []

    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/user-analytics/groups?dimension=trust")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []


@pytest.mark.asyncio
async def test_user_profile_detail_returns_all_profile_sections(monkeypatch):
    async def fake_fetchrow(query, *args):
        if "user_profile_profile" in query:
            assert args == (202,)
            assert "successful_order_users" in query
            assert "high_quality_referral_exempt_users" in query
            return {
                "row_type": "user_profile_profile",
                "id": 202,
                "username": "maker",
                "full_name": "Maker",
                "current_identity": "核心弟子",
                "user_group": "筑基期",
                "credits": 120,
                "generation_count": 44,
                "checkin_count": 12,
                "is_channel_member": True,
                "is_submission_banned": False,
                "is_low_trust_free_tier": False,
                "is_real_payer": True,
                "inviter_id": 99,
                "inviter_username": "root",
            }
        if "user_credit_flow_summary" in query:
            assert "from user_logs" in query
            return {"gross_income": 300, "gross_expense": 90, "net_change": 210}
        if "user_recharge_summary" in query:
            assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" in query
            assert "coalesce(orders.final_price, 0) > 0" in query
            return {"real_success_orders": 3, "real_success_usdt": 18.8, "internal_success_orders": 1}
        if "user_invitation_summary" in query:
            assert "from referrals" in query
            assert "successful_invitee_orders" in query
            assert "coalesce(orders.final_price, 0) > 0" not in query
            assert "orders.payment_channel in ('RMB', 'TON', 'XTR')" not in query
            assert "from affiliate_transactions" in query
            return {
                "referral_relations": 2,
                "invitee_generation_users": 1,
                "recharged_invitees_count": 1,
                "affiliate_available_balance_usdt": 4.4,
            }
        if "user_generation_summary" in query:
            assert "from history" in query
            return {"period_generations": 9, "all_generations": 44, "active_days": 5}
        if "user_checkin_summary" in query:
            assert "from checkin_history" in query
            return {"total_checkins": 12, "period_checkins": 4, "current_streak": 3, "longest_streak": 7}
        if "user_community_summary" in query:
            assert "from gallery_posts" in query
            return {"gallery_posts": 4, "likes": 11, "applies": 5, "gallery_signal": 33}
        if "user_prompt_unlock_summary" in query:
            assert "from gallery_prompt_unlocks" in query
            return {"purchased_unlocks": 5, "sold_unlocks": 6, "spent_credits": 5, "earned_credits": 6}
        if "user_social_summary" in query:
            assert "from user_follows" in query
            return {"followers_count": 7, "following_count": 8, "mutual_follow_count": 2}
        raise AssertionError(f"unexpected fetchrow query: {query}")

    async def fake_fetch(query, *args):
        if "user_credit_flow_categories" in query:
            return [{"category": "充值/套餐发放", "income": 120, "expense": 0}]
        if "user_recent_credit_logs" in query:
            return [{"operation_type": "recharge", "credit_change": 120, "current_balance": 120}]
        if "user_recent_orders" in query:
            return [{"status": "SUCCESS", "payment_channel": "RMB", "final_price": 88}]
        if "user_recent_invitees" in query:
            return [{"id": 303, "username": "invitee", "is_real_payer": True}]
        if "user_generation_type_distribution" in query:
            return [{"task_type": "image", "generations": 7}]
        if "user_generation_source_distribution" in query:
            return [{"source": "web", "generations": 6}]
        if "user_generation_hour_distribution" in query:
            return [{"hour": 22, "generations": 4}]
        if "user_generation_weekday_distribution" in query:
            return [{"weekday": 5, "generations": 3}]
        if "user_recent_generations" in query:
            assert "prompt" not in query.lower()
            return [{"task_id": "task-1", "type": "image", "rating": 1}]
        if "user_recent_checkins" in query:
            return [{"checkin_date": "2026-06-30"}]
        if "user_gallery_samples" in query:
            return [{"post_id": 1, "task_id": "task-1", "likes_count": 11}]
        if "user_recent_prompt_unlock_purchases" in query:
            return [{"post_id": 5, "author_id": 9, "task_type": "image"}]
        if "user_recent_prompt_unlock_sales" in query:
            return [{"post_id": 6, "buyer_id": 8, "task_type": "video"}]
        if "user_recent_following" in query:
            return [{"id": 401, "username": "followee"}]
        if "user_recent_followers" in query:
            return [{"id": 402, "username": "follower"}]
        raise AssertionError(f"unexpected fetch query: {query}")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/user-analytics/users/202?days=30")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "days",
        "profile",
        "credit_flow",
        "recharge",
        "invitation",
        "generation",
        "checkin",
        "community",
        "prompt_unlock",
        "social",
    }
    assert payload["profile"]["id"] == 202
    assert payload["recharge"]["summary"]["real_success_usdt"] == 18.8
    assert payload["prompt_unlock"]["summary"]["sold_unlocks"] == 6
    assert payload["social"]["summary"]["mutual_follow_count"] == 2


@pytest.mark.asyncio
async def test_user_profile_detail_returns_404_for_missing_user(monkeypatch):
    async def fake_fetchrow(query, *args):
        assert "user_profile_profile" in query
        return None

    async def fake_fetch(query, *args):  # pragma: no cover - should not be reached.
        raise AssertionError("detail queries should not run when profile is missing")

    monkeypatch.setattr(analytics_main, "_fetchrow", fake_fetchrow)
    monkeypatch.setattr(analytics_main, "_fetch", fake_fetch)

    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/user-analytics/users/999")

    assert response.status_code == 404
