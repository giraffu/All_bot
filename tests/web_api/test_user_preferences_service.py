from types import SimpleNamespace

import pytest

from src.web_api.services import user_preferences_service


class _FakeDbSession:
    def __init__(self):
        self.executed = []
        self.committed = False

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.committed = True


class _FakeRedis:
    def __init__(self):
        self.calls = []

    async def set(self, key, value):
        self.calls.append((key, value))


@pytest.mark.asyncio
async def test_update_user_language_preference_updates_db_and_syncs_redis(monkeypatch):
    db = _FakeDbSession()
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        user_preferences_service,
        "redis_client",
        SimpleNamespace(redis=fake_redis),
    )

    response = await user_preferences_service.update_user_language_preference(
        db=db,
        user_id=123,
        language_code="en",
    )

    assert len(db.executed) == 1
    assert db.committed is True
    assert fake_redis.calls == [("allbot:user_lang:123", "en")]
    assert response == {"status": "success", "language_code": "en"}


@pytest.mark.asyncio
async def test_update_user_language_preference_skips_redis_when_unavailable(monkeypatch):
    db = _FakeDbSession()
    monkeypatch.setattr(
        user_preferences_service,
        "redis_client",
        SimpleNamespace(redis=None),
    )

    response = await user_preferences_service.update_user_language_preference(
        db=db,
        user_id=456,
        language_code="zh",
    )

    assert len(db.executed) == 1
    assert db.committed is True
    assert response == {"status": "success", "language_code": "zh"}
