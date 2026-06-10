from __future__ import annotations

from datetime import date
from logging import Logger

from sqlalchemy import Float, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_utils import (
    build_hourly_distribution,
    build_zeroed_distribution,
    day_bounds,
    get_days_diff_expr,
    get_hour_expr,
)
from src.database.models import History, Order, Referral, TemplateContribution, User


def _build_video_cost_case(video_types: list[str]):
    return case((History.type.in_(video_types), 6), else_=2)


async def _load_user_summary(db: AsyncSession) -> dict:
    user_stats_stmt = select(
        func.count(User.id).label("total_db_users"),
        func.coalesce(
            func.sum(case((User.is_channel_member.is_(True), 1), else_=0)), 0
        ).label("total_users"),
        func.coalesce(
            func.sum(case((User.hashed_password.is_not(None), 1), else_=0)), 0
        ).label("total_password_users"),
        func.coalesce(
            func.sum(case((User.language_code.like("en%"), 1), else_=0)), 0
        ).label("total_en_users"),
        func.coalesce(
            func.sum(case((User.language_code.like("zh%"), 1), else_=0)), 0
        ).label("total_zh_users"),
        func.coalesce(func.sum(User.credits), 0).label("total_credits"),
        func.coalesce(
            func.sum(case((User.generation_count > 0, User.credits), else_=0)), 0
        ).label("total_active_credits"),
    )
    user_stats_row = (await db.execute(user_stats_stmt)).first()
    total_db_users = user_stats_row.total_db_users or 0
    total_users = int(user_stats_row.total_users)
    total_password_users = int(user_stats_row.total_password_users)
    total_en_users = int(user_stats_row.total_en_users)
    total_zh_users = int(user_stats_row.total_zh_users)
    total_credits = user_stats_row.total_credits
    total_active_credits = user_stats_row.total_active_credits
    return {
        "total_db_users": total_db_users,
        "total_users": total_users,
        "total_password_users": total_password_users,
        "total_en_users": total_en_users,
        "total_zh_users": total_zh_users,
        "total_credits": total_credits,
        "total_active_credits": total_active_credits,
    }


async def _load_identity_counts(db: AsyncSession) -> dict:
    identity_result = await db.execute(
        select(User.current_identity, func.count(User.id)).group_by(User.current_identity)
    )
    return {
        row.current_identity: row.count for row in identity_result if row.current_identity
    }


async def _load_user_group_distribution(
    db: AsyncSession,
    user_group_keys: list[str],
) -> dict:
    user_group_result = await db.execute(
        select(User.user_group, func.count(User.id)).group_by(User.user_group)
    )
    user_group_distribution = {
        row.user_group: row.count for row in user_group_result if row.user_group
    }
    for key in user_group_keys:
        user_group_distribution.setdefault(key, 0)
    return user_group_distribution


async def _load_global_activity_totals(db: AsyncSession, video_cost_case) -> dict:
    total_generations = (await db.execute(select(func.count()).select_from(History))).scalar()
    total_referrals = (
        await db.execute(select(func.count()).select_from(Referral))
    ).scalar() or 0
    total_consumed_credits = (
        await db.execute(select(func.sum(video_cost_case)))
    ).scalar() or 0
    return {
        "total_generations": total_generations,
        "total_referrals": total_referrals,
        "total_consumed_credits": total_consumed_credits,
    }


async def _load_template_contribution_totals(db: AsyncSession) -> dict:
    template_stmt = select(
        func.count(TemplateContribution.id).label("total"),
        func.coalesce(
            func.sum(case((TemplateContribution.is_reviewed.is_(True), 1), else_=0)),
            0,
        ).label("approved"),
    )
    template_row = (await db.execute(template_stmt)).first()
    total_template_contributions = template_row.total or 0
    total_approved_contributions = int(template_row.approved)
    return {
        "total_template_contributions": total_template_contributions,
        "total_approved_contributions": total_approved_contributions,
    }


