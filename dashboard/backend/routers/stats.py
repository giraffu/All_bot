import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
_STATS_CACHE_TTL_SECONDS = 300
_STATS_CACHE_MAX_ITEMS = 128
_stats_cache: dict[tuple[object, ...], tuple[float, object]] = {}
_stats_cache_locks: dict[tuple[object, ...], asyncio.Lock] = {}


def _get_stats_cache_lock(cache_key: tuple[object, ...]) -> asyncio.Lock:
    lock = _stats_cache_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _stats_cache_locks[cache_key] = lock
    return lock


def _prune_stats_cache(now: float) -> None:
    if len(_stats_cache) < _STATS_CACHE_MAX_ITEMS:
        return
    expired_keys = [
        cache_key
        for cache_key, (expires_at, _) in _stats_cache.items()
        if expires_at <= now
    ]
    for cache_key in expired_keys:
        _stats_cache.pop(cache_key, None)
        _stats_cache_locks.pop(cache_key, None)


async def _cached_stats_route(
    cache_key: tuple[object, ...],
    loader: Callable[[], Awaitable[object]],
    *,
    error_message: str,
):
    now = time.monotonic()
    cached = _stats_cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    async with _get_stats_cache_lock(cache_key):
        now = time.monotonic()
        cached = _stats_cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        value = await run_dashboard_route(
            loader,
            logger=logger,
            error_message=error_message,
        )
        _prune_stats_cache(now)
        _stats_cache[cache_key] = (time.monotonic() + _STATS_CACHE_TTL_SECONDS, value)
        return value


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    return await _cached_stats_route(
        ("summary",),
        lambda: load_dashboard_stats(db=db, logger=logger),
        error_message="Error getting stats",
    )


@router.get("/finance_hourly")
async def get_finance_hourly_stats(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get hourly finance stats (recharged credits and new disciples) for a specific date"""
    return await _cached_stats_route(
        ("finance_hourly", date_str or ""),
        lambda: load_finance_hourly_stats_by_date_str(db=db, date_str=date_str),
        error_message="Error getting finance hourly stats",
    )


@router.get("/finance_hourly/cumulative")
async def get_cumulative_finance_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly finance stats for the last N days"""
    return await _cached_stats_route(
        ("finance_hourly_cumulative", days),
        lambda: load_cumulative_finance_hourly_stats(db=db, days=days),
        error_message="Error getting cumulative finance hourly stats",
    )


@router.get("/hourly")
async def get_hourly_stats(date_str: str = None, db: AsyncSession = Depends(get_db)):
    """Get hourly generation stats for a specific date (YYYY-MM-DD)"""
    return await _cached_stats_route(
        ("hourly", date_str or ""),
        lambda: load_hourly_generation_stats_by_date_str(db=db, date_str=date_str),
        error_message="Error getting hourly stats",
    )


@router.get("/type_distribution")
async def get_type_distribution(
    date_str: str = None, db: AsyncSession = Depends(get_db)
):
    """Get generation type distribution for a specific date (YYYY-MM-DD)"""
    return await _cached_stats_route(
        ("type_distribution", date_str or ""),
        lambda: load_type_distribution_stats_by_date_str(db=db, date_str=date_str),
        error_message="Error getting type distribution stats",
    )


@router.get("/type_distribution/cumulative")
async def get_cumulative_type_distribution(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative generation type distribution for the last N days"""
    return await _cached_stats_route(
        ("type_distribution_cumulative", days),
        lambda: load_cumulative_type_distribution_stats(db=db, days=days),
        error_message="Error getting cumulative type distribution stats",
    )


@router.get("/hourly/cumulative")
async def get_cumulative_hourly_stats(
    days: int = 7, db: AsyncSession = Depends(get_db)
):
    """Get cumulative hourly generation stats for the last N days"""
    return await _cached_stats_route(
        ("hourly_cumulative", days),
        lambda: load_cumulative_hourly_generation_stats(db=db, days=days),
        error_message="Error getting cumulative hourly stats",
    )


@router.get("/history")
async def get_stats_history(days: int = 7, db: AsyncSession = Depends(get_db)):
    """Get historical stats for charts (last N days)"""
    return await _cached_stats_route(
        ("history", days),
        lambda: load_dashboard_stats_history(db=db, days=days, logger=logger),
        error_message="Error getting history stats",
    )
