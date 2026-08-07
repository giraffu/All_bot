import json

import pytest
from httpx import ASGITransport, AsyncClient

from local_analytics_platform.app import main as analytics_main
from local_analytics_platform.app.routes_r2_governance import load_governance_status


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def test_governance_status_summarizes_private_evidence_without_object_keys(tmp_path):
    _write(tmp_path / "report-100.json", {
        "batch_id": "batch-1", "mode": "dry-run", "generated_at": "2026-08-07T00:00:00Z",
        "candidate_count": 100, "verified_count": 100, "delete_count": 100,
        "delete_bytes": 123, "referenced_blocked_count": 2,
        "referenced_blocked_bytes": 9, "probe_failures": [],
        "staging": {"object_count": 4, "bytes": 20, "oldest_last_modified": "2026-08-05T00:00:00Z"},
        "inventory": {"object_count": 99, "bytes": 1000, "mtime": 1},
        "legacy_web_uploads_report_only": {"object_count": 3, "bytes": 30},
        "objects": [{"key": "secret-root-key.png"}],
    })
    _write(tmp_path / "central-result-storage-metrics.json", {
        "failure_counts": {
            "durable_copy_failed": 2,
            "legacy_media_completion_rejected": 3,
        }
    })

    result = load_governance_status(tmp_path)

    assert result["latest"]["candidate_count"] == 100
    assert result["latest"]["probe_failure_count"] == 0
    assert "objects" not in result["latest"]
    assert "secret-root-key.png" not in json.dumps(result)
    assert result["staging"]["bytes"] == 20
    assert result["web_uploads_report_only"]["bytes"] == 30
    assert result["alerts"]["inventory_older_than_36h"] is True
    assert result["alerts"]["blocked_bytes_present"] is True
    assert result["persistence_failure_counts"] == {
        "durable_copy_failed": 2,
        "legacy_media_completion_rejected": 3,
    }


@pytest.mark.asyncio
async def test_governance_api_requires_configured_local_login(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_TEMP_CLEANUP_EVIDENCE_ROOT", str(tmp_path))
    monkeypatch.delenv("LOCAL_ANALYTICS_AUTH_ENABLED", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=analytics_main.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/r2-governance/status")

    assert response.status_code == 503
