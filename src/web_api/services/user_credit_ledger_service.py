from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, func, select

from src.database.models import UserLog
from src.web_api.schemas.user_credit_ledger_schema import (
    CreditLedgerItem,
    CreditLedgerResponse,
)
from src.services.user_visible_generation_presenter import (
    resolve_credit_ledger_display_key,
)


SAFE_DISPLAY_CONTEXT_KEYS = (
    "reason",
    "plan_name",
    "amount_usdt",
    "credits_granted",
    "exchange_rate_snapshot",
    "rounding_mode",
    "via",
    "source_channel",
    "checkin_date",
    "reward",
    "checkin_base_reward",
    "checkin_identity_bonus",
    "checkin_user_group",
    "checkin_identity",
    "cost_credits",
)


def _parse_extra_info(extra_info: Any) -> dict[str, Any]:
    if not extra_info:
        return {}
    if isinstance(extra_info, dict):
        return extra_info
    if not isinstance(extra_info, str):
        return {}

    try:
        parsed = json.loads(extra_info)
    except json.JSONDecodeError:
        return {}

    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            return {}

    return parsed if isinstance(parsed, dict) else {}


def _safe_display_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        return normalized[:160]
    return None


def _build_display_context(extra_info: Any) -> dict[str, Any]:
    parsed = _parse_extra_info(extra_info)
    display_context: dict[str, Any] = {}
    for key in SAFE_DISPLAY_CONTEXT_KEYS:
        value = _safe_display_value(parsed.get(key))
        if value is not None:
            display_context[key] = value
    return display_context


def _to_credit_ledger_item(log: UserLog) -> CreditLedgerItem:
    credit_change = int(log.credit_change or 0)
    return CreditLedgerItem(
        id=int(log.id),
        operation_type=log.operation_type,
        display_key=resolve_credit_ledger_display_key(log.operation_type),
        direction="income" if credit_change > 0 else "expense",
        credit_change=credit_change,
        current_balance=int(log.current_balance or 0),
        created_at=log.created_at,
        display_context=_build_display_context(log.extra_info),
    )


async def get_current_user_credit_ledger_payload(
    *,
    current_user,
    db,
    page: int = 1,
    page_size: int = 20,
) -> CreditLedgerResponse:
    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 20)))
    filters = (
        UserLog.user_id == current_user.id,
        UserLog.credit_change != 0,
    )

    total = (
        await db.execute(select(func.count()).select_from(UserLog).where(*filters))
    ).scalar() or 0
    result = await db.execute(
        select(UserLog)
        .where(*filters)
        .order_by(desc(UserLog.created_at), desc(UserLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_to_credit_ledger_item(log) for log in result.scalars().all()]

    return CreditLedgerResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )
