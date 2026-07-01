from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Awaitable, Callable

from fastapi import HTTPException


Fetch = Callable[..., Awaitable[list[Any]]]
FetchRow = Callable[..., Awaitable[Any | None]]

GENERATION_OPERATION_TYPES = [
    "edit",
    "custom_video",
    "img2img_lora",
    "face_swap",
    "image",
    "video_lora",
    "undress",
    "perfect_video_insert",
    "i2i_pro",
    "ltx_video",
    "closeup_blowjob",
    "masturbation",
    "blowjob",
    "undress_tongue",
    "doggy_style",
    "wan22_video_v2",
    "txt2img",
    "i2i_draw",
    "face_video_step1",
    "penetration",
    "scail2_action_transfer",
    "text_to_image",
    "face_video",
    "scail2_video_replacement",
    "fuck",
    "scail2_face_swap_v2",
    "face_show",
    "face_tongue",
    "video_pro",
    "video_edit",
    "video_insert",
    "image_to_video",
]

USER_PROFILE_SEGMENTS = {
    "all": "true",
    "active": "is_period_active is true",
    "low_trust_free_tier": "is_low_trust_free_tier is true",
    "real_payer": "real_success_orders > 0",
    "non_payer_generator": "real_success_orders = 0 and coalesce(generation_count, 0) > 0",
    "has_invites": "referral_relations > 0",
    "has_gallery_posts": "gallery_posts > 0",
    "has_prompt_unlocks": "(prompt_unlocks_bought + prompt_unlocks_sold) > 0",
    "has_followers": "followers_count > 0",
    "submission_banned": "is_submission_banned is true",
}

USER_PROFILE_SORTS = {
    "last_activity": "last_activity desc nulls last, id desc",
    "generation_count": "coalesce(generation_count, 0) desc, id desc",
    "credits": "coalesce(credits, 0) desc, id desc",
    "recharge_usdt": "coalesce(recharge_usdt, 0) desc, real_success_orders desc, id desc",
    "credit_income": "coalesce(credit_income, 0) desc, id desc",
    "credit_expense": "coalesce(credit_expense, 0) desc, id desc",
    "referral_count": "coalesce(referral_relations, 0) desc, id desc",
    "gallery_signal": "coalesce(gallery_signal, 0) desc, gallery_posts desc, id desc",
    "followers": "coalesce(followers_count, 0) desc, id desc",
    "prompt_unlocks": "(coalesce(prompt_unlocks_bought, 0) + coalesce(prompt_unlocks_sold, 0)) desc, id desc",
    "checkins": "coalesce(checkin_count, 0) desc, id desc",
}

USER_PROFILE_GROUP_DIMENSIONS = {
    "channel_member": {
        "label": "入宗门",
        "key_sql": "case when is_channel_member is true then 'member' else 'non_member' end",
        "label_sql": "case when is_channel_member is true then '入宗门' else '未入宗门' end",
    },
    "trust": {
        "label": "信任层",
        "key_sql": "case when is_low_trust_free_tier is true then 'low_trust_free_tier' else 'standard' end",
        "label_sql": "case when is_low_trust_free_tier is true then '低信任免费层' else '常规用户' end",
    },
    "payer": {
        "label": "付费层",
        "key_sql": "case when coalesce(real_success_orders, 0) > 0 then 'real_payer' else 'non_payer' end",
        "label_sql": "case when coalesce(real_success_orders, 0) > 0 then '真实付费' else '未真实付费' end",
    },
    "identity": {
        "label": "身份",
        "key_sql": "coalesce(nullif(current_identity, ''), '外门弟子')",
        "label_sql": "coalesce(nullif(current_identity, ''), '外门弟子')",
    },
    "user_group": {
        "label": "修为",
        "key_sql": "coalesce(nullif(user_group, ''), '凡人')",
        "label_sql": "coalesce(nullif(user_group, ''), '凡人')",
    },
    "generation_band": {
        "label": "历史生成次数",
        "key_sql": """
            case
                when coalesce(generation_count, 0) = 0 then 'none'
                when coalesce(generation_count, 0) <= 5 then '1_5'
                when coalesce(generation_count, 0) <= 20 then '6_20'
                when coalesce(generation_count, 0) <= 100 then '21_100'
                else '100_plus'
            end
        """,
        "label_sql": """
            case
                when coalesce(generation_count, 0) = 0 then '0 次'
                when coalesce(generation_count, 0) <= 5 then '1-5 次'
                when coalesce(generation_count, 0) <= 20 then '6-20 次'
                when coalesce(generation_count, 0) <= 100 then '21-100 次'
                else '100+ 次'
            end
        """,
    },
    "credit_band": {
        "label": "灵石余额",
        "key_sql": """
            case
                when coalesce(credits, 0) <= 0 then 'zero_or_negative'
                when coalesce(credits, 0) < 100 then '1_99'
                when coalesce(credits, 0) < 1000 then '100_999'
                when coalesce(credits, 0) < 10000 then '1000_9999'
                else '10000_plus'
            end
        """,
        "label_sql": """
            case
                when coalesce(credits, 0) <= 0 then '0 或负数'
                when coalesce(credits, 0) < 100 then '1-99'
                when coalesce(credits, 0) < 1000 then '100-999'
                when coalesce(credits, 0) < 10000 then '1000-9999'
                else '10000+'
            end
        """,
    },
    "checkin_band": {
        "label": "历史签到",
        "key_sql": """
            case
                when coalesce(checkin_count, 0) = 0 then 'none'
                when coalesce(checkin_count, 0) <= 7 then '1_7'
                when coalesce(checkin_count, 0) <= 30 then '8_30'
                when coalesce(checkin_count, 0) <= 100 then '31_100'
                else '100_plus'
            end
        """,
        "label_sql": """
            case
                when coalesce(checkin_count, 0) = 0 then '0 次'
                when coalesce(checkin_count, 0) <= 7 then '1-7 次'
                when coalesce(checkin_count, 0) <= 30 then '8-30 次'
                when coalesce(checkin_count, 0) <= 100 then '31-100 次'
                else '100+ 次'
            end
        """,
    },
    "invitation": {
        "label": "邀请",
        "key_sql": "case when coalesce(referral_relations, 0) > 0 then 'has_invites' else 'no_invites' end",
        "label_sql": "case when coalesce(referral_relations, 0) > 0 then '有邀请' else '无邀请' end",
    },
    "community": {
        "label": "投稿社区",
        "key_sql": """
            case
                when coalesce(gallery_posts, 0) = 0 then 'no_posts'
                when coalesce(gallery_signal, 0) > 0 then 'positive_signal'
                else 'posted_no_positive_signal'
            end
        """,
        "label_sql": """
            case
                when coalesce(gallery_posts, 0) = 0 then '无投稿'
                when coalesce(gallery_signal, 0) > 0 then '投稿有正信号'
                else '投稿暂无正信号'
            end
        """,
    },
    "prompt_unlock": {
        "label": "提示词解锁",
        "key_sql": """
            case
                when coalesce(prompt_unlocks_bought, 0) > 0 and coalesce(prompt_unlocks_sold, 0) > 0 then 'buyer_author'
                when coalesce(prompt_unlocks_bought, 0) > 0 then 'buyer'
                when coalesce(prompt_unlocks_sold, 0) > 0 then 'author'
                else 'none'
            end
        """,
        "label_sql": """
            case
                when coalesce(prompt_unlocks_bought, 0) > 0 and coalesce(prompt_unlocks_sold, 0) > 0 then '既购买也被解锁'
                when coalesce(prompt_unlocks_bought, 0) > 0 then '购买解锁'
                when coalesce(prompt_unlocks_sold, 0) > 0 then '作者被解锁'
                else '无解锁'
            end
        """,
    },
    "social": {
        "label": "关注关系",
        "key_sql": """
            case
                when coalesce(mutual_follow_count, 0) > 0 then 'mutual'
                when coalesce(followers_count, 0) > 0 then 'has_followers'
                when coalesce(following_count, 0) > 0 then 'following_only'
                else 'isolated'
            end
        """,
        "label_sql": """
            case
                when coalesce(mutual_follow_count, 0) > 0 then '有互关'
                when coalesce(followers_count, 0) > 0 then '有粉丝'
                when coalesce(following_count, 0) > 0 then '只关注别人'
                else '无关注关系'
            end
        """,
    },
    "submission": {
        "label": "投稿权限",
        "key_sql": "case when is_submission_banned is true then 'submission_banned' else 'normal' end",
        "label_sql": "case when is_submission_banned is true then '投稿封禁' else '正常' end",
    },
}

