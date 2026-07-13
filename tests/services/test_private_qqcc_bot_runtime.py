import asyncio
from unittest.mock import AsyncMock

import pytest

from src.services.private_qqcc_bot_runtime import (
    private_bot_admission_lock,
    private_bot_has_active_tasks,
    private_bot_operation_lock,
)
from src.services.private_qqcc_bot_runtime import TaskRegistry
from src.services.private_qqcc_bot_service import (
    PrivateBotConflictError,
    PrivateBotServiceError,
)


class _Redis:
    def __init__(self):
        self.value = None
        self.releases = []

    async def set(self, _key, value, *, ex, nx):
        assert ex == 300
        assert nx is True
        if self.value is not None:
            return False
        self.value = value
        return True

    async def eval(self, _script, _key_count, key, lease, *args):
        if args:
            return int(self.value == lease)
        self.releases.append((key, lease))
        if self.value == lease:
            self.value = None
            return 1
        return 0


@pytest.mark.asyncio
async def test_private_bot_operation_lock_serializes_owner_mutations():
    redis = _Redis()

    async with private_bot_operation_lock(42, redis=redis):
        with pytest.raises(PrivateBotConflictError) as exc_info:
            async with private_bot_operation_lock(42, redis=redis):
                pytest.fail("a concurrent owner mutation acquired the same lease")
        assert exc_info.value.code == "operation_in_progress"

    assert redis.value is None
    assert len(redis.releases) == 1


@pytest.mark.asyncio
async def test_private_bot_admission_lock_fences_lifecycle_and_task_submission():
    redis = _Redis()

    async with private_bot_admission_lock(7, redis=redis, wait_seconds=0):
        with pytest.raises(PrivateBotConflictError) as exc_info:
            async with private_bot_admission_lock(7, redis=redis, wait_seconds=0):
                pytest.fail("a concurrent task admission acquired the same lease")
        assert exc_info.value.code == "admission_in_progress"

    assert redis.value is None
    assert len(redis.releases) == 1


@pytest.mark.asyncio
async def test_active_task_check_fails_closed_when_registry_is_unavailable(monkeypatch):
    async def unavailable():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(TaskRegistry, "get_all_tasks_strict", unavailable)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await private_bot_has_active_tasks(7)


@pytest.mark.asyncio
async def test_nonterminal_continuation_keeps_private_application_active(monkeypatch):
    monkeypatch.setattr(
        TaskRegistry,
        "get_all_tasks_strict",
        AsyncMock(return_value={}),
    )
    continuation_check = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "src.services.private_qqcc_bot_runtime.private_bot_has_nonterminal_continuations",
        continuation_check,
    )

    assert await private_bot_has_active_tasks(7) is True
    continuation_check.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_admission_lock_cancels_owner_when_lease_cannot_be_renewed():
    class RenewalLostRedis(_Redis):
        async def eval(self, _script, _key_count, key, lease, *args):
            if args:
                return 0
            return await super().eval(_script, _key_count, key, lease)

    redis = RenewalLostRedis()
    with pytest.raises(PrivateBotServiceError) as exc_info:
        async with private_bot_admission_lock(
            7,
            redis=redis,
            ttl_seconds=1,
        ):
            await asyncio.Event().wait()

    assert exc_info.value.code == "admission_lock_unavailable"
