import json
import logging
import os
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Float, and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from fastapi_cache.decorator import cache

from dashboard.backend.services.stats_service import (
    load_dashboard_stats,
    load_dashboard_stats_history,
)
from src.database.core import get_db

load_dotenv()
from src.database.models import (
    CheckinHistory,
    History,
    Order,
    MembershipPlan,
    Referral,
    TemplateContribution,
    User,
    UserLog,
)
from src.exchange_rates import get_exchange_rates

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger("dashboard.stats")


def get_hour_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("hour", col)
    return func.strftime("%H", col)


def get_days_diff_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("day", func.now() - col)
    return func.julianday("now") - func.julianday(col)


@router.get("")
@cache(expire=60)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    try:
        return await load_dashboard_stats(db=db, logger=logger)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/finance_hourly")
@cache(expire=60)
async def get_finance_hourly_stats(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get hourly finance stats (recharged credits and new disciples) for a specific date"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()

        dialect = db.bind.dialect.name
        order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
        hour_expr = get_hour_expr(order_paid_expr, dialect)

        order_stmt = select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)), 0).label("inner_disciples"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)), 0).label("core_disciples"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)), 0).label("true_disciples")
        ).join(MembershipPlan, Order.plan_id == MembershipPlan.id).where(
            Order.status == "SUCCESS",
            func.date(order_paid_expr) == target_date
        ).group_by(hour_expr)

        logs_result = await db.execute(order_stmt)

        hourly_data = {
            str(h).zfill(2): {
                "recharged_credits": 0,
                "inner_disciples": 0,
                "core_disciples": 0,
                "true_disciples": 0,
            }
            for h in range(24)
        }

        for row in logs_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_data[hour_str]["recharged_credits"] += int(row.recharged_credits)
            hourly_data[hour_str]["inner_disciples"] += int(row.inner_disciples)
            hourly_data[hour_str]["core_disciples"] += int(row.core_disciples)
            hourly_data[hour_str]["true_disciples"] += int(row.true_disciples)

        return hourly_data
    except Exception as e:
        logger.error(f"Error getting finance hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/finance_hourly/cumulative")
@cache(expire=60)
async def get_cumulative_finance_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly finance stats for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days - 1)
        dialect = db.bind.dialect.name
        order_paid_expr = func.coalesce(Order.paid_at, Order.created_at)
        hour_expr = get_hour_expr(order_paid_expr, dialect)

        order_stmt = select(
            hour_expr.label("hour"),
            func.coalesce(func.sum(MembershipPlan.reward_credits), 0).label("recharged_credits"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%内门%"), 1), else_=0)), 0).label("inner_disciples"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%核心%"), 1), else_=0)), 0).label("core_disciples"),
            func.coalesce(func.sum(case((MembershipPlan.identity_name.like("%真传%"), 1), else_=0)), 0).label("true_disciples")
        ).join(MembershipPlan, Order.plan_id == MembershipPlan.id).where(
            Order.status == "SUCCESS",
            func.date(order_paid_expr) >= start_date
        ).group_by(hour_expr)

        logs_result = await db.execute(order_stmt)

        hourly_data = {
            str(h).zfill(2): {
                "recharged_credits": 0,
                "inner_disciples": 0,
                "core_disciples": 0,
                "true_disciples": 0,
            }
            for h in range(24)
        }

        for row in logs_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_data[hour_str]["recharged_credits"] += int(row.recharged_credits)
            hourly_data[hour_str]["inner_disciples"] += int(row.inner_disciples)
            hourly_data[hour_str]["core_disciples"] += int(row.core_disciples)
            hourly_data[hour_str]["true_disciples"] += int(row.true_disciples)

        return hourly_data
    except Exception as e:
        logger.error(f"Error getting cumulative finance hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hourly")
async def get_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly generation stats for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()

        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)

        hourly_stmt = (
            select(hour_expr.label("hour"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) == target_date)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        hourly_result = await db.execute(hourly_stmt)

        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count

        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/type_distribution")
async def get_type_distribution(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get generation type distribution for a specific date (YYYY-MM-DD)"""
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            target_date = date.today()

        type_stmt = (
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) == target_date)
            .group_by(History.type)
        )
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}

        return type_distribution
    except Exception as e:
        logger.error(f"Error getting type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/type_distribution/cumulative")
async def get_cumulative_type_distribution(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative generation type distribution for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days - 1)
        type_stmt = (
            select(History.type, func.count(History.id))
            .where(func.date(History.created_at) >= start_date)
            .group_by(History.type)
        )
        type_result = await db.execute(type_stmt)
        type_distribution = {row.type or "unknown": row.count for row in type_result}
        return type_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative type distribution stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hourly/cumulative")
async def get_cumulative_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly generation stats for the last N days"""
    try:
        start_date = date.today() - timedelta(days=days - 1)
        dialect = db.bind.dialect.name
        hour_expr = get_hour_expr(History.created_at, dialect)
        hourly_stmt = (
            select(hour_expr.label("hour"), func.count(History.id).label("count"))
            .where(func.date(History.created_at) >= start_date)
            .group_by(hour_expr)
            .order_by(hour_expr)
        )
        hourly_result = await db.execute(hourly_stmt)

        hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
        for row in hourly_result:
            hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
            hourly_distribution[hour_str] = row.count

        return hourly_distribution
    except Exception as e:
        logger.error(f"Error getting cumulative hourly stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
@cache(expire=60)
async def get_stats_history(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get historical stats for charts (last N days)"""
    try:
        return await load_dashboard_stats_history(db=db, days=days, logger=logger)
    except Exception as e:
        logger.error(f"Error getting history stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
