from pathlib import Path
import json

import pytest

from scripts.run_daily_r2_temp_cleanup import build_args_from_env, validate_canary_evidence
from scripts import run_daily_r2_temp_cleanup as daily


ROOT = Path(__file__).resolve().parents[2]


def test_daily_cleanup_runtime_is_bounded_and_requires_current_inventory(monkeypatch, tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    inventory.touch()
    monkeypatch.setenv("R2_TEMP_CLEANUP_INVENTORY", str(inventory))
    monkeypatch.setenv("R2_TEMP_CLEANUP_DAILY_LIMIT", "99999")
    monkeypatch.setenv("R2_TEMP_CLEANUP_DAILY_MAX_BYTES", str(100 * 1024**3))

    args = build_args_from_env()

    assert args.limit == 10_000
    assert args.max_delete_bytes == 50 * 1024**3
    assert args.min_age_hours >= 24
    assert args.execute is False


def test_daily_cleanup_systemd_contract_keeps_exact_private_gate():
    service = (ROOT / "ops/r2_temp_cleanup/allbot-r2-temp-cleanup.service").read_text()
    example = (ROOT / "ops/r2_temp_cleanup/cleanup.example.env").read_text()

    assert "EnvironmentFile=%h/APP/All_bot/deploy/env.defaults" in service
    assert "EnvironmentFile=%h/.config/allbot/prod.env" in service
    assert "EnvironmentFile=%h/.config/allbot/r2-temp-cleanup/cleanup.env" in service
    assert "ProtectSystem=strict" in service
    assert "R2_TEMP_CLEANUP_ENABLED=false" in example
    assert "R2_TEMP_CLEANUP_AUTOMATION_ENABLED=false" in example
    assert "R2_TEMP_CLEANUP_DAILY_LIMIT=10000" in example
    assert "R2_TEMP_CLEANUP_DAILY_MAX_BYTES=53687091200" in example
    assert "R2_TEMP_CLEANUP_MAX_INVENTORY_AGE_HOURS=36" in example
    runner = (ROOT / "scripts/run_daily_r2_temp_cleanup.py").read_text()
    assert 'replace("cleanup-", "plan-", 1)' in runner
    assert 'report["plan_sha256"]' in runner
    assert 'R2_TEMP_CLEANUP_AUTOMATION_ENABLED' in runner


def test_daily_cleanup_never_automates_from_delete_gate_alone():
    runner = (ROOT / "scripts/run_daily_r2_temp_cleanup.py").read_text()

    assert 'R2_TEMP_CLEANUP_AUTOMATION_ENABLED' in runner
    assert 'automation_enabled and delete_enabled' in runner


def test_cleanup_service_refreshes_inventory_before_planning():
    service = (ROOT / "ops/r2_temp_cleanup/allbot-r2-temp-cleanup.service").read_text()

    assert "ExecStartPre=" in service
    assert "scripts.refresh_r2_temp_cleanup_inventory" in service


def test_cloud_cleanup_service_is_persistent_digest_pinned_and_cloud_only():
    service = (
        ROOT / "ops/r2_temp_cleanup/allbot-r2-temp-cleanup-cloud.service"
    ).read_text()

    assert "Restart=on-failure" in service
    assert "R2_TEMP_CLEANUP_CLOUD_IMAGE" in service
    assert "scripts.r2_temp_cleanup_cloud_coordinator" in service
    assert "/var/lib/allbot/r2-temp-cleanup-cloud/current" in service
    assert "R2_TEMP_CLEANUP_VERIFICATION_CONCURRENCY=16" in service
    assert "HTTP_PROXY=" in service
    assert "HTTPS_PROXY=" in service
    assert "ALL_PROXY=" in service
    assert "ExecStop=-/usr/bin/docker stop --timeout 30 allbot-r2-full-cleanup-cloud" in service
    assert "ExecStopPost=-/usr/bin/docker rm -f allbot-r2-full-cleanup-cloud" in service
    assert "%h" not in service


def test_daily_cleanup_rejects_stale_inventory(monkeypatch, tmp_path):
    inventory = tmp_path / "stale.sqlite3"
    inventory.touch()
    old = inventory.stat().st_mtime - 48 * 3600
    inventory.chmod(0o600)
    import os

    os.utime(inventory, (old, old))
    monkeypatch.setenv("R2_TEMP_CLEANUP_INVENTORY", str(inventory))

    try:
        build_args_from_env()
    except SystemExit as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale inventory must be rejected")


def test_daily_cleanup_stays_dry_run_without_independent_automation_gate(
    monkeypatch, tmp_path, capsys
):
    inventory = tmp_path / "inventory.sqlite3"
    inventory.touch()
    monkeypatch.setenv("R2_TEMP_CLEANUP_INVENTORY", str(inventory))
    monkeypatch.setenv("R2_TEMP_CLEANUP_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("R2_TEMP_CLEANUP_ENABLED", "true")
    monkeypatch.delenv("R2_TEMP_CLEANUP_AUTOMATION_ENABLED", raising=False)
    calls = []

    async def fake_run(args):
        calls.append(args.execute)
        return {
            "plan_sha256": "a" * 64,
            "delete_count": 1,
            "delete_bytes": 2,
            "referenced_blocked_count": 0,
            "probe_failures": [],
        }

    monkeypatch.setattr(daily, "run", fake_run)
    daily.main()

    assert calls == [False]
    assert '"delete_count": 1' in capsys.readouterr().out


def test_daily_cleanup_automation_consumes_the_just_sealed_plan(monkeypatch, tmp_path):
    inventory = tmp_path / "inventory.sqlite3"
    inventory.touch()
    monkeypatch.setenv("R2_TEMP_CLEANUP_INVENTORY", str(inventory))
    monkeypatch.setenv("R2_TEMP_CLEANUP_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("R2_TEMP_CLEANUP_ENABLED", "true")
    monkeypatch.setenv("R2_TEMP_CLEANUP_AUTOMATION_ENABLED", "true")
    monkeypatch.setenv(
        "R2_TEMP_CLEANUP_CONFIRMATION", "DELETE_VERIFIED_TEMP_R2_user-data-prod"
    )
    evidence = tmp_path / "canary-evidence.json"
    evidence.write_text(json.dumps({
        "schema_version": 1,
        "stages": {
            stage: {"status": "completed", "receipt_sha256": "c" * 64}
            for stage in ("100", "1000", "10000")
        },
    }))
    evidence.chmod(0o600)
    monkeypatch.setenv("R2_TEMP_CLEANUP_CANARY_EVIDENCE", str(evidence))
    calls = []

    async def fake_run(args):
        calls.append((args.execute, args.approved_plan, args.plan_sha256, args.confirm))
        return {
            "plan_sha256": "b" * 64,
            "delete_count": 1,
            "delete_bytes": 2,
            "referenced_blocked_count": 0,
            "probe_failures": [],
        }

    monkeypatch.setattr(daily, "run", fake_run)
    daily.main()

    assert calls[0][0] is False
    assert calls[1][0] is True
    assert calls[1][1].endswith("plan-") is False
    assert "/plan-" in calls[1][1]
    assert calls[1][2] == "b" * 64
    assert calls[1][3].endswith(":" + "b" * 64)


def test_daily_cleanup_rejects_missing_or_incomplete_canary_evidence(tmp_path):
    with pytest.raises(SystemExit, match="private canary evidence"):
        validate_canary_evidence("")
    evidence = tmp_path / "canary-evidence.json"
    evidence.write_text(json.dumps({
        "stages": {"100": {"status": "completed", "receipt_sha256": "a" * 64}}
    }))
    evidence.chmod(0o600)
    with pytest.raises(SystemExit, match="canary 1000"):
        validate_canary_evidence(str(evidence))
