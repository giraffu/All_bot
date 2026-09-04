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
from src.database.models import History, UserLog


CALIBRATION_NAME = "production_p50_5090_equivalent_v1"

# Median occupied-slot seconds from the latest production audit, normalized to
# one RTX 5090. These are deliberately task-level calibrations: the dashboard
# must not use WorkerLog.duration because that legacy field includes queue wait.
GPU_SECONDS_5090_BY_TASK_TYPE: dict[str, float] = {
    "txt2img": 23.32,
    "i2i_pro": 32.91,
    "img2img": 10.56,
    "img2img_lora": 12.08,
    "free_edit_v2_5": 16.01,
    "pornmaster_flux2_single_edit": 16.01,
    "pornmaster_flux2_multi_edit": 20.01,
    "pornmaster_flux2_edit_bf16": 16.01,
    "pornmaster_flux2_multi_edit_bf16": 20.01,
    "face_swap": 22.63,
    "random_faceswap": 22.63,
    "image_to_video": 25.74,
    "wan22_video_v2": 58.63,
    "ltx_video": 61.07,
    "ltx_video_v2": 61.07,
    "ltx_t2v": 61.07,
    "ltx_t2v_ic": 61.07,
    "minimax_h3_t2v": 87.3,
    "minimax_h3_i2v": 148.5,
    "minimax_h3_flf2v": 89.2,
    "minimax_h3_ref2v": 123.6,
    "scail2_action_transfer": 108.7,
    "scail2_action_transfer_long": 632.1,
    "scail2_video_replacement": 204.2,
    "scail2_face_swap_v2": 112.5,
}

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
            *GPU_SECONDS_5090_BY_TASK_TYPE,
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


def _build_task_count_distribution(rows: Iterable[Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        task_type = normalize_task_analytics_type(_row_value(row, "task_type"))
        task_count = max(0, int(_row_value(row, "task_count", 0) or 0))
        if task_count:
            result[task_type] = result.get(task_type, 0) + task_count
    return result


def build_task_gpu_efficiency(
    *,
    credit_rows: Iterable[Any],
    history_rows: Iterable[Any],
) -> dict[str, Any]:
    credits_by_type = build_task_credit_distribution(credit_rows)
    tasks_by_type = _build_task_count_distribution(history_rows)
    items: dict[str, dict[str, int | float | bool]] = {}
    covered_credits = 0
    uncovered_credits = 0

    for task_type, credits in credits_by_type.items():
        task_count = tasks_by_type.get(task_type, 0)
        calibrated_seconds = GPU_SECONDS_5090_BY_TASK_TYPE.get(task_type)
        if not task_count or not calibrated_seconds:
            uncovered_credits += credits
            continue

        gpu_hours = task_count * calibrated_seconds / 3600
        if gpu_hours <= 0:
            uncovered_credits += credits
            continue
        covered_credits += credits
        items[task_type] = {
            "value": round(credits / gpu_hours, 2),
            "credits": credits,
            "gpu_hours": round(gpu_hours, 4),
            "task_count": task_count,
            "estimated": True,
        }

    return {
        "unit": "lingshi_per_5090_gpu_hour",
        "calibration": CALIBRATION_NAME,
        "items": dict(
            sorted(
                items.items(),
                key=lambda item: (-float(item[1]["value"]), item[0]),
            )
        ),
        "total_credits": sum(credits_by_type.values()),
        "covered_credits": covered_credits,
        "uncovered_credits": uncovered_credits,
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


def _history_task_distribution_statement(*, start_date: date, end_date: date):
    return (
        select(
            History.type.label("task_type"),
            func.count().label("task_count"),
        )
        .select_from(History)
        .where(
            History.created_at >= start_date,
            History.created_at < end_date,
        )
        .group_by(History.type)
    )


async def _load_task_credit_rows(
    *, db: AsyncSession, target_date: date
) -> list[Any]:
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
    history_result = await db.execute(
        _history_task_distribution_statement(
            start_date=start_date,
            end_date=end_date,
        )
    )
    result = build_task_gpu_efficiency(
        credit_rows=credit_rows,
        history_rows=history_result,
    )
    return {"date": target_date.isoformat(), **result}
