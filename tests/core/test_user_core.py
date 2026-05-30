from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.user_core import get_or_create_user_by_telegram


@pytest.mark.asyncio
async def test_user_core_delegates_to_persistence_service():
    mock_user = SimpleNamespace(id=1, telegram_id=123456)
    persistence_func = AsyncMock(return_value=(mock_user, True))

    with patch(
        "src.core.user_core._get_or_create_user_by_telegram_impl",
        persistence_func,
    ):
        user, is_new = await get_or_create_user_by_telegram(
            123456,
            username="test_user",
            full_name="Test User",
            language_code="zh-CN",
        )

    persistence_func.assert_awaited_once_with(
        tg_id=123456,
        username="test_user",
        full_name="Test User",
        language_code="zh-CN",
    )
    assert user is mock_user
    assert is_new is True
