from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .analytics_common import (
    MAX_ANALYTICS_DAYS,
    RMB_TO_USDT,
    STARS_TO_USDT,
    TON_TO_USDT,
    _chart_days,
    _clamp,
    _clamp_days,
    _fetch,
    _fetchrow,
    _finance_health_flags,
    _parse_compare_dates,
    _query_days,
    _row,
    _rows,
)


router = APIRouter()


@router.get("/api/finance")
async def finance(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    return await _build_finance_payload(days=days, limit=limit)


async def _build_finance_payload(
    *,
    days: int,
    limit: int,
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        ),
        first_real_success as (
            select
                internal_user_id,
                min(coalesce(paid_at, updated_at, created_at)) as first_paid_at
            from orders
            where lower(coalesce(status, '')) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
              and internal_user_id is not null
            group by internal_user_id
        )
        select
            'finance_summary' as row_type,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(*) filter (where status_lower = 'pending')::bigint as pending_orders,
            count(*) filter (where status_lower = 'failed')::bigint as failed_orders,
            count(*) filter (where status_lower != 'success')::bigint as non_success_orders,
            count(distinct bounded.internal_user_id) filter (where real_success)::bigint as real_payers,
            count(distinct bounded.internal_user_id) filter (where real_success and first_real_success.first_paid_at >= (select since from bounds))::bigint as new_payers,
            count(distinct bounded.internal_user_id) filter (where real_success and first_real_success.first_paid_at < (select since from bounds))::bigint as repeat_payers,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0
            ) * {RMB_TO_USDT}
            + coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'TON'), 0
            ) * {TON_TO_USDT}
            + coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0
            ) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(avg(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_avg_order,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            count(*) filter (where status_lower = 'success' and not real_success)::bigint as internal_success_orders,
            case
                when count(distinct bounded.internal_user_id) filter (where real_success) = 0 then 0
                else round((
                    coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}
                ) / count(distinct bounded.internal_user_id) filter (where real_success), 2)
            end as arppu_usdt,
            case
                when count(*) = 0 then 0
                else round((count(*) filter (where status_lower = 'success'))::numeric / count(*)::numeric * 100, 2)
            end as success_rate,
            max(order_time) filter (where status_lower = 'success') as latest_success_at
        from bounded
        left join first_real_success on first_real_success.internal_user_id = bounded.internal_user_id
        """,
        query_days,
    )
    daily = await _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        bounded as (
            select
                coalesce(o.paid_at, o.updated_at, o.created_at)::date as day,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                coalesce(mp.duration_days, 0) as duration_days,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= current_date - (($1::int - 1) * interval '1 day')
        ),
        daily_orders as (
            select
                day,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}, 2) as rmb_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}, 2) as ton_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as stars_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                count(distinct internal_user_id) filter (where real_success)::bigint as payers,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples,
                count(*) filter (where status_lower = 'success' and duration_days = 0)::bigint as pure_credit_orders
            from bounded
            group by 1
        )
        select
            'finance_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(daily_orders.rmb_amount, 0) as rmb_amount,
            coalesce(daily_orders.ton_amount, 0) as ton_amount,
            coalesce(daily_orders.stars_amount, 0) as stars_amount,
            coalesce(daily_orders.rmb_usdt_amount, 0) as rmb_usdt_amount,
            coalesce(daily_orders.ton_usdt_amount, 0) as ton_usdt_amount,
            coalesce(daily_orders.stars_usdt_amount, 0) as stars_usdt_amount,
            coalesce(daily_orders.usdt_amount, 0) as usdt_amount,
            coalesce(daily_orders.success_orders, 0)::bigint as success_orders,
            coalesce(daily_orders.payers, 0)::bigint as payers,
            coalesce(daily_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(daily_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(daily_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(daily_orders.true_disciples, 0)::bigint as true_disciples,
            coalesce(daily_orders.pure_credit_orders, 0)::bigint as pure_credit_orders
        from days
        left join daily_orders using (day)
        order by days.day
        """,
        chart_days,
    )
    hourly = await _fetch(
        """
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        bounded as (
            select
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= now() - ($1::int * interval '1 day')
        ),
        hourly_orders as (
            select
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1
        )
        select
            'finance_hourly' as row_type,
            hours.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from hours
        left join hourly_orders using (hour)
        order by hours.hour
        """,
        query_days,
    )
    channels = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                case
                    when o.payment_channel in ('RMB', 'TON', 'XTR')
                     and coalesce(o.tx_hash, '') not like 'manual_%'
                     and coalesce(o.order_id, '') not like 'GIFT:%'
                    then o.payment_channel
                    else 'INTERNAL'
                end as channel,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_channels' as row_type,
            channel,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(*) filter (where status_lower = 'pending')::bigint as pending_orders,
            count(*) filter (where status_lower = 'failed')::bigint as failed_orders,
            count(*) filter (where status_lower != 'success')::bigint as non_success_orders,
            count(distinct internal_user_id) filter (where real_success)::bigint as payers,
            coalesce(sum(final_price) filter (where real_success), 0) as amount,
            round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(avg(final_price) filter (where real_success), 0) as avg_order_amount,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            min(order_time) filter (where status_lower = 'success') as first_paid_at,
            max(order_time) filter (where status_lower = 'success') as last_paid_at
        from bounded
        group by 1, 2
        order by usdt_amount desc, success_orders desc, channel
        """,
        query_days,
    )
    plans = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                coalesce(mp.name, '未知套餐') as plan_name,
                coalesce(mp.identity_name, '未知身份') as identity_name,
                coalesce(mp.duration_days, 0) as duration_days,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_plans' as row_type,
            plan_id,
            plan_name,
            identity_name,
            duration_days,
            max(reward_credits)::bigint as configured_reward_credits,
            count(*)::bigint as all_orders,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(distinct internal_user_id) filter (where real_success)::bigint as payers,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            case
                when count(*) = 0 then 0
                else round((count(*) filter (where status_lower = 'success'))::numeric / count(*)::numeric * 100, 2)
            end as success_rate,
            min(order_time) filter (where status_lower = 'success') as first_paid_at,
            max(order_time) filter (where status_lower = 'success') as last_paid_at
        from bounded
        group by plan_id, plan_name, identity_name, duration_days
        order by usdt_amount desc, success_orders desc, plan_id desc
        """,
        query_days,
    )
    first_purchase = await _fetchrow(
        """
        with first_success as (
            select distinct on (internal_user_id)
                   internal_user_id,
                   plan_id,
                   payment_channel,
                   final_price,
                   coalesce(paid_at, updated_at, created_at) as first_paid_at
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
              and internal_user_id is not null
            order by internal_user_id, coalesce(paid_at, updated_at, created_at)
        ),
        bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_first as (
            select fs.*, u.created_at as registered_at
            from first_success fs
            join users u on u.id = fs.internal_user_id
            where fs.first_paid_at >= (select since from bounds)
        )
        select
            'finance_first_purchase' as row_type,
            count(*)::bigint as first_purchase_users,
            coalesce(avg(extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as avg_hours_to_first_purchase,
            coalesce(percentile_cont(0.5) within group (order by extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as median_hours_to_first_purchase,
            count(*) filter (where first_paid_at - registered_at <= interval '24 hours')::bigint as first_day_payers
        from recent_first
        """,
        query_days,
    )
    segments = await _fetch(
        f"""
        with paid_users as (
            select
                internal_user_id,
                count(*)::bigint as orders,
                coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
                round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                max(coalesce(paid_at, updated_at, created_at)) as last_paid_at
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
              and internal_user_id is not null
            group by internal_user_id
        )
        select
            'finance_segments' as row_type,
            case
                when orders = 1 then '首充用户'
                when orders between 2 and 3 then '轻复购'
                when orders between 4 and 9 then '稳定复购'
                else '高频付费'
            end as segment,
            count(*)::bigint as users,
            sum(orders)::bigint as orders,
            coalesce(sum(rmb_amount), 0) as rmb_amount,
            coalesce(avg(rmb_amount), 0) as avg_rmb_per_user,
            coalesce(sum(usdt_amount), 0) as usdt_amount,
            coalesce(avg(usdt_amount), 0) as avg_usdt_per_user,
            max(last_paid_at) as latest_paid_at
        from paid_users
        group by 1, 2
        order by min(orders)
        """
    )
    invitation = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        invited_success as (
            select o.*
            from orders o
            join referrals r on r.invitee_id = o.internal_user_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
              and lower(coalesce(o.status, '')) = 'success'
              and o.payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(o.tx_hash, '') not like 'manual_%'
              and coalesce(o.order_id, '') not like 'GIFT:%'
        )
        select
            'finance_invitation' as row_type,
            count(distinct internal_user_id)::bigint as invitee_payers,
            count(*)::bigint as orders,
            coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount
        from invited_success
        """,
        query_days,
    )
    health_row = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        ),
        payer_usdt as (
            select
                internal_user_id,
                coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT} as usdt_amount
            from bounded
            where real_success
            group by internal_user_id
        ),
        totals as (
            select
                count(*)::numeric as all_orders,
                count(*) filter (where status_lower = 'success')::numeric as success_orders,
                count(*) filter (where status_lower = 'pending')::numeric as pending_orders,
                count(*) filter (where status_lower = 'failed')::numeric as failed_orders,
                count(*) filter (where status_lower = 'success' and not real_success)::numeric as internal_success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::numeric as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT} as usdt_amount
            from bounded
        )
        select
            'finance_health' as row_type,
            round(case when all_orders > 0 then success_orders / all_orders * 100 else 0 end, 2) as success_rate,
            pending_orders::bigint as pending_orders,
            round(case when all_orders > 0 then pending_orders / all_orders * 100 else 0 end, 2) as pending_ratio,
            round(case when all_orders > 0 then failed_orders / all_orders * 100 else 0 end, 2) as failure_rate,
            round(case when usdt_amount > 0 then coalesce((select max(usdt_amount) from payer_usdt), 0) / usdt_amount * 100 else 0 end, 2) as top_payer_share,
            round(case when success_orders > 0 then internal_success_orders / success_orders * 100 else 0 end, 2) as internal_success_ratio,
            round(case when usdt_amount > 0 then plan_reward_credits / usdt_amount else 0 end, 2) as credits_per_usdt
        from totals
        """,
        query_days,
    )
    top_payers = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        real_success as (
            select
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                coalesce(mp.reward_credits, 0) as reward_credits
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
              and lower(coalesce(o.status, '')) = 'success'
              and o.payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(o.tx_hash, '') not like 'manual_%'
              and coalesce(o.order_id, '') not like 'GIFT:%'
              and o.internal_user_id is not null
        )
        select
            'finance_top_payers' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            count(*)::bigint as orders,
            coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(sum(reward_credits), 0)::bigint as plan_reward_credits,
            max(order_time) as latest_paid_at
        from real_success
        join users u on u.id = real_success.internal_user_id
        group by u.id, u.username, u.full_name, u.current_identity, u.user_group
        order by usdt_amount desc, orders desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    recent_orders = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.id,
                o.order_id,
                o.business_order_id,
                o.internal_user_id,
                u.username,
                u.full_name,
                coalesce(mp.name, '未知套餐') as plan_name,
                coalesce(mp.identity_name, '未知身份') as identity_name,
                o.payment_channel,
                o.status,
                o.final_price,
                coalesce(mp.reward_credits, 0)::bigint as reward_credits,
                o.paid_at,
                o.created_at,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                (
                    coalesce(o.payment_channel, '') not in ('RMB', 'TON', 'XTR')
                    or coalesce(o.tx_hash, '') like 'manual_%'
                    or coalesce(o.order_id, '') like 'GIFT:%'
                ) as is_internal_order
            from orders o
            left join users u on u.id = o.internal_user_id
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_recent_orders' as row_type,
            id,
            order_id,
            business_order_id,
            internal_user_id,
            username,
            full_name,
            plan_name,
            identity_name,
            payment_channel,
            status,
            final_price,
            reward_credits,
            paid_at,
            created_at,
            order_time,
            is_internal_order
        from bounded
        order by order_time desc nulls last, id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    health = _row(health_row)
    health["flags"] = _finance_health_flags(health)
    return {
        "days": days,
        "limit": limit,
        "summary": _row(summary),
        "daily": _rows(daily),
        "hourly": _rows(hourly),
        "channels": _rows(channels),
        "plans": _rows(plans),
        "first_purchase": _row(first_purchase),
        "segments": _rows(segments),
        "invitation": _row(invitation),
        "health": health,
        "top_payers": _rows(top_payers),
        "recent_orders": _rows(recent_orders),
    }


