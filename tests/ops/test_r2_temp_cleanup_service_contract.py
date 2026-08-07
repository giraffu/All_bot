from pathlib import Path

from scripts.run_daily_r2_temp_cleanup import build_args_from_env


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
    assert args.execute is True


def test_daily_cleanup_systemd_contract_keeps_exact_private_gate():
    service = (ROOT / "ops/r2_temp_cleanup/allbot-r2-temp-cleanup.service").read_text()
    example = (ROOT / "ops/r2_temp_cleanup/cleanup.example.env").read_text()

    assert "EnvironmentFile=%h/APP/All_bot/deploy/env.defaults" in service
    assert "EnvironmentFile=%h/.config/allbot/prod.env" in service
    assert "EnvironmentFile=%h/.config/allbot/r2-temp-cleanup/cleanup.env" in service
    assert "ProtectSystem=strict" in service
    assert "R2_TEMP_CLEANUP_ENABLED=false" in example
    assert "R2_TEMP_CLEANUP_DAILY_LIMIT=10000" in example
    assert "R2_TEMP_CLEANUP_DAILY_MAX_BYTES=53687091200" in example
    assert "R2_TEMP_CLEANUP_MAX_INVENTORY_AGE_HOURS=36" in example


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