USER_PROFILE_GROUP_SORTS = {
    "users": "users desc, group_label asc",
    "active_rate": "active_rate desc nulls last, users desc",
    "paying_rate": "paying_rate desc nulls last, users desc",
    "recharge_usdt": "recharge_usdt desc, users desc",
    "generation_count": "generation_count desc, users desc",
    "credit_net_change": "credit_net_change desc, users desc",
    "gallery_signal": "gallery_signal desc, users desc",
    "prompt_unlocks": "prompt_unlocks desc, users desc",
    "followers": "followers_count desc, users desc",
    "checkins": "period_checkins desc, users desc",
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(record: Any | None) -> dict[str, Any]:
    if record is None:
        return {}
    return {key: _json_value(value) for key, value in dict(record).items() if key != "row_type"}


def _rows(records: list[Any]) -> list[dict[str, Any]]:
    return [_row(record) for record in records]


def _empty_summary(defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(defaults or {})


def _search_like(search: str | None) -> str:
    normalized = (search or "").strip().lower()
    return f"%{normalized}%" if normalized else ""


def _group_dimension(dimension: str | None) -> dict[str, str] | None:
    if not dimension:
        return None
    group_dimension = USER_PROFILE_GROUP_DIMENSIONS.get(dimension)
    if group_dimension is None:
        raise HTTPException(status_code=400, detail=f"unknown user group dimension: {dimension}")
    return group_dimension


USER_PROFILE_LIST_CTE = """
with bounds as (
    select
        coalesce($6::date::timestamp, now() - ($1::int * interval '1 day')) as start_at,
        coalesce(($7::date + interval '1 day')::timestamp, now()) as end_at,
        coalesce($6::date, (now() - ($1::int * interval '1 day'))::date) as start_date,
        coalesce($7::date, now()::date) as end_date
),
query_params as (
    select $2::text as search_pattern
),
successful_order_users as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and internal_user_id is not null
),
real_success_orders as (
    select
        orders.internal_user_id as user_id,
        count(*)::bigint as real_success_orders,
        coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'RMB'), 0)::numeric as recharge_rmb,
        coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'TON'), 0)::numeric as recharge_ton,
        coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'XTR'), 0)::numeric as recharge_stars,
        coalesce(sum(case
            when orders.payment_channel = 'RMB' then orders.final_price * $3::numeric
            when orders.payment_channel = 'TON' then orders.final_price * $4::numeric
            when orders.payment_channel = 'XTR' then orders.final_price * $5::numeric
            else 0
        end), 0)::numeric as recharge_usdt,
        min(coalesce(orders.paid_at, orders.updated_at, orders.created_at)) as first_recharge_at,
        max(coalesce(orders.paid_at, orders.updated_at, orders.created_at)) as last_recharge_at
    from orders, bounds
    where orders.status = 'SUCCESS'
      and coalesce(final_price, 0) > 0
      and orders.payment_channel in ('RMB', 'TON', 'XTR')
      and orders.internal_user_id is not null
      and coalesce(orders.paid_at, orders.updated_at, orders.created_at) >= bounds.start_at
      and coalesce(orders.paid_at, orders.updated_at, orders.created_at) < bounds.end_at
    group by orders.internal_user_id
),
user_credit_flow as (
    select
        user_id,
        count(*)::bigint as credit_events,
        coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as credit_income,
        abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as credit_expense,
        coalesce(sum(credit_change), 0)::bigint as credit_net_change
    from user_logs, bounds
    where user_logs.created_at >= bounds.start_at
      and user_logs.created_at < bounds.end_at
    group by user_id
),
period_generation as (
    select
        user_id,
        count(*)::bigint as period_generations,
        count(distinct created_at::date)::bigint as active_generation_days,
        max(created_at) as last_generation_at
    from history, bounds
    where history.created_at >= bounds.start_at
      and history.created_at < bounds.end_at
      and user_id is not null
    group by user_id
),
invitation_rollup as (
    select
        referrals.inviter_id as user_id,
        count(distinct referrals.invitee_id)::bigint as referral_relations,
        count(distinct referrals.invitee_id) filter (where invitees.is_channel_member is true)::bigint as invitee_channel_members,
        count(distinct referrals.invitee_id) filter (where coalesce(invitees.generation_count, 0) > 0)::bigint as invitee_generation_users,
        count(distinct real_success_orders.user_id)::bigint as recharged_invitees_count
    from referrals
    cross join bounds
    left join users invitees on invitees.id = referrals.invitee_id
    left join real_success_orders on real_success_orders.user_id = referrals.invitee_id
    where referrals.created_at >= bounds.start_at
      and referrals.created_at < bounds.end_at
    group by referrals.inviter_id
),
gallery_rollup as (
    select
        user_id,
        count(*) filter (where is_active is true)::bigint as gallery_posts,
        coalesce(sum(likes_count) filter (where is_active is true), 0)::bigint as gallery_likes,
        coalesce(sum(dislikes_count) filter (where is_active is true), 0)::bigint as gallery_dislikes,
        coalesce(sum(applied_count) filter (where is_active is true), 0)::bigint as gallery_applies,
        coalesce(sum(comments_count) filter (where is_active is true), 0)::bigint as gallery_comments,
        coalesce(sum(
            likes_count * 2
            - dislikes_count
            + applied_count * 5
            + comments_count * 2
        ) filter (where is_active is true), 0)::bigint as gallery_signal
    from gallery_posts, bounds
    where gallery_posts.created_at >= bounds.start_at
      and gallery_posts.created_at < bounds.end_at
    group by user_id
),
prompt_unlock_purchases as (
    select
        user_id,
        count(*)::bigint as prompt_unlocks_bought,
        coalesce(sum(cost_credits), 0)::bigint as prompt_unlock_credits_spent,
        max(created_at) as last_prompt_unlock_at
    from gallery_prompt_unlocks, bounds
    where gallery_prompt_unlocks.created_at >= bounds.start_at
      and gallery_prompt_unlocks.created_at < bounds.end_at
    group by user_id
),
prompt_unlock_sales as (
    select
        author_id as user_id,
        count(*)::bigint as prompt_unlocks_sold,
        coalesce(sum(cost_credits), 0)::bigint as prompt_unlock_credits_earned,
        max(created_at) as last_prompt_unlock_sale_at
    from gallery_prompt_unlocks, bounds
    where gallery_prompt_unlocks.created_at >= bounds.start_at
      and gallery_prompt_unlocks.created_at < bounds.end_at
    group by author_id
),
followers as (
    select followee_id as user_id, count(*)::bigint as followers_count
    from user_follows, bounds
    where user_follows.created_at >= bounds.start_at
      and user_follows.created_at < bounds.end_at
    group by followee_id
),
following as (
    select follower_id as user_id, count(*)::bigint as following_count
    from user_follows, bounds
    where user_follows.created_at >= bounds.start_at
      and user_follows.created_at < bounds.end_at
    group by follower_id
),
mutual_follows as (
    select f.follower_id as user_id, count(*)::bigint as mutual_follow_count
    from user_follows f
    cross join bounds
    join user_follows back
      on back.follower_id = f.followee_id
     and back.followee_id = f.follower_id
     and back.created_at >= bounds.start_at
     and back.created_at < bounds.end_at
    where f.created_at >= bounds.start_at
      and f.created_at < bounds.end_at
    group by f.follower_id
),
period_checkins as (
    select user_id, count(*)::bigint as period_checkins, max(checkin_date) as last_period_checkin
    from checkin_history, bounds
    where checkin_date >= bounds.start_date
      and checkin_date <= bounds.end_date
    group by user_id
),
user_profile_rows as (
    select
        users.id as user_id,
        users.id,
        users.username,
        users.full_name,
        coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
        coalesce(nullif(users.user_group, ''), '凡人') as user_group,
        coalesce(users.credits, 0)::bigint as credits,
        coalesce(users.generation_count, 0)::bigint as generation_count,
        coalesce(users.checkin_count, 0)::bigint as checkin_count,
        coalesce(users.referral_count, 0)::bigint as referral_count,
        users.is_channel_member,
        users.is_submission_banned,
        users.created_at,
        users.last_activity,
        (
            coalesce(users.checkin_count, 0) > 7
            and successful_order_users.user_id is null
        ) as is_low_trust_free_tier,
        (
            (users.last_activity >= bounds.start_at and users.last_activity < bounds.end_at)
            or coalesce(period_generation.period_generations, 0) > 0
        ) as is_period_active,
        (
            (users.created_at >= bounds.start_at and users.created_at < bounds.end_at)
            or (users.last_activity >= bounds.start_at and users.last_activity < bounds.end_at)
            or coalesce(real_success_orders.real_success_orders, 0) > 0
            or coalesce(user_credit_flow.credit_events, 0) > 0
            or coalesce(period_generation.period_generations, 0) > 0
            or coalesce(invitation_rollup.referral_relations, 0) > 0
            or coalesce(gallery_rollup.gallery_posts, 0) > 0
            or coalesce(prompt_unlock_purchases.prompt_unlocks_bought, 0) > 0
            or coalesce(prompt_unlock_sales.prompt_unlocks_sold, 0) > 0
            or coalesce(followers.followers_count, 0) > 0
            or coalesce(following.following_count, 0) > 0
            or coalesce(mutual_follows.mutual_follow_count, 0) > 0
            or coalesce(period_checkins.period_checkins, 0) > 0
        ) as is_in_period_scope,
        coalesce(real_success_orders.real_success_orders, 0)::bigint as real_success_orders,
        coalesce(real_success_orders.recharge_rmb, 0)::numeric as recharge_rmb,
        coalesce(real_success_orders.recharge_ton, 0)::numeric as recharge_ton,
        coalesce(real_success_orders.recharge_stars, 0)::numeric as recharge_stars,
        coalesce(real_success_orders.recharge_usdt, 0)::numeric as recharge_usdt,
        real_success_orders.first_recharge_at,
        real_success_orders.last_recharge_at,
        coalesce(user_credit_flow.credit_events, 0)::bigint as credit_events,
        coalesce(user_credit_flow.credit_income, 0)::bigint as credit_income,
        coalesce(user_credit_flow.credit_expense, 0)::bigint as credit_expense,
        coalesce(user_credit_flow.credit_net_change, 0)::bigint as credit_net_change,
        coalesce(period_generation.period_generations, 0)::bigint as period_generations,
        coalesce(period_generation.active_generation_days, 0)::bigint as active_generation_days,
        period_generation.last_generation_at,
        coalesce(invitation_rollup.referral_relations, 0)::bigint as referral_relations,
        coalesce(invitation_rollup.invitee_channel_members, 0)::bigint as invitee_channel_members,
        coalesce(invitation_rollup.invitee_generation_users, 0)::bigint as invitee_generation_users,
        coalesce(invitation_rollup.recharged_invitees_count, 0)::bigint as recharged_invitees_count,
        coalesce(gallery_rollup.gallery_posts, 0)::bigint as gallery_posts,
        coalesce(gallery_rollup.gallery_likes, 0)::bigint as gallery_likes,
        coalesce(gallery_rollup.gallery_dislikes, 0)::bigint as gallery_dislikes,
        coalesce(gallery_rollup.gallery_applies, 0)::bigint as gallery_applies,
        coalesce(gallery_rollup.gallery_comments, 0)::bigint as gallery_comments,
        coalesce(gallery_rollup.gallery_signal, 0)::bigint as gallery_signal,
        coalesce(prompt_unlock_purchases.prompt_unlocks_bought, 0)::bigint as prompt_unlocks_bought,
        coalesce(prompt_unlock_purchases.prompt_unlock_credits_spent, 0)::bigint as prompt_unlock_credits_spent,
        prompt_unlock_purchases.last_prompt_unlock_at,
        coalesce(prompt_unlock_sales.prompt_unlocks_sold, 0)::bigint as prompt_unlocks_sold,
        coalesce(prompt_unlock_sales.prompt_unlock_credits_earned, 0)::bigint as prompt_unlock_credits_earned,
        prompt_unlock_sales.last_prompt_unlock_sale_at,
        coalesce(followers.followers_count, 0)::bigint as followers_count,
        coalesce(following.following_count, 0)::bigint as following_count,
        coalesce(mutual_follows.mutual_follow_count, 0)::bigint as mutual_follow_count,
        coalesce(period_checkins.period_checkins, 0)::bigint as period_checkins,
        period_checkins.last_period_checkin
    from users
    cross join bounds
    left join successful_order_users on successful_order_users.user_id = users.id
    left join real_success_orders on real_success_orders.user_id = users.id
    left join user_credit_flow on user_credit_flow.user_id = users.id
    left join period_generation on period_generation.user_id = users.id
    left join invitation_rollup on invitation_rollup.user_id = users.id
    left join gallery_rollup on gallery_rollup.user_id = users.id
    left join prompt_unlock_purchases on prompt_unlock_purchases.user_id = users.id
    left join prompt_unlock_sales on prompt_unlock_sales.user_id = users.id
    left join followers on followers.user_id = users.id
    left join following on following.user_id = users.id
    left join mutual_follows on mutual_follows.user_id = users.id
    left join period_checkins on period_checkins.user_id = users.id
)
"""

USER_PROFILE_SEARCH_CLAUSE = """
(
    $2::text = ''
    or lower(coalesce(username, '')) like $2::text
    or lower(coalesce(full_name, '')) like $2::text
    or id::text = btrim($2::text, '%')
)
"""


async def get_user_profile_users(
    *,
    fetch: Fetch,
    fetchrow: FetchRow,
    days: int,
    query_days: int,
    page: int,
    size: int,
    search: str,
    segment: str,
    sort: str,
    rmb_to_usdt: float,
    ton_to_usdt: float,
    stars_to_usdt: float,
    start_date: date | None = None,
    end_date: date | None = None,
    dimension: str | None = None,
    group_key: str | None = None,
) -> dict[str, Any]:
    if segment not in USER_PROFILE_SEGMENTS:
        raise HTTPException(status_code=400, detail=f"unknown user segment: {segment}")
    if sort not in USER_PROFILE_SORTS:
        raise HTTPException(status_code=400, detail=f"unknown user sort: {sort}")
    group_dimension = _group_dimension(dimension)

    page = max(1, page)
    size = max(1, min(100, size))
    offset = (page - 1) * size
    search_pattern = _search_like(search)
    segment_clause = USER_PROFILE_SEGMENTS[segment]
    sort_sql = USER_PROFILE_SORTS[sort]
    base_args = (
        query_days,
        search_pattern,
        rmb_to_usdt,
        ton_to_usdt,
        stars_to_usdt,
        start_date,
        end_date,
    )
    normalized_group_key = (group_key or "").strip()
    group_clause = ""
    count_args = base_args
    row_args = (*base_args, size, offset)
    row_limit_sql = "limit $8::int offset $9::int"
    if group_dimension and normalized_group_key:
        group_clause = f"and ({group_dimension['key_sql']}) = $8::text"
        count_args = (*base_args, normalized_group_key)
        row_args = (*base_args, normalized_group_key, size, offset)
        row_limit_sql = "limit $9::int offset $10::int"

    count = _row(
        await fetchrow(
            f"""
            {USER_PROFILE_LIST_CTE}
            select
                'user_profile_count' as row_type,
                count(*)::bigint as total
            from user_profile_rows
            where {USER_PROFILE_SEARCH_CLAUSE}
              and is_in_period_scope is true
              and {segment_clause}
              {group_clause}
            """,
            *count_args,
        )
    )
    rows = await fetch(
        f"""
        {USER_PROFILE_LIST_CTE}
        select
            'user_profile_rows' as row_type,
            *
        from user_profile_rows
        where {USER_PROFILE_SEARCH_CLAUSE}
          and is_in_period_scope is true
          and {segment_clause}
          {group_clause}
        order by {sort_sql}
        {row_limit_sql}
        """,
        *row_args,
    )
    return {
        "days": days,
        "filters": {
            "search": search.strip(),
            "segment": segment,
            "sort": sort,
            "dimension": dimension or "",
            "group_key": normalized_group_key,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        },
        "pagination": {
            "page": page,
            "size": size,
            "total": int(count.get("total") or 0),
        },
        "items": _rows(rows),
        "available_segments": sorted(USER_PROFILE_SEGMENTS),
        "available_sorts": sorted(USER_PROFILE_SORTS),
        "available_dimensions": sorted(USER_PROFILE_GROUP_DIMENSIONS),
    }


async def get_user_profile_groups(
    *,
    fetch: Fetch,
    days: int,
    query_days: int,
    dimension: str,
    segment: str,
    search: str,
    sort: str,
    limit: int,
    rmb_to_usdt: float,
    ton_to_usdt: float,
    stars_to_usdt: float,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    if segment not in USER_PROFILE_SEGMENTS:
        raise HTTPException(status_code=400, detail=f"unknown user segment: {segment}")
    if sort not in USER_PROFILE_GROUP_SORTS:
        raise HTTPException(status_code=400, detail=f"unknown user group sort: {sort}")
    group_dimension = _group_dimension(dimension)
    if group_dimension is None:
        raise HTTPException(status_code=400, detail=f"unknown user group dimension: {dimension}")

    limit = max(1, min(100, limit))
    segment_clause = USER_PROFILE_SEGMENTS[segment]
    sort_sql = USER_PROFILE_GROUP_SORTS[sort]
    key_sql = group_dimension["key_sql"]
    label_sql = group_dimension["label_sql"]
    search_pattern = _search_like(search)

    rows = await fetch(
        f"""
        {USER_PROFILE_LIST_CTE}
        select
            'user_profile_groups' as row_type,
            ({key_sql})::text as group_key,
            ({label_sql})::text as group_label,
            count(*)::bigint as users,
            round(count(*)::numeric / nullif(sum(count(*)) over (), 0)::numeric * 100, 2)::numeric as share_percent,
            count(*) filter (where is_period_active is true)::bigint as active_users,
            round(count(*) filter (where is_period_active is true)::numeric / nullif(count(*), 0)::numeric * 100, 2)::numeric as active_rate,
            count(*) filter (where is_channel_member is true)::bigint as channel_members,
            round(count(*) filter (where is_channel_member is true)::numeric / nullif(count(*), 0)::numeric * 100, 2)::numeric as channel_member_rate,
            count(*) filter (where is_low_trust_free_tier is true)::bigint as low_trust_users,
            count(*) filter (where real_success_orders > 0)::bigint as real_payers,
            round(count(*) filter (where real_success_orders > 0)::numeric / nullif(count(*), 0)::numeric * 100, 2)::numeric as paying_rate,
            coalesce(sum(real_success_orders), 0)::bigint as real_success_orders,
            coalesce(sum(recharge_usdt), 0)::numeric as recharge_usdt,
            coalesce(sum(generation_count), 0)::bigint as generation_count,
            coalesce(sum(period_generations), 0)::bigint as period_generations,
            coalesce(sum(active_generation_days), 0)::bigint as active_generation_days,
            coalesce(sum(credit_income), 0)::bigint as credit_income,
            coalesce(sum(credit_expense), 0)::bigint as credit_expense,
            coalesce(sum(credit_net_change), 0)::bigint as credit_net_change,
            coalesce(sum(referral_relations), 0)::bigint as referral_relations,
            coalesce(sum(invitee_channel_members), 0)::bigint as invitee_channel_members,
            coalesce(sum(invitee_generation_users), 0)::bigint as invitee_generation_users,
            coalesce(sum(recharged_invitees_count), 0)::bigint as recharged_invitees_count,
            round(coalesce(sum(recharged_invitees_count), 0)::numeric / nullif(coalesce(sum(referral_relations), 0), 0)::numeric * 100, 2)::numeric as invitee_recharge_rate,
            coalesce(sum(gallery_posts), 0)::bigint as gallery_posts,
            coalesce(sum(gallery_likes), 0)::bigint as gallery_likes,
            coalesce(sum(gallery_dislikes), 0)::bigint as gallery_dislikes,
            coalesce(sum(gallery_applies), 0)::bigint as gallery_applies,
            coalesce(sum(gallery_comments), 0)::bigint as gallery_comments,
            coalesce(sum(gallery_signal), 0)::bigint as gallery_signal,
            coalesce(sum(prompt_unlocks_bought), 0)::bigint as prompt_unlocks_bought,
            coalesce(sum(prompt_unlocks_sold), 0)::bigint as prompt_unlocks_sold,
            coalesce(sum(prompt_unlocks_bought + prompt_unlocks_sold), 0)::bigint as prompt_unlocks,
            coalesce(sum(prompt_unlock_credits_spent), 0)::bigint as prompt_unlock_credits_spent,
            coalesce(sum(prompt_unlock_credits_earned), 0)::bigint as prompt_unlock_credits_earned,
            coalesce(sum(followers_count), 0)::bigint as followers_count,
            coalesce(sum(following_count), 0)::bigint as following_count,
            coalesce(sum(mutual_follow_count), 0)::bigint as mutual_follow_count,
            count(*) filter (where period_checkins > 0)::bigint as checkin_users,
            coalesce(sum(period_checkins), 0)::bigint as period_checkins
        from user_profile_rows
        where {USER_PROFILE_SEARCH_CLAUSE}
          and is_in_period_scope is true
          and {segment_clause}
        group by 2, 3
        order by {sort_sql}
        limit $8::int
        """,
        query_days,
        search_pattern,
        rmb_to_usdt,
        ton_to_usdt,
        stars_to_usdt,
        start_date,
        end_date,
        limit,
    )
    return {
        "days": days,
        "dimension": {
            "key": dimension,
            "label": group_dimension["label"],
        },
        "filters": {
            "dimension": dimension,
            "segment": segment,
            "search": search.strip(),
            "sort": sort,
            "limit": limit,
            "start_date": start_date.isoformat() if start_date else "",
            "end_date": end_date.isoformat() if end_date else "",
        },
        "rows": _rows(rows),
        "available_dimensions": sorted(USER_PROFILE_GROUP_DIMENSIONS),
        "available_segments": sorted(USER_PROFILE_SEGMENTS),
        "available_sorts": sorted(USER_PROFILE_GROUP_SORTS),
    }


async def get_user_profile_detail(
    *,
    fetch: Fetch,
    fetchrow: FetchRow,
    user_id: int,
    days: int,
    query_days: int,
    rmb_to_usdt: float,
    ton_to_usdt: float,
    stars_to_usdt: float,
) -> dict[str, Any]:
    profile = _row(await fetchrow(USER_PROFILE_PROFILE_SQL, user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="user not found")

    credit_summary = _row(
        await fetchrow(USER_CREDIT_FLOW_SUMMARY_SQL, user_id, query_days, GENERATION_OPERATION_TYPES)
    )
    recharge_summary = _row(
        await fetchrow(USER_RECHARGE_SUMMARY_SQL, user_id, rmb_to_usdt, ton_to_usdt, stars_to_usdt)
    )
    invitation_summary = _row(
        await fetchrow(USER_INVITATION_SUMMARY_SQL, user_id, rmb_to_usdt, ton_to_usdt, stars_to_usdt)
    )
    generation_summary = _row(await fetchrow(USER_GENERATION_SUMMARY_SQL, user_id, query_days))
    checkin_summary = _row(await fetchrow(USER_CHECKIN_SUMMARY_SQL, user_id, query_days))
    community_summary = _row(await fetchrow(USER_COMMUNITY_SUMMARY_SQL, user_id))
    prompt_unlock_summary = _row(await fetchrow(USER_PROMPT_UNLOCK_SUMMARY_SQL, user_id))
    social_summary = _row(await fetchrow(USER_SOCIAL_SUMMARY_SQL, user_id))

    return {
        "days": days,
        "profile": profile,
        "credit_flow": {
            "summary": credit_summary,
            "categories": _rows(await fetch(USER_CREDIT_FLOW_CATEGORIES_SQL, user_id, query_days, GENERATION_OPERATION_TYPES)),
            "recent_logs": _rows(await fetch(USER_RECENT_CREDIT_LOGS_SQL, user_id)),
        },
        "recharge": {
            "summary": recharge_summary,
            "recent_orders": _rows(await fetch(USER_RECENT_ORDERS_SQL, user_id)),
        },
        "invitation": {
            "summary": invitation_summary,
            "recent_invitees": _rows(await fetch(USER_RECENT_INVITEES_SQL, user_id)),
        },
        "generation": {
            "summary": generation_summary,
            "type_distribution": _rows(await fetch(USER_GENERATION_TYPE_DISTRIBUTION_SQL, user_id, query_days)),
            "source_distribution": _rows(await fetch(USER_GENERATION_SOURCE_DISTRIBUTION_SQL, user_id, query_days)),
            "hour_distribution": _rows(await fetch(USER_GENERATION_HOUR_DISTRIBUTION_SQL, user_id, query_days)),
            "weekday_distribution": _rows(await fetch(USER_GENERATION_WEEKDAY_DISTRIBUTION_SQL, user_id, query_days)),
            "recent_generations": _rows(await fetch(USER_RECENT_GENERATIONS_SQL, user_id)),
        },
        "checkin": {
            "summary": checkin_summary,
            "recent_checkins": _rows(await fetch(USER_RECENT_CHECKINS_SQL, user_id)),
        },
        "community": {
            "summary": community_summary,
            "samples": _rows(await fetch(USER_GALLERY_SAMPLES_SQL, user_id)),
        },
        "prompt_unlock": {
            "summary": prompt_unlock_summary,
            "recent_purchases": _rows(await fetch(USER_RECENT_PROMPT_UNLOCK_PURCHASES_SQL, user_id)),
            "recent_sales": _rows(await fetch(USER_RECENT_PROMPT_UNLOCK_SALES_SQL, user_id)),
        },
        "social": {
            "summary": social_summary,
            "recent_following": _rows(await fetch(USER_RECENT_FOLLOWING_SQL, user_id)),
            "recent_followers": _rows(await fetch(USER_RECENT_FOLLOWERS_SQL, user_id)),
        },
    }


USER_PROFILE_PROFILE_SQL = """
with successful_order_users as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and internal_user_id is not null
),
real_success_payers as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and coalesce(final_price, 0) > 0
      and payment_channel in ('RMB', 'TON', 'XTR')
      and internal_user_id is not null
)
select
    'user_profile_profile' as row_type,
    users.id,
    users.telegram_id,
    users.username,
    users.full_name,
    users.language_code,
    coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
    coalesce(nullif(users.user_group, ''), '凡人') as user_group,
    users.identity_expire_at,
    coalesce(users.credits, 0)::bigint as credits,
    coalesce(users.generation_count, 0)::bigint as generation_count,
    coalesce(users.checkin_count, 0)::bigint as checkin_count,
    coalesce(users.referral_count, 0)::bigint as referral_count,
    users.is_channel_member,
    users.is_submission_banned,
    users.submission_banned_at,
    users.submission_ban_reason,
    users.created_at,
    users.last_activity,
    users.last_checkin,
    (users.hashed_password is not null) as has_password,
    coalesce(referrals.inviter_id, users.invited_by) as inviter_id,
    inviter.username as inviter_username,
    inviter.full_name as inviter_full_name,
    real_success_payers.user_id is not null as is_real_payer,
    (
        coalesce(users.checkin_count, 0) > 7
        and successful_order_users.user_id is null
    ) as is_low_trust_free_tier
from users
left join referrals on referrals.invitee_id = users.id
left join users inviter on inviter.id = coalesce(referrals.inviter_id, users.invited_by)
left join successful_order_users on successful_order_users.user_id = users.id
left join real_success_payers on real_success_payers.user_id = users.id
where users.id = $1::bigint
"""

USER_CREDIT_FLOW_SUMMARY_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since),
flows as (
    select coalesce(operation_type, '') as operation_type, coalesce(credit_change, 0)::numeric as credit_change
    from user_logs, bounds
    where user_id = $1::bigint
      and created_at >= bounds.since
)
select
    'user_credit_flow_summary' as row_type,
    coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as gross_income,
    abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as gross_expense,
    coalesce(sum(credit_change), 0)::bigint as net_change,
    coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as recharge_income,
    coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
    coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'referral_reward%'), 0)::bigint as referral_income,
    coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'affiliate_credits_redeem'), 0)::bigint as affiliate_redeem_income,
    coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward'), 0)::bigint as prompt_unlock_income,
    abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase'), 0))::bigint as prompt_unlock_expense,
    abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($3::text[])), 0))::bigint as generation_expense,
    coalesce(count(*), 0)::bigint as events
