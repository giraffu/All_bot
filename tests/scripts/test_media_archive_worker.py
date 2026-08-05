import json
from pathlib import Path

import pytest

from scripts.media_archive_worker import (
    AdaptiveConcurrencyController,
    SpoolBudget,
    capacity_claim_priority,
    clear_proxy_environment,
    load_secure_config,
)


def test_worker_config_requires_regular_0600_file_owned_by_current_user(tmp_path: Path):
    config = tmp_path / "worker.json"
    config.write_text(json.dumps({"sources": []}), encoding="utf-8")
    config.chmod(0o644)
    with pytest.raises(PermissionError, match="0600"):
        load_secure_config(config)

    config.chmod(0o600)
    assert load_secure_config(config)["sources"] == []


def test_spool_budget_counts_parts_reserves_and_pauses_at_high_water(tmp_path: Path):
    existing = tmp_path / "old.part"
    existing.write_bytes(b"x" * 60)
    budget = SpoolBudget(tmp_path, capacity_bytes=100, pause_bytes=90)

    assert budget.used_bytes == 60
    budget.reserve(29)
    assert budget.used_bytes == 89
    with pytest.raises(RuntimeError, match="pause threshold"):
        budget.reserve(2)
    budget.release(29)
    assert budget.used_bytes == 60


def test_adaptive_concurrency_only_increases_on_low_error_sustained_window():
    controller = AdaptiveConcurrencyController(
        bandwidth_limit_bps=100,
        window_seconds=900,
        levels=(8, 16, 32),
    )
    assert controller.observe(bytes_transferred=45_000, errors=0, elapsed=900) == 16
    assert controller.observe(bytes_transferred=90_000, errors=2, elapsed=900) == 8


def test_worker_rejects_local_7890_proxy_before_clearing(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    with pytest.raises(RuntimeError, match="7890"):
        clear_proxy_environment()


def test_nas_capacity_gates_stop_cold_then_all_claims():
    assert capacity_claim_priority(archived_bytes=74, capacity_bytes=100) == 100
    assert capacity_claim_priority(archived_bytes=80, capacity_bytes=100) == 0
    assert capacity_claim_priority(archived_bytes=90, capacity_bytes=100) is None
