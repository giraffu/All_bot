from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
from typing import Any, Awaitable, Callable

import asyncpg


Fetch = Callable[..., Awaitable[list[Any]]]
FetchRow = Callable[..., Awaitable[Any | None]]

SNAPSHOT_TABLE = "analytics_user_profile_daily_snapshots"

SNAPSHOT_SCHEMA_SQL = f"""
create table if not exists {SNAPSHOT_TABLE} (
    snapshot_date date primary key,
    captured_at timestamptz not null default now(),
    total_users bigint not null,
    active_users_7d bigint not null,
    active_users_30d bigint not null,
    channel_members bigint not null,
    generation_users bigint not null,
    real_payers bigint not null,
    low_trust_free_tier_users bigint not null,
    low_trust_exempt_users bigint not null,
    submission_banned_users bigint not null
);

create index if not exists idx_user_profile_daily_snapshots_captured_at
on {SNAPSHOT_TABLE} (captured_at desc);
"""

SNAPSHOT_UPSERT_SQL = f"""
with snapshot_bounds as (
    select
        $1::date as snapshot_date,
        ($1::date + interval '1 day')::timestamp as end_at,
        ($1::date + interval '1 day' - interval '7 days')::timestamp as start_7d,
        ($1::date + interval '1 day' - interval '30 days')::timestamp as start_30d
),
successful_order_users as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and internal_user_id is not null
),
referral_quality as (
    select
        referrals.inviter_id as user_id,
        count(distinct referrals.invitee_id)::bigint as referral_relations,
        count(distinct successful_order_users.user_id)::bigint as successful_invitees_count
    from referrals
    left join successful_order_users on successful_order_users.user_id = referrals.invitee_id
    group by referrals.inviter_id
),
high_quality_referral_exempt_users as (
    select user_id
    from referral_quality
    where referral_relations > 100
      and successful_invitees_count * 100 > referral_relations * 3
),
real_success_payers as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and coalesce(final_price, 0) > 0
      and payment_channel in ('RMB', 'TON', 'XTR')
      and internal_user_id is not null
),
history_active_7d as (
    select distinct history.user_id
    from history, snapshot_bounds
    where history.user_id is not null
      and history.created_at >= snapshot_bounds.start_7d
      and history.created_at < snapshot_bounds.end_at
),
history_active_30d as (
    select distinct history.user_id
    from history, snapshot_bounds
    where history.user_id is not null
      and history.created_at >= snapshot_bounds.start_30d
      and history.created_at < snapshot_bounds.end_at
),
classified_users as (
    select
        users.id,
        users.is_channel_member,
        users.is_submission_banned,
        coalesce(users.generation_count, 0) as generation_count,
        coalesce(users.checkin_count, 0) as checkin_count,
        users.last_activity,
        successful_order_users.user_id is not null as has_success_order,
        real_success_payers.user_id is not null as is_real_payer,
        high_quality_referral_exempt_users.user_id is not null as has_low_trust_exemption,
        history_active_7d.user_id is not null as has_history_7d,
        history_active_30d.user_id is not null as has_history_30d
    from users
    cross join snapshot_bounds
    left join successful_order_users on successful_order_users.user_id = users.id
    left join real_success_payers on real_success_payers.user_id = users.id
    left join high_quality_referral_exempt_users on high_quality_referral_exempt_users.user_id = users.id
    left join history_active_7d on history_active_7d.user_id = users.id
    left join history_active_30d on history_active_30d.user_id = users.id
    where users.created_at < snapshot_bounds.end_at
)
insert into {SNAPSHOT_TABLE} (
    snapshot_date,
    captured_at,
    total_users,
    active_users_7d,
    active_users_30d,
    channel_members,
    generation_users,
    real_payers,
    low_trust_free_tier_users,
    low_trust_exempt_users,
    submission_banned_users
)
select
    snapshot_bounds.snapshot_date,
    now(),
    count(*)::bigint as total_users,
    count(*) filter (
        where (last_activity >= snapshot_bounds.start_7d and last_activity < snapshot_bounds.end_at)
           or has_history_7d is true
    )::bigint as active_users_7d,
    count(*) filter (
        where (last_activity >= snapshot_bounds.start_30d and last_activity < snapshot_bounds.end_at)
           or has_history_30d is true
    )::bigint as active_users_30d,
    count(*) filter (where is_channel_member is true)::bigint as channel_members,
    count(*) filter (where generation_count > 0)::bigint as generation_users,
    count(*) filter (where is_real_payer is true)::bigint as real_payers,
    count(*) filter (
        where checkin_count > 7
          and has_success_order is false
          and has_low_trust_exemption is false
    )::bigint as low_trust_free_tier_users,
    count(*) filter (
        where checkin_count > 7
          and has_success_order is false
          and has_low_trust_exemption is true
    )::bigint as low_trust_exempt_users,
    count(*) filter (where is_submission_banned is true)::bigint as submission_banned_users
from classified_users, snapshot_bounds
group by snapshot_bounds.snapshot_date
on conflict (snapshot_date) do update set
    captured_at = excluded.captured_at,
    total_users = excluded.total_users,
    active_users_7d = excluded.active_users_7d,
    active_users_30d = excluded.active_users_30d,
    channel_members = excluded.channel_members,
    generation_users = excluded.generation_users,
    real_payers = excluded.real_payers,
    low_trust_free_tier_users = excluded.low_trust_free_tier_users,
    low_trust_exempt_users = excluded.low_trust_exempt_users,
    submission_banned_users = excluded.submission_banned_users
returning *;
"""


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _row(record: Any | None) -> dict[str, Any]:
    if record is None:
        return {}
    return {key: _json_value(value) for key, value in dict(record).items()}


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [_row(record) for record in records]


