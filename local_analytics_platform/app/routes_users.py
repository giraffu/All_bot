from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from datetime import date

from .user_profile_analytics import (
    get_user_profile_detail,
    get_user_profile_groups,
    get_user_profile_users,
)
from .user_profile_snapshots import (
    build_user_profile_visualizations,
    get_user_profile_snapshot_rows,
)

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
    _query_days,
    _resolve_user_profile_period,
    _row,
    _rows,
)


router = APIRouter()


@router.get("/api/user-analytics")
async def user_analytics(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    return await _build_user_analytics_payload(
        days=days,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


async def _build_user_analytics_payload(
    *,
    days: int,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> dict[str, Any]:
    days, query_days, start_date, end_date = _resolve_user_profile_period(days, start_date, end_date)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    sections = await _fetch_user_analytics_sections(
        query_days=query_days,
        chart_days=chart_days,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    return _build_user_analytics_response(
        days=days,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        **sections,
    )


async def _fetch_user_analytics_sections(
    *,
    query_days: int,
    chart_days: int,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> dict[str, Any]:
    summary = await _fetchrow(
        """
        with bounds as (
            select
                coalesce($5::date::timestamp, now() - ($1::int * interval '1 day')) as start_at,
                coalesce(($6::date + interval '1 day')::timestamp, now()) as end_at
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
        period_generation_users as (
            select distinct history.user_id
            from history, bounds
            where history.user_id is not null
              and history.created_at >= bounds.start_at
              and history.created_at < bounds.end_at
        ),
        ever_generation_users as (
            select distinct history.user_id
            from history
            where history.user_id is not null
        ),
        low_trust_free_tier_users as (
            select users.*
            from users
            left join successful_order_users on successful_order_users.user_id = users.id
            left join high_quality_referral_exempt_users on high_quality_referral_exempt_users.user_id = users.id
            where coalesce(users.checkin_count, 0) > 7
              and successful_order_users.user_id is null
              and high_quality_referral_exempt_users.user_id is null
        ),
        low_trust_exempt_users as (
            select users.*
            from users
            left join successful_order_users on successful_order_users.user_id = users.id
            join high_quality_referral_exempt_users on high_quality_referral_exempt_users.user_id = users.id
            where coalesce(users.checkin_count, 0) > 7
              and successful_order_users.user_id is null
        ),
        referred_real_success_orders as (
            select orders.*
            from orders
            join referrals on referrals.invitee_id = orders.internal_user_id
            where orders.status = 'SUCCESS'
              and orders.internal_user_id is not null
        ),
        low_trust_referral_edges as (
            select
                referrals.inviter_id,
                referrals.invitee_id,
                invitees.is_channel_member,
                coalesce(invitees.generation_count, 0) as invitee_generation_count,
                (
                    coalesce(invitees.checkin_count, 0) > 7
                    and invitee_success.user_id is null
                    and invitee_high_quality.user_id is null
                ) as invitee_is_low_trust_free_tier
            from referrals
            join low_trust_free_tier_users inviters on inviters.id = referrals.inviter_id
            left join users invitees on invitees.id = referrals.invitee_id
            left join successful_order_users invitee_success on invitee_success.user_id = referrals.invitee_id
            left join high_quality_referral_exempt_users invitee_high_quality on invitee_high_quality.user_id = referrals.invitee_id
        ),
        low_trust_referred_real_success_orders as (
            select orders.*
            from orders
            join low_trust_referral_edges edges on edges.invitee_id = orders.internal_user_id
            where orders.status = 'SUCCESS'
              and orders.internal_user_id is not null
        ),
        inviter_recharge_rates as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::numeric as referral_relations,
                count(distinct successful_order_users.user_id)::numeric as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct successful_order_users.user_id)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate
            from referrals
            left join successful_order_users on successful_order_users.user_id = referrals.invitee_id
            group by referrals.inviter_id
        ),
        affiliate_ledger as (
            select
                coalesce(sum(amount_usdt) filter (where direction = 'IN'), 0)::numeric as total_commission_usdt,
                coalesce(sum(amount_usdt) filter (where direction = 'OUT'), 0)::numeric as spent_commission_usdt,
                coalesce(sum(case
                    when direction = 'IN' then amount_usdt
                    when direction = 'OUT' then -amount_usdt
                    else 0
                end), 0)::numeric as available_balance_usdt
            from affiliate_transactions
            where status = 'SUCCESS'
        )
        select
            count(*)::bigint as total_users,
            count(*) filter (
                where created_at >= bounds.start_at
                  and created_at < bounds.end_at
            )::bigint as new_users,
            count(*) filter (
                where (last_activity >= bounds.start_at and last_activity < bounds.end_at)
                   or period_generation_users.user_id is not null
            )::bigint as active_users,
            count(*) filter (
                where last_activity is null
                  and coalesce(generation_count, 0) = 0
                  and ever_generation_users.user_id is null
            )::bigint as never_active_users,
            count(*) filter (
                where (
                    last_activity is not null
                    or coalesce(generation_count, 0) > 0
                    or ever_generation_users.user_id is not null
                )
                  and not (
                      (last_activity >= bounds.start_at and last_activity < bounds.end_at)
                      or period_generation_users.user_id is not null
                  )
            )::bigint as dormant_users,
            count(*) filter (where is_channel_member is true)::bigint as channel_members,
            count(*) filter (where hashed_password is not null)::bigint as password_users,
            count(*) filter (where is_submission_banned is true)::bigint as submission_banned_users,
            count(*) filter (where coalesce(generation_count, 0) > 0)::bigint as generation_users,
            (select count(*) from real_success_payers)::bigint as paying_users,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                where payer_users.is_channel_member is true
            )::bigint as paying_channel_members,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                where coalesce(payer_users.generation_count, 0) > 0
            )::bigint as paying_generation_users,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                join bounds payer_bounds on true
                left join period_generation_users payer_period_generation
                    on payer_period_generation.user_id = payer_users.id
                where (
                    payer_users.last_activity >= payer_bounds.start_at
                    and payer_users.last_activity < payer_bounds.end_at
                )
                   or payer_period_generation.user_id is not null
            )::bigint as active_paying_users,
            round(
                case
                    when count(*) > 0
                    then (select count(*) from real_success_payers)::numeric / count(*)::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_total_users,
            round(
                case
                    when count(*) filter (where is_channel_member is true) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        where payer_users.is_channel_member is true
                    )::numeric / (count(*) filter (where is_channel_member is true))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_channel_members,
            round(
                case
                    when count(*) filter (where coalesce(generation_count, 0) > 0) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        where coalesce(payer_users.generation_count, 0) > 0
                    )::numeric / (count(*) filter (where coalesce(generation_count, 0) > 0))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_generation_users,
            round(
                case
                    when count(*) filter (
                        where (last_activity >= bounds.start_at and last_activity < bounds.end_at)
                           or period_generation_users.user_id is not null
                    ) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        join bounds payer_bounds on true
                        left join period_generation_users payer_period_generation
                            on payer_period_generation.user_id = payer_users.id
                        where (
                            payer_users.last_activity >= payer_bounds.start_at
                            and payer_users.last_activity < payer_bounds.end_at
                        )
                           or payer_period_generation.user_id is not null
                    )::numeric / (count(*) filter (
                        where (last_activity >= bounds.start_at and last_activity < bounds.end_at)
                           or period_generation_users.user_id is not null
                    ))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_active_users,
            coalesce((
                select round(avg(invitee_recharge_rate), 2)
                from inviter_recharge_rates
            ), 0)::numeric as avg_inviter_invitee_recharge_rate,
            (select count(*) from inviter_recharge_rates)::bigint as inviter_recharge_rate_sample_size,
            coalesce(sum(coalesce(credits, 0)), 0)::bigint as total_credits,
            coalesce(
                sum(coalesce(credits, 0)) filter (
                    where coalesce(generation_count, 0) > 0
                       or (last_activity >= bounds.start_at and last_activity < bounds.end_at)
                       or period_generation_users.user_id is not null
                ),
                0
            )::bigint as active_credits,
            (select count(*) from low_trust_free_tier_users)::bigint as low_trust_free_tier_users,
            (
                select count(*)
                from low_trust_free_tier_users
                cross join bounds as low_trust_bounds
                left join period_generation_users
                    on period_generation_users.user_id = low_trust_free_tier_users.id
                where (
                    last_activity >= low_trust_bounds.start_at
                    and last_activity < low_trust_bounds.end_at
                )
                   or period_generation_users.user_id is not null
            )::bigint as low_trust_active_users,
            (select count(*) from low_trust_free_tier_users where coalesce(generation_count, 0) > 0)::bigint as low_trust_generation_users,
            (select coalesce(sum(coalesce(credits, 0)), 0) from low_trust_free_tier_users)::bigint as low_trust_total_credits,
            (select count(*) from low_trust_exempt_users)::bigint as low_trust_exempt_users,
            (select count(distinct inviter_id) from low_trust_referral_edges)::bigint as low_trust_inviters_count,
            (
                select count(distinct invitee_id)
                from low_trust_referral_edges
                where invitee_is_low_trust_free_tier is false
            )::bigint as low_trust_non_low_trust_invitees_count,
            (
                select count(distinct internal_user_id)
                from low_trust_referred_real_success_orders
            )::bigint as low_trust_recharged_invitees_count,
            (select count(*) from referrals)::bigint as referral_relations,
            (select count(distinct inviter_id) from referrals)::bigint as inviters_count,
            (
                select count(distinct referrals.invitee_id)
                from referrals
                join users invitees on invitees.id = referrals.invitee_id
                where invitees.is_channel_member is true
            )::bigint as invitee_channel_members,
            (
                select count(distinct referrals.invitee_id)
                from referrals
                join users invitees on invitees.id = referrals.invitee_id
                where coalesce(invitees.generation_count, 0) > 0
            )::bigint as invitee_generation_users,
            (select count(distinct internal_user_id) from referred_real_success_orders)::bigint as recharged_invitees_count,
            (select count(*) from referred_real_success_orders)::bigint as invitee_recharge_orders,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'RMB'
            ), 0)::numeric as invitee_recharge_total_rmb,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'TON'
            ), 0)::numeric as invitee_recharge_total_ton,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'XTR'
            ), 0)::numeric as invitee_recharge_total_stars,
            coalesce((
                select
                    sum(case
                        when payment_channel = 'RMB' then final_price * $2::numeric
                        when payment_channel = 'TON' then final_price * $3::numeric
                        when payment_channel = 'XTR' then final_price * $4::numeric
                        else 0
                    end)
                from referred_real_success_orders
            ), 0)::numeric as invitee_recharge_total_usdt,
            (select total_commission_usdt from affiliate_ledger)::numeric as affiliate_total_commission_usdt,
            (select spent_commission_usdt from affiliate_ledger)::numeric as affiliate_spent_commission_usdt,
            (select available_balance_usdt from affiliate_ledger)::numeric as affiliate_available_balance_usdt
        from users
        cross join bounds
        left join period_generation_users on period_generation_users.user_id = users.id
        left join ever_generation_users on ever_generation_users.user_id = users.id
        """,
        query_days,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
        start_date,
        end_date,
    )
    daily = await _fetch(
        """
        with bounds as (
            select
                coalesce($2::date, current_date - (($1::int - 1) * interval '1 day'))::date as start_date,
                coalesce($3::date, current_date)::date as end_date
        ),
        days as (
            select generate_series(
                bounds.start_date,
                bounds.end_date,
                interval '1 day'
            )::date as day
            from bounds
        ),
        user_daily as (
            select created_at::date as day, count(*)::bigint as new_users
            from users, bounds
            where created_at >= bounds.start_date::timestamp
              and created_at < (bounds.end_date + 1)::timestamp
            group by 1
        ),
        channel_member_daily as (
            select created_at::date as day, count(*)::bigint as new_channel_members
            from users, bounds
            where created_at >= bounds.start_date::timestamp
              and created_at < (bounds.end_date + 1)::timestamp
              and is_channel_member is true
            group by 1
        ),
        first_generation_daily as (
            select first_day as day, count(*)::bigint as new_generation_users
            from (
                select user_id, min(created_at)::date as first_day
                from history
                where user_id is not null
                group by user_id
            ) first_generations, bounds
            where first_day >= bounds.start_date
              and first_day <= bounds.end_date
            group by 1
        ),
        active_daily as (
            select created_at::date as day, count(distinct user_id)::bigint as active_users
            from history, bounds
            where created_at >= bounds.start_date::timestamp
              and created_at < (bounds.end_date + 1)::timestamp
            group by 1
        ),
        checkin_daily as (
            select checkin_date::date as day, count(*)::bigint as checkins
            from checkin_history, bounds
            where checkin_date >= bounds.start_date
              and checkin_date <= bounds.end_date
            group by 1
        )
        select
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(user_daily.new_users, 0)::bigint as new_users,
            coalesce(channel_member_daily.new_channel_members, 0)::bigint as new_channel_members,
            coalesce(first_generation_daily.new_generation_users, 0)::bigint as new_generation_users,
            coalesce(active_daily.active_users, 0)::bigint as active_users,
            coalesce(checkin_daily.checkins, 0)::bigint as checkins
        from days
        left join user_daily using (day)
        left join channel_member_daily using (day)
        left join first_generation_daily using (day)
        left join active_daily using (day)
        left join checkin_daily using (day)
        order by days.day
        """,
        chart_days,
        start_date,
        end_date,
    )
    identity = await _fetch(
        """
        with grouped as (
            select
                coalesce(nullif(current_identity, ''), '外门弟子') as identity_label,
                count(*)::bigint as users
            from users
            group by 1
        )
        select identity_label as label, users as count
        from grouped
        order by case identity_label
            when '外门弟子' then 1
            when '内门弟子' then 2
            when '核心弟子' then 3
            when '真传弟子' then 4
            else 99
        end, identity_label
        """
    )
    user_group = await _fetch(
        """
        with grouped as (
            select
                coalesce(nullif(user_group, ''), '凡人') as user_group_label,
                count(*)::bigint as users
            from users
            group by 1
        )
        select user_group_label as label, users as count
        from grouped
        order by case user_group_label
            when '凡人' then 1
            when '练气期' then 2
            when '筑基期' then 3
            when '金丹期' then 4
            when '元婴期' then 5
            else 99
        end, user_group_label
        """
    )
    credit_holding = await _fetch(
        """
        with bucketed as (
            select case
                when coalesce(credits, 0) <= 0 then '0'
                when coalesce(credits, 0) between 1 and 10 then '1-10'
                when coalesce(credits, 0) between 11 and 50 then '11-50'
                when coalesce(credits, 0) between 51 and 100 then '51-100'
                when coalesce(credits, 0) between 101 and 500 then '101-500'
                when coalesce(credits, 0) between 501 and 1000 then '501-1000'
                when coalesce(credits, 0) between 1001 and 5000 then '1001-5000'
                else '5000+'
            end as credit_bucket
            from users
        )
        select credit_bucket as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case credit_bucket
            when '0' then 1
            when '1-10' then 2
            when '11-50' then 3
            when '51-100' then 4
            when '101-500' then 5
            when '501-1000' then 6
            when '1001-5000' then 7
            else 8
        end
        """
    )
    generation_count = await _fetch(
        """
        with bucketed as (
            select case
                when coalesce(generation_count, 0) <= 0 then '0'
                when coalesce(generation_count, 0) = 1 then '1'
                when coalesce(generation_count, 0) = 2 then '2'
                when coalesce(generation_count, 0) = 3 then '3'
                when coalesce(generation_count, 0) = 4 then '4'
                when coalesce(generation_count, 0) = 5 then '5'
                when coalesce(generation_count, 0) between 6 and 10 then '6-10'
                when coalesce(generation_count, 0) between 11 and 20 then '11-20'
                when coalesce(generation_count, 0) between 21 and 50 then '21-50'
                when coalesce(generation_count, 0) between 51 and 100 then '51-100'
                when coalesce(generation_count, 0) between 101 and 200 then '101-200'
                when coalesce(generation_count, 0) between 201 and 500 then '201-500'
                when coalesce(generation_count, 0) between 501 and 1000 then '501-1000'
                else '1000+'
            end as generation_bucket
            from users
        )
        select generation_bucket as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case generation_bucket
            when '0' then 1
            when '1' then 2
            when '2' then 3
            when '3' then 4
            when '4' then 5
            when '5' then 6
            when '6-10' then 7
            when '11-20' then 8
            when '21-50' then 9
            when '51-100' then 10
            when '101-200' then 11
            when '201-500' then 12
            when '501-1000' then 13
            else 14
        end
        """
    )
    activity_segments = await _fetch(
        """
        with bounds as (
            select
                coalesce($2::date::timestamp, now() - ($1::int * interval '1 day')) as start_at,
                coalesce(($3::date + interval '1 day')::timestamp, now()) as end_at
        ),
        bucketed as (
            select case
                when last_activity >= now() - interval '1 day' then '24h 活跃'
                when last_activity >= now() - interval '7 day' then '7天活跃'
                when last_activity >= bounds.start_at and last_activity < bounds.end_at then '近周期活跃'
                when last_activity is null then '从未活跃'
                else '沉睡用户'
            end as activity_segment
            from users, bounds
        )
        select activity_segment as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case activity_segment
            when '24h 活跃' then 1
            when '7天活跃' then 2
            when '近周期活跃' then 3
            when '沉睡用户' then 4
            else 5
        end
        """,
        query_days,
        start_date,
        end_date,
    )
    generation_rank = await _fetch(
        """
        select
            'generation_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by coalesce(generation_count, 0) desc, id desc
        limit $1::int
        """,
        limit,
    )
    credits_rank = await _fetch(
        """
        select
            'credits_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by coalesce(credits, 0) desc, id desc
        limit $1::int
        """,
        limit,
    )
    referrals_rank = await _fetch(
        """
        with inviter_recharge as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::bigint as referral_relations,
                count(distinct referrals.invitee_id) filter (
                    where invitees.is_channel_member is true
                )::bigint as invitee_channel_members,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.generation_count, 0) > 0
                )::bigint as invitee_generation_users,
                count(distinct orders.internal_user_id) filter (
                    where orders.id is not null
                )::bigint as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct orders.internal_user_id) filter (where orders.id is not null)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate,
                count(orders.id)::bigint as invitee_recharge_orders,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'RMB'), 0)::numeric as invitee_recharge_total_rmb,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'TON'), 0)::numeric as invitee_recharge_total_ton,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'XTR'), 0)::numeric as invitee_recharge_total_stars,
                coalesce(sum(case
                    when orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
                    when orders.payment_channel = 'TON' then orders.final_price * $3::numeric
                    when orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
                    else 0
                end), 0)::numeric as invitee_recharge_total_usdt
            from referrals
            left join users invitees on invitees.id = referrals.invitee_id
            left join orders on orders.internal_user_id = referrals.invitee_id
                and orders.status = 'SUCCESS'
            group by referrals.inviter_id
        ),
        affiliate_ledger as (
            select
                user_id,
                coalesce(sum(amount_usdt) filter (where direction = 'IN'), 0)::numeric as affiliate_total_commission_usdt,
                coalesce(sum(amount_usdt) filter (where direction = 'OUT'), 0)::numeric as affiliate_spent_commission_usdt,
                coalesce(sum(case
                    when direction = 'IN' then amount_usdt
                    when direction = 'OUT' then -amount_usdt
                    else 0
                end), 0)::numeric as affiliate_available_balance_usdt
            from affiliate_transactions
            where status = 'SUCCESS'
            group by user_id
        )
        select
            'referrals_rank' as leaderboard,
            users.id,
            users.username,
            users.full_name,
            coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(users.user_group, ''), '凡人') as user_group,
            coalesce(users.generation_count, 0)::bigint as generation_count,
            coalesce(users.credits, 0)::bigint as credits,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0)::bigint as referral_count,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0)::bigint as referral_relations,
            coalesce(inviter_recharge.invitee_channel_members, 0)::bigint as invitee_channel_members,
            coalesce(inviter_recharge.invitee_generation_users, 0)::bigint as invitee_generation_users,
            coalesce(inviter_recharge.recharged_invitees_count, 0)::bigint as recharged_invitees_count,
            coalesce(inviter_recharge.invitee_recharge_rate, 0)::numeric as invitee_recharge_rate,
            coalesce(inviter_recharge.invitee_recharge_orders, 0)::bigint as invitee_recharge_orders,
            coalesce(inviter_recharge.invitee_recharge_total_rmb, 0)::numeric as invitee_recharge_total_rmb,
            coalesce(inviter_recharge.invitee_recharge_total_ton, 0)::numeric as invitee_recharge_total_ton,
            coalesce(inviter_recharge.invitee_recharge_total_stars, 0)::numeric as invitee_recharge_total_stars,
            coalesce(inviter_recharge.invitee_recharge_total_usdt, 0)::numeric as invitee_recharge_total_usdt,
            coalesce(affiliate_ledger.affiliate_total_commission_usdt, 0)::numeric as affiliate_total_commission_usdt,
            coalesce(affiliate_ledger.affiliate_spent_commission_usdt, 0)::numeric as affiliate_spent_commission_usdt,
            coalesce(affiliate_ledger.affiliate_available_balance_usdt, 0)::numeric as affiliate_available_balance_usdt,
            coalesce(users.checkin_count, 0)::bigint as checkin_count,
            users.last_activity,
            users.created_at,
            users.is_channel_member,
            users.is_submission_banned
        from users
        join inviter_recharge on inviter_recharge.inviter_id = users.id
        left join affiliate_ledger on affiliate_ledger.user_id = users.id
        order by
            coalesce(inviter_recharge.recharged_invitees_count, 0) desc,
            coalesce(inviter_recharge.invitee_recharge_total_usdt, 0) desc,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0) desc,
            users.id desc
        limit $1::int
        """,
        limit,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
    )
    low_trust_rank = await _fetch(
        """
        with successful_order_users as (
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
        low_trust_users as (
            select users.*
            from users
            left join successful_order_users on successful_order_users.user_id = users.id
            left join high_quality_referral_exempt_users on high_quality_referral_exempt_users.user_id = users.id
            where coalesce(users.checkin_count, 0) > 7
              and successful_order_users.user_id is null
              and high_quality_referral_exempt_users.user_id is null
        ),
        invitee_rollup as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::bigint as referral_relations,
                count(distinct referrals.invitee_id) filter (
                    where not (
                        coalesce(invitees.checkin_count, 0) > 7
                        and invitee_success.user_id is null
                        and invitee_high_quality.user_id is null
                    )
                )::bigint as non_low_trust_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct referrals.invitee_id) filter (
                            where not (
                                coalesce(invitees.checkin_count, 0) > 7
                                and invitee_success.user_id is null
                                and invitee_high_quality.user_id is null
                            )
                        )::numeric / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as non_low_trust_invitee_rate,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.checkin_count, 0) > 7
                      and invitee_success.user_id is null
                      and invitee_high_quality.user_id is null
                )::bigint as low_trust_invitees_count,
                count(distinct referrals.invitee_id) filter (
                    where invitees.is_channel_member is true
                )::bigint as invitee_channel_members,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.generation_count, 0) > 0
                )::bigint as invitee_generation_users,
                count(distinct orders.internal_user_id) filter (
                    where orders.id is not null
                )::bigint as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct orders.internal_user_id) filter (where orders.id is not null)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate,
                count(orders.id)::bigint as invitee_recharge_orders,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'RMB'), 0)::numeric as invitee_recharge_total_rmb,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'TON'), 0)::numeric as invitee_recharge_total_ton,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'XTR'), 0)::numeric as invitee_recharge_total_stars,
                coalesce(sum(case
                    when orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
                    when orders.payment_channel = 'TON' then orders.final_price * $3::numeric
                    when orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
                    else 0
                end), 0)::numeric as invitee_recharge_total_usdt
            from referrals
            left join users invitees on invitees.id = referrals.invitee_id
            left join successful_order_users invitee_success on invitee_success.user_id = referrals.invitee_id
            left join high_quality_referral_exempt_users invitee_high_quality on invitee_high_quality.user_id = referrals.invitee_id
            left join orders on orders.internal_user_id = referrals.invitee_id
                and orders.status = 'SUCCESS'
            group by referrals.inviter_id
        )
        select
            'low_trust_rank' as leaderboard,
            low_trust_users.id,
            low_trust_users.username,
            low_trust_users.full_name,
            coalesce(nullif(low_trust_users.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(low_trust_users.user_group, ''), '凡人') as user_group,
            coalesce(low_trust_users.generation_count, 0)::bigint as generation_count,
            coalesce(low_trust_users.credits, 0)::bigint as credits,
            coalesce(invitee_rollup.referral_relations, low_trust_users.referral_count, 0)::bigint as referral_count,
            coalesce(invitee_rollup.referral_relations, low_trust_users.referral_count, 0)::bigint as referral_relations,
            coalesce(invitee_rollup.non_low_trust_invitees_count, 0)::bigint as non_low_trust_invitees_count,
            coalesce(invitee_rollup.non_low_trust_invitee_rate, 0)::numeric as non_low_trust_invitee_rate,
            coalesce(invitee_rollup.low_trust_invitees_count, 0)::bigint as low_trust_invitees_count,
            coalesce(invitee_rollup.invitee_channel_members, 0)::bigint as invitee_channel_members,
            coalesce(invitee_rollup.invitee_generation_users, 0)::bigint as invitee_generation_users,
            coalesce(invitee_rollup.recharged_invitees_count, 0)::bigint as recharged_invitees_count,
            coalesce(invitee_rollup.invitee_recharge_rate, 0)::numeric as invitee_recharge_rate,
            coalesce(invitee_rollup.invitee_recharge_orders, 0)::bigint as invitee_recharge_orders,
            coalesce(invitee_rollup.invitee_recharge_total_rmb, 0)::numeric as invitee_recharge_total_rmb,
            coalesce(invitee_rollup.invitee_recharge_total_ton, 0)::numeric as invitee_recharge_total_ton,
            coalesce(invitee_rollup.invitee_recharge_total_stars, 0)::numeric as invitee_recharge_total_stars,
            coalesce(invitee_rollup.invitee_recharge_total_usdt, 0)::numeric as invitee_recharge_total_usdt,
            coalesce(low_trust_users.checkin_count, 0)::bigint as checkin_count,
            low_trust_users.last_activity,
            low_trust_users.created_at,
            low_trust_users.is_channel_member,
            low_trust_users.is_submission_banned,
            true as is_low_trust_free_tier
        from low_trust_users
        left join invitee_rollup on invitee_rollup.inviter_id = low_trust_users.id
        order by
            coalesce(invitee_rollup.non_low_trust_invitees_count, 0) desc,
            coalesce(invitee_rollup.recharged_invitees_count, 0) desc,
            coalesce(invitee_rollup.invitee_recharge_total_usdt, 0) desc,
            coalesce(invitee_rollup.invitee_generation_users, 0) desc,
            coalesce(invitee_rollup.invitee_channel_members, 0) desc,
            coalesce(low_trust_users.checkin_count, 0) desc,
            low_trust_users.id desc
        limit $1::int
        """,
        limit,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
    )
    recent_active_rank = await _fetch(
        """
        select
            'recent_active_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by last_activity desc nulls last, id desc
        limit $1::int
        """,
        limit,
    )
    summary_row = _row(summary)
    daily_rows = _rows(daily)
    snapshot_rows = await get_user_profile_snapshot_rows(
        fetch=_fetch,
        fetchrow=_fetchrow,
        days=chart_days,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "summary_row": summary_row,
        "daily_rows": daily_rows,
        "snapshot_rows": snapshot_rows,
        "identity": identity,
        "user_group": user_group,
        "credit_holding": credit_holding,
        "generation_count": generation_count,
        "activity_segments": activity_segments,
        "generation_rank": generation_rank,
        "credits_rank": credits_rank,
        "referrals_rank": referrals_rank,
        "low_trust_rank": low_trust_rank,
        "recent_active_rank": recent_active_rank,
    }


def _build_user_analytics_response(
    *,
    days: int,
    limit: int,
    start_date: date | None,
    end_date: date | None,
    summary_row: dict[str, Any],
    daily_rows: list[dict[str, Any]],
    snapshot_rows: list[dict[str, Any]],
    identity: Any,
    user_group: Any,
    credit_holding: Any,
    generation_count: Any,
    activity_segments: Any,
    generation_rank: Any,
    credits_rank: Any,
    referrals_rank: Any,
    low_trust_rank: Any,
    recent_active_rank: Any,
) -> dict[str, Any]:
    return {
        "days": days,
        "limit": limit,
        "filters": {
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        },
        "summary": summary_row,
        "daily": daily_rows,
        "visualizations": build_user_profile_visualizations(
            summary=summary_row,
            daily=daily_rows,
            snapshots=snapshot_rows,
            days=days,
        ),
        "distributions": {
            "identity": _rows(identity),
            "user_group": _rows(user_group),
            "credit_holding": _rows(credit_holding),
            "generation_count": _rows(generation_count),
            "activity_segments": _rows(activity_segments),
        },
        "leaderboards": {
            "generation": _rows(generation_rank),
            "credits": _rows(credits_rank),
            "referrals": _rows(referrals_rank),
            "low_trust": _rows(low_trust_rank),
            "recent_active": _rows(recent_active_rank),
        },
    }


@router.get("/api/user-analytics/users")
async def user_analytics_users(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1, le=10000),
    size: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    segment: str = Query("all"),
    sort: str = Query("last_activity"),
    dimension: str = Query(""),
    group_key: str = Query(""),
) -> dict[str, Any]:
    days, query_days, resolved_start_date, resolved_end_date = _resolve_user_profile_period(
        days,
        start_date,
        end_date,
    )
    return await get_user_profile_users(
        fetch=_fetch,
        fetchrow=_fetchrow,
        days=days,
        query_days=query_days,
        page=page,
        size=size,
        search=search,
        segment=segment,
        sort=sort,
        dimension=dimension or None,
        group_key=group_key,
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )


@router.get("/api/user-analytics/groups")
async def user_analytics_groups(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    dimension: str = Query("payer"),
    segment: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("users"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    days, query_days, resolved_start_date, resolved_end_date = _resolve_user_profile_period(
        days,
        start_date,
        end_date,
    )
    return await get_user_profile_groups(
        fetch=_fetch,
        days=days,
        query_days=query_days,
        dimension=dimension,
        segment=segment,
        search=search,
        sort=sort,
        limit=limit,
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )


@router.get("/api/user-analytics/users/{user_id}")
async def user_analytics_user_detail(
    user_id: int,
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp_days(days)
    return await get_user_profile_detail(
        fetch=_fetch,
        fetchrow=_fetchrow,
        user_id=user_id,
        days=days,
        query_days=_query_days(days),
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
    )
