import asyncio
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend import auth as dashboard_auth
from dashboard.backend import qqcc_config_auth, qqcc_config_main
from dashboard.backend.routers import qqcc as qqcc_router
from src.database import core as database_core
from src.services.qqcc_config_service import QQCC_LAZY_BOT_CONFIG_KEY


class _Result:
    def __init__(self, checkpoint):
        self._checkpoint = checkpoint

    def scalar_one_or_none(self):
        return self._checkpoint


class _FakeCheckpoint:
    def __init__(self, *, value=None):
        self.key = QQCC_LAZY_BOT_CONFIG_KEY
        self.value = value or {}
        self.updated_at = None


class _FakeSession:
    def __init__(self, checkpoint=None):
        self.checkpoint = checkpoint
        self.added = []
        self.committed = False
        self.refreshed = []

    async def execute(self, _stmt):
        return _Result(self.checkpoint)

    def add(self, checkpoint):
        self.checkpoint = checkpoint
        self.added.append(checkpoint)

    async def commit(self):
        self.committed = True

    async def refresh(self, checkpoint):
        self.refreshed.append(checkpoint)


@pytest.fixture(autouse=True)
def qqcc_config_auth_env(monkeypatch):
    monkeypatch.setenv("QQCC_CONFIG_ADMIN_USERNAME", "qqcc-admin")
    monkeypatch.setenv("QQCC_CONFIG_ADMIN_PASSWORD_HASH", "test-hash")
    monkeypatch.setenv("QQCC_CONFIG_SECRET_KEY", "qqcc-config-test-secret")
    monkeypatch.setattr(
        qqcc_config_auth,
        "verify_password",
        lambda plain_password, _hashed_password: plain_password == "secret",
    )


async def _override_db(fake_db):
    yield fake_db


async def _login(client: AsyncClient) -> str:
    response = await client.post(
        "/api/auth/login",
        data={"username": "qqcc-admin", "password": "secret"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_qqcc_config_startup_only_initializes_database(monkeypatch):
    init_db = AsyncMock()
    monkeypatch.setattr(qqcc_config_main, "init_db", init_db)
    qqcc_config_main.app.state.qqcc_config_health = {
        "database_ready": False,
        "startup_complete": False,
        "database_error": None,
    }

    await qqcc_config_main.startup_event()

    init_db.assert_awaited_once_with()
    assert qqcc_config_main.app.state.qqcc_config_health == {
        "database_ready": True,
        "startup_complete": True,
        "database_error": None,
    }


@pytest.mark.asyncio
async def test_qqcc_config_auth_uses_dedicated_credentials():
    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        bad_response = await client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "secret"},
        )
        token = await _login(client)
        me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert bad_response.status_code == 401
    assert me_response.status_code == 200
    assert me_response.json() == {"username": "qqcc-admin"}


@pytest.mark.asyncio
async def test_qqcc_config_rejects_missing_and_dashboard_tokens():
    dashboard_token = dashboard_auth.create_access_token(
        {"sub": dashboard_auth.ADMIN_USERNAME}
    )

    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        missing_response = await client.get("/api/qqcc/config")
        dashboard_token_response = await client.get(
            "/api/qqcc/config",
            headers={"Authorization": f"Bearer {dashboard_token}"},
        )

    assert missing_response.status_code == 401
    assert dashboard_token_response.status_code == 401


@pytest.mark.asyncio
async def test_qqcc_config_routes_load_and_save_runtime_checkpoint():
    fake_db = _FakeSession(
        _FakeCheckpoint(
            value={
                "global_enabled": True,
                "main_buttons": {"quick_undress": False},
            }
        )
    )

    async def override_get_db():
        async for session in _override_db(fake_db):
            yield session

    qqcc_config_main.app.dependency_overrides[qqcc_router.get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=qqcc_config_main.app),
            base_url="http://testserver",
        ) as client:
            token = await _login(client)
            get_response = await client.get(
                "/api/qqcc/config",
                headers={"Authorization": f"Bearer {token}"},
            )
            put_response = await client.put(
                "/api/qqcc/config",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "global_enabled": False,
                    "main_buttons": {"quick_undress": True, "unknown": True},
                    "main_menu_layout": {
                        "buttons_per_row": 2,
                        "button_order": ["market", "quick_faceswap"],
                    },
                },
            )
    finally:
        qqcc_config_main.app.dependency_overrides.pop(qqcc_router.get_db, None)

    assert get_response.status_code == 200
    assert get_response.json()["key"] == QQCC_LAZY_BOT_CONFIG_KEY
    assert get_response.json()["config"]["main_buttons"]["quick_undress"] is False

    assert put_response.status_code == 200
    saved = put_response.json()
    assert saved["key"] == QQCC_LAZY_BOT_CONFIG_KEY
    assert saved["config"]["global_enabled"] is False
    assert "unknown" not in saved["config"]["main_buttons"]
    assert saved["config"]["main_menu_layout"]["buttons_per_row"] == 2
    assert saved["config"]["main_menu_layout"]["button_order"][:2] == [
        "market",
        "quick_faceswap",
    ]
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_demo_generation_releases_config_session_before_background_monitor(
    monkeypatch,
):
    open_sessions = 0
    monitor_session_counts = []

    class _TrackedSessionContext:
        async def __aenter__(self):
            nonlocal open_sessions
            open_sessions += 1
            return object()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            nonlocal open_sessions
            open_sessions -= 1

    monkeypatch.setattr(
        database_core,
        "AsyncSessionLocal",
        lambda: _TrackedSessionContext(),
    )
    monkeypatch.setattr(
        qqcc_router,
        "load_qqcc_config_payload",
        AsyncMock(return_value={"config": {"video_scenes": []}}),
    )
    monkeypatch.setattr(
        qqcc_router,
        "submit_qqcc_demo_generation",
        AsyncMock(return_value={"generation_id": "task-1", "status": "pending"}),
    )

    async def complete_demo(**_kwargs):
        monitor_session_counts.append(open_sessions)

    monkeypatch.setattr(
        qqcc_router,
        "complete_qqcc_demo_generation",
        complete_demo,
    )

    async with AsyncClient(
        transport=ASGITransport(app=qqcc_config_main.app),
        base_url="http://testserver",
    ) as client:
        token = await _login(client)
        responses = await asyncio.gather(
            *(
                client.post(
                    "/api/qqcc/demo-generation/video",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"scene": {"id": f"scene-{index}"}},
                )
                for index in range(3)
            )
        )

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert monitor_session_counts == [0, 0, 0]