def _number(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def _delta(current: float, previous: float | None) -> dict[str, Any]:
    if previous is None:
        return {"value": None, "percent": None}
    change = current - previous
    return {
        "value": int(change) if float(change).is_integer() else round(change, 2),
        "percent": None if previous == 0 else round(change / previous * 100, 2),
    }


def _metric(
    *,
    key: str,
    label: str,
    summary: dict[str, Any],
    total_users: float,
    snapshot_key: str,
    previous_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    value = _number(summary, key)
    previous_value = None if previous_snapshot is None else _number(previous_snapshot, snapshot_key)
    return {
        "key": key,
        "label": label,
        "value": int(value),
        "share_percent": _percent(value, total_users),
        "delta": _delta(value, previous_value),
    }


async def ensure_user_profile_snapshot_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SNAPSHOT_SCHEMA_SQL)


async def refresh_user_profile_daily_snapshot(
    conn: asyncpg.Connection,
    *,
    snapshot_date: date | None = None,
    statement_timeout_ms: int = 3_600_000,
) -> dict[str, Any]:
    target_date = snapshot_date or date.today()
    await conn.execute(f"set statement_timeout = {int(statement_timeout_ms)}")
    await ensure_user_profile_snapshot_schema(conn)
    record = await conn.fetchrow(SNAPSHOT_UPSERT_SQL, target_date)
    return _row(record)


async def get_user_profile_snapshot_rows(
    *,
    fetch: Fetch,
    fetchrow: FetchRow,
    days: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    table = _row(
        await fetchrow(
            "select to_regclass('public.analytics_user_profile_daily_snapshots')::text as table_name"
        )
    )
    if not table.get("table_name"):
        return []

    rows = await fetch(
        """
        with bounds as (
            select
                coalesce($2::date, current_date - (($1::int - 1) * interval '1 day'))::date as start_date,
                coalesce($3::date, current_date)::date as end_date
        )
        select
            snapshot_date::text as day,
            captured_at,
            total_users,
            active_users_7d,
            active_users_30d,
            channel_members,
            generation_users,
            real_payers,
            low_trust_free_tier_users,
            low_trust_exempt_users,
            submission_banned_users
        from analytics_user_profile_daily_snapshots, bounds
        where snapshot_date >= bounds.start_date
          and snapshot_date <= bounds.end_date
        order by snapshot_date
        """,
        days,
        start_date,
        end_date,
    )
    return _rows(rows)


def build_user_profile_visualizations(
    *,
    summary: dict[str, Any],
    daily: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    days: int,
) -> dict[str, Any]:
    total_users = _number(summary, "total_users")
    previous_snapshot = snapshots[-2] if len(snapshots) >= 2 else None
    active_snapshot_key = "active_users_7d" if days <= 7 else "active_users_30d"
    low_trust_users = _number(summary, "low_trust_free_tier_users")
    exempt_users = _number(summary, "low_trust_exempt_users")
    standard_users = max(total_users - low_trust_users - exempt_users, 0)

    snapshot_by_day = {row.get("day"): dict(row) for row in snapshots}
    trend_by_day = {row.get("day"): dict(row) for row in daily}
    for day, row in snapshot_by_day.items():
        trend_by_day.setdefault(day, {}).update(row)
    trend = [trend_by_day[day] for day in sorted(day for day in trend_by_day if day)]

    return {
        "metrics": [
            _metric(
                key="total_users",
                label="总用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="total_users",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="active_users",
                label="周期活跃用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key=active_snapshot_key,
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="channel_members",
                label="入宗门用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="channel_members",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="generation_users",
                label="生成用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="generation_users",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="paying_users",
                label="真实付费用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="real_payers",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="low_trust_free_tier_users",
                label="低信任免费层用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="low_trust_free_tier_users",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="low_trust_exempt_users",
                label="豁免低信任用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="low_trust_exempt_users",
                previous_snapshot=previous_snapshot,
            ),
            _metric(
                key="submission_banned_users",
                label="投稿封禁用户数",
                summary=summary,
                total_users=total_users,
                snapshot_key="submission_banned_users",
                previous_snapshot=previous_snapshot,
            ),
        ],
        "trend": trend,
        "trust_composition": [
            {"label": "常规用户", "count": int(standard_users), "share_percent": _percent(standard_users, total_users)},
            {"label": "低信任免费层", "count": int(low_trust_users), "share_percent": _percent(low_trust_users, total_users)},
            {"label": "豁免低信任", "count": int(exempt_users), "share_percent": _percent(exempt_users, total_users)},
        ],
        "conversion_funnel": [
            {"label": "总用户", "count": int(total_users)},
            {"label": "周期活跃", "count": int(_number(summary, "active_users"))},
            {"label": "入宗门", "count": int(_number(summary, "channel_members"))},
            {"label": "生成用户", "count": int(_number(summary, "generation_users"))},
            {"label": "真实付费", "count": int(_number(summary, "paying_users"))},
        ],
        "recharge_rates": [
            {
                "label": "总用户",
                "rate": _number(summary, "recharge_rate_total_users"),
                "numerator": int(_number(summary, "paying_users")),
                "denominator": int(total_users),
            },
            {
                "label": "入宗门",
                "rate": _number(summary, "recharge_rate_channel_members"),
                "numerator": int(_number(summary, "paying_channel_members")),
                "denominator": int(_number(summary, "channel_members")),
            },
            {
                "label": "生成用户",
                "rate": _number(summary, "recharge_rate_generation_users"),
                "numerator": int(_number(summary, "paying_generation_users")),
                "denominator": int(_number(summary, "generation_users")),
            },
            {
                "label": "活跃用户",
                "rate": _number(summary, "recharge_rate_active_users"),
                "numerator": int(_number(summary, "active_paying_users")),
                "denominator": int(_number(summary, "active_users")),
            },
        ],
    }


def database_url_from_env() -> str:
    dsn = os.getenv("LOCAL_ANALYTICS_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("LOCAL_ANALYTICS_DATABASE_URL is not configured")
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn.removeprefix("postgresql+asyncpg://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn.removeprefix("postgres://")
    return dsn

