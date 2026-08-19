import asyncio
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import billing_reconciler


ROOT = Path(__file__).resolve().parents[2]


def test_build_runners_keeps_ton_and_usdt_independent(monkeypatch):
    ton = SimpleNamespace(poll_transactions=AsyncMock())
    usdt = SimpleNamespace(poll_transactions=AsyncMock())
    monkeypatch.setattr(
        billing_reconciler,
        "build_ton_payment_validator_if_available",
        lambda app: ton,
    )
    monkeypatch.setattr(
        billing_reconciler,
        "build_usdt_ton_payment_validator_if_available",
        lambda app: usdt,
    )

    specs = billing_reconciler.build_billing_reconciler_specs(object())

    assert {spec.name for spec in specs} == {"ton", "usdt-ton"}
    assert {spec.runner for spec in specs} == {
        ton.poll_transactions,
        usdt.poll_transactions,
    }


def test_main_bot_payment_polling_host_stays_enabled_by_default(monkeypatch):
    from src import bot_main

    monkeypatch.delenv("MAIN_BOT_PAYMENT_POLLING_ENABLED", raising=False)
    assert bot_main._env_enabled("MAIN_BOT_PAYMENT_POLLING_ENABLED", default=True)

    monkeypatch.setenv("MAIN_BOT_PAYMENT_POLLING_ENABLED", "false")
    assert not bot_main._env_enabled(
        "MAIN_BOT_PAYMENT_POLLING_ENABLED",
        default=True,
    )


@pytest.mark.asyncio
async def test_supervisor_restarts_only_failed_channel(monkeypatch):
    attempts = 0
    stop = asyncio.Event()

    async def runner():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        stop.set()

    monkeypatch.setattr(billing_reconciler, "RESTART_DELAY_SECONDS", 0)
    states = {}
    await billing_reconciler.run_billing_channel_supervisor(
        billing_reconciler.BillingReconcilerSpec("ton", runner),
        task_states=states,
        stop_event=stop,
    )

    assert attempts == 2
    assert states["ton"]["restarts"] == 1
    assert states["ton"]["outcome"] == "stopped"


@pytest.mark.asyncio
async def test_disabled_entrypoint_does_not_initialize_payment_runtime(monkeypatch):
    from src import billing_reconciler as entrypoint

    class FakeServer:
        def close(self):
            return None

        async def wait_closed(self):
            return None

    stop = asyncio.Event()
    stop.set()
    runner = AsyncMock()
    monkeypatch.setenv("BILLING_RECONCILER_ENABLED", "false")
    monkeypatch.setattr(
        entrypoint.asyncio,
        "start_server",
        AsyncMock(return_value=FakeServer()),
    )
    monkeypatch.setattr(
        entrypoint,
        "build_notification_application",
        lambda _token: pytest.fail("disabled worker built Telegram application"),
    )

    await entrypoint.run_billing_reconciler_worker(
        stop_event=stop,
        reconciler_runner=runner,
    )

    runner.assert_not_awaited()


def test_disabled_entrypoint_imports_without_runtime_configuration():
    result = subprocess.run(
        [sys.executable, "-c", "import src.billing_reconciler"],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(ROOT),
            "BILLING_RECONCILER_ENABLED": "false",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_billing_provider_import_does_not_initialize_storage_without_minio():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    for key in tuple(env):
        if key.startswith("MINIO_"):
            env.pop(key)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import src.billing_core_provider_setup; "
                "assert 'src.services.storage' not in sys.modules"
            ),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
