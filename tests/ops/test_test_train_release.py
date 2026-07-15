import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "test_train_release.py"
SHA = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location("test_train_release", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_state_requires_all_smoke_checks(tmp_path):
    module = _load_module()
    state_root = tmp_path / "state"
    coordinator = module.TestTrainCoordinator(state_root=state_root)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "sha": SHA,
                "pr": 42,
                "slot": "A",
                "tested_by": "integration-ai",
                "started_at": "2026-07-15T10:00:00+00:00",
                "completed_at": "2026-07-15T10:10:00+00:00",
                "tracks": ["control-plane"],
                "modules": ["web-api"],
                "smoke": {"health": True, "task": False},
            }
        ),
        encoding="utf-8",
    )
    coordinator.record_deployed(SHA, pr=42, slot="A", tracks=["control-plane"])

    with pytest.raises(module.TestTrainError, match="smoke"):
        coordinator.accept(SHA, evidence)

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["smoke"]["task"] = True
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    coordinator.accept(SHA, evidence)
    assert coordinator.status()["status"] == "accepted"


def test_block_preserves_failed_candidate_for_forward_fix(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")

    coordinator.record_deployed(SHA, pr=42, slot="B", tracks=["control-plane"])
    coordinator.block(SHA, "manual smoke failed")

    state = coordinator.status()
    assert state["status"] == "blocked"
    assert state["sha"] == SHA
    assert state["reason"] == "manual smoke failed"


def test_blocked_train_rejects_an_unrelated_candidate(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()

    coordinator.record_deployed(SHA, pr=42, slot="B", tracks=["control-plane"])
    coordinator.block(SHA, "manual smoke failed")

    with pytest.raises(module.TestTrainError, match="forward-fix"):
        coordinator.deploy_candidate("e" * 40, pr=43, slot="C", runner=runner)

    assert runner.events == []

    coordinator.deploy_candidate("e" * 40, pr=44, slot="B", runner=runner)
    assert coordinator.status()["sha"] == "e" * 40


def test_nonblocking_lock_rejects_a_second_integrator(tmp_path):
    module = _load_module()
    state_root = tmp_path / "allbot" / "test-train"
    first = module.TestTrainCoordinator(state_root=state_root)
    second = module.TestTrainCoordinator(state_root=state_root)

    with first.acquire_lock():
        assert first.lock_path == tmp_path / "allbot" / "test-train.lock"
        with pytest.raises(module.TestTrainError, match="locked"):
            with second.acquire_lock():
                pass


class _FakeReleaseRunner:
    def __init__(self, *, fail_track=None, gpu=False):
        self.fail_track = fail_track
        self.events = []
        self.plans = {
            "control-plane": {
                "track": "control-plane",
                "previous_sha": "b" * 40,
                "artifacts": {"web-api": {}},
            },
            "test-execution": {
                "track": "test-execution",
                "previous_sha": "c" * 40,
                "artifacts": {"worker-agent": {}},
            },
            "gpu-execution": {
                "track": "gpu-execution",
                "previous_sha": "d" * 40,
                "artifacts": {"i2i_pro": {}} if gpu else {},
            },
        }

    def plan(self, sha, track):
        self.events.append(("plan", track, sha))
        return self.plans[track]

    def preflight(self, sha, track):
        self.events.append(("preflight", track, sha))

    def deploy(self, sha, track):
        self.events.append(("deploy", track, sha))
        if track == self.fail_track:
            raise RuntimeError("deploy failed")

    def rollback(self, sha, track):
        self.events.append(("rollback", track, sha))


def test_deploy_orders_tracks_and_records_candidate(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()

    coordinator.deploy_candidate(SHA, pr=42, slot="C", runner=runner)

    mutations = [event[:2] for event in runner.events if event[0] != "plan"]
    assert mutations == [
        ("preflight", "control-plane"),
        ("deploy", "control-plane"),
        ("preflight", "test-execution"),
        ("deploy", "test-execution"),
    ]
    assert coordinator.status()["status"] == "deployed"


def test_later_track_failure_rolls_back_completed_track_in_reverse(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner(fail_track="test-execution")

    with pytest.raises(module.TestTrainError, match="recovered"):
        coordinator.deploy_candidate(SHA, pr=42, slot="D", runner=runner)

    assert runner.events[-1] == ("rollback", "control-plane", "b" * 40)


def test_gpu_candidate_is_planned_but_never_mutated(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner(gpu=True)

    with pytest.raises(module.TestTrainError, match="GPU"):
        coordinator.deploy_candidate(SHA, pr=42, slot="A", runner=runner)

    assert not any(event[0] in {"preflight", "deploy"} for event in runner.events)


def test_release_runner_finds_nested_oras_v2_manifest(tmp_path):
    module = _load_module()
    cache = tmp_path / "cache"
    manifest = cache / SHA / "release-v2" / "release-index.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    runner = module.ReleaseCLI(repo=ROOT, bundle_cache=cache)

    assert runner._manifest_path(SHA) == manifest


def test_release_runner_keeps_an_unavailable_gpu_track_as_a_read_only_plan(
    tmp_path, monkeypatch
):
    module = _load_module()
    runner = module.ReleaseCLI(repo=ROOT, bundle_cache=tmp_path / "cache")

    def unavailable(_args):
        raise module.TestTrainError(
            "ERROR: gpu-execution track has no available artifacts"
        )

    monkeypatch.setattr(runner, "_run", unavailable)

    plan = runner.plan(SHA, "gpu-execution")

    assert plan == {
        "track": "gpu-execution",
        "artifacts": {},
        "services": [],
        "availability": "unavailable",
        "reason": "gpu-execution track has no available artifacts",
    }


def test_release_runner_does_not_hide_other_plan_failures(tmp_path, monkeypatch):
    module = _load_module()
    runner = module.ReleaseCLI(repo=ROOT, bundle_cache=tmp_path / "cache")

    def failed(_args):
        raise module.TestTrainError("candidate provenance is invalid")

    monkeypatch.setattr(runner, "_run", failed)

    with pytest.raises(module.TestTrainError, match="provenance"):
        runner.plan(SHA, "gpu-execution")
