from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Sequence

from fastapi import HTTPException
from sqlalchemy import and_, func, insert, or_, select

from src.database.models import Order, User, UserLog
from src.services.rmb_payment_provider_service import ALIPAY_DIRECT

logger = logging.getLogger("dashboard.alipay_direct")

MAX_BULK_USERS = 10_000
RosterSortField = Literal["created_at", "paid_count", "direct_paid_count", "id"]
SortOrder = Literal["asc", "desc"]


@dataclass(frozen=True)
class AlipayDirectUserFilters:
    min_paid_count: int | None = None
    max_paid_count: int | None = None
    first_used_from: date | None = None
    first_used_to: date | None = None
    direct_paid: bool | None = None
    enabled: bool | None = None
    query: str | None = None


def _payment_stats_subquery():
    successful_payment = and_(
        Order.status == "SUCCESS",
        Order.paid_at.is_not(None),
    )
    successful_direct_payment = Order.payment_provider == ALIPAY_DIRECT
    return (
        select(
            Order.internal_user_id.label("user_id"),
            func.count(Order.id).label("paid_count"),
            func.count(Order.id)
            .filter(successful_direct_payment)
            .label("direct_paid_count"),
            func.max(Order.paid_at)
            .filter(successful_direct_payment)
            .label("last_direct_paid_at"),
        )
        .where(successful_payment)
        .group_by(Order.internal_user_id)
        .subquery("alipay_direct_payment_stats")
    )


def _apply_roster_filters(stmt, stats, filters: AlipayDirectUserFilters):
    paid_count = func.coalesce(stats.c.paid_count, 0)
    direct_paid_count = func.coalesce(stats.c.direct_paid_count, 0)

    if filters.min_paid_count is not None:
        stmt = stmt.where(paid_count >= filters.min_paid_count)
    if filters.max_paid_count is not None:
        stmt = stmt.where(paid_count <= filters.max_paid_count)
    if filters.first_used_from is not None:
        stmt = stmt.where(User.created_at >= filters.first_used_from)
    if filters.first_used_to is not None:
        stmt = stmt.where(User.created_at < filters.first_used_to + timedelta(days=1))
    if filters.direct_paid is True:
        stmt = stmt.where(direct_paid_count > 0)
    elif filters.direct_paid is False:
        stmt = stmt.where(direct_paid_count == 0)
    if filters.enabled is not None:
        stmt = stmt.where(User.alipay_direct_enabled.is_(filters.enabled))
    if filters.query:
        normalized_query = filters.query.strip()
        if normalized_query:
            search_conditions = [
                User.username.ilike(f"%{normalized_query}%"),
                User.full_name.ilike(f"%{normalized_query}%"),
            ]
            if normalized_query.isdigit():
                search_conditions.append(User.id == int(normalized_query))
            stmt = stmt.where(or_(*search_conditions))
    return stmt


def _build_filtered_user_ids_stmt(filters: AlipayDirectUserFilters):
    stats = _payment_stats_subquery()
    stmt = select(User.id).outerjoin(stats, stats.c.user_id == User.id)
    return _apply_roster_filters(stmt, stats, filters)


