from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from dashboard.backend.schemas import (
    PaidGroupGuardConfigResponse,
    PaidGroupGuardLogItem,
    PaidGroupGuardLogListResponse,
)
from paid_group_guard_bot.moderation import (
    DEFAULT_MODERATION_CONFIG_PATH,
    DEFAULT_MODERATION_LOG_PATH,
    PaidGroupModerationConfig,
    load_moderation_config,
    moderation_config_to_dict,
    normalize_moderation_config,
    write_moderation_config,
)

logger = logging.getLogger("dashboard.paid_group_guard")
MAX_PAGE_SIZE = 100


def _config_path() -> str:
    return os.getenv(
        "PAID_GROUP_MODERATION_CONFIG_FILE",
        DEFAULT_MODERATION_CONFIG_PATH,
    )


def _log_path() -> str:
    return os.getenv(
        "PAID_GROUP_MODERATION_LOG_FILE",
        DEFAULT_MODERATION_LOG_PATH,
    )


def _config_response(config: PaidGroupModerationConfig) -> PaidGroupGuardConfigResponse:
    payload = moderation_config_to_dict(config)
    return PaidGroupGuardConfigResponse(
        **payload,
        config_path=_config_path(),
        log_path=_log_path(),
    )


async def get_paid_group_guard_config_payload() -> PaidGroupGuardConfigResponse:
    try:
        return _config_response(load_moderation_config(_config_path()))
    except Exception as exc:
        logger.error("Error loading paid group guard config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


async def update_paid_group_guard_config_payload(payload) -> PaidGroupGuardConfigResponse:
    try:
        config = normalize_moderation_config(payload.model_dump())
        write_moderation_config(_config_path(), config)
        return _config_response(config)
    except Exception as exc:
        logger.error("Error saving paid group guard config: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def parse_guard_log_filter_date(
    date_str: str | None,
    *,
    end_of_day: bool = False,
) -> datetime | None:
    if not date_str:
        return None
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        return parsed.replace(hour=23, minute=59, second=59)
    return parsed


def _parse_event_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_log_item(payload: dict) -> PaidGroupGuardLogItem | None:
    try:
        return PaidGroupGuardLogItem(
            timestamp=str(payload.get("timestamp") or ""),
            chat_id=_coerce_int(payload.get("chat_id")),
            message_id=_coerce_int(payload.get("message_id")),
            user_id=_coerce_int(payload.get("user_id")),
            username=payload.get("username"),
            full_name=payload.get("full_name"),
            reason=str(payload.get("reason") or "unknown"),
            matched_value=payload.get("matched_value"),
            text_snippet=str(payload.get("text_snippet") or ""),
            action=str(payload.get("action") or "unknown"),
            error=payload.get("error"),
        )
    except Exception:
        return None


def _iter_log_items(path: str) -> list[PaidGroupGuardLogItem]:
    log_file = Path(path)
    if not log_file.exists():
        return []

    items: list[PaidGroupGuardLogItem] = []
    with log_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            item = _normalize_log_item(raw)
            if item is not None:
                items.append(item)
    return items


async def get_paid_group_guard_logs_payload(
    *,
    reason: str | None = None,
    user_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PaidGroupGuardLogListResponse:
    try:
        normalized_page = max(int(page or 1), 1)
        normalized_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
        start_dt = parse_guard_log_filter_date(start_date)
        end_dt = parse_guard_log_filter_date(end_date, end_of_day=True)
        reason_filter = (reason or "").strip()

        items = _iter_log_items(_log_path())
        filtered: list[PaidGroupGuardLogItem] = []
        for item in items:
            if reason_filter and item.reason != reason_filter:
                continue
            if user_id is not None and item.user_id != int(user_id):
                continue
            event_dt = _parse_event_timestamp(item.timestamp)
            if start_dt and event_dt and event_dt.replace(tzinfo=None) < start_dt:
                continue
            if end_dt and event_dt and event_dt.replace(tzinfo=None) > end_dt:
                continue
            filtered.append(item)

        filtered.sort(key=lambda item: item.timestamp, reverse=True)
        total = len(filtered)
        start = (normalized_page - 1) * normalized_size
        end = start + normalized_size
        total_pages = (total + normalized_size - 1) // normalized_size if total else 0

        return PaidGroupGuardLogListResponse(
            total=total,
            page=normalized_page,
            page_size=normalized_size,
            total_pages=total_pages,
            items=filtered[start:end],
        )
    except Exception as exc:
        logger.error("Error loading paid group guard logs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
