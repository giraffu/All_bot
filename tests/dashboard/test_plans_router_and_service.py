from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.presenters import plan_admin_presenter
from dashboard.backend.routers import plans as plans_router
from dashboard.backend.services import plan_admin_service


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _RowsResult:
    def __init__(self, rows):
        self.rows = list(rows)

    def __iter__(self):
        return iter(self.rows)


class _FakePlansDb:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.executed_stmts = []

    async def execute(self, stmt):
        self.executed_stmts.append(str(stmt))
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return self.execute_results.pop(0)


def _build_order(**overrides):
    base = {
        "id": 1,
        "order_id": "order-1",
        "telegram_id": 123,
        "internal_user_id": 123,
        "plan_id": 5,
        "original_price": 10.0,
        "final_price": 8.0,
        "status": "SUCCESS",
        "tx_hash": "tx-1",
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
    }
    base.update(overrides)
    obj = SimpleNamespace(**base)
    obj.__table__ = SimpleNamespace(columns=[SimpleNamespace(name=k) for k in base.keys()])
    return obj


def test_build_order_item_payload_flattens_username_and_plan_name():
    payload = plan_admin_presenter.build_order_item_payload(
        order=_build_order(),
        username="tester",
        plan_name="月卡",
    )

    assert payload["username"] == "tester"
    assert payload["plan_name"] == "月卡"
    assert payload["order_id"] == "order-1"
    assert payload["internal_user_id"] == 123


@pytest.mark.asyncio
async def test_get_orders_payload_applies_filters_and_flattens_items():
    order = _build_order()
    db = _FakePlansDb([
        _ScalarResult(1),
        _RowsResult([(order, "tester", "月卡")]),
    ])

    result = await plan_admin_service.get_orders_payload(
        page=2,
        page_size=10,
        status="SUCCESS",
        internal_user_id=123,
        username="test",
        db=db,
    )

    assert result["total"] == 1
    assert result["items"][0]["username"] == "tester"
    assert result["items"][0]["plan_name"] == "月卡"
    list_stmt = db.executed_stmts[1]
    assert "orders.status = :status_1" in list_stmt
    assert "orders.telegram_id =" in list_stmt
    assert "users.username" in list_stmt
    assert ":telegram_id_1" in list_stmt or ":internal_user_id_1" in list_stmt
    assert "username_1" in list_stmt


@pytest.mark.asyncio
async def test_get_orders_router_routes_to_service(monkeypatch):
    expected = {"items": [], "total": 0}
    service_mock = AsyncMock(return_value=expected)
    monkeypatch.setattr(plans_router, "get_orders_payload", service_mock)
    db = object()

    result = await plans_router.get_orders(
        page=1,
        page_size=20,
        status="ALL",
        internal_user_id=123,
        username="tester",
        db=db,
    )

    assert result == expected
    service_mock.assert_awaited_once_with(
        page=1,
        page_size=20,
        status="ALL",
        internal_user_id=123,
        username="tester",
        db=db,
        logger_override=plans_router.logger,
    )
