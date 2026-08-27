import logging

import pytest

from src.services.storage import StorageService


class _FakeRowResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.statements = []

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_prune_user_web_history_r2_cache_deletes_only_first_overflow_task(
    monkeypatch,
):
    monkeypatch.setenv("R2_ARCHIVE_DELETE_ENABLED", "true")
    monkeypatch.setenv("R2_ARCHIVE_DELETE_CONFIRMATION", "DELETE_VERIFIED_COLD_R2")
    service = StorageService()
    service.r2_client = object()
    service.r2_bucket = "unit-test-r2"

    session = _FakeSession(
        [
            _FakeRowResult(
                [(77, "old-task", "123/output_images/old.mp4", "custom_video")]
            ),
            _FakeRowResult([True]),
            _FakeRowResult([False]),
        ]
    )

    deleted_keys = []

    async def _fake_delete(keys):
        deleted_keys.extend(keys)
        return len(keys)

    monkeypatch.setattr(
        "src.services.storage.AsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(service, "async_delete_r2_objects", _fake_delete)

    await service.async_prune_user_web_history_r2_cache(user_id=123, keep_recent=2)

    assert set(deleted_keys) == {
        "history/old-task/original.mp4",
        "history/old-task/thumb.jpg",
        "old.mp4",
        "old_thumb.jpg",
    }
    assert len(session.statements) == 3


@pytest.mark.asyncio
async def test_prune_user_web_history_r2_cache_counts_hidden_items_in_recent_window(
    monkeypatch,
):
    monkeypatch.setenv("R2_ARCHIVE_DELETE_ENABLED", "true")
    monkeypatch.setenv("R2_ARCHIVE_DELETE_CONFIRMATION", "DELETE_VERIFIED_COLD_R2")
    service = StorageService()
    service.r2_client = object()
    service.r2_bucket = "unit-test-r2"

    session = _FakeSession(
        [
            _FakeRowResult(
                [(78, "older-visible-task", "123/output_images/older.png", "image")]
            ),
            _FakeRowResult([True]),
            _FakeRowResult([False]),
        ]
    )

    deleted_keys = []

    async def _fake_delete(keys):
        deleted_keys.extend(keys)
        return len(keys)

    monkeypatch.setattr(
        "src.services.storage.AsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(service, "async_delete_r2_objects", _fake_delete)

    await service.async_prune_user_web_history_r2_cache(user_id=123, keep_recent=2)

    assert set(deleted_keys) == {
        "history/older-visible-task/original.png",
        "history/older-visible-task/thumb.webp",
        "older.png",
        "older_thumb.webp",
    }

    recent_sql = str(session.statements[0])
    assert "is_visible" not in recent_sql
    assert "OFFSET" in recent_sql.upper()


@pytest.mark.asyncio
async def test_prune_user_web_history_r2_cache_skips_when_no_overflow_task(
    monkeypatch,
):
    monkeypatch.setenv("R2_ARCHIVE_DELETE_ENABLED", "true")
    monkeypatch.setenv("R2_ARCHIVE_DELETE_CONFIRMATION", "DELETE_VERIFIED_COLD_R2")
    service = StorageService()
    service.r2_client = object()
    service.r2_bucket = "unit-test-r2"

    session = _FakeSession(
        [
            _FakeRowResult([]),
        ]
    )

    deleted_keys = []

    async def _fake_delete(keys):
        deleted_keys.extend(keys)
        return len(keys)

    monkeypatch.setattr(
        "src.services.storage.AsyncSessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(service, "async_delete_r2_objects", _fake_delete)

    await service.async_prune_user_web_history_r2_cache(user_id=123, keep_recent=1)

    assert deleted_keys == []
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_prune_user_web_history_r2_cache_is_fail_closed_by_default(
    monkeypatch,
    caplog,
):
    service = StorageService()
    service.r2_client = object()
    service.r2_bucket = "unit-test-r2"
    monkeypatch.delenv("R2_ARCHIVE_DELETE_ENABLED", raising=False)
    monkeypatch.delenv("R2_ARCHIVE_DELETE_CONFIRMATION", raising=False)
    deleted_keys = []

    async def _fake_delete(keys):
        deleted_keys.extend(keys)
        return len(keys)

    monkeypatch.setattr(service, "async_delete_r2_objects", _fake_delete)
    with caplog.at_level("INFO", logger="src.services.storage_r2_cleanup"):
        await service.async_prune_user_web_history_r2_cache(user_id=123, keep_recent=1)
    assert deleted_keys == []
    assert "123" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.INFO]
