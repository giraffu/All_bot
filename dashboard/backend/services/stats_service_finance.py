from __future__ import annotations

from datetime import date, timedelta
from logging import Logger

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_summary import (
    load_external_balances_from_cache,
    load_identity_counts,
    load_invitation_revenue_totals,
)
from dashboard.backend.services.stats_service_utils import date_key, trailing_start_date
from src.database.models import MembershipPlan, Order
from src.exchange_rates import get_exchange_rates
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT


RMB_CHANNEL_KEYS = (
    "direct_alipay",
    "collected_alipay",
    "collected_wechat",
    "legacy_unclassified",
)


def _number(row, name: str, default=0):
    return getattr(row, name, default) if row is not None else default


def _rmb_channel_conditions():
    pay_type = func.lower(
        func.coalesce(Order.settlement_snapshot["rmb_pay_type"].as_string(), "")
    )
    provider = func.coalesce(Order.payment_provider, "HUANYUY")
    is_rmb = Order.payment_channel == "RMB"
    is_direct = and_(is_rmb, provider == ALIPAY_DIRECT)
    is_collected = and_(is_rmb, provider != ALIPAY_DIRECT)
    return {
        "direct_alipay": is_direct,
        "collected_alipay": and_(is_collected, pay_type == "alipay"),
        "collected_wechat": and_(is_collected, pay_type == "wxpay"),
        "legacy_unclassified": and_(
            is_collected,
            or_(pay_type == "", pay_type.not_in(("alipay", "wxpay"))),
        ),
    }


def _rmb_channel_aggregate_columns(*, include_orders: bool) -> list:
    columns = []
    for key, condition in _rmb_channel_conditions().items():
        columns.append(
            func.coalesce(
                func.sum(case((condition, Order.final_price), else_=0)),
                0,
            ).label(f"{key}_amount")
        )
        if include_orders:
            columns.append(
                func.coalesce(
                    func.sum(case((condition, 1), else_=0)),
                    0,
                ).label(f"{key}_orders")
            )
    return columns


def serialize_rmb_channel_totals(row) -> dict[str, dict[str, float | int]]:
    return {
        key: {
            "amount": round(float(_number(row, f"{key}_amount")), 2),
            "orders": int(_number(row, f"{key}_orders")),
        }
        for key in RMB_CHANNEL_KEYS
    }


async def load_finance_dashboard_summary_impl(
    *,
    db: AsyncSession,
    logger: Logger,
) -> dict:
    identity_counts = await load_identity_counts(db)
    invitation_totals = await load_invitation_revenue_totals(db)
    external_balances = await load_external_balances_from_cache(logger)
    rmb_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Order.final_price), 0).label("rmb_total"),
                *_rmb_channel_aggregate_columns(include_orders=True),
            ).where(Order.status == "SUCCESS", Order.payment_channel == "RMB")
        )
    ).first()

    return {
        "ton_balance": external_balances["ton_balance"],
        "usdt_balance": external_balances["usdt_balance"],
        "star_balance": external_balances["star_balance"],
        "rmb_balance": round(float(_number(rmb_row, "rmb_total")), 2),
        "rmb_channels": serialize_rmb_channel_totals(rmb_row),
        "inner_disciple_count": identity_counts.get("内门弟子", 0),
        "core_disciple_count": identity_counts.get("核心弟子", 0),
        "true_disciple_count": identity_counts.get("真传弟子", 0),
        "total_invitation_ton": round(invitation_totals["total_invitation_ton"], 2),
        "total_invitation_rmb": round(invitation_totals["total_invitation_rmb"], 2),
        "total_invitation_stars": invitation_totals["total_invitation_stars"],
    }


