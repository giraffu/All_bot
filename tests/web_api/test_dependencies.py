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


@pytest.mark.asyncio
async def test_get_current_user_from_session_checks_permission_by_internal_user_id(
    monkeypatch,
):
    user = SimpleNamespace(
        id=9,
        telegram_id=42,
        current_identity="outer",
        user_group="outer",
    )
    session = _FakeSession(execute_result=_FakeResult(user))
    stats_mock = AsyncMock(return_value={"identity": "核心弟子", "group": "练气期"})

    monkeypatch.setattr(
        dependencies,
        "verify_token",
        lambda _token: {"sub": "9"},
    )
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats_by_user_id",
        stats_mock,
    )

    result = await dependencies._get_current_user_from_session(session, "token")

    assert result is user
    stats_mock.assert_awaited_once_with(9)


@pytest.mark.asyncio
async def test_get_payment_user_from_session_allows_low_privilege_user(monkeypatch):
    user = SimpleNamespace(
        id=9,
        telegram_id=42,
        current_identity="外门弟子",
        user_group="凡人",
    )
    session = _FakeSession(execute_result=_FakeResult(user))
    stats_mock = AsyncMock()

    monkeypatch.setattr(
        dependencies,
        "verify_token",
        lambda _token: {"sub": "9", "channel": "telegram_payment"},
    )
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats_by_user_id",
        stats_mock,
    )

    result = await dependencies._get_payment_user_from_session(session, "token")

    assert result is user
    stats_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_web_user_still_rejects_low_privilege_payment_user(monkeypatch):
    user = SimpleNamespace(
        id=9,
        telegram_id=42,
        current_identity="外门弟子",
        user_group="凡人",
    )
    session = _FakeSession(execute_result=_FakeResult(user))

    monkeypatch.setattr(
        dependencies,
        "verify_token",
        lambda _token: {"sub": "9", "channel": "telegram_payment"},
    )
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats_by_user_id",
        AsyncMock(return_value={"identity": "外门弟子", "group": "凡人"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependencies._get_current_user_from_session(session, "token")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_current_web_user_rejects_payment_session_even_if_user_has_web_access(
    monkeypatch,
):
    user = SimpleNamespace(
        id=9,
        telegram_id=42,
        current_identity="核心弟子",
        user_group="练气期",
    )
    session = _FakeSession(execute_result=_FakeResult(user))
    stats_mock = AsyncMock(return_value={"identity": "核心弟子", "group": "练气期"})

    monkeypatch.setattr(
        dependencies,
        "verify_token",
        lambda _token: {"sub": "9", "channel": "telegram_payment"},
    )
    monkeypatch.setattr(
        "src.services.permission_service.permission_service.get_user_detailed_stats_by_user_id",
        stats_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependencies._get_current_user_from_session(session, "token")

    assert exc_info.value.status_code == 403
    stats_mock.assert_not_awaited()
