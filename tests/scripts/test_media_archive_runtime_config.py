import json

import pytest

from scripts.render_media_archive_worker_config import (
    render,
    validate_worker_config,
    write_private_config,
)
from scripts.media_archive_source_health import build_report


def _config():
    return {
        "central_api": "https://central.example",
        "agent_token": "secret",
        "catalog_database_url": "postgresql://catalog",
        "bandwidth_bytes_per_second": 50 * 1024**2,
        "max_spool_bytes": 100 * 1024**3,
        "pause_spool_bytes": 90 * 1024**3,
        "nas": {"name": "nas", "type": "filesystem", "roots": ["/tmp"]},
        "sources": [{"name": "r2-user-data-prod", "type": "filesystem", "roots": ["/tmp"]}],
    }


def test_worker_runtime_renderer_resolves_env_without_printing_values(monkeypatch, tmp_path):
    template = tmp_path / "template.json"
    template.write_text(json.dumps({**_config(), "agent_token": "env:ARCHIVE_TOKEN"}))
    monkeypatch.setenv("ARCHIVE_TOKEN", "top-secret-value")

    config, summary = render(template)
    output = tmp_path / "private/worker.json"
    write_private_config(output, config)

    assert config["agent_token"] == "top-secret-value"
    assert "top-secret-value" not in json.dumps(summary)
    assert output.stat().st_mode & 0o777 == 0o600


def test_worker_runtime_rejects_retired_bucket_and_excess_limits():
    config = _config()
    config["sources"] = [{"name": "r2-user-data", "bucket": "user-data"}]
    with pytest.raises(ValueError, match="retired"):
        validate_worker_config(config)


def test_source_health_reports_offline_without_treating_it_as_not_found(tmp_path):
    config = _config()
    config["sources"].append(
        {"name": "offline-filesystem", "type": "filesystem", "roots": [str(tmp_path / "missing")]}
    )

    report = build_report(config)

    assert report["healthy"] is False
    assert report["offline"] == ["offline-filesystem"]
    assert report["sources"][1]["status"] == "source_offline"
