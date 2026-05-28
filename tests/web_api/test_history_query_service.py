from unittest.mock import AsyncMock

import pytest

from src.web_api.services.history_query_service import fetch_recent_user_history


class _FakeScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return _FakeScalarResult(self._items)


class _CapturingSession:
    def __init__(self, items):
        self._items = list(items)
        self.commit = AsyncMock()
        self.last_stmt = None

    async def execute(self, stmt):
        self.last_stmt = stmt
        return _FakeResult(self._items)


@pytest.mark.asyncio
async def test_fetch_recent_user_history_hides_deleted_rows_without_backfilling_older_items():
    visible_latest = type(
        "HistoryRow",
        (),
        {"task_id": "task-visible-latest", "is_visible": True},
    )()
    hidden_latest = type(
        "HistoryRow",
        (),
        {"task_id": "task-hidden-latest", "is_visible": False},
    )()
    db = _CapturingSession([visible_latest, hidden_latest])

    histories, task_ids = await fetch_recent_user_history(
        db=db,
        current_user_id=123,
        limit=8,
    )

    assert histories == [visible_latest]
    assert task_ids == ["task-visible-latest"]
    assert db.last_stmt is not None

    compiled_sql = str(db.last_stmt)
    assert "history.user_id" in compiled_sql
    assert "history.is_visible = true" not in compiled_sql.lower()
