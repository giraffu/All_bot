from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.services.alipay_direct_admin_service import (
    AlipayDirectUserFilters,
    bulk_update_alipay_direct_users_payload,
    get_alipay_direct_users_payload,
)
from src.database.models import User


class _Result:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = list(rows or [])
        self._scalars = list(scalars or [])

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _Result(rows=self._scalars)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.statements = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        if not self._results:
            return _Result()
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_roster_list_filters_paid_count_first_use_and_direct_payment():
    created_at = datetime(2026, 2, 5, 8, 30)
    db = _FakeSession(
        [
            _Result(
                rows=[
                    {
                        "id": 1001,
                        "username": "repeat_buyer",
                        "full_name": "Repeat Buyer",
                        "created_at": created_at,
                        "alipay_direct_enabled": True,
                        "paid_count": 6,
                        "direct_paid_count": 2,
                        "last_direct_paid_at": datetime(2026, 8, 20, 12, 0),
                        "total_count": 1,
                    }
                ]
            )
        ]
    )

    payload = await get_alipay_direct_users_payload(
        db=db,
        page=1,
        page_size=20,
        filters=AlipayDirectUserFilters(
            min_paid_count=4,
            max_paid_count=9,
            first_used_from=date(2026, 1, 1),
            first_used_to=date(2026, 5, 31),
            direct_paid=True,
            enabled=True,
        ),
    )

    assert payload == {
        "items": [
            {
                "id": 1001,
                "username": "repeat_buyer",
                "full_name": "Repeat Buyer",
                "created_at": created_at,
                "alipay_direct_enabled": True,
                "paid_count": 6,
                "direct_paid_count": 2,
                "has_direct_paid": True,
                "last_direct_paid_at": datetime(2026, 8, 20, 12, 0),
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    sql = db.statements[0]
    assert "orders.status =" in sql
    assert "orders.paid_at IS NOT NULL" in sql
    assert "orders.payment_provider =" in sql
    assert "users.created_at >=" in sql
    assert "users.created_at <" in sql
    assert "coalesce" in sql.lower()
    assert "OVER ()" in sql


@pytest.mark.asyncio
async def test_bulk_update_uses_all_matching_filters_and_commits_audits_atomically():
    first = User(
        id=1001,
        username="first",
        credits=10,
        alipay_direct_enabled=False,
    )
    second = User(
        id=1002,
        username="second",
        credits=20,
        alipay_direct_enabled=True,
    )
    db = _FakeSession(
        [
            _Result(scalars=[1001, 1002]),
            _Result(scalars=[first, second]),
            _Result(),
        ]
    )

    payload = await bulk_update_alipay_direct_users_payload(
        db=db,
        enabled=True,
        selection_mode="filters",
        filters=AlipayDirectUserFilters(min_paid_count=2, direct_paid=False),
    )

    assert payload == {
        "status": "ok",
        "enabled": True,
        "matched_count": 2,
        "updated_count": 1,
    }
    assert first.alipay_direct_enabled is True
    assert second.alipay_direct_enabled is True
    assert "FOR UPDATE" in db.statements[1]
    assert "INSERT INTO user_logs" in db.statements[2]
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_update_rejects_an_unbounded_large_match_before_locking_users():
    db = _FakeSession([_Result(scalars=range(10_001))])

    with pytest.raises(Exception) as exc_info:
        await bulk_update_alipay_direct_users_payload(
            db=db,
            enabled=True,
            selection_mode="filters",
            filters=AlipayDirectUserFilters(),
        )

    assert getattr(exc_info.value, "status_code", None) == 400
    assert len(db.statements) == 1
    db.commit.assert_not_awaited()