@router.get("/api/finance/hourly-comparison")
async def finance_hourly_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    hourly = await _fetch(
        f"""
        with selected_dates as (
            select unnest($1::text[]) as selected_date
        ),
        hours as (
            select generate_series(0, 23)::int as hour
        ),
        grid as (
            select selected_dates.selected_date, hours.hour
            from selected_dates
            cross join hours
        ),
        bounded as (
            select
                to_char(coalesce(o.paid_at, o.updated_at, o.created_at)::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where to_char(coalesce(o.paid_at, o.updated_at, o.created_at)::date, 'YYYY-MM-DD') = any($1::text[])
        ),
        hourly_orders as (
            select
                selected_date,
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1, 2
        )
        select
            'finance_hourly_comparison' as row_type,
            grid.selected_date as date,
            grid.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.usdt_amount, 0) as usdt_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from grid
        left join hourly_orders
          on hourly_orders.selected_date = grid.selected_date
         and hourly_orders.hour = grid.hour
        order by array_position($1::text[], grid.selected_date), grid.hour
        """,
        compare_dates,
    )
    return {"dates": compare_dates, "hourly": _rows(hourly)}


@router.get("/api/finance/hourly-cumulative")
async def finance_hourly_cumulative(
    days: int = Query(30, ge=1, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp(days, 1, MAX_ANALYTICS_DAYS)
    hourly = await _fetch(
        f"""
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        bounded as (
            select
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= now() - ($1::int * interval '1 day')
        ),
        hourly_orders as (
            select
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1
        )
        select
            'finance_hourly_cumulative' as row_type,
            hours.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.usdt_amount, 0) as usdt_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from hours
        left join hourly_orders using (hour)
        order by hours.hour
        """,
        days,
    )
    return {"days": days, "hourly": _rows(hourly)}