from flows
"""

USER_CREDIT_FLOW_CATEGORIES_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since),
classified as (
    select
        case
            when credit_change > 0 and operation_type = 'recharge' then '充值/套餐发放'
            when credit_change > 0 and operation_type = 'checkin' then '签到收入'
            when credit_change > 0 and operation_type = 'welcome_bonus' then '注册欢迎'
            when credit_change > 0 and operation_type like 'referral_reward%' then '邀请奖励'
            when credit_change > 0 and operation_type = 'affiliate_credits_redeem' then '返佣兑换'
            when credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward' then 'Gallery 解锁收入'
            when credit_change > 0 and operation_type like 'refund%' then '退款/补偿'
            when credit_change > 0 then '其他收入'
            when credit_change < 0 and operation_type = any($3::text[]) then '生成/消费支出'
            when credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase' then 'Gallery 解锁支出'
            else '其他支出'
        end as category,
        case when credit_change > 0 then 'income' else 'expense' end as direction,
        coalesce(credit_change, 0)::numeric as credit_change
    from user_logs, bounds
    where user_id = $1::bigint
      and created_at >= bounds.since
      and credit_change <> 0
)
select
    'user_credit_flow_categories' as row_type,
    category,
    direction,
    count(*)::bigint as events,
    coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
    abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
    coalesce(sum(credit_change), 0)::bigint as net_change
from classified
group by category, direction
order by abs(coalesce(sum(credit_change), 0)) desc, category
"""

