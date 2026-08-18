import asyncio
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from src.services import task_control_worker


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_leased_worker_session_skips_when_another_owner_holds_lease():
    store = AsyncMock()
    store.acquire.return_value = False
    runner = AsyncMock()

    outcome = await task_control_worker.run_leased_worker_session(
        lease_name="web-finalizer",
        runner=runner,
        lease_store=store,
        owner_id="worker-1",
    )

    assert outcome == "not_acquired"
    runner.assert_not_awaited()
    store.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_leased_worker_session_cancels_runner_when_renewal_is_lost():
    store = AsyncMock()
    store.acquire.return_value = True
    store.renew.return_value = False
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def runner():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    outcome = await task_control_worker.run_leased_worker_session(
        lease_name="submission-reconciliation",
        runner=runner,
        lease_store=store,
        owner_id="worker-1",
        renew_interval_seconds=0,
    )

    assert started.is_set()
    assert cancelled.is_set()
    assert outcome == "lease_lost"
    store.release.assert_awaited_once()


def test_task_control_specs_have_independent_leases():
    specs = task_control_worker.build_task_control_specs()

    assert {spec.lease_name for spec in specs} == {
        "submission-reconciliation",
        "web-finalizer",
        "generic-zombie-sweep",
    }
    assert len({spec.lease_name for spec in specs}) == len(specs)


@pytest.mark.asyncio
async def test_disabled_entrypoint_stays_healthy_without_starting_services(monkeypatch):
    from src import task_control_worker as entrypoint

    class FakeServer:
        def close(self):
            return None

        async def wait_closed(self):
            return None

    start_server = AsyncMock(return_value=FakeServer())
    service_runner = AsyncMock()
    stop_event = asyncio.Event()
    stop_event.set()
    monkeypatch.setenv("TASK_CONTROL_WORKER_ENABLED", "false")
    monkeypatch.setattr(entrypoint.asyncio, "start_server", start_server)

    await entrypoint.run_task_control_worker(
        stop_event=stop_event,
        service_runner=service_runner,
    )

    service_runner.assert_not_awaited()
    start_server.assert_awaited_once()


def test_disabled_entrypoint_imports_without_runtime_configuration():
    result = subprocess.run(
        [sys.executable, "-c", "import src.task_control_worker"],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(ROOT),
            "TASK_CONTROL_WORKER_ENABLED": "false",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_task_control_health_payload_does_not_expose_lease_tokens():
    payload = task_control_worker.build_task_control_health_payload(
        enabled=True,
        worker_id="worker-1",
        task_states={"web-finalizer": {"outcome": "not_acquired"}},
    )

    assert payload["status"] == "enabled"
    assert payload["tasks"]["web-finalizer"] == {"outcome": "not_acquired"}
    assert "token" not in str(payload).lower()
