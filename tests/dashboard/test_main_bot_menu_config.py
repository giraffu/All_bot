from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend import main as dashboard_main
from dashboard.backend.auth import ADMIN_USERNAME, create_access_token
from dashboard.backend.routers import main_bot_menu as main_bot_menu_router
from src.services.main_bot_menu_config_service import (
    MAIN_BOT_MENU_CONFIG_KEY,
    MAIN_MENU_KEYS,
)
from src.services.task_pricing_config_service import TASK_PRICING_CONFIG_KEY


class _Result:
    def __init__(self, checkpoint):
        self._checkpoint = checkpoint

    def scalar_one_or_none(self):
        return self._checkpoint


class _FakeSession:
    def __init__(self, checkpoint=None):
        self.checkpoint = checkpoint
        self.committed = False

    async def execute(self, _stmt):
        return _Result(self.checkpoint)

    def add(self, checkpoint):
        self.checkpoint = checkpoint

    async def commit(self):
        self.committed = True

    async def refresh(self, checkpoint):
        if getattr(checkpoint, "updated_at", None) is None:
            checkpoint.updated_at = None


@pytest.mark.asyncio
async def test_main_bot_menu_config_routes_are_authenticated_and_persist_config():
    fake_db = _FakeSession(
        SimpleNamespace(
            key=MAIN_BOT_MENU_CONFIG_KEY,
            value={"main_menu": {"buttons_per_row": 4, "items": []}},
            updated_at=None,
        )
    )

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[main_bot_menu_router.get_db] = (
        override_get_db
    )
    token = create_access_token({"sub": ADMIN_USERNAME})
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            unauthenticated = await client.get("/api/main-bot/menu-config")
            get_response = await client.get(
                "/api/main-bot/menu-config", headers=headers
            )
            config = get_response.json()["config"]
            config["main_menu"]["items"][0]["visible"] = False
            put_response = await client.put(
                "/api/main-bot/menu-config",
                headers=headers,
                json=config,
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(main_bot_menu_router.get_db, None)

    assert unauthenticated.status_code == 401
    assert get_response.status_code == 200
    assert get_response.json()["key"] == MAIN_BOT_MENU_CONFIG_KEY
    assert get_response.json()["config"]["main_menu"]["buttons_per_row"] == 4
    assert put_response.status_code == 200
    assert put_response.json()["config"]["main_menu"]["items"][0]["visible"] is False
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_main_bot_menu_config_route_rejects_all_hidden_main_items():
    fake_db = _FakeSession()

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[main_bot_menu_router.get_db] = (
        override_get_db
    )
    token = create_access_token({"sub": ADMIN_USERNAME})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                "/api/main-bot/menu-config",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "main_menu": {
                        "buttons_per_row": 3,
                        "items": [
                            {"key": key, "visible": False} for key in MAIN_MENU_KEYS
                        ],
                    },
                    "submenus": {},
                },
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(main_bot_menu_router.get_db, None)

    assert response.status_code == 400
    assert fake_db.committed is False


@pytest.mark.asyncio
async def test_task_pricing_routes_publish_sellable_catalog_and_persist_variants():
    fake_db = _FakeSession()

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[main_bot_menu_router.get_db] = (
        override_get_db
    )
    token = create_access_token({"sub": ADMIN_USERNAME})
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            unauthenticated = await client.get("/api/main-bot/task-pricing")
            get_response = await client.get(
                "/api/main-bot/task-pricing", headers=headers
            )
            categories = get_response.json()["categories"]
            txt2img_variant = next(
                variant["variant_id"]
                for category in categories
                for offer in category["offers"]
                if offer["id"] == "txt2img"
                for variant in offer["variants"]
            )
            put_response = await client.put(
                "/api/main-bot/task-pricing",
                headers=headers,
                json={"schema_version": 2, "prices": {txt2img_variant: 9}},
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(main_bot_menu_router.get_db, None)

    assert unauthenticated.status_code == 401
    assert get_response.status_code == 200
    assert get_response.json()["key"] == TASK_PRICING_CONFIG_KEY
    assert get_response.json()["schema_version"] == 2
    assert len(get_response.json()["categories"]) == 5
    assert "blowjob" not in str(get_response.json()["categories"])
    assert put_response.status_code == 200
    assert put_response.json()["prices"] == {txt2img_variant: 9}
    assert fake_db.committed is True


@pytest.mark.asyncio
async def test_task_pricing_route_rejects_unknown_variant():
    fake_db = _FakeSession()

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[main_bot_menu_router.get_db] = (
        override_get_db
    )
    token = create_access_token({"sub": ADMIN_USERNAME})
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            response = await client.put(
                "/api/main-bot/task-pricing",
                headers={"Authorization": f"Bearer {token}"},
                json={"schema_version": 2, "prices": {"not-a-variant": 5}},
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(main_bot_menu_router.get_db, None)

    assert response.status_code == 400
    assert fake_db.committed is False
