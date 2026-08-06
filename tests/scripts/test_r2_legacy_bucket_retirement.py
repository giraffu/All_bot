import sqlite3
import threading
import time

import pytest

from scripts.r2_legacy_bucket_retirement import (
    _copy_batch,
    initialize_state,
    retirement_summary,
    validate_delete_gate,
)


def _inventory(path, rows):
    db = sqlite3.connect(path)
    db.execute(
        "create table objects(key text primary key,size integer,etag text,last_modified text,storage_class text)"
    )
    db.executemany("insert into objects values(?,?,?,?,?)", rows)
    db.commit()
    db.close()


def test_initialize_state_marks_exact_keys_present_and_missing(tmp_path):
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    state = tmp_path / "state.sqlite3"
    _inventory(
        source,
        [
            ("same.png", 10, "a", "2026-01-01", "STANDARD"),
            ("missing.png", 20, "b", "2026-01-01", "STANDARD"),
        ],
    )
    _inventory(
        target,
        [("same.png", 10, "different-etag", "2026-01-01", "STANDARD")],
    )

    initialize_state(state, source, target)
    summary = retirement_summary(state)

    assert summary["total"] == 2
    assert summary["present"] == 1
    assert summary["pending"] == 1
    assert summary["bytes_pending"] == 20


def test_delete_gate_requires_exact_verified_count_and_confirmation():
    validate_delete_gate(
        enabled=True,
        source_bucket="user-data",
        target_bucket="user-data-prod",
        verified=141569,
        total=141569,
        confirmation="DELETE_LEGACY_BUCKET_user-data_141569",
    )
    with pytest.raises(ValueError):
        validate_delete_gate(
            enabled=True,
            source_bucket="user-data",
            target_bucket="user-data-prod",
            verified=141568,
            total=141569,
            confirmation="DELETE_LEGACY_BUCKET_user-data_141569",
        )


def test_legacy_copy_batch_uses_bounded_workers(monkeypatch):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def fake_copy(_client, key, _expected_size):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return {"key": key, "status": "copied"}

    monkeypatch.setattr(
        "scripts.r2_legacy_bucket_retirement._copy_one", fake_copy
    )

    results = _copy_batch(
        object(), [(f"key-{index}", index) for index in range(12)], workers=4
    )

    assert len(results) == 12
    assert 1 < maximum <= 4
