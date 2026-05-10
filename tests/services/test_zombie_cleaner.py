import pytest
from unittest.mock import AsyncMock, patch
from src.services.zombie_cleaner_service import clean_zombies


@pytest.mark.asyncio
async def test_clean_zombies_lock_self_healing():
    with patch("src.services.zombie_cleaner_service.redis_client") as mock_redis:
        # Mock active tasks: empty
        mock_redis.get_active_tasks = AsyncMock(return_value={})
        # Mock user concurrencies: user 123 has 1 lock
        mock_redis.get_all_user_concurrencies = AsyncMock(return_value={123: 1})
        mock_redis.decrement_user_concurrency = AsyncMock()

        await clean_zombies()

        # Verify it noticed the deadlock and decremented the lock
        mock_redis.decrement_user_concurrency.assert_called_once_with(123)