def build_finance_history_payload(
    *,
    start_date: date,
    days: int,
    before_row,
    daily_rows,
    rates: dict,
) -> list[dict]:
    daily_by_date = {date_key(row.date): row for row in daily_rows}
    cumulative = {
        "ton": float(_number(before_row, "ton_sum")),
        "stars": int(_number(before_row, "stars_sum")),
        "rmb": float(_number(before_row, "rmb_total")),
        "credits": int(_number(before_row, "credits_sum")),
        **{
            key: float(_number(before_row, f"{key}_amount"))
            for key in RMB_CHANNEL_KEYS
        },
    }
    result = []
    for offset in range(days):
        current_date = start_date + timedelta(days=offset)
        current_date_str = current_date.strftime("%Y-%m-%d")
        row = daily_by_date.get(current_date_str)
        ton_today = float(_number(row, "ton_sum"))
        stars_today = int(_number(row, "stars_sum"))
        rmb_today = float(_number(row, "rmb_sum"))
        credits_today = int(_number(row, "credits_sum"))
        channel_today = {
            key: float(_number(row, f"{key}_amount")) for key in RMB_CHANNEL_KEYS
        }

        cumulative["ton"] += ton_today
        cumulative["stars"] += stars_today
        cumulative["rmb"] += rmb_today
        cumulative["credits"] += credits_today
        for key, amount in channel_today.items():
            cumulative[key] += amount

        usdt_today = round(
            ton_today * rates["ton_to_usdt"]
            + stars_today * rates["stars_to_usdt"]
            + rmb_today * rates["rmb_to_usdt"],
            2,
        )
        cumulative_usdt = round(
            cumulative["ton"] * rates["ton_to_usdt"]
            + cumulative["stars"] * rates["stars_to_usdt"]
            + cumulative["rmb"] * rates["rmb_to_usdt"],
            2,
        )
        payload = {
            "date": current_date_str,
            "ton_recharge": ton_today,
            "stars_recharge": stars_today,
            "rmb_recharge": round(rmb_today, 2),
            "usdt_recharge": usdt_today,
            "cumulative_ton": round(cumulative["ton"], 2),
            "cumulative_stars": cumulative["stars"],
            "cumulative_rmb": round(cumulative["rmb"], 2),
            "cumulative_usdt": cumulative_usdt,
            "recharged_credits": credits_today,
            "cumulative_recharged_credits": cumulative["credits"],
            "inner_disciples": int(_number(row, "inner_count")),
            "core_disciples": int(_number(row, "core_count")),
            "true_disciples": int(_number(row, "true_count")),
        }
        for key, amount in channel_today.items():
            payload[f"rmb_{key}"] = round(amount, 2)
            payload[f"cumulative_rmb_{key}"] = round(cumulative[key], 2)
        result.append(payload)
    return result


async def load_finance_dashboard_history_impl(
    *,
    db: AsyncSession,
    days: int,
) -> list[dict]:
    start_date = trailing_start_date(days)
    order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
    order_paid_date = func.date(order_paid_expr)
    base_columns = [
        func.coalesce(
            func.sum(case((Order.payment_channel == "RMB", Order.final_price), else_=0)),
            0,
        ).label("rmb_total"),
        func.coalesce(
            func.sum(case((Order.payment_channel == "XTR", Order.final_price), else_=0)),
            0,
        ).label("stars_sum"),
        func.coalesce(
            func.sum(case((Order.payment_channel == "TON", Order.final_price), else_=0)),
            0,
        ).label("ton_sum"),
        func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("credits_sum"),
    ]
    before_row = (
        await db.execute(
            select(*base_columns, *_rmb_channel_aggregate_columns(include_orders=False))
            .join(MembershipPlan, Order.plan_id == MembershipPlan.id)
            .where(Order.status == "SUCCESS", order_paid_expr < start_date)
        )
    ).first()
    daily_rows = await db.execute(
        select(
            order_paid_date.label("date"),
            base_columns[0].label("rmb_sum"),
            *base_columns[1:],
            *_rmb_channel_aggregate_columns(include_orders=False),
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
        .order_by(order_paid_date)
    )
    return build_finance_history_payload(
        start_date=start_date,
        days=days,
        before_row=before_row,
        daily_rows=daily_rows,
        rates=await get_exchange_rates(),
    )