async def get_alipay_direct_users_payload(
    *,
    db,
    page: int,
    page_size: int,
    filters: AlipayDirectUserFilters,
    sort_by: RosterSortField = "created_at",
    sort_order: SortOrder = "desc",
) -> dict:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="Invalid pagination")

    stats = _payment_stats_subquery()
    paid_count = func.coalesce(stats.c.paid_count, 0)
    direct_paid_count = func.coalesce(stats.c.direct_paid_count, 0)
    sort_fields = {
        "created_at": User.created_at,
        "paid_count": paid_count,
        "direct_paid_count": direct_paid_count,
        "id": User.id,
    }
    if sort_by not in sort_fields or sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid sort")

    stmt = select(
        User.id,
        User.username,
        User.full_name,
        User.created_at,
        User.alipay_direct_enabled,
        paid_count.label("paid_count"),
        direct_paid_count.label("direct_paid_count"),
        stats.c.last_direct_paid_at,
        func.count().over().label("total_count"),
    ).outerjoin(stats, stats.c.user_id == User.id)
    stmt = _apply_roster_filters(stmt, stats, filters)
    sort_column = sort_fields[sort_by]
    primary_order = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    secondary_order = User.id.asc() if sort_order == "asc" else User.id.desc()
    stmt = stmt.order_by(primary_order.nullslast(), secondary_order)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    try:
        rows = (await db.execute(stmt)).mappings().all()
    except Exception as exc:
        logger.error("Failed to list Alipay direct roster: %s", type(exc).__name__)
        raise HTTPException(
            status_code=500, detail="Failed to load Alipay direct roster"
        ) from exc

    total = int(rows[0]["total_count"]) if rows else 0
    items = [
        {
            "id": int(row["id"]),
            "username": row["username"],
            "full_name": row["full_name"],
            "created_at": row["created_at"],
            "alipay_direct_enabled": bool(row["alipay_direct_enabled"]),
            "paid_count": int(row["paid_count"] or 0),
            "direct_paid_count": int(row["direct_paid_count"] or 0),
            "has_direct_paid": int(row["direct_paid_count"] or 0) > 0,
            "last_direct_paid_at": row["last_direct_paid_at"],
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


async def bulk_update_alipay_direct_users_payload(
    *,
    db,
    enabled: bool,
    selection_mode: Literal["ids", "filters"],
    filters: AlipayDirectUserFilters | None = None,
    user_ids: Sequence[int] | None = None,
) -> dict:
    if selection_mode == "ids":
        normalized_ids = sorted({int(user_id) for user_id in user_ids or []})
        if not normalized_ids:
            raise HTTPException(status_code=400, detail="No users selected")
        if len(normalized_ids) > MAX_BULK_USERS:
            raise HTTPException(status_code=400, detail="Too many users selected")
        target_ids_stmt = select(User.id).where(User.id.in_(normalized_ids))
    elif selection_mode == "filters":
        target_ids_stmt = _build_filtered_user_ids_stmt(
            filters or AlipayDirectUserFilters()
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid selection mode")

    try:
        target_ids = list(
            (await db.execute(target_ids_stmt.limit(MAX_BULK_USERS + 1)))
            .scalars()
            .all()
        )
        if len(target_ids) > MAX_BULK_USERS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"At most {MAX_BULK_USERS} users can be changed at once; "
                    "narrow the filters"
                ),
            )
        if not target_ids:
            return {
                "status": "ok",
                "enabled": bool(enabled),
                "matched_count": 0,
                "updated_count": 0,
            }

        users = list(
            (
                await db.execute(
                    select(User)
                    .where(User.id.in_(target_ids))
                    .order_by(User.id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        changed_users = [
            user for user in users if bool(user.alipay_direct_enabled) != bool(enabled)
        ]
        changed_at = datetime.now()
        for user in changed_users:
            user.alipay_direct_enabled = bool(enabled)

        if changed_users:
            await db.execute(
                insert(UserLog),
                [
                    {
                        "user_id": user.id,
                        "username": (user.username or user.full_name or "")[:100]
                        or None,
                        "operation_type": "admin_update_alipay_direct",
                        "credit_change": 0,
                        "current_balance": int(user.credits or 0),
                        "created_at": changed_at,
                        "extra_info": json.dumps(
                            {
                                "old_status": not bool(enabled),
                                "new_status": bool(enabled),
                                "source": "dashboard_alipay_direct_roster_bulk",
                            }
                        ),
                    }
                    for user in changed_users
                ],
            )
        await db.commit()
        return {
            "status": "ok",
            "enabled": bool(enabled),
            "matched_count": len(target_ids),
            "updated_count": len(changed_users),
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(
            "Failed to bulk update Alipay direct roster: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update Alipay direct roster",
        ) from exc