async def _load_invitation_revenue_totals(db: AsyncSession) -> dict:
    invitation_stmt = (
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
        )
        .join(Referral, Referral.invitee_id == Order.internal_user_id)
        .where(Order.status == "SUCCESS")
    )
    invitation_row = (await db.execute(invitation_stmt)).first()
    total_invitation_rmb = float(invitation_row.rmb_sum)
    total_invitation_stars = int(invitation_row.stars_sum)
    total_invitation_ton = float(invitation_row.ton_sum)
    return {
        "total_invitation_rmb": total_invitation_rmb,
        "total_invitation_stars": total_invitation_stars,
        "total_invitation_ton": total_invitation_ton,
    }


async def _load_today_user_summary(db: AsyncSession, today: date) -> dict:
    start_date, end_date = day_bounds(today)
    today_user_stmt = select(
        func.count().label("today_users_all"),
        func.coalesce(
            func.sum(case((User.is_channel_member.is_(True), 1), else_=0)), 0
        ).label("today_users"),
        func.coalesce(
            func.sum(case((User.hashed_password.is_not(None), 1), else_=0)), 0
        ).label("today_password_users"),
    ).where(User.created_at >= start_date, User.created_at < end_date)
    today_user_row = (await db.execute(today_user_stmt)).first()
    today_users_all = today_user_row.today_users_all or 0
    today_users = int(today_user_row.today_users)
    today_password_users = int(today_user_row.today_password_users)

    today_checkins = (
        await db.execute(select(func.count(User.id)).where(User.last_checkin == today))
    ).scalar() or 0
    return {
        "today_users_all": today_users_all,
        "today_users": today_users,
        "today_password_users": today_password_users,
        "today_checkins": today_checkins,
    }


