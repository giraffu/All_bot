import asyncio

import pytest

from src.services.private_bot_update_admission import (
    PrivateBotUpdateAdmissionScope,
    activate_private_bot_update_scope,
    get_private_bot_submission_cursor,
    mark_private_bot_task_durable,
    track_private_bot_background,
)


@pytest.mark.asyncio
async def test_update_waits_until_background_task_reaches_durable_submission():
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=101)
    release = asyncio.Event()

    async def background():
        await release.wait()
        mark_private_bot_task_durable()
        await asyncio.Event().wait()

    with activate_private_bot_update_scope(scope):
        tracked, admission = track_private_bot_background(background())
        task = asyncio.create_task(tracked)
        assert admission is not None
        admission.task = task

    waiter = asyncio.create_task(scope.wait_until_durable(timeout_seconds=1))
    await asyncio.sleep(0)
    assert waiter.done() is False

    release.set()
    await asyncio.wait_for(waiter, timeout=1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_admission_timeout_fails_without_cancelling_submission_saga():
    scope = PrivateBotUpdateAdmissionScope(private_bot_id=7, update_id=102)
    cancelled = asyncio.Event()

    async def background():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with activate_private_bot_update_scope(scope):
        tracked, admission = track_private_bot_background(background())
        task = asyncio.create_task(tracked)
        assert admission is not None
        admission.task = task

    with pytest.raises(TimeoutError):
        await scope.wait_until_durable(timeout_seconds=0.01)

    assert cancelled.is_set() is False
    assert task.done() is False
    assert scope.failed is True
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def test_submission_cursor_can_resume_at_persisted_sequence():
    scope = PrivateBotUpdateAdmissionScope(
        private_bot_id=9,
        update_id=303,
        _task_sequence=4,
    )

    with activate_private_bot_update_scope(scope):
        cursor = get_private_bot_submission_cursor()
        assert cursor is not None
        assert cursor.private_bot_id == 9
        assert cursor.update_id == 303
        assert cursor.next_sequence == 4
        assert cursor.next_submission_key == "private_bot_update:9:303:4"

        assert scope.next_submission_key() == "private_bot_update:9:303:4"
        assert get_private_bot_submission_cursor().next_sequence == 5

    assert get_private_bot_submission_cursor() is None
