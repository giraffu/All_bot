from __future__ import annotations

from datetime import timedelta
from logging import Logger

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_consumption import (
    load_daily_consumed_credit_map,
)
from dashboard.backend.services.stats_service_utils import date_key, trailing_start_date
from src.database.models import CheckinHistory, History, MembershipPlan, Order, User
from src.exchange_rates import get_exchange_rates


async def _load_date_count_map(db: AsyncSession, stmt) -> dict[str, int]:
    result = await db.execute(stmt)
    return {date_key(row.date): row.count for row in result}


async def load_dashboard_stats_history_impl(
    *, db: AsyncSession, days: int, logger: Logger, video_types: list[str]
) -> list[dict]:
    _ = logger
    _ = video_types
    start_date = trailing_start_date(days)

    user_history = await _load_date_count_map(
        db,
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count"),
        )
        .where(User.created_at >= start_date, User.is_channel_member.is_(True))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at)),
    )
    user_all_history = await _load_date_count_map(
        db,
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count"),
        )
        .where(User.created_at >= start_date)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at)),
    )
    user_en_history = await _load_date_count_map(
        db,
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count"),
        )
        .where(User.created_at >= start_date, User.language_code.like("en%"))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at)),
    )
    user_zh_history = await _load_date_count_map(
        db,
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count"),
        )
        .where(User.created_at >= start_date, User.language_code.like("zh%"))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at)),
    )
    user_pwd_history = await _load_date_count_map(
        db,
        select(
            func.date(User.created_at).label("date"),
            func.count().label("count"),
        )
        .where(
            User.created_at >= start_date,
            User.hashed_password.is_not(None),
        )
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at)),
    )

    users_before_stmt = select(
        func.count(User.id).label("cumulative_users"),
        func.coalesce(
            func.sum(case((User.language_code.like("en%"), 1), else_=0)), 0
        ).label("cumulative_en_users"),
        func.coalesce(
            func.sum(case((User.language_code.like("zh%"), 1), else_=0)), 0
        ).label("cumulative_zh_users"),
        func.coalesce(
            func.sum(case((User.hashed_password.is_not(None), 1), else_=0)), 0
        ).label("cumulative_pwd_users"),
    ).where(User.created_at < start_date)
    users_before_row = (await db.execute(users_before_stmt)).first()
    current_cumulative = users_before_row.cumulative_users or 0
    current_cumulative_en = int(users_before_row.cumulative_en_users)
    current_cumulative_zh = int(users_before_row.cumulative_zh_users)
    current_cumulative_pwd = int(users_before_row.cumulative_pwd_users)

    daily_growth_rates = {}
    daily_en_cumulative = {}
    daily_zh_cumulative = {}
    daily_pwd_cumulative = {}
    for i in range(days):
        current_date_obj = start_date + timedelta(days=i)
        current_date_str = current_date_obj.strftime("%Y-%m-%d")
        new_users_today = user_all_history.get(current_date_str, 0)
        new_en_users_today = user_en_history.get(current_date_str, 0)
        new_zh_users_today = user_zh_history.get(current_date_str, 0)
        new_pwd_users_today = user_pwd_history.get(current_date_str, 0)

        total_users_today = current_cumulative + new_users_today
        total_en_users_today = current_cumulative_en + new_en_users_today
        total_zh_users_today = current_cumulative_zh + new_zh_users_today
        total_pwd_users_today = current_cumulative_pwd + new_pwd_users_today

        growth_rate = (
            new_users_today / current_cumulative
            if current_cumulative > 0
            else (0 if new_users_today == 0 else 1.0)
        )
        daily_growth_rates[current_date_str] = round(growth_rate * 100, 2)

        current_cumulative = total_users_today
        current_cumulative_en = total_en_users_today
        current_cumulative_zh = total_zh_users_today
        current_cumulative_pwd = total_pwd_users_today

        daily_en_cumulative[current_date_str] = total_en_users_today
        daily_zh_cumulative[current_date_str] = total_zh_users_today
        daily_pwd_cumulative[current_date_str] = total_pwd_users_today

    gen_history = await _load_date_count_map(
        db,
        select(
            func.date(History.created_at).label("date"),
            func.count().label("count"),
        )
        .where(History.created_at >= start_date)
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at)),
    )
    active_history = await _load_date_count_map(
        db,
        select(
            func.date(History.created_at).label("date"),
            func.count(func.distinct(History.user_id)).label("count"),
        )
        .where(History.created_at >= start_date)
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at)),
    )
    web_active_history = await _load_date_count_map(
        db,
        select(
            func.date(History.created_at).label("date"),
            func.count(func.distinct(History.user_id)).label("count"),
        )
        .where(History.created_at >= start_date, History.source == "web")
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at)),
    )
    checkin_history = await _load_date_count_map(
        db,
        select(
            func.date(CheckinHistory.checkin_date).label("date"),
            func.count().label("count"),
        )
        .where(CheckinHistory.checkin_date >= start_date)
        .group_by(func.date(CheckinHistory.checkin_date))
        .order_by(func.date(CheckinHistory.checkin_date)),
    )
    consumed_history = await load_daily_consumed_credit_map(
        db,
        start_date=start_date,
    )

    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    order_paid_date = func.date(order_paid_expr)
    orders_before_stmt = (
        select(
            func.coalesce(
                func.sum(case((Order.payment_channel == "RMB", Order.final_price), else_=0)),
                0,
            ).label("rmb_sum"),
            func.coalesce(
                func.sum(case((Order.payment_channel == "XTR", Order.final_price), else_=0)),
                0,
            ).label("stars_sum"),
            func.coalesce(
                func.sum(case((Order.payment_channel == "TON", Order.final_price), else_=0)),
                0,
            ).label("ton_sum"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("credits_sum"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", order_paid_expr < start_date)
    )
    before_row = (await db.execute(orders_before_stmt)).first()
    current_ton_cumulative = float(before_row.ton_sum) if before_row else 0.0
    current_stars_cumulative = int(before_row.stars_sum) if before_row else 0
    current_rmb_cumulative = float(before_row.rmb_sum) if before_row else 0.0
    current_recharged_credits_cumulative = int(before_row.credits_sum) if before_row else 0

    order_stmt = (
        select(
            order_paid_date.label("date"),
            func.coalesce(
                func.sum(case((Order.payment_channel == "RMB", Order.final_price), else_=0)),
                0,
            ).label("rmb_sum"),
            func.coalesce(
                func.sum(case((Order.payment_channel == "XTR", Order.final_price), else_=0)),
                0,
            ).label("stars_sum"),
            func.coalesce(
                func.sum(case((Order.payment_channel == "TON", Order.final_price), else_=0)),
                0,
            ).label("ton_sum"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("credits_sum"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)),
                0,
            ).label("inner_count"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)),
                0,
            ).label("core_count"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)),
                0,
            ).label("true_count"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", order_paid_expr >= start_date)
        .group_by(order_paid_date)
    )
    order_result = await db.execute(order_stmt)
    ton_history = {}
    stars_history = {}
    rmb_history = {}
    inner_history = {}
    core_history = {}
    true_history = {}
    recharged_credits_history = {}
    for row in order_result:
        current_date_str = date_key(row.date)
        ton_history[current_date_str] = float(row.ton_sum)
        stars_history[current_date_str] = int(row.stars_sum)
        rmb_history[current_date_str] = float(row.rmb_sum)
        recharged_credits_history[current_date_str] = int(row.credits_sum)
        inner_history[current_date_str] = int(row.inner_count)
        core_history[current_date_str] = int(row.core_count)
        true_history[current_date_str] = int(row.true_count)

    rates = await get_exchange_rates()
    ton_to_usdt = rates["ton_to_usdt"]
    rmb_to_usdt = rates["rmb_to_usdt"]
    stars_to_usdt = rates["stars_to_usdt"]

    history_data = []
    for i in range(days):
        current_date_obj = start_date + timedelta(days=i)
        current_date_str = current_date_obj.strftime("%Y-%m-%d")

        ton_today = ton_history.get(current_date_str, 0.0)
        stars_today = stars_history.get(current_date_str, 0)
        rmb_today = rmb_history.get(current_date_str, 0.0)
        recharged_credits_today = recharged_credits_history.get(current_date_str, 0)

        usdt_today = round(
            (ton_today * ton_to_usdt)
            + (stars_today * stars_to_usdt)
            + (rmb_today * rmb_to_usdt),
            2,
        )

        current_ton_cumulative += ton_today
        current_stars_cumulative += stars_today
        current_rmb_cumulative += rmb_today
        current_recharged_credits_cumulative += recharged_credits_today

        current_usdt_cumulative = round(
            (current_ton_cumulative * ton_to_usdt)
            + (current_stars_cumulative * stars_to_usdt)
            + (current_rmb_cumulative * rmb_to_usdt),
            2,
        )

        history_data.append(
            {
                "date": current_date_str,
                "new_users": user_history.get(current_date_str, 0),
                "new_users_all": user_all_history.get(current_date_str, 0),
                "new_en_users": user_en_history.get(current_date_str, 0),
                "new_zh_users": user_zh_history.get(current_date_str, 0),
                "new_pwd_users": user_pwd_history.get(current_date_str, 0),
                "growth_rate": daily_growth_rates.get(current_date_str, 0),
                "generations": gen_history.get(current_date_str, 0),
                "active_users": active_history.get(current_date_str, 0),
                "web_active_users": web_active_history.get(current_date_str, 0),
                "checkins": checkin_history.get(current_date_str, 0),
                "consumed_credits": consumed_history.get(current_date_str, 0),
                "ton_recharge": ton_today,
                "stars_recharge": stars_today,
                "rmb_recharge": round(rmb_today, 2),
                "usdt_recharge": usdt_today,
                "cumulative_ton": round(current_ton_cumulative, 2),
                "cumulative_stars": current_stars_cumulative,
                "cumulative_rmb": round(current_rmb_cumulative, 2),
                "cumulative_usdt": current_usdt_cumulative,
                "recharged_credits": recharged_credits_today,
                "cumulative_recharged_credits": current_recharged_credits_cumulative,
                "inner_disciples": inner_history.get(current_date_str, 0),
                "core_disciples": core_history.get(current_date_str, 0),
                "true_disciples": true_history.get(current_date_str, 0),
                "cumulative_en_users": daily_en_cumulative.get(current_date_str, 0),
                "cumulative_zh_users": daily_zh_cumulative.get(current_date_str, 0),
                "cumulative_pwd_users": daily_pwd_cumulative.get(current_date_str, 0),
            }
        )

    return history_data
