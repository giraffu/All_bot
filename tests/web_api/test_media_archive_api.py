import pytest
from fastapi import HTTPException

from src.web_api.main import app
from src.web_api.routers.media_archive import require_archive_agent


def test_media_archive_internal_routes_are_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/api/internal/media-archive/jobs", ("GET",)) in routes
    assert ("/api/internal/media-archive/receipts", ("POST",)) in routes
    assert ("/api/internal/media-archive/failures", ("POST",)) in routes


def test_media_archive_agent_auth_fails_closed_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MEDIA_ARCHIVE_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        require_archive_agent("Bearer anything")
    assert error.value.status_code == 503


def test_media_archive_agent_auth_uses_bearer_secret(monkeypatch):
    monkeypatch.setenv("MEDIA_ARCHIVE_AGENT_TOKEN", "archive-secret")
    with pytest.raises(HTTPException) as error:
        require_archive_agent("Bearer wrong")
    assert error.value.status_code == 401
    assert require_archive_agent("Bearer archive-secret") == "archive-secret"
