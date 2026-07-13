from types import SimpleNamespace
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, call, patch

from src.services.zombie_cleaner_service import (
    clean_private_qqcc_zombies,
    clean_zombies,
)


@pytest.mark.asyncio
async def test_clean_zombies_lock_self_healing():
    with (
        patch("src.services.zombie_cleaner_service.time.time", return_value=8000),
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
    ):
        mock_redis.get_active_tasks = AsyncMock(return_value={})
        mock_redis.repair_stale_user_concurrency_acquisitions = AsyncMock(
            return_value=1
        )

        await clean_zombies()

        mock_redis.repair_stale_user_concurrency_acquisitions.assert_awaited_once_with(
            active_registry_task_ids=set(),
            stale_before_timestamp=800,
        )


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
        mock_redis.repair_stale_user_concurrency_acquisitions = AsyncMock(
            return_value=0
        )
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


@pytest.mark.asyncio
async def test_main_zombie_cleaner_does_not_finalize_qqcc_or_private_tasks():
    tasks = {
        "main": {"client_type": "bot", "user_id": 1, "created_at": 0},
        "qqcc": {"client_type": "bot:qqcc", "user_id": 2, "created_at": 0},
        "private": {
            "client_type": "bot:qqcc-private:7",
            "user_id": 3,
            "created_at": 0,
        },
    }
    with (
        patch("src.services.zombie_cleaner_service.time.time", return_value=8000),
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.finalize_zombie_cleanup_for_task_record",
            new_callable=AsyncMock,
        ) as finalize,
    ):
        mock_redis.get_active_tasks = AsyncMock(return_value=tasks)
        mock_redis.repair_stale_user_concurrency_acquisitions = AsyncMock(
            return_value=0
        )
        finalize.return_value = (SimpleNamespace(refunded=True), True)

        await clean_zombies(bot=object(), client_type="bot", include_legacy=True)

    assert finalize.await_count == 1
    assert finalize.await_args.kwargs["registry_task_id"] == "main"


@pytest.mark.asyncio
async def test_unfiltered_manual_cleaner_never_finalizes_private_bot_tasks():
    tasks = {
        "legacy": {"user_id": 1, "created_at": 0},
        "private": {
            "client_type": "bot:qqcc-private:7",
            "user_id": 2,
            "created_at": 0,
        },
    }
    with (
        patch("src.services.zombie_cleaner_service.time.time", return_value=8000),
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.finalize_zombie_cleanup_for_task_record",
            new_callable=AsyncMock,
        ) as finalize,
    ):
        mock_redis.get_active_tasks = AsyncMock(return_value=tasks)
        mock_redis.repair_stale_user_concurrency_acquisitions = AsyncMock(
            return_value=0
        )
        finalize.return_value = (SimpleNamespace(refunded=True), True)

        await clean_zombies()

    assert finalize.await_count == 1
    assert finalize.await_args.kwargs["registry_task_id"] == "legacy"


@pytest.mark.asyncio
async def test_private_zombie_cleaner_routes_through_owning_application():
    tasks = {
        "private-7": {
            "client_type": "bot:qqcc-private:7",
            "user_id": 3,
            "created_at": 0,
        },
        "private-9": {
            "client_type": "bot:qqcc-private:9",
            "user_id": 4,
            "created_at": 7999,
        },
        "official": {"client_type": "bot:qqcc", "user_id": 5, "created_at": 0},
    }
    application = SimpleNamespace(bot=object())
    resolver = AsyncMock(return_value=application)

    @asynccontextmanager
    async def monitor_lease(_registry_task_id):
        yield

    with (
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.finalize_private_bot_submission",
            new_callable=AsyncMock,
        ) as finalize,
        patch(
            "src.services.zombie_cleaner_service.private_bot_task_monitor_lease",
            monitor_lease,
        ),
        patch(
            "src.services.zombie_cleaner_service.private_bot_submission_ledger.get_private_bot_submission_by_registry_task_id",
            new_callable=AsyncMock,
        ) as get_submission,
    ):
        mock_redis.get_active_tasks_strict = AsyncMock(return_value=tasks)
        get_submission.return_value = SimpleNamespace(actual_cost=5)
        finalize.return_value = SimpleNamespace(completed=True)

        count = await clean_private_qqcc_zombies(resolver, now=8000)

    assert count == 1
    resolver.assert_awaited_once_with(7)
    assert finalize.await_args.kwargs["registry_task_id"] == "private-7"


@pytest.mark.asyncio
async def test_private_zombie_does_not_finalize_task_owned_by_live_monitor():
    from src.services.private_bot_task_monitor_lease import (
        PrivateBotTaskMonitorAlreadyOwned,
    )

    @asynccontextmanager
    async def already_owned(_registry_task_id):
        raise PrivateBotTaskMonitorAlreadyOwned("live monitor")
        yield

    resolver = AsyncMock(return_value=SimpleNamespace(bot=object()))
    with (
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.private_bot_task_monitor_lease",
            already_owned,
        ),
        patch(
            "src.services.zombie_cleaner_service.finalize_private_bot_submission",
            new_callable=AsyncMock,
        ) as finalize,
    ):
        mock_redis.get_active_tasks_strict = AsyncMock(
            return_value={
                "private-live": {
                    "client_type": "bot:qqcc-private:7",
                    "user_id": 3,
                    "created_at": 0,
                }
            }
        )

        count = await clean_private_qqcc_zombies(resolver, now=8000)

    assert count == 0
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_zombie_unavailable_tenant_does_not_block_later_tenants():
    @asynccontextmanager
    async def monitor_lease(_registry_task_id):
        yield

    resolver = AsyncMock(
        side_effect=lambda private_bot_id: (
            None if private_bot_id == 7 else SimpleNamespace(bot=object())
        )
    )
    with (
        patch("src.services.zombie_cleaner_service.redis_client") as mock_redis,
        patch(
            "src.services.zombie_cleaner_service.private_bot_task_monitor_lease",
            monitor_lease,
        ),
        patch(
            "src.services.zombie_cleaner_service.private_bot_submission_ledger.get_private_bot_submission_by_registry_task_id",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(actual_cost=5),
        ),
        patch(
            "src.services.zombie_cleaner_service.finalize_private_bot_submission",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(completed=True),
        ) as finalize,
    ):
        mock_redis.get_active_tasks_strict = AsyncMock(
            return_value={
                "tenant-7": {
                    "client_type": "bot:qqcc-private:7",
                    "user_id": 7,
                    "created_at": 0,
                },
                "tenant-9": {
                    "client_type": "bot:qqcc-private:9",
                    "user_id": 9,
                    "created_at": 0,
                },
            }
        )

        count = await clean_private_qqcc_zombies(resolver, now=8000)

    assert count == 1
    assert resolver.await_args_list == [
        call(7),
        call(9),
    ]
    assert finalize.await_args.kwargs["registry_task_id"] == "tenant-9"
