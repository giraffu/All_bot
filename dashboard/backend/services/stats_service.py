from __future__ import annotations

from datetime import date, datetime, timedelta
from logging import Logger

from sqlalchemy import Float, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    CheckinHistory,
    History,
    MembershipPlan,
    Order,
    Referral,
    TemplateContribution,
    User,
)
from src.exchange_rates import get_exchange_rates

VIDEO_TYPES = [
    "video",
    "video_undress",
    "custom_video",
    "perfect_video_insert",
    "video_pro",
    "doggy_style",
    "blowjob",
    "undress_tongue",
    "closeup_blowjob",
    "face_show",
    "face_tongue",
    "fuck",
    "penetration",
    "penetration_step1",
    "penetration_step2",
    "masturbation",
    "face_video_step1",
    "face_video_step2",
]
USER_GROUP_KEYS = ["凡人", "练气期", "筑基期", "金丹期", "元婴期"]


def get_hour_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("hour", col)
    return func.strftime("%H", col)


def get_days_diff_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("day", func.now() - col)
    return func.julianday("now") - func.julianday(col)


def _date_key(value) -> str:
    return value if isinstance(value, str) else value.strftime("%Y-%m-%d")


def _build_zeroed_distribution(keys: list[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _build_hourly_distribution(rows) -> dict[str, int]:
    hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
    for row in rows:
        hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
        hourly_distribution[hour_str] = row.count
    return hourly_distribution


def parse_stats_target_date(date_str: str | None) -> date:
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    return date.today()


def _build_finance_hourly_distribution(rows) -> dict[str, dict[str, int]]:
    hourly_data = {
        str(h).zfill(2): {
            "recharged_credits": 0,
            "inner_disciples": 0,
            "core_disciples": 0,
            "true_disciples": 0,
        }
        for h in range(24)
    }
    for row in rows:
        hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
        hourly_data[hour_str]["recharged_credits"] += int(row.recharged_credits)
        hourly_data[hour_str]["inner_disciples"] += int(row.inner_disciples)
        hourly_data[hour_str]["core_disciples"] += int(row.core_disciples)
        hourly_data[hour_str]["true_disciples"] += int(row.true_disciples)
    return hourly_data


async def load_finance_hourly_stats(*, db: AsyncSession, target_date: date) -> dict:
    dialect = db.bind.dialect.name
    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    hour_expr = get_hour_expr(order_paid_expr, dialect)
    order_stmt = (
        select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)),
                0,
            ).label("inner_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)),
                0,
            ).label("core_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)),
                0,
            ).label("true_disciples"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", func.date(order_paid_expr) == target_date)
        .group_by(hour_expr)
    )
    rows = await db.execute(order_stmt)
    return _build_finance_hourly_distribution(rows)


async def load_finance_hourly_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict:
    return await load_finance_hourly_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_finance_hourly_stats(*, db: AsyncSession, days: int) -> dict:
    start_date = date.today() - timedelta(days=days - 1)
    dialect = db.bind.dialect.name
    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    hour_expr = get_hour_expr(order_paid_expr, dialect)
    order_stmt = (
        select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)),
                0,
            ).label("inner_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)),
                0,
            ).label("core_disciples"),
            func.coalesce(
                func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)),
                0,
            ).label("true_disciples"),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", func.date(order_paid_expr) >= start_date)
        .group_by(hour_expr)
    )
    rows = await db.execute(order_stmt)
    return _build_finance_hourly_distribution(rows)