USER_RECENT_CREDIT_LOGS_SQL = """
select
    'user_recent_credit_logs' as row_type,
    operation_type,
    credit_change,
    current_balance,
    created_at
from user_logs
where user_id = $1::bigint
order by created_at desc, id desc
limit 12
"""

USER_RECHARGE_SUMMARY_SQL = """
select
    'user_recharge_summary' as row_type,
    count(*) filter (
        where orders.status = 'SUCCESS'
          and coalesce(orders.final_price, 0) > 0
          and orders.payment_channel in ('RMB', 'TON', 'XTR')
    )::bigint as real_success_orders,
    count(*) filter (
        where orders.status = 'SUCCESS'
          and not (
              coalesce(orders.final_price, 0) > 0
              and orders.payment_channel in ('RMB', 'TON', 'XTR')
          )
    )::bigint as internal_success_orders,
    coalesce(sum(orders.final_price) filter (where orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'RMB'), 0)::numeric as real_success_rmb,
    coalesce(sum(orders.final_price) filter (where orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'TON'), 0)::numeric as real_success_ton,
    coalesce(sum(orders.final_price) filter (where orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'XTR'), 0)::numeric as real_success_stars,
    coalesce(sum(case
        when orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
        when orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'TON' then orders.final_price * $3::numeric
        when orders.status = 'SUCCESS' and coalesce(orders.final_price, 0) > 0 and orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
        else 0
    end), 0)::numeric as real_success_usdt,
    min(coalesce(orders.paid_at, orders.updated_at, orders.created_at)) filter (
        where orders.status = 'SUCCESS'
          and coalesce(orders.final_price, 0) > 0
          and orders.payment_channel in ('RMB', 'TON', 'XTR')
    ) as first_recharge_at,
    max(coalesce(orders.paid_at, orders.updated_at, orders.created_at)) filter (
        where orders.status = 'SUCCESS'
          and coalesce(orders.final_price, 0) > 0
          and orders.payment_channel in ('RMB', 'TON', 'XTR')
    ) as last_recharge_at
from orders
where orders.internal_user_id = $1::bigint
"""

