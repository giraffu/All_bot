from __future__ import annotations

from datetime import date
from logging import Logger

from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_activity import (
    load_cumulative_finance_hourly_stats_impl,
    load_cumulative_hourly_generation_stats_impl,
    load_cumulative_type_distribution_stats_impl,
    load_finance_hourly_stats_impl,
    load_hourly_generation_stats_impl,
    load_type_distribution_stats_impl,
)
from dashboard.backend.services.stats_service_history import (
    load_dashboard_stats_history_impl,
)
from dashboard.backend.services.stats_service_finance import (
    load_finance_dashboard_history_impl,
    load_finance_dashboard_summary_impl,
)
from dashboard.backend.services.stats_service_summary import load_dashboard_stats_impl
from dashboard.backend.services.stats_service_utils import (
    build_hourly_distribution,
    parse_stats_target_date,
)

_build_hourly_distribution = build_hourly_distribution

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


async def load_finance_hourly_stats(*, db: AsyncSession, target_date: date) -> dict:
    return await load_finance_hourly_stats_impl(db=db, target_date=target_date)


async def load_finance_hourly_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict:
    return await load_finance_hourly_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_finance_hourly_stats(*, db: AsyncSession, days: int) -> dict:
    return await load_cumulative_finance_hourly_stats_impl(db=db, days=days)


async def load_hourly_generation_stats(*, db: AsyncSession, target_date: date) -> dict[str, int]:
    return await load_hourly_generation_stats_impl(db=db, target_date=target_date)


async def load_hourly_generation_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict[str, int]:
    return await load_hourly_generation_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_hourly_generation_stats(*, db: AsyncSession, days: int) -> dict[str, int]:
    return await load_cumulative_hourly_generation_stats_impl(db=db, days=days)


async def load_type_distribution_stats(*, db: AsyncSession, target_date: date) -> dict[str, int]:
    return await load_type_distribution_stats_impl(db=db, target_date=target_date)


async def load_type_distribution_stats_by_date_str(
    *, db: AsyncSession, date_str: str | None
) -> dict[str, int]:
    return await load_type_distribution_stats(
        db=db,
        target_date=parse_stats_target_date(date_str),
    )


async def load_cumulative_type_distribution_stats(*, db: AsyncSession, days: int) -> dict[str, int]:
    return await load_cumulative_type_distribution_stats_impl(db=db, days=days)


async def load_dashboard_stats(*, db: AsyncSession, logger: Logger) -> dict:
    return await load_dashboard_stats_impl(
        db=db,
        logger=logger,
        video_types=VIDEO_TYPES,
        user_group_keys=USER_GROUP_KEYS,
    )


async def load_dashboard_stats_history(
    *, db: AsyncSession, days: int, logger: Logger
) -> list[dict]:
    return await load_dashboard_stats_history_impl(
        db=db,
        days=days,
        logger=logger,
        video_types=VIDEO_TYPES,
    )


async def load_finance_dashboard_summary(*, db: AsyncSession, logger: Logger) -> dict:
    return await load_finance_dashboard_summary_impl(db=db, logger=logger)


async def load_finance_dashboard_history(*, db: AsyncSession, days: int) -> list[dict]:
    return await load_finance_dashboard_history_impl(db=db, days=days)
