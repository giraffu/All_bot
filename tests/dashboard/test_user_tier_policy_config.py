from copy import deepcopy
import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.backend import main as dashboard_main
from dashboard.backend.auth import ADMIN_USERNAME, create_access_token
from dashboard.backend.routers import user_tier_policy as policy_router
from src.services.user_tier_policy_service import (
    DEFAULT_USER_TIER_POLICY_CONFIG,
    USER_TIER_POLICY_CONFIG_KEY,
)


class _Result:
    def __init__(self, checkpoint):
        self.checkpoint = checkpoint

    def scalar_one_or_none(self):
        return self.checkpoint


class _FakeSession:
    def __init__(self):
        self.checkpoint = None
        self.committed = False

    async def execute(self, _stmt):
        return _Result(self.checkpoint)

    def add(self, checkpoint):
        self.checkpoint = checkpoint

    async def commit(self):
        self.committed = True

    async def refresh(self, checkpoint):
        checkpoint.updated_at = None


@pytest.mark.asyncio
async def test_user_tier_policy_routes_require_auth_and_persist_normalized_policy():
    fake_db = _FakeSession()

    async def override_get_db():
        yield fake_db

    dashboard_main.app.dependency_overrides[policy_router.get_db] = override_get_db
    token = create_access_token({"sub": ADMIN_USERNAME})
    payload = deepcopy(DEFAULT_USER_TIER_POLICY_CONFIG)
    payload["cultivation_ranks"]["元婴期"]["benefits"]["flashback_bonus"] = 6
    payload["membership_identities"]["内门弟子"]["benefits"]["concurrent_tasks"] = 6
    try:
        async with AsyncClient(
            transport=ASGITransport(app=dashboard_main.app),
            base_url="http://testserver",
        ) as client:
            unauthenticated = await client.get("/api/user-tier-policy")
            response = await client.put(
                "/api/user-tier-policy",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
    finally:
        dashboard_main.app.dependency_overrides.pop(policy_router.get_db, None)

    assert unauthenticated.status_code == 401
    assert response.status_code == 200
    assert response.json()["key"] == USER_TIER_POLICY_CONFIG_KEY
    assert response.json()["config"]["schema_version"] == 2
    assert response.json()["config"]["flashback_base"] == 5
    assert response.json()["config"]["cultivation_ranks"]["元婴期"]["benefits"]["flashback_bonus"] == 6
    assert fake_db.committed is True
