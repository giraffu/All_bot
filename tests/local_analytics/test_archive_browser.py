import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main


@pytest.mark.asyncio
async def test_archive_browser_fails_closed_when_local_login_is_disabled(monkeypatch):
    monkeypatch.delenv("LOCAL_ANALYTICS_AUTH_ENABLED", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/archive/assets/1")

    assert response.status_code == 503
    assert "requires configured" in response.json()["detail"]
