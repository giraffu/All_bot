import asyncio
from types import SimpleNamespace

import pytest

from src.services.telegram_update_processor import PerUserUpdateProcessor


def _update(user_id: int, update_id: int):
    return SimpleNamespace(
        update_id=update_id,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=user_id),
    )


@pytest.mark.asyncio
async def test_different_users_can_process_updates_concurrently():
    processor = PerUserUpdateProcessor(max_concurrent_updates=2)
    release = asyncio.Event()
    started = {1: asyncio.Event(), 2: asyncio.Event()}

    async def handle(user_id: int):
        started[user_id].set()
        await release.wait()

    tasks = [
        asyncio.create_task(processor.process_update(_update(1, 1), handle(1))),
        asyncio.create_task(processor.process_update(_update(2, 2), handle(2))),
    ]

    await asyncio.wait_for(started[1].wait(), timeout=1)
    await asyncio.wait_for(started[2].wait(), timeout=1)
    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_same_user_updates_remain_strictly_serial():
    processor = PerUserUpdateProcessor(max_concurrent_updates=2)
    release_first = asyncio.Event()
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def first_handler():
        first_started.set()
        await release_first.wait()

    async def second_handler():
        second_started.set()

    first = asyncio.create_task(
        processor.process_update(_update(7, 1), first_handler())
    )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    second = asyncio.create_task(
        processor.process_update(_update(7, 2), second_handler())
    )

    await asyncio.sleep(0)
    assert not second_started.is_set()

    release_first.set()
    await asyncio.gather(first, second)
    assert second_started.is_set()


@pytest.mark.asyncio
async def test_processor_never_exceeds_global_concurrency_limit():
    processor = PerUserUpdateProcessor(max_concurrent_updates=2)
    release = asyncio.Event()
    started = [asyncio.Event() for _ in range(3)]

    async def handle(index: int):
        started[index].set()
        await release.wait()

    tasks = [
        asyncio.create_task(
            processor.process_update(_update(index + 1, index), handle(index))
        )
        for index in range(3)
    ]

    await asyncio.wait_for(started[0].wait(), timeout=1)
    await asyncio.wait_for(started[1].wait(), timeout=1)
    await asyncio.sleep(0)
    assert not started[2].is_set()

    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_block_later_updates_for_same_user():
    processor = PerUserUpdateProcessor(max_concurrent_updates=3)
    release_first = asyncio.Event()
    first_started = asyncio.Event()
    third_started = asyncio.Event()

    async def first_handler():
        first_started.set()
        await release_first.wait()

    async def waiting_handler():
        raise AssertionError("cancelled update must not start")

    async def third_handler():
        third_started.set()

    first = asyncio.create_task(
        processor.process_update(_update(9, 1), first_handler())
    )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    cancelled = asyncio.create_task(
        processor.process_update(_update(9, 2), waiting_handler())
    )
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    third = asyncio.create_task(
        processor.process_update(_update(9, 3), third_handler())
    )
    release_first.set()
    await asyncio.gather(first, third)
    assert third_started.is_set()


@pytest.mark.asyncio
async def test_one_users_backlog_does_not_starve_another_user():
    processor = PerUserUpdateProcessor(max_concurrent_updates=2)
    release = asyncio.Event()
    first_user_started = asyncio.Event()
    other_user_started = asyncio.Event()

    async def first_user_handler(index: int):
        if index == 0:
            first_user_started.set()
        await release.wait()

    async def other_user_handler():
        other_user_started.set()
        await release.wait()

    backlog = [
        asyncio.create_task(
            processor.process_update(_update(1, index), first_user_handler(index))
        )
        for index in range(8)
    ]
    await asyncio.wait_for(first_user_started.wait(), timeout=1)
    other = asyncio.create_task(
        processor.process_update(_update(2, 99), other_user_handler())
    )

    await asyncio.wait_for(other_user_started.wait(), timeout=1)
    release.set()
    await asyncio.gather(*backlog, other)
