import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_cache.decorator import cache

from dashboard.backend.routers.utils import run_dashboard_route
from dashboard.backend.services.stats_service import (
    load_cumulative_finance_hourly_stats,
    load_cumulative_hourly_generation_stats,
    load_cumulative_type_distribution_stats,
    load_dashboard_stats,
    load_dashboard_stats_history,
    load_finance_hourly_stats_by_date_str,
    load_hourly_generation_stats_by_date_str,
    load_type_distribution_stats_by_date_str,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger("dashboard.stats")


@router.get("")
@cache(expire=60)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    return await run_dashboard_route(
        lambda: load_dashboard_stats(db=db, logger=logger),
        logger=logger,
        error_message="Error getting stats",
    )


@router.get("/finance_hourly")
@cache(expire=60)
async def get_finance_hourly_stats(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get hourly finance stats (recharged credits and new disciples) for a specific date"""
    return await run_dashboard_route(
        lambda: load_finance_hourly_stats_by_date_str(db=db, date_str=date_str),
        logger=logger,
        error_message="Error getting finance hourly stats",
    )


@router.get("/finance_hourly/cumulative")
@cache(expire=60)
async def get_cumulative_finance_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly finance stats for the last N days"""
    return await run_dashboard_route(
        lambda: load_cumulative_finance_hourly_stats(db=db, days=days),
        logger=logger,
        error_message="Error getting cumulative finance hourly stats",
    )


@router.get("/hourly")
async def get_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly generation stats for a specific date (YYYY-MM-DD)"""
    return await run_dashboard_route(
        lambda: load_hourly_generation_stats_by_date_str(db=db, date_str=date_str),
        logger=logger,
        error_message="Error getting hourly stats",
    )


@router.get("/type_distribution")
async def get_type_distribution(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get generation type distribution for a specific date (YYYY-MM-DD)"""
    return await run_dashboard_route(
        lambda: load_type_distribution_stats_by_date_str(db=db, date_str=date_str),
        logger=logger,
        error_message="Error getting type distribution stats",
    )


@router.get("/type_distribution/cumulative")
async def get_cumulative_type_distribution(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative generation type distribution for the last N days"""
    return await run_dashboard_route(
        lambda: load_cumulative_type_distribution_stats(db=db, days=days),
        logger=logger,
        error_message="Error getting cumulative type distribution stats",
    )


@router.get("/hourly/cumulative")
async def get_cumulative_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly generation stats for the last N days"""
    return await run_dashboard_route(
        lambda: load_cumulative_hourly_generation_stats(db=db, days=days),
        logger=logger,
        error_message="Error getting cumulative hourly stats",
    )


@router.get("/history")
@cache(expire=60)
async def get_stats_history(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get historical stats for charts (last N days)"""
    return await run_dashboard_route(
        lambda: load_dashboard_stats_history(db=db, days=days, logger=logger),
        logger=logger,
        error_message="Error getting history stats",
    )
