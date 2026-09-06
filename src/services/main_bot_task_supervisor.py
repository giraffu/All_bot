"""Own background tasks created by the main Telegram Bot lifecycle."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


def spawn_main_bot_task(application, coroutine: Coroutine[Any, Any, Any], *, name: str):
    tasks = application.bot_data.setdefault("bg_tasks", set())
    task = asyncio.create_task(coroutine, name=f"main-bot:{name}")
    tasks.add(task)

    def task_done(completed_task: asyncio.Task) -> None:
        tasks.discard(completed_task)
        if completed_task.cancelled():
            return
        exception = completed_task.exception()
        if exception is not None:
            logger.error(
                "Main Bot background task failed task=%s error_type=%s",
                completed_task.get_name(),
                type(exception).__name__,
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )

    task.add_done_callback(task_done)
    return task


async def stop_main_bot_tasks(application) -> None:
    tasks = application.bot_data.setdefault("bg_tasks", set())
    owned_tasks = [task for task in tuple(tasks) if not task.done()]
    for task in owned_tasks:
        task.cancel()
    if owned_tasks:
        results = await asyncio.gather(*owned_tasks, return_exceptions=True)
        for task, result in zip(owned_tasks, results, strict=True):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning(
                    "Main Bot background task failed during shutdown task=%s error=%s",
                    task.get_name(),
                    type(result).__name__,
                )
    tasks.clear()
