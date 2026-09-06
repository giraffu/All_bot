from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat

import pytest

from scripts.media_archive_r2_cleanup import (
    DELETE_CONFIRMATION,
    PLAN_KIND,
    _build_cleanup_objects,
    _freeze,
    build_argument_parser,
    load_frozen_artifact,
    validate_execute_artifacts,
)


ROOT = Path(__file__).resolve().parents[2]


def test_cleanup_artifact_rejects_tampered_plan(tmp_path):
    plan = _freeze(
        {"kind": PLAN_KIND, "bucket": "user-data-prod", "objects": []},
        "plan_sha256",
    )
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    loaded = load_frozen_artifact(
        path,
        expected_kind=PLAN_KIND,
        hash_field="plan_sha256",
        expected_sha256=plan["plan_sha256"],
    )
    assert loaded == plan

    plan["objects"] = [{"key": "unexpected"}]
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="plan_sha256 mismatch"):
        load_frozen_artifact(
            path,
            expected_kind=PLAN_KIND,
            hash_field="plan_sha256",
            expected_sha256=loaded["plan_sha256"],
        )


def test_execute_requires_fresh_probe_bound_to_exact_plan():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    plan = {"plan_sha256": "a" * 64, "bucket": "user-data-prod"}
    probe = {
        "probe_sha256": "b" * 64,
        "plan_sha256": plan["plan_sha256"],
        "bucket": plan["bucket"],
        "probe_ok": True,
        "failures": [],
        "generated_at": now.isoformat(),
    }
    validate_execute_artifacts(
        plan=plan,
        probe=probe,
        plan_sha256=plan["plan_sha256"],
        probe_sha256=probe["probe_sha256"],
        confirmation=DELETE_CONFIRMATION,
        now=now,
    )

    stale = dict(probe, generated_at=(now - timedelta(hours=2)).isoformat())
    with pytest.raises(ValueError, match="probe is stale"):
        validate_execute_artifacts(
            plan=plan,
            probe=stale,
            plan_sha256=plan["plan_sha256"],
            probe_sha256=probe["probe_sha256"],
            confirmation=DELETE_CONFIRMATION,
            now=now,
        )
    with pytest.raises(ValueError, match="probe does not belong"):
        validate_execute_artifacts(
            plan=plan,
            probe=dict(probe, plan_sha256="c" * 64),
            plan_sha256=plan["plan_sha256"],
            probe_sha256=probe["probe_sha256"],
            confirmation=DELETE_CONFIRMATION,
            now=now,
        )


def test_plan_excludes_keys_that_became_hot():
    rows = [
        (1, "task-1", "source-1", "img2img", "output", 0, "a" * 64, 10, "archive", "blob-1"),
        (2, "task-2", "source-2", "img2img", "output", 0, "b" * 64, 20, "archive", "blob-2"),
    ]
    hot_rows = [("task-2", "img2img", "output", "source-2")]

    def build_keys(task_id, *_args):
        return [f"task-results/{task_id}.png"]

    objects, blocked = _build_cleanup_objects(rows, hot_rows, build_keys)

    assert [item["key"] for item in objects] == ["task-results/task-1.png"]
    assert blocked == ["task-results/task-2.png"]


def test_cli_exposes_only_plan_probe_execute_phases():
    parser = build_argument_parser()
    assert parser.parse_args(["plan", "--output", "plan.json"]).command == "plan"
    with pytest.raises(SystemExit):
        parser.parse_args(["--execute", "--output", "receipt.json"])


def test_cleanup_script_remains_directly_executable():
    mode = (ROOT / "scripts/media_archive_r2_cleanup.py").stat().st_mode

    assert mode & stat.S_IXUSR
