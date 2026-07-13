from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import language_runtime_service
from src.web_api.services.user_task_api_service import (
    update_user_language_preference_payload,
)


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
async def test_update_user_language_preference_updates_db_and_syncs_redis():
    db = _FakeDbSession()
    fake_redis = _FakeRedis()

    normalized_lang = await language_runtime_service.persist_user_language_preference(
        db=db,
        internal_user_id=123,
        telegram_user_id=789,
        language_code="en-US",
        redis_client_obj=SimpleNamespace(redis=fake_redis),
    )

    assert len(db.executed) == 1
    assert db.committed is True
    assert fake_redis.calls == [
        ("allbot:user_lang:123", "en"),
        ("allbot:user_lang:tg:789", "en"),
    ]
    assert normalized_lang == "en"


@pytest.mark.asyncio
async def test_update_user_language_preference_skips_redis_when_unavailable():
    db = _FakeDbSession()

    normalized_lang = await language_runtime_service.persist_user_language_preference(
        db=db,
        internal_user_id=456,
        telegram_user_id=None,
        language_code="zh-CN",
        redis_client_obj=SimpleNamespace(redis=None),
    )

    assert len(db.executed) == 1
    assert db.committed is True
    assert normalized_lang == "zh"


@pytest.mark.asyncio
async def test_router_update_user_language_preference_delegates_with_telegram_id():
    service_fn = AsyncMock(return_value="en")
    db = _FakeDbSession()

    response = await update_user_language_preference_payload(
        db=db,
        user_id=321,
        telegram_user_id=654321,
        language_code="en",
        persist_language_fn=service_fn,
    )

    assert response == {"status": "success", "language_code": "en"}
    service_fn.assert_awaited_once_with(
        db=db,
        internal_user_id=321,
        telegram_user_id=654321,
        language_code="en",
    )
