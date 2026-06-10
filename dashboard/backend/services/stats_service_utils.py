from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func


def get_hour_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("hour", col)
    return func.strftime("%H", col)


def get_days_diff_expr(col, dialect_name):
    if dialect_name == "postgresql":
        return func.extract("day", func.now() - col)
    return func.julianday("now") - func.julianday(col)


def date_key(value) -> str:
    return value if isinstance(value, str) else value.strftime("%Y-%m-%d")


def build_zeroed_distribution(keys: list[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def build_hourly_distribution(rows) -> dict[str, int]:
    hourly_distribution = {str(h).zfill(2): 0 for h in range(24)}
    for row in rows:
        hour_str = str(int(row.hour)).zfill(2) if row.hour is not None else "00"
        hourly_distribution[hour_str] = row.count
    return hourly_distribution


def parse_stats_target_date(date_str: str | None) -> date:
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    return date.today()


def day_bounds(target_date: date) -> tuple[date, date]:
    return target_date, target_date + timedelta(days=1)


def trailing_start_date(days: int) -> date:
    return date.today() - timedelta(days=days - 1)


def build_finance_hourly_distribution(rows) -> dict[str, dict[str, int]]:
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