USER_RECENT_ORDERS_SQL = """
select
    'user_recent_orders' as row_type,
    orders.id,
    orders.order_id,
    orders.business_order_id,
    orders.status,
    orders.payment_channel,
    orders.final_price,
    orders.original_price,
    orders.commission_usdt,
    membership_plans.name as plan_name,
    membership_plans.identity_name as plan_identity,
    coalesce(orders.paid_at, orders.updated_at, orders.created_at) as occurred_at,
    (
        orders.status = 'SUCCESS'
        and coalesce(orders.final_price, 0) > 0
        and orders.payment_channel in ('RMB', 'TON', 'XTR')
    ) as is_real_success
from orders
left join membership_plans on membership_plans.id = orders.plan_id
where orders.internal_user_id = $1::bigint
order by coalesce(orders.paid_at, orders.updated_at, orders.created_at) desc, orders.id desc
limit 12
"""

USER_INVITATION_SUMMARY_SQL = """
with real_success_orders as (
    select
        orders.internal_user_id as user_id,
        count(*)::bigint as real_success_orders,
        coalesce(sum(case
            when orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
            when orders.payment_channel = 'TON' then orders.final_price * $3::numeric
            when orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
            else 0
        end), 0)::numeric as recharge_usdt
    from orders
    where orders.status = 'SUCCESS'
      and coalesce(orders.final_price, 0) > 0
      and orders.payment_channel in ('RMB', 'TON', 'XTR')
      and orders.internal_user_id is not null
    group by orders.internal_user_id
),
invitees as (
    select referrals.invitee_id, users.is_channel_member, coalesce(users.generation_count, 0) as generation_count
    from referrals
    left join users on users.id = referrals.invitee_id
    where referrals.inviter_id = $1::bigint
),
affiliate_ledger as (
    select
        coalesce(sum(amount_usdt) filter (where direction = 'IN'), 0)::numeric as affiliate_total_commission_usdt,
        coalesce(sum(amount_usdt) filter (where direction = 'OUT'), 0)::numeric as affiliate_spent_commission_usdt,
        coalesce(sum(case
            when direction = 'IN' then amount_usdt
            when direction = 'OUT' then -amount_usdt
            else 0
        end), 0)::numeric as affiliate_available_balance_usdt
    from affiliate_transactions
    where user_id = $1::bigint
      and status = 'SUCCESS'
),
referral_rewards as (
    select coalesce(sum(credit_change), 0)::bigint as referral_reward_credits
    from user_logs
    where user_id = $1::bigint
      and credit_change > 0
      and operation_type like 'referral_reward%'
)
select
    'user_invitation_summary' as row_type,
    count(distinct invitees.invitee_id)::bigint as referral_relations,
    count(distinct invitees.invitee_id) filter (where invitees.is_channel_member is true)::bigint as invitee_channel_members,
    count(distinct invitees.invitee_id) filter (where invitees.generation_count > 0)::bigint as invitee_generation_users,
    count(distinct real_success_orders.user_id)::bigint as recharged_invitees_count,
    coalesce(sum(real_success_orders.real_success_orders), 0)::bigint as invitee_recharge_orders,
    coalesce(sum(real_success_orders.recharge_usdt), 0)::numeric as invitee_recharge_usdt,
    round(
        case
            when count(distinct invitees.invitee_id) > 0
            then count(distinct real_success_orders.user_id)::numeric / count(distinct invitees.invitee_id)::numeric * 100
            else 0
        end,
        2
    )::numeric as invitee_recharge_rate,
    (select referral_reward_credits from referral_rewards)::bigint as referral_reward_credits,
    (select affiliate_total_commission_usdt from affiliate_ledger)::numeric as affiliate_total_commission_usdt,
    (select affiliate_spent_commission_usdt from affiliate_ledger)::numeric as affiliate_spent_commission_usdt,
    (select affiliate_available_balance_usdt from affiliate_ledger)::numeric as affiliate_available_balance_usdt
from invitees
left join real_success_orders on real_success_orders.user_id = invitees.invitee_id
"""

