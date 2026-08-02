from unittest.mock import AsyncMock

import pytest

from src.core.task_lifecycle_contract import build_task_terminal_snapshot
from src.services import task_lifecycle_runner


@pytest.mark.asyncio
async def test_run_monitored_task_lifecycle_routes_monitor_result():
    monitor_stage = AsyncMock(return_value={"status": "done"})
    route_stage = AsyncMock(return_value=("ok", "result.png"))

    result = await task_lifecycle_runner.run_monitored_task_lifecycle(
        monitor_stage_func=monitor_stage,
        route_terminal_result_func=route_stage,
    )

    assert result == ("ok", "result.png")
    monitor_stage.assert_awaited_once()
    route_stage.assert_awaited_once_with({"status": "done"})


@pytest.mark.asyncio
async def test_route_backend_terminal_snapshot_prefers_success_when_result_exists():
    success = AsyncMock(return_value="success")
    cancelled = AsyncMock()
    failure = AsyncMock()

    result = await task_lifecycle_runner.route_backend_terminal_snapshot(
        terminal_snapshot=build_task_terminal_snapshot(
            status="done",
            result_path="output.png",
        ),
        handle_success=success,
        handle_cancelled=cancelled,
        handle_failure=failure,
    )

    assert result == "success"
    success.assert_awaited_once()
    cancelled.assert_not_called()
    failure.assert_not_called()


@pytest.mark.asyncio
async def test_route_backend_terminal_snapshot_accepts_text_result_without_path():
    success = AsyncMock(return_value="success")
    failure = AsyncMock()

    result = await task_lifecycle_runner.route_backend_terminal_snapshot(
        terminal_snapshot=build_task_terminal_snapshot(
            status="done",
            result_kind="text",
            result_text="optimized prompt",
            result_meta={"prompt_optimizer": {"profile_ref": "profile@1"}},
        ),
        handle_success=success,
        handle_cancelled=AsyncMock(),
        handle_failure=failure,
    )

    assert result == "success"
    success.assert_awaited_once()
    failure.assert_not_called()


@pytest.mark.asyncio
async def test_route_backend_terminal_snapshot_routes_cancelled_and_failure():
    cancelled = AsyncMock(return_value="cancelled")
    failure = AsyncMock(return_value="failed")

    cancelled_result = await task_lifecycle_runner.route_backend_terminal_snapshot(
        terminal_snapshot=build_task_terminal_snapshot(status="cancelled"),
        handle_success=AsyncMock(),
        handle_cancelled=cancelled,
        handle_failure=AsyncMock(),
    )
    failure_result = await task_lifecycle_runner.route_backend_terminal_snapshot(
        terminal_snapshot=build_task_terminal_snapshot(status="error"),
        handle_success=AsyncMock(),
        handle_cancelled=AsyncMock(),
        handle_failure=failure,
    )

    assert cancelled_result == "cancelled"
    assert failure_result == "failed"
    cancelled.assert_awaited_once()
    failure.assert_awaited_once()
