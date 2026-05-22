from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core import auth_core_dependencies


@pytest.mark.asyncio
async def test_build_auth_core_dependencies_exposes_wrapped_runtime_dependencies(
    monkeypatch,
):
    redis = SimpleNamespace()
    session_factory = lambda: "session"
    get_or_create_user = AsyncMock(return_value=("user", False))
    get_user_detailed_stats = AsyncMock(return_value={"identity": "inner"})
    check_web_access = AsyncMock(return_value=True)

    monkeypatch.setattr(auth_core_dependencies, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(
        auth_core_dependencies,
        "get_or_create_user_by_telegram",
        get_or_create_user,
    )
    monkeypatch.setattr(
        auth_core_dependencies.redis_client,
        "redis",
        redis,
    )
    monkeypatch.setattr(
        auth_core_dependencies.permission_service,
        "get_user_detailed_stats",
        get_user_detailed_stats,
    )
    monkeypatch.setattr(
        auth_core_dependencies.permission_service,
        "check_web_access",
        check_web_access,
    )

    dependencies = auth_core_dependencies.build_auth_core_dependencies()

    assert dependencies.redis is redis
    assert dependencies.session_factory is session_factory

    assert (
        await dependencies.get_or_create_user_by_telegram_func(
            tg_id=42,
            username="tester",
            full_name="Test User",
            language_code="zh-hans",
        )
        == ("user", False)
    )
    assert await dependencies.get_user_detailed_stats_func(42) == {
        "identity": "inner"
    }
    assert await dependencies.check_web_access_func(9) is True

    get_or_create_user.assert_awaited_once_with(
        tg_id=42,
        username="tester",
        full_name="Test User",
        language_code="zh-hans",
    )
    get_user_detailed_stats.assert_awaited_once_with(42)
    check_web_access.assert_awaited_once_with(9)