USER_RECENT_INVITEES_SQL = """
with real_success_payers as (
    select distinct internal_user_id as user_id
    from orders
    where status = 'SUCCESS'
      and coalesce(final_price, 0) > 0
      and payment_channel in ('RMB', 'TON', 'XTR')
      and internal_user_id is not null
)
select
    'user_recent_invitees' as row_type,
    invitees.id,
    invitees.username,
    invitees.full_name,
    coalesce(nullif(invitees.current_identity, ''), '外门弟子') as current_identity,
    coalesce(nullif(invitees.user_group, ''), '凡人') as user_group,
    invitees.is_channel_member,
    coalesce(invitees.generation_count, 0)::bigint as generation_count,
    real_success_payers.user_id is not null as is_real_payer,
    referrals.created_at as referred_at
from referrals
left join users invitees on invitees.id = referrals.invitee_id
left join real_success_payers on real_success_payers.user_id = referrals.invitee_id
where referrals.inviter_id = $1::bigint
order by referrals.created_at desc, referrals.id desc
limit 12
"""

USER_GENERATION_SUMMARY_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since),
period_history as (
    select *
    from history, bounds
    where history.user_id = $1::bigint
      and history.created_at >= bounds.since
)
select
    'user_generation_summary' as row_type,
    (select count(*) from history where user_id = $1::bigint)::bigint as all_generations,
    count(*)::bigint as period_generations,
    count(distinct created_at::date)::bigint as active_days,
    min(created_at) as first_period_generation_at,
    max(created_at) as last_period_generation_at,
    count(*) filter (where output_file is not null and output_file <> '')::bigint as result_generations,
    count(*) filter (where is_favorited is true)::bigint as favorited_generations,
    count(*) filter (where is_public is true)::bigint as public_generations,
    count(*) filter (where source = 'web')::bigint as web_generations,
    count(*) filter (where source <> 'web')::bigint as bot_generations
