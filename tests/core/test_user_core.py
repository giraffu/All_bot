import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.user_core import get_or_create_user_by_telegram

@pytest.mark.asyncio
async def test_user_core_flush_mechanism():
    # Mock AsyncSessionLocal and its session
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    # Ensure flush is an AsyncMock
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.execute = AsyncMock()
    # Mock scalar_one_or_none to return None initially, triggering creation
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    class MockAsyncSessionLocal:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("src.core.user_core.AsyncSessionLocal", MockAsyncSessionLocal):
        # Using a valid username pattern "test_user"
        user, is_new = await get_or_create_user_by_telegram(123456, username="test_user", full_name="Test User")
        
        # Check if flush was called
        mock_session.flush.assert_called()
        assert is_new is True
        assert user.telegram_id == 123456
