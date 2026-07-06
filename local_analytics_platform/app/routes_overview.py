from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .analytics_common import (
    MAX_ANALYTICS_DAYS,
    _chart_days,
    _clamp_days,
    _fetch,
    _fetchrow,
    _masked_dsn,
    _media_base_url,
    _media_bucket,
    _query_days,
    _row,
    _rows,
)


router = APIRouter()


@router.get("/api/overview")
async def overview(days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS)) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    metrics = await _fetchrow(
        """
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        )
        select
            current_database() as database_name,
            (select count(*) from users)::bigint as total_users,
            (select count(*) from users, bounds where created_at >= bounds.since)::bigint as new_users,
            (select count(*) from users, bounds where last_activity >= bounds.since)::bigint as active_users,
            (select count(*) from history)::bigint as total_history,
            (select count(*) from history, bounds where created_at >= bounds.since)::bigint as recent_history,
            (select count(*) from orders where lower(status) = 'success')::bigint as successful_orders,
            (select count(distinct internal_user_id) from orders where lower(status) = 'success' and payment_channel in ('RMB', 'TON', 'XTR'))::bigint as paying_users,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'RMB' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_rmb_amount,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'TON' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_ton_amount,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'XTR' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_stars_amount,
            (select count(*) from gallery_posts where is_active is true)::bigint as active_gallery_posts,
            (select count(*) from gallery_prompt_unlocks, bounds where created_at >= bounds.since)::bigint as recent_prompt_unlocks,
            (select max(created_at) from history) as latest_history_at,
            (select max(coalesce(paid_at, updated_at, created_at)) from orders where lower(status) = 'success') as latest_order_at
        """,
        query_days,
    )
    daily = await _fetch(
        """
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        user_daily as (
            select created_at::date as day, count(*)::bigint as new_users
            from users
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        history_daily as (
            select created_at::date as day, count(*)::bigint as generations, count(distinct user_id)::bigint as creators
            from history
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        order_daily as (
            select coalesce(paid_at, updated_at, created_at)::date as day,
                   count(*) filter (where lower(status) = 'success')::bigint as orders,
                   coalesce(sum(final_price) filter (where lower(status) = 'success' and payment_channel = 'RMB'), 0) as rmb_amount
            from orders
            where coalesce(paid_at, updated_at, created_at) >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        )
        select to_char(days.day, 'YYYY-MM-DD') as day,
               coalesce(user_daily.new_users, 0)::bigint as new_users,
               coalesce(history_daily.generations, 0)::bigint as generations,
               coalesce(history_daily.creators, 0)::bigint as creators,
               coalesce(order_daily.orders, 0)::bigint as orders,
               coalesce(order_daily.rmb_amount, 0) as rmb_amount
        from days
        left join user_daily using (day)
        left join history_daily using (day)
        left join order_daily using (day)
        order by days.day
        """,
        chart_days,
    )
    return {
        "days": days,
        "source": {
            "database_url": _masked_dsn(),
            "media_bucket": _media_bucket(),
            "media_url_enabled": bool(_media_base_url()),
        },
        "metrics": _row(metrics),
        "daily": _rows(daily),
    }