from period_history
"""

USER_GENERATION_TYPE_DISTRIBUTION_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since)
select
    'user_generation_type_distribution' as row_type,
    coalesce(type, 'unknown') as task_type,
    count(*)::bigint as generations,
    max(created_at) as last_generation_at
from history, bounds
where user_id = $1::bigint
  and created_at >= bounds.since
group by coalesce(type, 'unknown')
order by generations desc, task_type
limit 20
"""

USER_GENERATION_SOURCE_DISTRIBUTION_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since)
select
    'user_generation_source_distribution' as row_type,
    coalesce(source, 'unknown') as source,
    count(*)::bigint as generations
from history, bounds
where user_id = $1::bigint
  and created_at >= bounds.since
group by coalesce(source, 'unknown')
order by generations desc, source
"""

USER_GENERATION_HOUR_DISTRIBUTION_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since)
select
    'user_generation_hour_distribution' as row_type,
    extract(hour from created_at)::int as hour,
    count(*)::bigint as generations
from history, bounds
where user_id = $1::bigint
  and created_at >= bounds.since
group by 2
order by hour
"""

USER_GENERATION_WEEKDAY_DISTRIBUTION_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since)
select
    'user_generation_weekday_distribution' as row_type,
    extract(isodow from created_at)::int as weekday,
    count(*)::bigint as generations
from history, bounds
where user_id = $1::bigint
  and created_at >= bounds.since
group by 2
order by weekday
"""

USER_RECENT_GENERATIONS_SQL = """
select
    'user_recent_generations' as row_type,
    history.id,
    history.task_id,
    history.type,
    history.source,
    history.created_at,
    history.rating,
    history.is_public,
    history.is_favorited,
    history.allow_contribute,
    history.billing_resolution,
    history.width,
    history.height,
    history.duration,
    history.requested_duration,
    gallery_posts.id as gallery_post_id,
    gallery_posts.likes_count,
    gallery_posts.dislikes_count,
    gallery_posts.applied_count,
    gallery_posts.comments_count
