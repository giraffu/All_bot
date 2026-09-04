from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.services.stats_service_consumption import (
    GENERATION_CONSUMPTION_OPERATION_TYPES,
)
from dashboard.backend.services.stats_service_utils import day_bounds
from src.database.models import History, UserLog, WorkerLog

from dashboard.backend.services.worker_gpu_telemetry import parse_gpu_phase_factor


CALIBRATION_NAME = "worker_gpu_phase_5090_equivalent_v1"

_TASK_ANALYTICS_ALIASES = {
    "image": "img2img",
    "edit": "img2img",
    "quick_image": "img2img",
    "text_to_image": "txt2img",
    "faceswap_step1": "face_swap",
    "faceswap_step2": "face_swap",
    "face_video_step1": "face_video",
    "face_video_step2": "face_video",
    "video": "image_to_video",
    "custom_video": "image_to_video",
    "video_lora": "image_to_video",
    "ltx_video_flf2v": "ltx_video",
    "ltx_video_v2_flf2v": "ltx_video_v2",
    "free_edit_v3": "pornmaster_flux2_edit_bf16",
}

TASK_ANALYTICS_CHARGE_OPERATION_TYPES = tuple(
    dict.fromkeys(
        [
            *GENERATION_CONSUMPTION_OPERATION_TYPES,
            *_TASK_ANALYTICS_ALIASES,
            "character_reference_build",
        ]
    )
)


def build_task_analytics_charge_filter():
    return and_(
        UserLog.credit_change < 0,
        UserLog.operation_type.in_(TASK_ANALYTICS_CHARGE_OPERATION_TYPES),
    )


def normalize_task_analytics_type(value: Any) -> str:
    task_type = str(value or "unknown").strip() or "unknown"
    return _TASK_ANALYTICS_ALIASES.get(task_type, task_type)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def build_task_credit_distribution(rows: Iterable[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        task_type = normalize_task_analytics_type(_row_value(row, "task_type"))
        credits = max(0, int(_row_value(row, "credits", 0) or 0))
        if credits:
            result[task_type] = result.get(task_type, 0) + credits
    return dict(sorted(result.items(), key=lambda item: (-item[1], item[0])))


def build_task_gpu_efficiency(
    *,
    credit_rows: Iterable[Any],
    worker_rows: Iterable[Any],
) -> dict[str, Any]:
    credits_by_type = build_task_credit_distribution(credit_rows)
    total_tasks_by_type: dict[str, int] = {}
    telemetry_tasks_by_type: dict[str, int] = {}
    telemetry_seconds_by_type: dict[str, float] = {}
    telemetry_workers_by_type: dict[str, set[str]] = {}

    for row in worker_rows:
        task_type = normalize_task_analytics_type(_row_value(row, "task_type"))
        total_tasks_by_type[task_type] = total_tasks_by_type.get(task_type, 0) + 1
        factor = parse_gpu_phase_factor(_row_value(row, "error_message"))
        try:
            duration = float(_row_value(row, "duration", 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        if factor is None or duration <= 0:
            continue
        telemetry_tasks_by_type[task_type] = (
            telemetry_tasks_by_type.get(task_type, 0) + 1
        )
        telemetry_seconds_by_type[task_type] = (
            telemetry_seconds_by_type.get(task_type, 0) + duration * factor
        )
        telemetry_workers_by_type.setdefault(task_type, set()).add(
            str(_row_value(row, "worker_id", "unknown") or "unknown")
        )

    items: dict[str, dict[str, int | float | bool | str]] = {}
    covered_credits = 0.0

    for task_type, credits in credits_by_type.items():
        successful_task_count = total_tasks_by_type.get(task_type, 0)
        task_count = telemetry_tasks_by_type.get(task_type, 0)
        gpu_seconds = telemetry_seconds_by_type.get(task_type, 0.0)
        if not successful_task_count or not task_count or gpu_seconds <= 0:
            continue

        telemetry_coverage = min(1.0, task_count / successful_task_count)
        attributed_credits = round(credits * telemetry_coverage, 2)
        gpu_hours = gpu_seconds / 3600
        covered_credits += attributed_credits
        items[task_type] = {
            "value": round(attributed_credits / gpu_hours, 2),
            "credits": attributed_credits,
            "gross_credits": credits,
            "gpu_hours": round(gpu_hours, 4),
            "task_count": task_count,
            "successful_task_count": successful_task_count,
            "worker_count": len(telemetry_workers_by_type.get(task_type, set())),
            "telemetry_coverage": round(telemetry_coverage, 4),
            "estimated": telemetry_coverage < 1,
            "gpu_time_source": "worker_gpu_phase",
        }

    total_credits = sum(credits_by_type.values())
    covered_credits = round(covered_credits, 2)
    return {
        "unit": "lingshi_per_5090_gpu_hour",
        "calibration": CALIBRATION_NAME,
        "basis": "actual_worker_task_gpu_phase",
        "items": dict(
            sorted(
                items.items(),
                key=lambda item: (-float(item[1]["value"]), item[0]),
            )
        ),
        "total_credits": total_credits,
        "covered_credits": covered_credits,
        "uncovered_credits": round(max(0, total_credits - covered_credits), 2),
    }


def _task_credit_distribution_statement(*, start_date: date, end_date: date):
    return (
        select(
            UserLog.operation_type.label("task_type"),
            func.coalesce(func.sum(-UserLog.credit_change), 0).label("credits"),
        )
        .select_from(UserLog)
        .where(
            build_task_analytics_charge_filter(),
            UserLog.created_at >= start_date,
            UserLog.created_at < end_date,
        )
        .group_by(UserLog.operation_type)
    )


def _worker_task_execution_statement(*, start_date: date, end_date: date):
    return (
        select(
            History.type.label("task_type"),
            WorkerLog.worker_id.label("worker_id"),
            WorkerLog.duration.label("duration"),
            WorkerLog.error_message.label("error_message"),
        )
        .select_from(WorkerLog)
        .join(History, History.task_id == WorkerLog.task_id)
        .where(
            WorkerLog.status == "success",
            History.created_at >= start_date,
            History.created_at < end_date,
        )
    )


async def _load_task_credit_rows(*, db: AsyncSession, target_date: date) -> list[Any]:
    start_date, end_date = day_bounds(target_date)
    rows = await db.execute(
        _task_credit_distribution_statement(
            start_date=start_date,
            end_date=end_date,
        )
    )
    return list(rows)


async def load_task_credit_distribution_stats(
    *, db: AsyncSession, target_date: date
) -> dict[str, Any]:
    values = build_task_credit_distribution(
        await _load_task_credit_rows(db=db, target_date=target_date)
    )
    return {
        "date": target_date.isoformat(),
        "unit": "lingshi",
        "basis": "gross_generation_debits",
        "total_credits": sum(values.values()),
        "values": values,
    }


async def load_task_gpu_efficiency_stats(
    *, db: AsyncSession, target_date: date
) -> dict[str, Any]:
    credit_rows = await _load_task_credit_rows(db=db, target_date=target_date)
    start_date, end_date = day_bounds(target_date)
    worker_result = await db.execute(
        _worker_task_execution_statement(
            start_date=start_date,
            end_date=end_date,
        )
    )
    result = build_task_gpu_efficiency(
        credit_rows=credit_rows,
        worker_rows=worker_result,
    )
    return {"date": target_date.isoformat(), **result}
