import asyncio
import inspect
import sqlite3
import threading
import time

import pytest

from scripts.r2_temp_cleanup import (
    Candidate,
    _eligible_candidates,
    _verify_candidates,
    _matching_refs,
    select_duplicate_candidates,
    validate_delete_gate,
    _history_references,
    _apply_delete_byte_cap,
)


def _inventory():
    db = sqlite3.connect(":memory:")
    db.execute(
        "create table objects(key text primary key,size integer,etag text,last_modified text)"
    )
    db.executemany(
        "insert into objects values(?,?,?,?)",
        [
            ("12345678-1234-1234-1234-123456789abc__raw.png", 10, "same", "2026-08-01T00:00:00Z"),
            ("42/output_images/raw.png", 10, "same", "2026-08-01T00:01:00Z"),
            ("only-root.png", 9, "unique", "2026-08-01T00:00:00Z"),
            ("temps/template.png", 10, "same", "2026-08-01T00:00:00Z"),
            ("young.png", 10, "young", "2026-08-06T12:00:00Z"),
            ("task-results/t/primary.png", 10, "young", "2026-08-06T12:00:00Z"),
        ],
    )
    return db


def test_selects_only_old_root_objects_with_a_durable_signature_twin():
    rows = select_duplicate_candidates(
        _inventory(), cutoff="2026-08-05T00:00:00Z", limit=100
    )
    assert [(row.key, row.durable_key) for row in rows] == [
        ("12345678-1234-1234-1234-123456789abc__raw.png", "42/output_images/raw.png")
    ]


def test_active_task_reference_matching_walks_nested_registry_payloads():
    key = "12345678-1234-1234-1234-123456789abc__raw.png"
    assert _matching_refs(
        {"task": {"saved_input_images": [f"user-data-prod/{key}"]}},
        {key, "unrelated.png"},
    ) == {key}


def test_business_references_block_an_otherwise_verified_duplicate():
    candidate = Candidate(
        key="12345678-1234-1234-1234-123456789abc__raw.png",
        durable_key="task-results/task/primary.png",
        byte_size=10,
        etag="same",
        last_modified="2026-08-01T00:00:00Z",
    )
    eligible, blocked = _eligible_candidates(
        [candidate],
        set(),
        set(),
        {candidate.key},
    )
    assert eligible == []
    assert blocked == {candidate.key}


def test_history_reference_query_scans_each_history_role_once():
    source = inspect.getsource(_history_references)
    assert "regexp_replace" in source
    assert "like '%/'||candidate.key" not in source


def test_temp_delete_gate_is_bucket_and_confirmation_scoped():
    validate_delete_gate(
        bucket="user-data-prod",
        enabled=True,
        confirmation="DELETE_VERIFIED_TEMP_R2_user-data-prod",
    )
    with pytest.raises(ValueError):
        validate_delete_gate(
            bucket="user-data",
            enabled=True,
            confirmation="DELETE_VERIFIED_TEMP_R2_user-data",
        )


def test_sha_verification_uses_bounded_parallel_reads(monkeypatch):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def fake_sha256(_client, _bucket, _key):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return "same"

    monkeypatch.setattr("scripts.r2_temp_cleanup._sha256_object", fake_sha256)
    candidates = [
        Candidate(
            key=f"source-{index}",
            durable_key=f"durable-{index}",
            byte_size=10,
            etag="same",
            last_modified="2026-08-01T00:00:00Z",
        )
        for index in range(8)
    ]

    verified, failures = asyncio.run(
        _verify_candidates(object(), "user-data-prod", candidates, concurrency=3)
    )

    assert len(verified) == 8
    assert failures == []
    assert 1 < maximum <= 3


def test_daily_delete_byte_cap_stops_before_crossing_limit():
    verified = [
        {"key": "one", "byte_size": 30},
        {"key": "two", "byte_size": 25},
        {"key": "three", "byte_size": 10},
    ]

    selected, blocked = _apply_delete_byte_cap(verified, max_bytes=50)

    assert [item["key"] for item in selected] == ["one"]
    assert [item["key"] for item in blocked] == ["two", "three"]
    assert sum(item["byte_size"] for item in selected) == 30
