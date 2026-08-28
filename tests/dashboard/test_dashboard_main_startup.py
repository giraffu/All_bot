from unittest.mock import AsyncMock, MagicMock

import pytest

from dashboard.backend import main as dashboard_main


class _DummyTask:
    def add_done_callback(self, _callback):
        return None


@pytest.mark.asyncio
async def test_startup_event_registers_task_core_providers(monkeypatch):
    init_cache = MagicMock()
    init_db = AsyncMock()
    ensure_providers = MagicMock()
    run_alipay_roster_reconciler = AsyncMock()

    monkeypatch.setattr(dashboard_main.FastAPICache, "init", init_cache)
    monkeypatch.setattr(dashboard_main, "init_db", init_db)
    monkeypatch.setattr(
        dashboard_main,
        "ensure_task_core_service_providers_registered",
        ensure_providers,
    )
    monkeypatch.setattr(
        dashboard_main,
        "run_alipay_direct_roster_reconciler",
        run_alipay_roster_reconciler,
    )

    def fake_create_task(coro):
        coro.close()
        return _DummyTask()

    monkeypatch.setattr(dashboard_main.asyncio, "create_task", fake_create_task)
    dashboard_main.background_tasks.clear()
    dashboard_main.app.state.dashboard_health = {
        "database_ready": False,
        "startup_complete": False,
        "database_error": None,
    }

    await dashboard_main.startup_event()

    ensure_providers.assert_called_once_with()
    run_alipay_roster_reconciler.assert_called_once_with()
    init_db.assert_awaited_once_with()
    assert dashboard_main.app.state.dashboard_health["database_ready"] is True
    assert dashboard_main.app.state.dashboard_health["startup_complete"] is True
