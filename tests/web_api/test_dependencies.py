from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.web_api import dependencies


class _FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeSession:
    def __init__(self, *, execute_result):
        self.execute = AsyncMock(return_value=execute_result)


@pytest.mark.asyncio
async def test_get_current_user_from_session_rejects_blacklisted_password_version(
    monkeypatch,
):
    user = SimpleNamespace(
        id=9,
        telegram_id=42,
        current_identity="outer",
        user_group="outer",
    )
    session = _FakeSession(execute_result=_FakeResult(user))
    redis = SimpleNamespace(get=AsyncMock(return_value="1"))

    monkeypatch.setattr(
        dependencies,
        "verify_token",
        lambda _token: {"sub": "9", "pwd_ver": 3},
    )
    monkeypatch.setattr(
        "src.services.redis_client.redis_client.redis",
        redis,
    )

    with pytest.raises(HTTPException, match="密咒已变更"):
        await dependencies._get_current_user_from_session(session, "token")

    redis.get.assert_awaited_once_with("allbot:auth:blacklist:9:3")