async def load_hourly_generation_stats(*, db: AsyncSession, target_date: date) -> dict[str, int]:
    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_stmt = (
        select(hour_expr.label("hour"), func.count(History.id).label("count"))
        .where(func.date(History.created_at) == target_date)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    rows = await db.execute(hourly_stmt)
    return _build_hourly_distribution(rows)


async def load_hourly_generation_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict[str, int]:
    return await load_hourly_generation_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_hourly_generation_stats(*, db: AsyncSession, days: int) -> dict[str, int]:
    start_date = date.today() - timedelta(days=days - 1)
    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_stmt = (
        select(hour_expr.label("hour"), func.count(History.id).label("count"))
        .where(func.date(History.created_at) >= start_date)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    rows = await db.execute(hourly_stmt)
    return _build_hourly_distribution(rows)


async def load_type_distribution_stats(*, db: AsyncSession, target_date: date) -> dict[str, int]:
    rows = await db.execute(
        select(History.type, func.count(History.id))
        .where(func.date(History.created_at) == target_date)
        .group_by(History.type)
    )
    return {row.type or "unknown": row.count for row in rows}


async def load_type_distribution_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict[str, int]:
    return await load_type_distribution_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_type_distribution_stats(*, db: AsyncSession, days: int) -> dict[str, int]:
    start_date = date.today() - timedelta(days=days - 1)
    rows = await db.execute(
        select(History.type, func.count(History.id))
        .where(func.date(History.created_at) >= start_date)
        .group_by(History.type)
    )
    return {row.type or "unknown": row.count for row in rows}


async def load_dashboard_stats(*, db: AsyncSession, logger: Logger) -> dict:
    video_cost_case = case((History.type.in_(VIDEO_TYPES), 6), else_=2)

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

    identity_result = await db.execute(
        select(User.current_identity, func.count(User.id)).group_by(
            User.current_identity
        )
    )
    identity_counts = {
        row.current_identity: row.count
        for row in identity_result
        if row.current_identity
    }

    user_group_result = await db.execute(
        select(User.user_group, func.count(User.id)).group_by(User.user_group)
    )
    user_group_distribution = {
        row.user_group: row.count for row in user_group_result if row.user_group
    }
    for key in USER_GROUP_KEYS:
        user_group_distribution.setdefault(key, 0)

    total_generations = (await db.execute(select(func.count(History.id)))).scalar()
    total_referrals = (await db.execute(select(func.count(Referral.id)))).scalar() or 0
    total_consumed_credits = (
        await db.execute(select(func.sum(video_cost_case)))
    ).scalar() or 0

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

    invitation_stmt = (
        select(
            func.coalesce(
                func.sum(
                    case((Order.payment_channel == "RMB", Order.final_price), else_=0)
                ),
                0,
            ).label("rmb_sum"),
            func.coalesce(
                func.sum(
                    case((Order.payment_channel == "XTR", Order.final_price), else_=0)
                ),
                0,
            ).label("stars_sum"),
            func.coalesce(
                func.sum(
                    case((Order.payment_channel == "TON", Order.final_price), else_=0)
                ),
                0,
            ).label("ton_sum"),
        )
        .join(Referral, Referral.invitee_id == Order.telegram_id)
        .where(Order.status == "SUCCESS")
    )
    invitation_row = (await db.execute(invitation_stmt)).first()
    total_invitation_rmb = float(invitation_row.rmb_sum)
    total_invitation_stars = int(invitation_row.stars_sum)
    total_invitation_ton = float(invitation_row.ton_sum)

    today = date.today()
    today_user_stmt = select(
        func.count(User.id).label("today_users_all"),
        func.coalesce(
            func.sum(case((User.is_channel_member.is_(True), 1), else_=0)), 0
        ).label("today_users"),
        func.coalesce(
            func.sum(case((User.hashed_password.is_not(None), 1), else_=0)), 0
        ).label("today_password_users"),
    ).where(func.date(User.created_at) == today)
    today_user_row = (await db.execute(today_user_stmt)).first()
    today_users_all = today_user_row.today_users_all or 0
    today_users = int(today_user_row.today_users)
    today_password_users = int(today_user_row.today_password_users)

    today_checkins = (
        await db.execute(select(func.count(User.id)).where(User.last_checkin == today))
    ).scalar() or 0

    history_stats_stmt = select(
        func.count(History.id).label("today_generations"),
        func.count(func.distinct(History.user_id)).label("today_active_users"),
        func.count(
            func.distinct(case((History.source == "web", History.user_id), else_=None))
        ).label("today_web_users"),
        func.coalesce(func.sum(video_cost_case), 0).label("today_consumed_credits"),
    ).where(func.date(History.created_at) == today)
    history_stats_row = (await db.execute(history_stats_stmt)).first()

    total_web_users = (
        await db.execute(
            select(func.count(func.distinct(History.user_id))).where(
                History.source == "web"
            )
        )
    ).scalar() or 0

    today_type_distribution = {
        row.type or "unknown": row.count
        for row in await db.execute(
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) == today)
            .group_by(History.type)
        )
    }
    total_type_distribution = {
        row.type or "unknown": row.count
        for row in await db.execute(
            select(History.type, func.count(History.id)).group_by(History.type)
        )
    }

    dialect = db.bind.dialect.name
    hour_expr = get_hour_expr(History.created_at, dialect)
    hourly_result = await db.execute(
        select(hour_expr.label("hour"), func.count(History.id).label("count"))
        .where(func.date(History.created_at) == today)
        .group_by(hour_expr)
        .order_by(hour_expr)
    )
    today_hourly_distribution = _build_hourly_distribution(hourly_result)

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
    gen_distribution = _build_zeroed_distribution(gen_distribution_order)
    gen_dist_result = await db.execute(
        select(gen_case.label("range"), func.count(User.id).label("count")).group_by(
            gen_case
        )
    )
    for row in gen_dist_result:
        if row.range in gen_distribution:
            gen_distribution[row.range] = row.count

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
    avg_distribution = _build_zeroed_distribution(avg_distribution_order)
    avg_dist_result = await db.execute(
        select(avg_case.label("range"), func.count(User.id).label("count")).group_by(
            avg_case
        )
    )
    for row in avg_dist_result:
        if row.range in avg_distribution:
            avg_distribution[row.range] = row.count

    consumed_sub = (
        select(History.user_id, func.sum(video_cost_case).label("consumed"))
        .group_by(History.user_id)
        .subquery()
    )
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
    credit_distribution = _build_zeroed_distribution(credit_distribution_order)
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
    avg_credit_distribution = _build_zeroed_distribution(avg_credit_distribution_order)
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
    holding_distribution = _build_zeroed_distribution(holding_distribution_order)
    holding_dist_result = await db.execute(
        select(holding_case.label("range"), func.count(User.id).label("count")).group_by(
            holding_case
        )
    )
    for row in holding_dist_result:
        if row.range in holding_distribution:
            holding_distribution[row.range] = row.count

    ton_balance = 0.0
    usdt_balance = 0.0
    star_balance = 0
    rmb_balance = 0.0
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

    try:
        rmb_stmt = select(func.coalesce(func.sum(Order.final_price), 0)).where(
            Order.status == "SUCCESS", Order.payment_channel == "RMB"
        )
        rmb_balance += float((await db.execute(rmb_stmt)).scalar())
    except Exception as e:
        logger.error(f"Error calculating RMB balance: {e}")

    return {
        "total_users": total_users,
        "total_password_users": total_password_users,
        "today_password_users": today_password_users,
        "total_en_users": total_en_users,
        "total_zh_users": total_zh_users,
        "inner_disciple_count": identity_counts.get("内门弟子", 0),
        "core_disciple_count": identity_counts.get("核心弟子", 0),
        "true_disciple_count": identity_counts.get("真传弟子", 0),
        "total_generations": total_generations,
        "total_credits": total_credits,
        "total_active_credits": total_active_credits,
        "total_referrals": total_referrals,
        "total_consumed_credits": total_consumed_credits,
        "total_template_contributions": total_template_contributions,
        "total_approved_contributions": total_approved_contributions,
        "today_users": today_users,
        "today_users_all": today_users_all,
        "today_generations": history_stats_row.today_generations or 0,
        "today_active_users": history_stats_row.today_active_users or 0,
        "total_web_users": total_web_users,
        "today_web_users": history_stats_row.today_web_users or 0,
        "today_checkins": today_checkins,
        "today_consumed_credits": history_stats_row.today_consumed_credits or 0,
        "today_type_distribution": today_type_distribution,
        "total_type_distribution": total_type_distribution,
        "today_hourly_distribution": today_hourly_distribution,
        "generation_distribution": gen_distribution,
        "avg_daily_distribution": avg_distribution,
        "credit_distribution": credit_distribution,
        "avg_daily_credit_distribution": avg_credit_distribution,
        "credit_holding_distribution": holding_distribution,
        "user_group_distribution": user_group_distribution,
        "ton_balance": ton_balance,
        "usdt_balance": usdt_balance,
        "star_balance": star_balance,
        "rmb_balance": round(rmb_balance, 2),
        "total_invitation_ton": round(total_invitation_ton, 2),
        "total_invitation_rmb": round(total_invitation_rmb, 2),
        "total_invitation_stars": total_invitation_stars,
    }


