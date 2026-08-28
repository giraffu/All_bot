from datetime import date
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from dashboard.backend.routers import alipay_direct
from dashboard.backend.schemas import (
    AlipayDirectBulkFilters,
    AlipayDirectBulkUpdateRequest,
)


@pytest.mark.asyncio
async def test_list_router_passes_server_side_filters(monkeypatch):
    list_payload = AsyncMock(return_value={"items": [], "total": 0})
    monkeypatch.setattr(
        alipay_direct,
        "get_alipay_direct_users_payload",
        list_payload,
    )
    db = object()

    await alipay_direct.list_alipay_direct_users(
        page=2,
        page_size=50,
        min_paid_count=2,
        max_paid_count=8,
        first_used_from=date(2026, 1, 1),
        first_used_to=date(2026, 6, 1),
        direct_paid=False,
        enabled=True,
        query="buyer",
        sort_by="paid_count",
        sort_order="desc",
        db=db,
    )

    kwargs = list_payload.await_args.kwargs
    assert kwargs["db"] is db
    assert kwargs["page"] == 2
    assert kwargs["page_size"] == 50
    assert kwargs["filters"].min_paid_count == 2
    assert kwargs["filters"].direct_paid is False
    assert kwargs["filters"].enabled is True
    assert kwargs["sort_by"] == "paid_count"


@pytest.mark.asyncio
async def test_bulk_router_supports_explicit_and_filtered_selection(monkeypatch):
    bulk_payload = AsyncMock(return_value={"status": "ok", "updated_count": 3})
    monkeypatch.setattr(
        alipay_direct,
        "bulk_update_alipay_direct_users_payload",
        bulk_payload,
    )
    request = AlipayDirectBulkUpdateRequest(
        enabled=True,
        selection_mode="filters",
        filters=AlipayDirectBulkFilters(
            min_paid_count=4,
            enabled=False,
        ),
    )

    await alipay_direct.bulk_update_alipay_direct_users(request=request, db=object())

    kwargs = bulk_payload.await_args.kwargs
    assert kwargs["enabled"] is True
    assert kwargs["selection_mode"] == "filters"
    assert kwargs["filters"].min_paid_count == 4
    assert kwargs["filters"].enabled is False


def test_bulk_schema_rejects_missing_or_conflicting_selection():
    with pytest.raises(ValidationError):
        AlipayDirectBulkUpdateRequest(enabled=True, selection_mode="ids")

    with pytest.raises(ValidationError):
        AlipayDirectBulkUpdateRequest(
            enabled=True,
            selection_mode="filters",
            filters=AlipayDirectBulkFilters(
                min_paid_count=5,
                max_paid_count=2,
            ),
        )
