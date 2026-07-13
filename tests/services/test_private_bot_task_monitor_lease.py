import asyncio

import pytest

from src.services.private_bot_task_monitor_lease import (
    PrivateBotTaskMonitorAlreadyOwned,
    PrivateBotTaskMonitorInterrupted,
    private_bot_task_monitor_lease,
)


class _Redis:
    def __init__(self):
        self.values = {}
        self.fail_renewal = False

    async def set(self, key, value, *, ex, nx):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script, _key_count, key, lease, *args):
        if args:
            if self.fail_renewal:
                return 0
            return int(self.values.get(key) == lease)
        if self.values.get(key) == lease:
            self.values.pop(key, None)
            return 1
        return 0


@pytest.mark.asyncio
async def test_task_monitor_lease_has_one_owner_and_releases_safely():
    redis = _Redis()

    async with private_bot_task_monitor_lease("task-1", redis=redis):
        with pytest.raises(PrivateBotTaskMonitorAlreadyOwned):
            async with private_bot_task_monitor_lease("task-1", redis=redis):
                pytest.fail("a second monitor acquired the same task")

    assert redis.values == {}


@pytest.mark.asyncio
async def test_task_monitor_lease_loss_interrupts_monitor_for_recovery():
    redis = _Redis()
    redis.fail_renewal = True

    with pytest.raises(PrivateBotTaskMonitorInterrupted):
        async with private_bot_task_monitor_lease(
            "task-2",
            redis=redis,
            ttl_seconds=1,
            renew_seconds=0.01,
        ):
            await asyncio.Event().wait()