async def load_dashboard_stats_history(
    *, db: AsyncSession, days: int, logger: Logger
) -> list[dict]:
    _ = logger
    video_cost_case = case((History.type.in_(VIDEO_TYPES), 6), else_=2)
    start_date = date.today() - timedelta(days=days - 1)

    async def _load_date_count_map(stmt):
        result = await db.execute(stmt)
        return {_date_key(row.date): row.count for row in result}

    user_history = await _load_date_count_map(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(func.date(User.created_at) >= start_date, User.is_channel_member.is_(True))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    user_all_history = await _load_date_count_map(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(func.date(User.created_at) >= start_date)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    user_en_history = await _load_date_count_map(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(func.date(User.created_at) >= start_date, User.language_code.like("en%"))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    user_zh_history = await _load_date_count_map(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(func.date(User.created_at) >= start_date, User.language_code.like("zh%"))
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    user_pwd_history = await _load_date_count_map(
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count"),
        )
        .where(
            func.date(User.created_at) >= start_date,
            User.hashed_password.is_not(None),
        )
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
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
    ).where(func.date(User.created_at) < start_date)
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
        select(
            func.date(History.created_at).label("date"),
            func.count(History.id).label("count"),
        )
        .where(func.date(History.created_at) >= start_date)
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at))
    )
    active_history = await _load_date_count_map(
        select(
            func.date(History.created_at).label("date"),
            func.count(func.distinct(History.user_id)).label("count"),
        )
        .where(func.date(History.created_at) >= start_date)
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at))
    )
    web_active_history = await _load_date_count_map(
        select(
            func.date(History.created_at).label("date"),
            func.count(func.distinct(History.user_id)).label("count"),
        )
        .where(func.date(History.created_at) >= start_date, History.source == "web")
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at))
    )
    checkin_history = await _load_date_count_map(
        select(
            func.date(CheckinHistory.checkin_date).label("date"),
            func.count(CheckinHistory.id).label("count"),
        )
        .where(func.date(CheckinHistory.checkin_date) >= start_date)
        .group_by(func.date(CheckinHistory.checkin_date))
        .order_by(func.date(CheckinHistory.checkin_date))
    )
    consumed_history = await _load_date_count_map(
        select(
            func.date(History.created_at).label("date"),
            func.sum(video_cost_case).label("count"),
        )
        .where(func.date(History.created_at) >= start_date)
        .group_by(func.date(History.created_at))
        .order_by(func.date(History.created_at))
    )

    order_paid_date = func.date(func.coalesce(Order.paid_at, Order.created_at))
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
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label(
                "credits_sum"
            ),
        )
        .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
        .where(Order.status == "SUCCESS", order_paid_date < start_date)
    )
    before_row = (await db.execute(orders_before_stmt)).first()
    current_ton_cumulative = float(before_row.ton_sum) if before_row else 0.0
    current_stars_cumulative = int(before_row.stars_sum) if before_row else 0
    current_rmb_cumulative = float(before_row.rmb_sum) if before_row else 0.0
    current_recharged_credits_cumulative = (
        int(before_row.credits_sum) if before_row else 0
    )

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
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label(
                "credits_sum"
            ),
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
        .where(Order.status == "SUCCESS", order_paid_date >= start_date)
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
        current_date_str = _date_key(row.date)
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
