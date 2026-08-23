from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend import main as dashboard_main
from dashboard.backend.auth import ADMIN_USERNAME, create_access_token
from dashboard.backend.routers import feature_entry_visibility as entry_router
from src.services.feature_entry_visibility_service import (
    FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
)


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
async def test_feature_entry_visibility_routes_are_authenticated_and_persist_scopes():
    fake_db = _FakeSession(
        SimpleNamespace(
            key=FEATURE_ENTRY_VISIBILITY_CONFIG_KEY,
            value={
                "web": {
                    "ltx_video": True,
                    "minimax_h3": False,
                    "character_assets": False,
                },
                "gallery": {"minimax_h3": False},
            },
            updated_at=None,
        )
    )

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[entry_router.get_db] = override_get_db
    token = create_access_token({"sub": ADMIN_USERNAME})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "web": {
            "ltx_video": True,
            "minimax_h3": True,
            "character_assets": False,
        },
        "gallery": {"minimax_h3": False},
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            unauthenticated = await client.get("/api/entry-visibility")
            response = await client.put(
                "/api/entry-visibility",
                headers=headers,
                json=payload,
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(entry_router.get_db, None)

    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert response.json()["config"] == payload
    assert fake_db.committed is True
