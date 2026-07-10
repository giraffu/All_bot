from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from .analytics_common import (
    CHECKIN_SPLIT_CTES,
    GENERATION_OPERATION_TYPES,
    MAX_ANALYTICS_DAYS,
    _chart_days,
    _clamp,
    _clamp_days,
    _credit_health_flags,
    _fetch,
    _fetchrow,
    _gather_limited,
    _query_days,
    _row,
    _rows,
)


router = APIRouter()


@router.get("/api/credit-flow-analytics")
async def credit_flow_analytics(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    return await _build_credit_flow_analytics(days=days, limit=limit)


async def _build_credit_flow_analytics(
    *,
    days: int,
    limit: int,
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    tasks = _start_credit_flow_analytics_tasks(
        query_days=query_days,
        chart_days=chart_days,
        limit=limit,
    )
    (
        summary_row,
        daily,
        daily_categories,
        categories,
        composition_identity,
        composition_group,
        composition_channel,
        composition_payer,
        health_row,
        risk_users,
    ) = await _gather_limited(2, *tasks)
    return _build_credit_flow_response(
        days=days,
        limit=limit,
        summary_row=summary_row,
        daily=daily,
        daily_categories=daily_categories,
        categories=categories,
        composition_identity=composition_identity,
        composition_group=composition_group,
        composition_channel=composition_channel,
        composition_payer=composition_payer,
        health_row=health_row,
        risk_users=risk_users,
    )


def _start_credit_flow_analytics_tasks(
    *,
    query_days: int,
    chart_days: int,
    limit: int,
) -> tuple[Any, ...]:
    summary_task = _fetchrow(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
        ),
        {CHECKIN_SPLIT_CTES},
        summary as (
            select
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as gross_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as gross_expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as paid_recharge_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                coalesce(sum(credit_change) filter (
                    where credit_change > 0
                      and (
                        operation_type in ('checkin', 'welcome_bonus', 'affiliate_credits_redeem')
                        or operation_type like 'referral_reward%'
                      )
                ), 0)::bigint as non_paid_grant_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward'), 0)::bigint as internal_transfer_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase'), 0))::bigint as internal_transfer_expense
            from checkin_split
        ),
        balances as (
            select coalesce(sum(coalesce(credits, 0)), 0)::bigint as current_total_credits
            from users
        )
        select
            summary.gross_income,
            summary.gross_expense,
            summary.net_change,
            summary.paid_recharge_income,
            summary.checkin_income,
            summary.free_checkin_income,
            summary.identity_checkin_bonus_income,
            summary.non_paid_grant_income,
            summary.refund_income,
            summary.generation_expense,
            balances.current_total_credits,
            round(summary.gross_expense::numeric / greatest($1::numeric, 1), 2) as avg_daily_expense,
            case
                when summary.gross_expense <= 0 then 0
                else round(balances.current_total_credits::numeric / (summary.gross_expense::numeric / greatest($1::numeric, 1)), 2)
            end as balance_burn_days,
            summary.internal_transfer_income,
            summary.internal_transfer_expense
        from summary, balances
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    daily_task = _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        flows as (
            select
                created_at::date as day,
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
        ),
        {CHECKIN_SPLIT_CTES},
        daily_logs as (
            select
                day,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as recharge_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income
            from checkin_split
            group by 1
        )
        select
            'credit_flow_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(daily_logs.income, 0)::bigint as income,
            coalesce(daily_logs.expense, 0)::bigint as expense,
            coalesce(daily_logs.net_change, 0)::bigint as net_change,
            coalesce(daily_logs.recharge_income, 0)::bigint as recharge_income,
            coalesce(daily_logs.checkin_income, 0)::bigint as checkin_income,
            coalesce(daily_logs.free_checkin_income, 0)::bigint as free_checkin_income,
            coalesce(daily_logs.identity_checkin_bonus_income, 0)::bigint as identity_checkin_bonus_income,
            coalesce(daily_logs.generation_expense, 0)::bigint as generation_expense,
            coalesce(daily_logs.refund_income, 0)::bigint as refund_income
        from days
        left join daily_logs using (day)
        order by days.day
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    daily_categories_task = _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        category_order(category, direction, sort_order) as (
            values
                ('充值/套餐发放', 'income', 1),
                ('免费签到', 'income', 2),
                ('身份加成签到', 'income', 3),
                ('注册欢迎', 'income', 4),
                ('邀请奖励', 'income', 5),
                ('返佣兑换', 'income', 6),
                ('退款/补偿', 'income', 7),
                ('Gallery 解锁收入', 'income', 8),
                ('后台调整', 'income', 9),
                ('其他收入', 'income', 10),
                ('生成/消费支出', 'expense', 20),
                ('Gallery 解锁支出', 'expense', 21),
                ('后台调整', 'expense', 22),
                ('其他支出', 'expense', 23)
        ),
        flows as (
            select
                created_at::date as day,
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        classified as (
            select
                day,
                user_id,
                free_checkin_income as credit_change,
                'income' as direction,
                '免费签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and free_checkin_income > 0

            union all

            select
                day,
                user_id,
                greatest(credit_change - free_checkin_income, 0) as credit_change,
                'income' as direction,
                '身份加成签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and greatest(credit_change - free_checkin_income, 0) > 0

            union all

            select
                day,
                user_id,
                credit_change,
                case when credit_change > 0 then 'income' else 'expense' end as direction,
                case
                    when credit_change > 0 and operation_type = 'recharge' then '充值/套餐发放'
                    when credit_change > 0 and operation_type = 'welcome_bonus' then '注册欢迎'
                    when credit_change > 0 and operation_type like 'referral_reward%' then '邀请奖励'
                    when credit_change > 0 and operation_type = 'affiliate_credits_redeem' then '返佣兑换'
                    when credit_change > 0 and operation_type like 'refund%' then '退款/补偿'
                    when credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward' then 'Gallery 解锁收入'
                    when credit_change > 0 and operation_type = 'admin_update' then '后台调整'
                    when credit_change > 0 then '其他收入'
                    when credit_change < 0 and operation_type = any($2::text[]) then '生成/消费支出'
                    when credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase' then 'Gallery 解锁支出'
                    when credit_change < 0 and operation_type = 'admin_update' then '后台调整'
                    else '其他支出'
                end as category
            from checkin_split
            where credit_change <> 0
              and not (credit_change > 0 and operation_type = 'checkin')
        ),
        grouped as (
            select
                day,
                category,
                direction,
                count(*)::bigint as events,
                count(distinct user_id)::bigint as users,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change
            from classified
            group by 1, 2, 3
        )
        select
            'credit_flow_daily_category' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            category_order.category,
            category_order.direction,
            coalesce(grouped.events, 0)::bigint as events,
            coalesce(grouped.users, 0)::bigint as users,
            coalesce(grouped.income, 0)::bigint as income,
            coalesce(grouped.expense, 0)::bigint as expense,
            coalesce(grouped.net_change, 0)::bigint as net_change
        from days
        cross join category_order
        left join grouped
          on grouped.day = days.day
         and grouped.category = category_order.category
         and grouped.direction = category_order.direction
        where coalesce(grouped.events, 0) > 0
        order by days.day, category_order.sort_order
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    categories_task = _fetch(
        f"""
        with category_order(category, direction, sort_order) as (
            values
                ('充值/套餐发放', 'income', 1),
                ('免费签到', 'income', 2),
                ('身份加成签到', 'income', 3),
                ('注册欢迎', 'income', 4),
                ('邀请奖励', 'income', 5),
                ('返佣兑换', 'income', 6),
                ('退款/补偿', 'income', 7),
                ('Gallery 解锁收入', 'income', 8),
                ('后台调整', 'income', 9),
                ('其他收入', 'income', 10),
                ('生成/消费支出', 'expense', 20),
                ('Gallery 解锁支出', 'expense', 21),
                ('后台调整', 'expense', 22),
                ('其他支出', 'expense', 23)
        ),
        bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                created_at,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        classified as (
            select
                user_id,
                free_checkin_income as credit_change,
                'income' as direction,
                '免费签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and free_checkin_income > 0

            union all

            select
                user_id,
                greatest(credit_change - free_checkin_income, 0) as credit_change,
                'income' as direction,
                '身份加成签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and greatest(credit_change - free_checkin_income, 0) > 0

            union all

            select
                user_id,
                credit_change,
                case when credit_change > 0 then 'income' else 'expense' end as direction,
                case
                    when credit_change > 0 and operation_type = 'recharge' then '充值/套餐发放'
                    when credit_change > 0 and operation_type = 'welcome_bonus' then '注册欢迎'
                    when credit_change > 0 and operation_type like 'referral_reward%' then '邀请奖励'
                    when credit_change > 0 and operation_type = 'affiliate_credits_redeem' then '返佣兑换'
                    when credit_change > 0 and operation_type like 'refund%' then '退款/补偿'
                    when credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward' then 'Gallery 解锁收入'
                    when credit_change > 0 and operation_type = 'admin_update' then '后台调整'
                    when credit_change > 0 then '其他收入'
                    when credit_change < 0 and operation_type = any($2::text[]) then '生成/消费支出'
                    when credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase' then 'Gallery 解锁支出'
                    when credit_change < 0 and operation_type = 'admin_update' then '后台调整'
                    else '其他支出'
                end as category
            from checkin_split
            where credit_change <> 0
              and not (credit_change > 0 and operation_type = 'checkin')
        ),
        grouped as (
            select
                category,
                direction,
                count(*)::bigint as events,
                count(distinct user_id)::bigint as users,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change
            from classified
            group by 1, 2
        )
        select
            'credit_flow_category' as row_type,
            category_order.category,
            category_order.direction,
            coalesce(grouped.events, 0)::bigint as events,
            coalesce(grouped.users, 0)::bigint as users,
            coalesce(grouped.income, 0)::bigint as income,
            coalesce(grouped.expense, 0)::bigint as expense,
            coalesce(grouped.net_change, 0)::bigint as net_change
        from category_order
        left join grouped
          on grouped.category = category_order.category
         and grouped.direction = category_order.direction
        order by category_order.sort_order
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    composition_identity_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_identity' as row_type,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        limit 20
        """,
        query_days,
    )
    composition_group_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_user_group' as row_type,
            coalesce(nullif(u.user_group, ''), '凡人') as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        limit 20
        """,
        query_days,
    )
    composition_channel_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_channel_member' as row_type,
            case when u.is_channel_member is true then '入宗门' else '未入宗门' end as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        """,
        query_days,
    )
    composition_payer_task = _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        paid_users as (
            select distinct internal_user_id
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and internal_user_id is not null
        ),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_payer' as row_type,
            case when paid_users.internal_user_id is null then '未付费用户' else '付费用户' end as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join paid_users on paid_users.internal_user_id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        """,
        query_days,
    )
    health_task = _fetchrow(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
        ),
        {CHECKIN_SPLIT_CTES},
        summary as (
            select
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::numeric as gross_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::numeric as gross_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::numeric as paid_recharge_income,
                coalesce(sum(credit_change) filter (
                    where credit_change > 0
                      and (
                        operation_type in ('checkin', 'welcome_bonus', 'affiliate_credits_redeem')
                        or operation_type like 'referral_reward%'
                      )
                ), 0)::numeric as non_paid_grant_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::numeric as refund_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::numeric as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::numeric as checkin_income
            from checkin_split
        ),
        top_income as (
            select coalesce(max(user_income), 0)::numeric as top_user_income
            from (
                select user_id, sum(credit_change) as user_income
                from checkin_split
                where credit_change > 0
                group by user_id
            ) ranked
        )
        select
            'credit_flow_health' as row_type,
            round(case when gross_income > 0 then paid_recharge_income / gross_income * 100 else 0 end, 2) as paid_recharge_ratio,
            round(case when gross_income > 0 then non_paid_grant_income / gross_income * 100 else 0 end, 2) as non_paid_grant_ratio,
            round(case when generation_expense > 0 then refund_income / generation_expense * 100 else 0 end, 2) as refund_to_generation_ratio,
            round(case when gross_income > 0 then gross_expense / gross_income * 100 else 0 end, 2) as expense_coverage_ratio,
            round(case when gross_income > 0 then top_user_income / gross_income * 100 else 0 end, 2) as top_income_user_share,
            round(case when gross_income > 0 then checkin_income / gross_income * 100 else 0 end, 2) as checkin_pressure_ratio
        from summary, top_income
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    risk_users_task = _fetch(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                created_at,
                current_balance,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        user_flow as (
            select
                user_id,
                count(*)::bigint as events,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'referral_reward%'), 0)::bigint as referral_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as recharge_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                (array_agg(current_balance order by created_at desc))[1] as latest_balance
            from checkin_split
            group by user_id
        ),
        scored as (
            select
                coalesce(u.id, user_flow.user_id) as id,
                u.username,
                u.full_name,
                coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
                coalesce(nullif(u.user_group, ''), '凡人') as user_group,
                u.is_channel_member,
                coalesce(u.credits, user_flow.latest_balance, 0)::bigint as current_balance,
                user_flow.events,
                user_flow.income,
                user_flow.expense,
                user_flow.net_change,
                user_flow.checkin_income,
                user_flow.free_checkin_income,
                user_flow.identity_checkin_bonus_income,
                user_flow.referral_income,
                user_flow.refund_income,
                user_flow.recharge_income,
                user_flow.generation_expense,
                (
                    case when user_flow.checkin_income >= 300 and user_flow.generation_expense <= 30 then 40 else 0 end
                    + case when user_flow.referral_income >= 100 then 30 else 0 end
                    + case when user_flow.refund_income >= 50 and user_flow.refund_income >= greatest(user_flow.generation_expense * 0.2, 1) then 30 else 0 end
                    + case when user_flow.income >= 500 and user_flow.recharge_income = 0 and user_flow.generation_expense < user_flow.income * 0.25 then 25 else 0 end
                    + case when coalesce(u.credits, user_flow.latest_balance, 0) >= 500 and user_flow.generation_expense <= 50 then 20 else 0 end
                    + case when user_flow.net_change >= 300 then 15 else 0 end
                )::bigint as risk_score,
                array_remove(array[
                    case when user_flow.checkin_income >= 300 and user_flow.generation_expense <= 30 then '签到高且低消耗' end,
                    case when user_flow.referral_income >= 100 then '邀请奖励集中' end,
                    case when user_flow.refund_income >= 50 and user_flow.refund_income >= greatest(user_flow.generation_expense * 0.2, 1) then '退款补偿偏高' end,
                    case when user_flow.income >= 500 and user_flow.recharge_income = 0 and user_flow.generation_expense < user_flow.income * 0.25 then '非付费净增高' end,
                    case when coalesce(u.credits, user_flow.latest_balance, 0) >= 500 and user_flow.generation_expense <= 50 then '高余额低消耗' end,
                    case when user_flow.net_change >= 300 then '周期净增较高' end
                ], null::text) as risk_reasons
            from user_flow
            left join users u on u.id = user_flow.user_id
        )
        select
            'risk_user_rank' as row_type,
            id,
            username,
            full_name,
            current_identity,
            user_group,
            is_channel_member,
            current_balance,
            events,
            income,
            expense,
            net_change,
            checkin_income,
            free_checkin_income,
            identity_checkin_bonus_income,
            referral_income,
            refund_income,
            recharge_income,
            generation_expense,
            risk_score,
            risk_reasons
        from scored
        where risk_score > 0
        order by risk_score desc, net_change desc, income desc, id desc
        limit $3::int
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
        limit,
    )
    return (
        summary_task,
        daily_task,
        daily_categories_task,
        categories_task,
        composition_identity_task,
        composition_group_task,
        composition_channel_task,
        composition_payer_task,
        health_task,
        risk_users_task,
    )


def _build_credit_flow_response(
    *,
    days: int,
    limit: int,
    summary_row: Any,
    daily: Any,
    daily_categories: Any,
    categories: Any,
    composition_identity: Any,
    composition_group: Any,
    composition_channel: Any,
    composition_payer: Any,
    health_row: Any,
    risk_users: Any,
) -> dict[str, Any]:
    summary = _row(summary_row)
    health = _row(health_row)
    health["flags"] = _credit_health_flags(summary, health)
    return {
        "days": days,
        "limit": limit,
        "summary": summary,
        "daily": _rows(daily),
        "daily_categories": _rows(daily_categories),
        "categories": _rows(categories),
        "composition": {
            "identity": _rows(composition_identity),
            "user_group": _rows(composition_group),
            "channel_member": _rows(composition_channel),
            "payer": _rows(composition_payer),
        },
        "health": health,
        "risk_users": _rows(risk_users),
    }
