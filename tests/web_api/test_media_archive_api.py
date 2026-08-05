import pytest
from fastapi import HTTPException

from src.web_api.main import app
from src.web_api.routers.media_archive import require_archive_agent


def test_media_archive_internal_routes_are_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ("/api/internal/media-archive/jobs", ("GET",)) in routes
    assert ("/api/internal/media-archive/leases/renew", ("POST",)) in routes
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


def test_receipt_contract_records_actual_source_and_candidate_key():
    from src.web_api.routers.media_archive import ReceiptItem

    item = ReceiptItem(
        role="output",
        ordinal=0,
        source_ref="https://example.test/a.png",
        found_source="r2-user-data-prod",
        source_key="history/task-1/a.png",
        sha256="a" * 64,
        byte_size=10,
        nas_bucket="allbot-media-archive-v1",
        nas_key="blobs/sha256/aa/aa/" + "a" * 64 + ".png",
        verified_at="2026-08-05T00:00:00Z",
    )
    assert item.found_source == "r2-user-data-prod"
    assert item.source_key == "history/task-1/a.png"


def test_job_completion_contracts_require_revision():
    from pydantic import ValidationError
    from src.web_api.routers.media_archive import FailureRequest, ReceiptsRequest

    with pytest.raises(ValidationError):
        ReceiptsRequest(history_id=1, worker_id="w", receipts=[])
    with pytest.raises(ValidationError):
        FailureRequest(
            history_id=1,
            worker_id="w",
            error_code="offline",
            message="offline",
        )
