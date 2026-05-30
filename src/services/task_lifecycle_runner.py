from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.core.task_lifecycle_contract import (
    TaskTerminalSnapshot,
    is_backend_cancelled_status,
    is_backend_success_status,
)

T = TypeVar("T")


async def run_monitored_task_lifecycle(
    *,
    monitor_stage_func: Callable[[], Awaitable[object]],
    route_terminal_result_func: Callable[[object], Awaitable[T]],
) -> T:
    terminal_result = await monitor_stage_func()
    return await route_terminal_result_func(terminal_result)


async def route_backend_terminal_snapshot(
    *,
    terminal_snapshot: TaskTerminalSnapshot,
    handle_success: Callable[[TaskTerminalSnapshot], Awaitable[T]],
    handle_cancelled: Callable[[TaskTerminalSnapshot], Awaitable[T]],
    handle_failure: Callable[[TaskTerminalSnapshot], Awaitable[T]],
) -> T:
    if (
        is_backend_success_status(terminal_snapshot.status)
        and terminal_snapshot.result_path
    ):
        return await handle_success(terminal_snapshot)

    if is_backend_cancelled_status(terminal_snapshot.status):
        return await handle_cancelled(terminal_snapshot)

    return await handle_failure(terminal_snapshot)
