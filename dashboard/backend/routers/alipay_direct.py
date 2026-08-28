from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.schemas import AlipayDirectBulkUpdateRequest
from dashboard.backend.services.alipay_direct_admin_service import (
    AlipayDirectUserFilters,
    bulk_update_alipay_direct_users_payload,
    get_alipay_direct_users_payload,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/alipay-direct-users", tags=["alipay-direct-users"])


@router.get("")
async def list_alipay_direct_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    min_paid_count: int | None = Query(default=None, ge=0),
    max_paid_count: int | None = Query(default=None, ge=0),
    first_used_from: date | None = Query(default=None),
    first_used_to: date | None = Query(default=None),
    direct_paid: bool | None = Query(default=None),
    enabled: bool | None = Query(default=True),
    query: str | None = Query(default=None, max_length=100),
    sort_by: Literal["created_at", "paid_count", "direct_paid_count", "id"] = Query(
        default="created_at"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    db: AsyncSession = Depends(get_db),
):
    return await get_alipay_direct_users_payload(
        db=db,
        page=page,
        page_size=page_size,
        filters=AlipayDirectUserFilters(
            min_paid_count=min_paid_count,
            max_paid_count=max_paid_count,
            first_used_from=first_used_from,
            first_used_to=first_used_to,
            direct_paid=direct_paid,
            enabled=enabled,
            query=query,
        ),
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.post("/bulk-status")
async def bulk_update_alipay_direct_users(
    request: AlipayDirectBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    filter_values = request.filters.model_dump() if request.filters else {}
    return await bulk_update_alipay_direct_users_payload(
        db=db,
        enabled=request.enabled,
        selection_mode=request.selection_mode,
        user_ids=request.user_ids,
        filters=AlipayDirectUserFilters(**filter_values),
    )
