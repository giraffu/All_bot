from __future__ import annotations

from datetime import datetime

from src.services.log_service import LogService


def parse_log_filter_date(date_str: str | None, *, end_of_day: bool = False) -> datetime | None:
    if not date_str:
        return None
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        return parsed.replace(hour=23, minute=59, second=59)
    return parsed


async def get_logs_payload(
    *,
    user_id: int | None = None,
    username: str | None = None,
    operation_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    return await LogService.get_logs(
        user_id=user_id,
        username=username,
        operation_type=operation_type,
        start_date=parse_log_filter_date(start_date),
        end_date=parse_log_filter_date(end_date, end_of_day=True),
        page=page,
        page_size=page_size,
    )
