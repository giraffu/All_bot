from pathlib import Path
import subprocess
import sys

from scripts.refresh_r2_history_snapshot_analytics import classify_snapshot_state
from scripts.serve_r2_history_snapshot_nas import (
    parse_byte_range,
    safe_remote_object_path,
)


def test_classify_snapshot_state_requires_completed_object_and_verified_batch():
    assert classify_snapshot_state(None, batch_status=None) == "not_backed_up"
    assert classify_snapshot_state({"status": "completed"}, batch_status="copying") == "backing_up"
    assert classify_snapshot_state({"status": "completed"}, batch_status="verified") == "backed_up"
    assert (
        classify_snapshot_state(
            {"status": "failed", "error_http_status": 404, "error_code": "NoSuchKey"},
            batch_status="verified",
        )
        == "file_missing"
    )
    assert (
        classify_snapshot_state(
            {"status": "failed", "error_http_status": 503, "error_code": "SlowDown"},
            batch_status="verified",
        )
        == "backup_failed"
    )


def test_gateway_path_and_range_are_bounded():
    assert safe_remote_object_path("snapshots/batches", 12, "100/output_images/a.mp4") == (
        "snapshots/batches/batch-000012/100/output_images/a.mp4"
    )
    assert parse_byte_range("bytes=10-19", size=100) == (10, 19)
    assert parse_byte_range("bytes=-10", size=100) == (90, 99)


def test_gateway_rejects_path_traversal_and_invalid_ranges():
    for key in ("../secret", "/absolute", "a//b", "a/./b"):
        try:
            safe_remote_object_path("snapshots/batches", 1, key)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe key accepted: {key}")
    for value in ("bytes=-", "bytes=20-10", "items=0-10", "bytes=100-101"):
        try:
            parse_byte_range(value, size=100)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid range accepted: {value}")


def test_refresh_script_can_start_outside_repository(tmp_path):
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "refresh_r2_history_snapshot_analytics.py"
    )
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
