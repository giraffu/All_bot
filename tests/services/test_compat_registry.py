import json
import logging
from pathlib import Path

from scripts.validate_compat_registry import validate_registry
from src.services.compat_telemetry import get_compat_hit_counts, record_compat_hit


ROOT = Path(__file__).resolve().parents[2]


def test_compat_registry_is_machine_validated():
    assert validate_registry() == []


def test_every_compat_entry_has_an_operational_exit_contract():
    entries = json.loads(
        (ROOT / "config" / "compat_registry.json").read_text(encoding="utf-8")
    )["entries"]

    assert all(entry["owner"] for entry in entries)
    assert all(entry["telemetry_key"].startswith("compat.") for entry in entries)
    assert all(entry["replacement"] for entry in entries)
    assert all(entry["exit_condition"] for entry in entries)
    assert all(entry["historical_data"] for entry in entries)


def test_compat_hit_telemetry_counts_without_user_payload(caplog):
    key = "compat.test.example"
    caplog.set_level(logging.INFO, logger="allbot.compat")
    record_compat_hit(key, entrypoint="test entry")

    assert get_compat_hit_counts()[key] >= 1
    record = next(record for record in caplog.records if record.telemetry_key == key)
    assert record.event == "compat_hit"
    assert record.entrypoint == "test entry"
    assert record.getMessage() == (
        "event=compat_hit telemetry_key=compat.test.example entrypoint=test entry"
    )