async def _load_history_today_summary(
    *,
    db: AsyncSession,
    today: date,
    video_cost_case,
) -> dict:
    start_date, end_date = day_bounds(today)
    history_stats_stmt = select(
        func.count().label("today_generations"),
        func.count(func.distinct(History.user_id)).label("today_active_users"),
        func.count(
            func.distinct(case((History.source == "web", History.user_id), else_=None))
        ).label("today_web_users"),
        func.coalesce(func.sum(video_cost_case), 0).label("today_consumed_credits"),
    ).where(History.created_at >= start_date, History.created_at < end_date)
    history_stats_row = (await db.execute(history_stats_stmt)).first()

    total_web_users = (
        await db.execute(
            select(func.count(func.distinct(History.user_id))).where(History.source == "web")
        )
    ).scalar() or 0

    today_type_distribution = {
        row.type or "unknown": row.count
        for row in await db.execute(
            select(History.type, func.count().label("count"))
            .where(History.created_at >= start_date, History.created_at < end_date)
            .group_by(History.type)
        )
    }
    total_type_distribution = {
        row.type or "unknown": row.count
        for row in await db.execute(
            select(History.type, func.count().label("count")).group_by(History.type)
        )
    }

    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_result = await db.execute(
        select(hour_expr.label("hour"), func.count().label("count"))
        .where(History.created_at >= start_date, History.created_at < end_date)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    today_hourly_distribution = build_hourly_distribution(hourly_result)
    return {
        "today_generations": history_stats_row.today_generations or 0,
        "today_active_users": history_stats_row.today_active_users or 0,
        "today_web_users": history_stats_row.today_web_users or 0,
        "today_consumed_credits": history_stats_row.today_consumed_credits or 0,
        "total_web_users": total_web_users,
        "today_type_distribution": today_type_distribution,
        "total_type_distribution": total_type_distribution,
        "today_hourly_distribution": today_hourly_distribution,
    }


async def _load_generation_distribution(db: AsyncSession) -> dict:
    user_gen_count = func.coalesce(User.generation_count, 0)
    gen_case = case(
        (user_gen_count == 0, "0"),
        (user_gen_count == 1, "1"),
        (user_gen_count == 2, "2"),
        (user_gen_count == 3, "3"),
        (user_gen_count == 4, "4"),
        (user_gen_count == 5, "5"),
        ((user_gen_count >= 6) & (user_gen_count <= 10), "6-10"),
        ((user_gen_count >= 11) & (user_gen_count <= 20), "11-20"),
        ((user_gen_count >= 21) & (user_gen_count <= 50), "21-50"),
        ((user_gen_count >= 51) & (user_gen_count <= 100), "51-100"),
        ((user_gen_count >= 101) & (user_gen_count <= 200), "101-200"),
        ((user_gen_count >= 201) & (user_gen_count <= 500), "201-500"),
        ((user_gen_count >= 501) & (user_gen_count <= 1000), "501-1000"),
        (user_gen_count > 1000, "1000+"),
        else_="0",
    )
    gen_distribution_order = [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6-10",
        "11-20",
        "21-50",
        "51-100",
        "101-200",
        "201-500",
        "501-1000",
        "1000+",
    ]
    gen_distribution = build_zeroed_distribution(gen_distribution_order)
    gen_dist_result = await db.execute(
        select(gen_case.label("range"), func.count(User.id).label("count")).group_by(gen_case)
    )
    for row in gen_dist_result:
        if row.range in gen_distribution:
            gen_distribution[row.range] = row.count
    return gen_distribution


async def _load_avg_daily_distribution(db: AsyncSession, dialect: str) -> dict:
    days_diff = get_days_diff_expr(User.created_at, dialect)
    days_valid = case((days_diff < 1, 1), else_=days_diff)
    avg_daily = func.cast(func.coalesce(User.generation_count, 0), Float) / days_valid
    avg_case = case(
        (avg_daily <= 0, "0"),
        ((avg_daily > 0) & (avg_daily <= 1), "0-1"),
        ((avg_daily > 1) & (avg_daily <= 3), "1-3"),
        ((avg_daily > 3) & (avg_daily <= 5), "3-5"),
        ((avg_daily > 5) & (avg_daily <= 10), "5-10"),
        ((avg_daily > 10) & (avg_daily <= 20), "10-20"),
        (avg_daily > 20, "20+"),
        else_="0",
    )
    avg_distribution_order = ["0", "0-1", "1-3", "3-5", "5-10", "10-20", "20+"]
    avg_distribution = build_zeroed_distribution(avg_distribution_order)
    avg_dist_result = await db.execute(
        select(avg_case.label("range"), func.count(User.id).label("count")).group_by(avg_case)
    )
    for row in avg_dist_result:
        if row.range in avg_distribution:
            avg_distribution[row.range] = row.count
    return avg_distribution


def _build_consumed_subquery(video_cost_case):
    consumed_sub = (
        select(History.user_id, func.sum(video_cost_case).label("consumed"))
        .group_by(History.user_id)
        .subquery()
    )
    return consumed_sub


async def _load_credit_distribution(
    *,
    db: AsyncSession,
    total_db_users: int,
    consumed_sub,
) -> dict:
    consumed_col = consumed_sub.c.consumed
    credit_dist_case = case(
        ((consumed_col >= 1) & (consumed_col <= 10), "1-10"),
        ((consumed_col >= 11) & (consumed_col <= 50), "11-50"),
        ((consumed_col >= 51) & (consumed_col <= 100), "51-100"),
        ((consumed_col >= 101) & (consumed_col <= 500), "101-500"),
        ((consumed_col >= 501) & (consumed_col <= 1000), "501-1000"),
        ((consumed_col >= 1001) & (consumed_col <= 5000), "1001-5000"),
        (consumed_col > 5000, "5000+"),
        else_="0",
    )
    credit_distribution_order = [
        "0",
        "1-10",
        "11-50",
        "51-100",
        "101-500",
        "501-1000",
        "1001-5000",
        "5000+",
    ]
    credit_distribution = build_zeroed_distribution(credit_distribution_order)
    users_with_consumption = 0
    credit_dist_result = await db.execute(
        select(credit_dist_case.label("range"), func.count().label("count")).group_by(
            credit_dist_case
        )
    )
    for row in credit_dist_result:
        if row.range in credit_distribution:
            credit_distribution[row.range] = row.count
            users_with_consumption += row.count
    credit_distribution["0"] = max(0, total_db_users - users_with_consumption)
    return credit_distribution


async def _load_avg_daily_credit_distribution(
    *,
    db: AsyncSession,
    total_db_users: int,
    dialect: str,
    consumed_sub,
) -> dict:
    consumed_col = consumed_sub.c.consumed
    days_diff_sub = get_days_diff_expr(User.created_at, dialect)
    days_valid_sub = case((days_diff_sub < 1, 1), else_=days_diff_sub)
    avg_daily_credit = func.cast(consumed_col, Float) / days_valid_sub
    avg_credit_case = case(
        (avg_daily_credit <= 0, "0"),
        ((avg_daily_credit > 0) & (avg_daily_credit <= 1), "0-1"),
        ((avg_daily_credit > 1) & (avg_daily_credit <= 5), "1-5"),
        ((avg_daily_credit > 5) & (avg_daily_credit <= 10), "5-10"),
        ((avg_daily_credit > 10) & (avg_daily_credit <= 20), "10-20"),
        ((avg_daily_credit > 20) & (avg_daily_credit <= 50), "20-50"),
        (avg_daily_credit > 50, "50+"),
        else_="0",
    )
    avg_credit_distribution_order = ["0", "0-1", "1-5", "5-10", "10-20", "20-50", "50+"]
    avg_credit_distribution = build_zeroed_distribution(avg_credit_distribution_order)
    users_with_avg_credit = 0
    avg_credit_dist_result = await db.execute(
        select(avg_credit_case.label("range"), func.count().label("count"))
        .select_from(User)
        .join(consumed_sub, User.id == consumed_sub.c.user_id)
        .group_by(avg_credit_case)
    )
    for row in avg_credit_dist_result:
        if row.range in avg_credit_distribution:
            avg_credit_distribution[row.range] = row.count
            users_with_avg_credit += row.count
    avg_credit_distribution["0"] = max(0, total_db_users - users_with_avg_credit)
    return avg_credit_distribution


async def _load_credit_holding_distribution(db: AsyncSession) -> dict:
    user_credits = func.coalesce(User.credits, 0)
    holding_case = case(
        (user_credits <= 0, "0"),
        ((user_credits >= 1) & (user_credits <= 10), "1-10"),
        ((user_credits >= 11) & (user_credits <= 50), "11-50"),
        ((user_credits >= 51) & (user_credits <= 100), "51-100"),
        ((user_credits >= 101) & (user_credits <= 500), "101-500"),
        ((user_credits >= 501) & (user_credits <= 1000), "501-1000"),
        ((user_credits >= 1001) & (user_credits <= 5000), "1001-5000"),
        (user_credits > 5000, "5000+"),
        else_="0",
    )
    holding_distribution_order = [
        "0",
        "1-10",
        "11-50",
        "51-100",
        "101-500",
        "501-1000",
        "1001-5000",
        "5000+",
    ]
    holding_distribution = build_zeroed_distribution(holding_distribution_order)
    holding_dist_result = await db.execute(
        select(holding_case.label("range"), func.count(User.id).label("count")).group_by(
            holding_case
        )
    )
    for row in holding_dist_result:
        if row.range in holding_distribution:
            holding_distribution[row.range] = row.count
    return holding_distribution


async def _load_external_balances_from_cache(logger: Logger) -> dict:
    ton_balance = 0.0
    usdt_balance = 0.0
    star_balance = 0
    try:
        from src.services.redis_client import redis_client

        if redis_client and redis_client.redis:
            ton_balance_str = await redis_client.redis.get("dashboard:ton_balance")
            if ton_balance_str:
                ton_balance = float(ton_balance_str)

            usdt_balance_str = await redis_client.redis.get("dashboard:usdt_balance")
            if usdt_balance_str:
                usdt_balance = float(usdt_balance_str)

            star_balance_str = await redis_client.redis.get("dashboard:star_balance")
            if star_balance_str:
                star_balance = int(star_balance_str)
    except Exception as e:
        logger.error(f"Error fetching external balances from Redis: {e}")
    return {
        "ton_balance": ton_balance,
        "usdt_balance": usdt_balance,
        "star_balance": star_balance,
    }


async def _load_rmb_balance(db: AsyncSession, logger: Logger) -> float:
    rmb_balance = 0.0
    try:
        rmb_stmt = select(func.coalesce(func.sum(Order.final_price), 0)).where(
            Order.status == "SUCCESS", Order.payment_channel == "RMB"
        )
        rmb_balance += float((await db.execute(rmb_stmt)).scalar())
    except Exception as e:
        logger.error(f"Error calculating RMB balance: {e}")
    return rmb_balance


async def load_dashboard_stats_impl(
    *,
    db: AsyncSession,
    logger: Logger,
    video_types: list[str],
    user_group_keys: list[str],
) -> dict:
    video_cost_case = _build_video_cost_case(video_types)
    today = date.today()
    dialect = db.bind.dialect.name

    user_summary = await _load_user_summary(db)
    total_db_users = user_summary["total_db_users"]
    identity_counts = await _load_identity_counts(db)
    user_group_distribution = await _load_user_group_distribution(db, user_group_keys)
    global_activity_totals = await _load_global_activity_totals(db, video_cost_case)
    template_totals = await _load_template_contribution_totals(db)
    invitation_totals = await _load_invitation_revenue_totals(db)
    today_user_summary = await _load_today_user_summary(db, today)
    today_history_summary = await _load_history_today_summary(
        db=db,
        today=today,
        video_cost_case=video_cost_case,
    )

    gen_distribution = await _load_generation_distribution(db)
    avg_distribution = await _load_avg_daily_distribution(db, dialect)
    consumed_sub = _build_consumed_subquery(video_cost_case)
    credit_distribution = await _load_credit_distribution(
        db=db,
        total_db_users=total_db_users,
        consumed_sub=consumed_sub,
    )
    avg_credit_distribution = await _load_avg_daily_credit_distribution(
        db=db,
        total_db_users=total_db_users,
        dialect=dialect,
        consumed_sub=consumed_sub,
    )
    holding_distribution = await _load_credit_holding_distribution(db)
    external_balances = await _load_external_balances_from_cache(logger)
    rmb_balance = await _load_rmb_balance(db, logger)

    return {
        "total_users": user_summary["total_users"],
        "total_password_users": user_summary["total_password_users"],
        "today_password_users": today_user_summary["today_password_users"],
        "total_en_users": user_summary["total_en_users"],
        "total_zh_users": user_summary["total_zh_users"],
        "inner_disciple_count": identity_counts.get("内门弟子", 0),
        "core_disciple_count": identity_counts.get("核心弟子", 0),
        "true_disciple_count": identity_counts.get("真传弟子", 0),
        "total_generations": global_activity_totals["total_generations"],
        "total_credits": user_summary["total_credits"],
        "total_active_credits": user_summary["total_active_credits"],
        "total_referrals": global_activity_totals["total_referrals"],
        "total_consumed_credits": global_activity_totals["total_consumed_credits"],
        "total_template_contributions": template_totals["total_template_contributions"],
        "total_approved_contributions": template_totals["total_approved_contributions"],
        "today_users": today_user_summary["today_users"],
        "today_users_all": today_user_summary["today_users_all"],
        "today_generations": today_history_summary["today_generations"],
        "today_active_users": today_history_summary["today_active_users"],
        "total_web_users": today_history_summary["total_web_users"],
        "today_web_users": today_history_summary["today_web_users"],
        "today_checkins": today_user_summary["today_checkins"],
        "today_consumed_credits": today_history_summary["today_consumed_credits"],
        "today_type_distribution": today_history_summary["today_type_distribution"],
        "total_type_distribution": today_history_summary["total_type_distribution"],
        "today_hourly_distribution": today_history_summary["today_hourly_distribution"],
        "generation_distribution": gen_distribution,
        "avg_daily_distribution": avg_distribution,
        "credit_distribution": credit_distribution,
        "avg_daily_credit_distribution": avg_credit_distribution,
        "credit_holding_distribution": holding_distribution,
        "user_group_distribution": user_group_distribution,
        "ton_balance": external_balances["ton_balance"],
        "usdt_balance": external_balances["usdt_balance"],
        "star_balance": external_balances["star_balance"],
        "rmb_balance": round(rmb_balance, 2),
        "total_invitation_ton": round(invitation_totals["total_invitation_ton"], 2),
        "total_invitation_rmb": round(invitation_totals["total_invitation_rmb"], 2),
        "total_invitation_stars": invitation_totals["total_invitation_stars"],
    }
