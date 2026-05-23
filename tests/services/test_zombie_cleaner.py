from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, patch

from src.services.zombie_cleaner_service import clean_zombies


@pytest.mark.asyncio
async def test_clean_zombies_lock_self_healing():
    with (
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.sync_user_concurrency",
            new_callable=AsyncMock,
        ) as sync_user_concurrency,
    ):
        # Mock active tasks: empty
        mock_redis.get_active_tasks = AsyncMock(return_value={})
        # Mock user concurrencies: user 123 has 1 lock
        mock_redis.get_all_user_concurrencies = AsyncMock(return_value={123: 1})

        await clean_zombies()

        # Verify it noticed the deadlock and used the core sync helper
        sync_user_concurrency.assert_awaited_once_with(123, 0)


@pytest.mark.asyncio
async def test_clean_zombies_uses_finalize_task_failure_for_stale_task():
    stale_task = {
        "task-1": {
            "user_id": 123,
            "username": "tester",
            "cost": 5,
            "backend_task_id": "backend-1",
            "chat_id": 456,
            "created_at": 0,
        }
    }

    with (
        patch("src.services.zombie_cleaner_service.time.time", return_value=8000),
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.finalize_zombie_cleanup_for_task_record",
            new_callable=AsyncMock,
        ) as mock_finalize,
        patch(
            "src.services.zombie_cleaner_service.cancel_backend_task_best_effort",
            new_callable=AsyncMock,
        ) as mock_cancel,
    ):
        mock_redis.get_active_tasks = AsyncMock(return_value=stale_task)
        mock_redis.get_all_user_concurrencies = AsyncMock(return_value={})
        mock_finalize.return_value = (
            SimpleNamespace(refunded=True),
            True,
        )

        bot = object()
        await clean_zombies(bot=bot)

        mock_finalize.assert_awaited_once()
        kwargs = mock_finalize.await_args.kwargs
        assert kwargs["registry_task_id"] == "task-1"
        assert kwargs["task_data"] == stale_task["task-1"]
        assert kwargs["bot"] is bot
        mock_cancel.assert_not_awaited()
