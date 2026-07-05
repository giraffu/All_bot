from local_analytics_platform.app.user_profile_snapshots import (
    SNAPSHOT_SCHEMA_SQL,
    SNAPSHOT_UPSERT_SQL,
    build_user_profile_visualizations,
)


def test_user_profile_snapshot_schema_tracks_fixed_user_metrics():
    assert "create table if not exists analytics_user_profile_daily_snapshots" in SNAPSHOT_SCHEMA_SQL
    for column in [
        "total_users",
        "active_users_7d",
        "active_users_30d",
        "never_active_users",
        "dormant_users_7d",
        "dormant_users_30d",
        "channel_members",
        "generation_users",
        "real_payers",
        "low_trust_free_tier_users",
        "low_trust_exempt_users",
        "submission_banned_users",
    ]:
        assert column in SNAPSHOT_SCHEMA_SQL


def test_user_profile_snapshot_upsert_uses_existing_low_trust_exemption_rule():
    assert "successful_order_users" in SNAPSHOT_UPSERT_SQL
    assert "high_quality_referral_exempt_users" in SNAPSHOT_UPSERT_SQL
    assert "successful_invitees_count * 100 > referral_relations * 3" in SNAPSHOT_UPSERT_SQL
    assert "coalesce(users.checkin_count, 0)" in SNAPSHOT_UPSERT_SQL
    assert "history_active_7d" in SNAPSHOT_UPSERT_SQL
    assert "history_active_30d" in SNAPSHOT_UPSERT_SQL
    assert "history_ever_active" in SNAPSHOT_UPSERT_SQL
    assert "never_active_users" in SNAPSHOT_UPSERT_SQL
    assert "dormant_users_7d" in SNAPSHOT_UPSERT_SQL
    assert "dormant_users_30d" in SNAPSHOT_UPSERT_SQL
    assert "on conflict (snapshot_date) do update" in SNAPSHOT_UPSERT_SQL


def test_build_user_profile_visualizations_keeps_missing_snapshot_delta_stable():
    payload = build_user_profile_visualizations(
        summary={
            "total_users": 100,
            "active_users": 40,
            "never_active_users": 12,
            "dormant_users": 48,
            "channel_members": 50,
            "generation_users": 45,
            "paying_users": 8,
            "low_trust_free_tier_users": 6,
            "low_trust_exempt_users": 4,
            "submission_banned_users": 2,
            "recharge_rate_total_users": 8,
        },
        daily=[{"day": "2026-07-01", "new_users": 3, "active_users": 9}],
        snapshots=[],
        days=30,
    )

    assert payload["metrics"][0]["delta"] == {"value": None, "percent": None}
    metric_keys = [item["key"] for item in payload["metrics"]]
    assert "never_active_users" in metric_keys
    assert "dormant_users" in metric_keys
    assert payload["trust_composition"] == [
        {"label": "常规用户", "count": 90, "share_percent": 90.0},
        {"label": "低信任免费层", "count": 6, "share_percent": 6.0},
        {"label": "豁免低信任", "count": 4, "share_percent": 4.0},
    ]
    assert payload["trend"] == [{"day": "2026-07-01", "new_users": 3, "active_users": 9}]


def test_build_user_profile_visualizations_extends_population_trend_to_period_days():
    payload = build_user_profile_visualizations(
        summary={
            "total_users": 120,
            "active_users": 50,
            "never_active_users": 20,
            "dormant_users": 50,
            "channel_members": 70,
            "generation_users": 60,
            "paying_users": 10,
            "low_trust_free_tier_users": 7,
            "low_trust_exempt_users": 3,
            "submission_banned_users": 1,
            "recharge_rate_total_users": 8,
        },
        daily=[
            {"day": "2026-06-30", "new_users": 2, "active_users": 8},
            {"day": "2026-07-01", "new_users": 3, "active_users": 9},
        ],
        snapshots=[
            {
                "day": "2026-07-01",
                "total_users": 120,
                "active_users_7d": 35,
                "active_users_30d": 50,
                "never_active_users": 20,
                "dormant_users_7d": 65,
                "dormant_users_30d": 50,
                "channel_members": 70,
                "generation_users": 60,
                "real_payers": 10,
                "low_trust_free_tier_users": 7,
                "low_trust_exempt_users": 3,
                "submission_banned_users": 1,
            }
        ],
        days=30,
    )

    assert [row["day"] for row in payload["trend"]] == ["2026-06-30", "2026-07-01"]
    assert payload["trend"][0]["total_users"] == 120
    assert payload["trend"][0]["period_active_users"] == 50
    assert payload["trend"][0]["dormant_users"] == 50
    assert payload["trend"][0]["never_active_users"] == 20
