from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.user_persistence_service import (
    _is_legacy_internal_id_adopt_candidate,
    get_or_create_user_by_telegram,
)


@pytest.mark.asyncio
async def test_user_persistence_service_flushes_before_commit():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    class MockAsyncSessionLocal:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    with patch(
        "src.services.user_persistence_service.AsyncSessionLocal",
        MockAsyncSessionLocal,
    ):
        user, is_new = await get_or_create_user_by_telegram(
            123456,
            username="test_user",
            full_name="Test User",
        )

    mock_session.flush.assert_called_once()
    mock_session.commit.assert_called()
    assert is_new is True
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_user_persistence_service_adopts_legacy_internal_id_user():
    legacy_user = MagicMock()
    legacy_user.id = 123456
    legacy_user.telegram_id = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()

    telegram_lookup = MagicMock()
    telegram_lookup.scalar_one_or_none.return_value = None
    legacy_lookup = MagicMock()
    legacy_lookup.scalar_one_or_none.return_value = legacy_user
    mock_session.execute.side_effect = [telegram_lookup, legacy_lookup]

    class MockAsyncSessionLocal:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    with patch(
        "src.services.user_persistence_service.AsyncSessionLocal",
        MockAsyncSessionLocal,
    ):
        user, is_new = await get_or_create_user_by_telegram(123456)

    assert user is legacy_user
    assert is_new is False
    assert legacy_user.telegram_id == 123456
    mock_session.commit.assert_awaited_once()


def test_is_legacy_internal_id_adopt_candidate_only_accepts_unbound_legacy_user():
    user = MagicMock()
    user.id = 123456
    user.telegram_id = None
    assert _is_legacy_internal_id_adopt_candidate(user, tg_id=123456) is True

    user.telegram_id = 999
    assert _is_legacy_internal_id_adopt_candidate(user, tg_id=123456) is False
