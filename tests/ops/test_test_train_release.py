import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess

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


class _FakePromotionProvider:
    def __init__(self):
        self.runtime_state = {
            "schema_version": 2,
            "track": "control-plane",
            "artifacts": {
                "web-api": {"digest": "sha256:" + "1" * 64},
            },
        }
        runtime_payload = json.dumps(
            self.runtime_state, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.runtime_digest = "sha256:" + hashlib.sha256(runtime_payload).hexdigest()
        self.snapshot = {
            "schema_version": 1,
            "candidate_sha": SHA,
            "candidate_bundle_digest": "sha256:" + "2" * 64,
            "artifacts": {
                "web-api": {
                    "digest": "sha256:" + "1" * 64,
                    "source_sha": SHA,
                },
                "dashboard-backend": {
                    "digest": "sha256:" + "3" * 64,
                    "source_sha": SHA,
                },
            },
        }
        self.published = []

    def candidate_snapshot(self, sha):
        assert sha == SHA
        return self.snapshot

    def test_runtime_state(self):
        return self.runtime_state

    def publish_approval(self, sha, path):
        self.published.append((sha, json.loads(path.read_text(encoding="utf-8"))))
        return f"ghcr.io/giraffu/allbot-release-v2-promotions:{sha}"


def _record_accepted(coordinator):
    coordinator._write_state(
        {
            "status": "accepted",
            "sha": SHA,
            "pr": 42,
            "slot": "A",
            "tracks": ["control-plane"],
        }
    )


def _release_evidence(provider, tmp_path):
    evidence = {
        "schema_version": 1,
        "candidate_sha": SHA,
        "candidate_bundle_digest": "sha256:" + "2" * 64,
        "test_runtime_state_digest": provider.runtime_digest,
        "started_at": "2026-07-18T00:00:00+00:00",
        "completed_at": "2026-07-18T01:00:00+00:00",
        "checks": {
            "combination_tests": True,
            "health": True,
            "rollback_drill": True,
            "manual_acceptance": True,
        },
        "artifacts": {
            "web-api": {
                "digest": "sha256:" + "1" * 64,
                "source_sha": SHA,
                "status": "verified",
                "evidence_source": "cloud-test/control-plane/current.json",
            },
            "dashboard-backend": {
                "digest": "sha256:" + "3" * 64,
                "source_sha": SHA,
                "status": "approved-direct",
                "evidence_source": "owner-tools-direct-policy",
            },
        },
    }
    path = tmp_path / "release-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


def test_freeze_locks_the_accepted_candidate_and_abort_restores_it(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    provider = _FakePromotionProvider()
    _record_accepted(coordinator)

    coordinator.freeze(SHA, provider=provider)

    assert coordinator.status()["status"] == "frozen"
    assert coordinator.status()["frozen"]["candidate_bundle_digest"].startswith(
        "sha256:"
    )
    assert coordinator.status()["frozen"]["test_runtime_state_digest"] == (
        provider.runtime_digest
    )
    with pytest.raises(module.TestTrainError, match="frozen"):
        coordinator.deploy_candidate("e" * 40, pr=43, slot="B", runner=_FakeReleaseRunner())
    with pytest.raises(module.TestTrainError, match="frozen"):
        coordinator.block(SHA, "must not rewrite frozen state")

    coordinator.abort_freeze()
    assert coordinator.status()["status"] == "accepted"


def test_release_approval_publishes_exact_frozen_artifacts(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    provider = _FakePromotionProvider()
    _record_accepted(coordinator)
    coordinator.freeze(SHA, provider=provider)

    coordinator.approve_release(
        SHA,
        _release_evidence(provider, tmp_path),
        approved_by="operator",
        provider=provider,
    )

    state = coordinator.status()
    assert state["status"] == "release-approved"
    assert state["approval_ref"].endswith(SHA)
    assert provider.published[0][1]["artifacts"]["web-api"]["status"] == "verified"


def test_release_approval_rejects_verified_digest_not_running_in_test(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    provider = _FakePromotionProvider()
    _record_accepted(coordinator)
    coordinator.freeze(SHA, provider=provider)
    evidence_path = _release_evidence(provider, tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["artifacts"]["web-api"]["digest"] = "sha256:" + "f" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(module.TestTrainError, match="web-api"):
        coordinator.approve_release(
            SHA,
            evidence_path,
            approved_by="operator",
            provider=provider,
        )


def test_deploy_orders_tracks_and_records_candidate(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()

    coordinator.deploy_candidate(SHA, pr=42, slot="C", runner=runner)

    mutations = [event[:2] for event in runner.events if event[0] != "plan"]
    assert mutations == [
        ("preflight", "control-plane"),
        ("deploy", "control-plane"),
    ]
    assert coordinator.status()["status"] == "deployed"


def test_expanded_workspace_slot_can_flow_through_test_train_audit(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()

    coordinator.deploy_candidate(SHA, pr=42, slot="H", runner=runner)

    assert coordinator.status()["slot"] == "H"


def test_deploy_can_explicitly_include_test_execution_for_a_diagnostic_window(
    tmp_path,
):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()

    coordinator.deploy_candidate(
        SHA,
        pr=42,
        slot="A",
        runner=runner,
        with_test_execution=True,
    )

    mutations = [event[:2] for event in runner.events if event[0] != "plan"]
    assert mutations == [
        ("preflight", "control-plane"),
        ("deploy", "control-plane"),
        ("preflight", "test-execution"),
        ("deploy", "test-execution"),
    ]
    assert coordinator.status()["tracks"] == ["control-plane", "test-execution"]


def test_owner_tools_candidate_is_ready_without_mutating_shared_test(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()
    runner.plans["control-plane"] = {
        "track": "control-plane",
        "previous_sha": "b" * 40,
        "level": "rolling",
        "risk_class": "owner-tools",
        "strategy": "direct",
        "test_required": False,
        "artifacts": {"dashboard-backend": {}},
        "services": ["dashboard-backend"],
    }

    coordinator.deploy_candidate(SHA, pr=42, slot="A", runner=runner)

    assert not any(
        event[0] in {"preflight", "deploy", "rollback"} for event in runner.events
    )
    state = coordinator.status()
    assert state["status"] == "ready-for-acceptance"
    assert state["deployment_mode"] == "test-not-required"


@pytest.mark.parametrize("level", ["none", "maintenance"])
def test_non_runtime_control_plane_can_be_accepted_without_fake_deployment(
    tmp_path, level
):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner()
    runner.plans["control-plane"] = {
        "track": "control-plane",
        "previous_sha": "b" * 40,
        "level": level,
        "matched_rules": ["non-runtime", "track:control-plane"],
        "artifacts": {},
        "services": [],
    }

    coordinator.deploy_candidate(
        SHA,
        pr=42,
        slot="A",
        runner=runner,
    )

    assert not any(
        event[0] in {"preflight", "deploy", "rollback"}
        for event in runner.events
    )
    assert coordinator.status() == {
        "status": "ready-for-acceptance",
        "sha": SHA,
        "pr": 42,
        "slot": "A",
        "tracks": ["control-plane"],
        "deployment_mode": "non-runtime",
        "deferred_tracks": ["test-execution"],
        "updated_at": coordinator.status()["updated_at"],
    }

    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "sha": SHA,
                "pr": 42,
                "slot": "A",
                "tested_by": "integration-ai",
                "started_at": "2026-07-16T10:00:00+00:00",
                "completed_at": "2026-07-16T10:01:00+00:00",
                "tracks": ["control-plane"],
                "modules": [],
                "smoke": {
                    "candidate_bundle_published": True,
                    "control_plane_plan_is_non_runtime": True,
                    "test_execution_deferred": True,
                },
            }
        ),
        encoding="utf-8",
    )

    coordinator.accept(SHA, evidence)
    assert coordinator.status()["status"] == "accepted"


def test_deploy_cli_requires_an_explicit_flag_to_include_test_execution():
    module = _load_module()

    default_args = module.build_parser().parse_args(
        ["deploy", "--sha", SHA, "--pr", "42", "--slot", "A", "--execute"]
    )
    worker_args = module.build_parser().parse_args(
        [
            "deploy",
            "--sha",
            SHA,
            "--pr",
            "42",
            "--slot",
            "A",
            "--execute",
            "--with-test-execution",
        ]
    )

    assert default_args.with_test_execution is False
    assert worker_args.with_test_execution is True


def test_later_track_failure_rolls_back_completed_track_in_reverse(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner(fail_track="test-execution")

    with pytest.raises(module.TestTrainError, match="recovered"):
        coordinator.deploy_candidate(
            SHA,
            pr=42,
            slot="D",
            runner=runner,
            with_test_execution=True,
        )

    assert runner.events[-1] == ("rollback", "control-plane", "b" * 40)


def test_later_track_failure_preserves_original_error_after_recovery(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner(fail_track="test-execution")

    with pytest.raises(
        module.TestTrainError,
        match="completed tracks were recovered: deploy failed",
    ):
        coordinator.deploy_candidate(
            SHA,
            pr=42,
            slot="D",
            runner=runner,
            with_test_execution=True,
        )


def test_gpu_candidate_is_planned_but_does_not_block_control_plane_test(tmp_path):
    module = _load_module()
    coordinator = module.TestTrainCoordinator(state_root=tmp_path / "state")
    runner = _FakeReleaseRunner(gpu=True)

    coordinator.deploy_candidate(SHA, pr=42, slot="A", runner=runner)

    mutations = [event[:2] for event in runner.events if event[0] != "plan"]
    assert mutations == [("preflight", "control-plane"), ("deploy", "control-plane")]


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


def test_release_runner_publishes_approval_with_a_relative_layer_path(
    tmp_path, monkeypatch
):
    module = _load_module()
    runner = module.ReleaseCLI(repo=ROOT, bundle_cache=tmp_path / "cache")
    approval_dir = tmp_path / "state" / "approvals"
    approval_dir.mkdir(parents=True)
    approval = approval_dir / f"{SHA}.json"
    approval.write_text("{}\n", encoding="utf-8")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((list(args), kwargs))
        return subprocess.CompletedProcess(
            args,
            1 if args[:3] == ["oras", "manifest", "fetch"] else 0,
            stdout="",
            stderr="not found" if args[:3] == ["oras", "manifest", "fetch"] else "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    reference = runner.publish_approval(SHA, approval)

    assert reference.endswith(f":{SHA}")
    push_args, push_kwargs = calls[-1]
    assert push_args[:2] == ["oras", "push"]
    assert push_args[-1] == (
        f"{approval.name}:application/vnd.allbot.release-approval.v1+json"
    )
    assert push_kwargs["cwd"] == approval_dir


def test_release_runner_accepts_identical_remote_approval_with_another_layer_name(
    tmp_path, monkeypatch
):
    module = _load_module()
    runner = module.ReleaseCLI(repo=ROOT, bundle_cache=tmp_path / "cache")
    approval = tmp_path / f"{SHA}.json"
    approval.write_text("{\"status\":\"approved\"}\n", encoding="utf-8")

    def fake_run(args, **kwargs):
        if args[:2] == ["oras", "pull"]:
            output = Path(args[-1])
            (output / "promotion-approval.json").write_bytes(approval.read_bytes())
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    reference = runner.publish_approval(SHA, approval)

    assert reference.endswith(f":{SHA}")
