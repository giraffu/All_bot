import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app import routes_archive


@pytest.mark.asyncio
async def test_archive_browser_fails_closed_when_local_login_is_disabled(monkeypatch):
    monkeypatch.delenv("LOCAL_ANALYTICS_AUTH_ENABLED", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/archive/assets/1")

    assert response.status_code == 503
    assert "requires configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_content_rejects_cloudflare_tunnel_before_database_access(
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_USERNAME", "admin")
    monkeypatch.setenv("LOCAL_ANALYTICS_AUTH_PASSWORD_HASH", "unused")
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/archive/assets/1/content",
            headers={"CF-Ray": "abc-SJC", "CF-Connecting-IP": "203.0.113.2"},
        )

    assert response.status_code == 403
    assert "LAN" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_status_exposes_progress_backlog_capacity_and_alerts(monkeypatch):
    fetchrow = AsyncMock(
        side_effect=[
            {
                "logical_assets": 10,
                "verified_assets": 7,
                "offline_assets": 1,
                "provisional_missing": 1,
                "confirmed_lost": 0,
                "checksum_errors": 1,
                "pending_assets": 0,
            },
            {"blob_count": 6, "archived_bytes": 80},
            {
                "run_type": "archive",
                "status": "running",
                "stats": {"bytes_per_second": 5},
                "error": None,
            },
            {"present": True},
            {
                "backlog": 3,
                "leased": 1,
                "manual_review": 0,
                "oldest_backlog_seconds": 90000,
            },
        ]
    )
    monkeypatch.setattr(routes_archive, "_fetchrow", fetchrow)
    monkeypatch.setattr(routes_archive, "_fetch", AsyncMock(return_value=[]))
    monkeypatch.setenv("NAS_ARCHIVE_CAPACITY_BYTES", "100")

    result = await routes_archive.archive_status()

    assert result["usage_ratio"] == 0.8
    assert result["pause_reason"] == "nas_usage_80_stop_cold"
    assert result["outbox"]["backlog"] == 3
    assert result["alerts"]["checksum_error"] is True
    assert result["alerts"]["archive_critical"] is True
