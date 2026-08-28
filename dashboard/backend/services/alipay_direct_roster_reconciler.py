from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select

from src.database.core import AsyncSessionLocal
from src.database.models import Order, User, UserLog
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT

logger = logging.getLogger("dashboard.alipay_direct_roster_reconciler")
DEFAULT_RECONCILE_INTERVAL_SECONDS = 300
DEFAULT_RECONCILE_BATCH_SIZE = 500
MAX_RECONCILE_BATCH_SIZE = 1_000


@dataclass(frozen=True, slots=True)
class AlipayDirectRosterDependencies:
    session_factory: Callable[[], Any]
    now_func: Callable[[], datetime]


def build_default_dependencies() -> AlipayDirectRosterDependencies:
    return AlipayDirectRosterDependencies(
        session_factory=AsyncSessionLocal,
        now_func=datetime.now,
    )


def _reconcile_interval_seconds() -> int:
    raw_value = os.getenv(
        "DASHBOARD_ALIPAY_DIRECT_RECONCILE_INTERVAL_SECONDS",
        str(DEFAULT_RECONCILE_INTERVAL_SECONDS),
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_RECONCILE_INTERVAL_SECONDS
    return max(10, value)


def _successful_direct_payers_stmt(*, batch_size: int):
    paid_direct_user_ids = (
        select(Order.internal_user_id.label("user_id"))
        .where(
            Order.payment_provider == ALIPAY_DIRECT,
            Order.status == "SUCCESS",
            Order.paid_at.is_not(None),
        )
        .distinct()
        .subquery("successful_alipay_direct_users")
    )
    return (
        select(User)
        .join(paid_direct_user_ids, paid_direct_user_ids.c.user_id == User.id)
        .where(User.alipay_direct_enabled.is_(True))
        .order_by(User.id)
        .limit(batch_size)
        .with_for_update(of=User, skip_locked=True)
    )


async def reconcile_alipay_direct_roster_once(
    *,
    dependencies: AlipayDirectRosterDependencies | None = None,
    batch_size: int = DEFAULT_RECONCILE_BATCH_SIZE,
) -> int:
    dependencies = dependencies or build_default_dependencies()
    normalized_batch_size = max(1, min(int(batch_size), MAX_RECONCILE_BATCH_SIZE))
    async with dependencies.session_factory() as session:
        try:
            users = list(
                (
                    await session.execute(
                        _successful_direct_payers_stmt(
                            batch_size=normalized_batch_size
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not users:
                return 0

            changed_at = dependencies.now_func()
            for user in users:
                user.alipay_direct_enabled = False
                session.add(
                    UserLog(
                        user_id=user.id,
                        username=(user.username or user.full_name or "")[:100] or None,
                        operation_type="auto_disable_alipay_direct_after_payment",
                        credit_change=0,
                        current_balance=int(user.credits or 0),
                        created_at=changed_at,
                        extra_info=json.dumps(
                            {
                                "old_status": True,
                                "new_status": False,
                                "reason": "successful_alipay_direct_payment",
                                "source": "dashboard_alipay_direct_roster_reconciler",
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
            await session.commit()
            logger.info(
                "Automatically removed %s successful direct payers from roster",
                len(users),
            )
            return len(users)
        except Exception:
            await session.rollback()
            raise


async def run_alipay_direct_roster_reconciler(
    *,
    stop_event: asyncio.Event | None = None,
    interval_seconds: int | None = None,
    reconcile_once_func: Callable[[], Awaitable[int]] | None = None,
) -> None:
    interval = max(
        1,
        int(
            interval_seconds
            if interval_seconds is not None
            else _reconcile_interval_seconds()
        ),
    )
    reconcile = reconcile_once_func or reconcile_alipay_direct_roster_once
    while stop_event is None or not stop_event.is_set():
        try:
            await reconcile()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Failed to reconcile Alipay direct roster error_type=%s",
                type(exc).__name__,
                exc_info=True,
            )

        if stop_event is not None and stop_event.is_set():
            return
        if stop_event is None:
            await asyncio.sleep(interval)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