from history
left join gallery_posts on gallery_posts.task_id = history.task_id and gallery_posts.is_active is true
where history.user_id = $1::bigint
order by history.created_at desc, history.id desc
limit 12
"""

USER_CHECKIN_SUMMARY_SQL = """
with bounds as (select now() - ($2::int * interval '1 day') as since),
dates as (
    select distinct checkin_date::date as day
    from checkin_history
    where user_id = $1::bigint
),
numbered as (
    select
        day,
        day - (row_number() over (order by day))::int as streak_group
    from dates
),
streaks as (
    select min(day) as start_day, max(day) as end_day, count(*)::bigint as days
    from numbered
    group by streak_group
)
select
    'user_checkin_summary' as row_type,
    (select count(*) from dates)::bigint as total_checkins,
    (select count(*) from dates, bounds where day >= bounds.since::date)::bigint as period_checkins,
    (select max(day) from dates) as last_checkin_date,
    coalesce((select days from streaks order by end_day desc limit 1), 0)::bigint as current_streak,
    coalesce((select max(days) from streaks), 0)::bigint as longest_streak
"""

USER_RECENT_CHECKINS_SQL = """
select
    'user_recent_checkins' as row_type,
    checkin_date,
    created_at
from checkin_history
where user_id = $1::bigint
order by checkin_date desc, id desc
limit 12
"""

USER_COMMUNITY_SUMMARY_SQL = """
select
    'user_community_summary' as row_type,
    count(*) filter (where is_active is true)::bigint as gallery_posts,
    count(*) filter (where is_active is not true)::bigint as inactive_gallery_posts,
    coalesce(sum(likes_count) filter (where is_active is true), 0)::bigint as likes,
    coalesce(sum(dislikes_count) filter (where is_active is true), 0)::bigint as dislikes,
    coalesce(sum(applied_count) filter (where is_active is true), 0)::bigint as applies,
    coalesce(sum(comments_count) filter (where is_active is true), 0)::bigint as comments,
    coalesce(sum(likes_count * 2 - dislikes_count + applied_count * 5 + comments_count * 2) filter (where is_active is true), 0)::bigint as gallery_signal,
    max(created_at) filter (where is_active is true) as latest_gallery_post_at
from gallery_posts
where user_id = $1::bigint
"""

USER_GALLERY_SAMPLES_SQL = """
select
    'user_gallery_samples' as row_type,
    gallery_posts.id as post_id,
    gallery_posts.task_id,
    gallery_posts.media_type,
    gallery_posts.likes_count,
    gallery_posts.dislikes_count,
    gallery_posts.applied_count,
    gallery_posts.comments_count,
    gallery_posts.created_at,
    history.type as task_type,
    history.rating,
    history.is_public,
    history.billing_resolution
from gallery_posts
left join history on history.task_id = gallery_posts.task_id and history.user_id = gallery_posts.user_id
where gallery_posts.user_id = $1::bigint
order by
    (gallery_posts.likes_count * 2 - gallery_posts.dislikes_count + gallery_posts.applied_count * 5 + gallery_posts.comments_count * 2) desc,
    gallery_posts.created_at desc,
    gallery_posts.id desc
limit 12
"""

USER_PROMPT_UNLOCK_SUMMARY_SQL = """
select
    'user_prompt_unlock_summary' as row_type,
    (select count(*) from gallery_prompt_unlocks where user_id = $1::bigint)::bigint as purchased_unlocks,
    (select coalesce(sum(cost_credits), 0) from gallery_prompt_unlocks where user_id = $1::bigint)::bigint as spent_credits,
    (select count(*) from gallery_prompt_unlocks where author_id = $1::bigint)::bigint as sold_unlocks,
    (select coalesce(sum(cost_credits), 0) from gallery_prompt_unlocks where author_id = $1::bigint)::bigint as earned_credits,
    (select max(created_at) from gallery_prompt_unlocks where user_id = $1::bigint) as latest_purchase_at,
    (select max(created_at) from gallery_prompt_unlocks where author_id = $1::bigint) as latest_sale_at
"""

USER_RECENT_PROMPT_UNLOCK_PURCHASES_SQL = """
select
    'user_recent_prompt_unlock_purchases' as row_type,
    unlocks.id,
    unlocks.post_id,
    unlocks.author_id,
    unlocks.cost_credits,
    unlocks.created_at,
    posts.task_id,
    history.type as task_type,
    posts.media_type
from gallery_prompt_unlocks unlocks
left join gallery_posts posts on posts.id = unlocks.post_id
left join history on history.task_id = posts.task_id and history.user_id = posts.user_id
where unlocks.user_id = $1::bigint
order by unlocks.created_at desc, unlocks.id desc
limit 12
"""

USER_RECENT_PROMPT_UNLOCK_SALES_SQL = """
select
    'user_recent_prompt_unlock_sales' as row_type,
    unlocks.id,
    unlocks.post_id,
    unlocks.user_id as buyer_id,
    buyer.username as buyer_username,
    buyer.full_name as buyer_full_name,
    unlocks.cost_credits,
    unlocks.created_at,
    posts.task_id,
    history.type as task_type,
    posts.media_type
from gallery_prompt_unlocks unlocks
left join users buyer on buyer.id = unlocks.user_id
left join gallery_posts posts on posts.id = unlocks.post_id
left join history on history.task_id = posts.task_id and history.user_id = posts.user_id
where unlocks.author_id = $1::bigint
order by unlocks.created_at desc, unlocks.id desc
limit 12
"""

USER_SOCIAL_SUMMARY_SQL = """
select
    'user_social_summary' as row_type,
    (select count(*) from user_follows where followee_id = $1::bigint)::bigint as followers_count,
    (select count(*) from user_follows where follower_id = $1::bigint)::bigint as following_count,
    (
        select count(*)
        from user_follows f
        join user_follows back
          on back.follower_id = f.followee_id
         and back.followee_id = f.follower_id
        where f.follower_id = $1::bigint
    )::bigint as mutual_follow_count
"""

USER_RECENT_FOLLOWING_SQL = """
select
    'user_recent_following' as row_type,
    users.id,
    users.username,
    users.full_name,
    coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
    coalesce(nullif(users.user_group, ''), '凡人') as user_group,
    user_follows.created_at as followed_at
from user_follows
join users on users.id = user_follows.followee_id
where user_follows.follower_id = $1::bigint
order by user_follows.created_at desc, user_follows.id desc
limit 12
"""

USER_RECENT_FOLLOWERS_SQL = """
select
    'user_recent_followers' as row_type,
    users.id,
    users.username,
    users.full_name,
    coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
    coalesce(nullif(users.user_group, ''), '凡人') as user_group,
    user_follows.created_at as followed_at
from user_follows
join users on users.id = user_follows.follower_id
where user_follows.followee_id = $1::bigint
order by user_follows.created_at desc, user_follows.id desc
limit 12
"""
