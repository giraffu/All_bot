import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "auto_integrate_handoffs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("auto_integrate_handoffs", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _handoff(slot: str, suffix: str, *, queued_at: str) -> dict[str, str]:
    digit = str(ord(suffix[-1]) % 10)
    return {
        "slot": slot,
        "branch": f"codex/{slot.lower()}-{suffix}",
        "head": digit * 40,
        "base_sha": "a" * 40,
        "queued_at": queued_at,
    }


def test_queue_is_idempotent_and_freezes_pending_items_in_order(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    later = _handoff("B", "second", queued_at="2026-07-22T02:00:00+00:00")
    earlier = _handoff("A", "first", queued_at="2026-07-22T01:00:00+00:00")

    assert queue.enqueue(later)["status"] == "queued"
    assert queue.enqueue(earlier)["status"] == "queued"
    assert queue.enqueue(earlier)["status"] == "already-queued"

    batch = queue.freeze_pending()

    assert [member["head"] for member in batch["members"]] == [
        earlier["head"],
        later["head"],
    ]
    assert not list((tmp_path / "queue" / "pending").glob("*.json"))
    assert Path(batch["path"]).is_file()


def test_failed_batch_blocks_later_work_until_operator_requeues_it(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    queue.enqueue(_handoff("A", "first", queued_at="2026-07-22T01:00:00+00:00"))
    batch = queue.freeze_pending()
    queue.update_batch(batch, stage="waiting-main-ci", main_sha="b" * 40)
    queue.fail_batch(batch, "CI failed")
    queue.enqueue(_handoff("B", "second", queued_at="2026-07-22T02:00:00+00:00"))

    with pytest.raises(module.IntegrationQueueError, match="failed batch blocks"):
        queue.freeze_pending()

    failed = json.loads(Path(batch["path"]).read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert failed["error"] == "CI failed"

    retried = queue.retry_batch(batch["batch"])
    assert retried["status"] == "running"
    assert retried["stage"] == "waiting-main-ci"
    assert retried["main_sha"] == "b" * 40
    assert "error" not in retried
    assert Path(retried["path"]).parent.name == "running"
    assert not list((tmp_path / "queue" / "failed").glob("*.json"))


def test_queued_batch_retry_resets_automation_owned_local_branch(tmp_path):
    module = _load_module()
    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
    )
    calls = []
    coordinator._validate_members = lambda _members: None

    def fake_git(*args, cwd=None):
        calls.append((args, cwd))
        if args[:2] == ("switch", "-C"):
            raise RuntimeError("stop after branch preparation")
        return ""

    coordinator._git = fake_git
    batch = {
        "batch": "20260727-161018-68941719",
        "status": "running",
        "stage": "queued",
        "members": [_handoff("A", "first", queued_at="2026-07-22T01:00:00+00:00")],
    }

    with pytest.raises(RuntimeError, match="stop after branch preparation"):
        coordinator.process(batch)

    switch = next(args for args, _cwd in calls if args[0] == "switch")
    assert switch == (
        "switch",
        "-C",
        "codex/release-batch-20260727-161018-68941719",
        "origin/main",
    )


def test_pr_check_wait_uses_structured_status_without_gh_version_flags(tmp_path):
    module = _load_module()
    responses = iter(
        [
            {
                "state": "OPEN",
                "statusCheckRollup": [
                    {"name": "tests", "status": "IN_PROGRESS", "conclusion": ""}
                ],
            },
            {
                "state": "OPEN",
                "statusCheckRollup": [
                    {
                        "name": "tests",
                        "status": "COMPLETED",
                        "conclusion": "SUCCESS",
                    }
                ],
            },
        ]
    )
    calls = []

    def run_func(args, *, cwd, text, capture_output, check):
        calls.append(list(args))
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps(next(responses)), stderr=""
        )

    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
        run_func=run_func,
    )
    original_sleep = module.time.sleep
    module.time.sleep = lambda _seconds: None
    try:
        coordinator._wait_pr_checks("https://example/pr/1", cwd=tmp_path)
    finally:
        module.time.sleep = original_sleep

    assert calls == [
        [
            "gh",
            "pr",
            "view",
            "https://example/pr/1",
            "--json",
            "state,statusCheckRollup",
        ],
        [
            "gh",
            "pr",
            "view",
            "https://example/pr/1",
            "--json",
            "state,statusCheckRollup",
        ],
    ]
    assert all("--fail-fast" not in call for call in calls)


def test_pr_check_wait_fails_closed_with_failed_check_name(tmp_path):
    module = _load_module()

    def run_func(args, *, cwd, text, capture_output, check):
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                {
                    "state": "OPEN",
                    "statusCheckRollup": [
                        {
                            "name": "python-tests",
                            "status": "COMPLETED",
                            "conclusion": "FAILURE",
                        }
                    ],
                }
            ),
            stderr="",
        )

    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
        run_func=run_func,
    )
    with pytest.raises(module.IntegrationQueueError, match="python-tests"):
        coordinator._wait_pr_checks("https://example/pr/1", cwd=tmp_path)


def test_pr_retry_can_adopt_only_a_fast_forward_repair_head(tmp_path):
    module = _load_module()
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert '"state,mergeCommit,headRefOid"' in source
    assert '"merge-base",' in source
    assert '"--is-ancestor",' in source
    assert "recorded_batch_head" in source
    assert "batch_head=remote_batch_head" in source


def test_test_deployment_commands_are_fixed_to_test_and_exact_sha(tmp_path):
    module = _load_module()
    sha = "b" * 40

    commands = module.test_deployment_commands(tmp_path, sha)

    assert all(command[0] == sys.executable for command in commands)
    assert [command[2] for command in commands] == ["plan", "deploy"]
    assert all(command[-1] in {sha, "--execute"} for command in commands)
    assert commands[1][-3:] == ["--sha", sha, "--execute"]
    flattened = " ".join(part for command in commands for part in command)
    assert "--env test" in flattened
    assert all(
        "--bundle-repository ghcr.io/giraffu/allbot-release-v2"
        in " ".join(command)
        for command in commands
    )
    assert "preflight" not in flattened
    assert "prod" not in flattened
    assert "promote" not in flattened


def test_test_deploy_command_reuses_validated_plan_token(tmp_path):
    module = _load_module()
    token = "rp_" + "x" * 40

    _plan, deploy = module.test_deployment_commands(
        tmp_path, "b" * 40, token
    )

    assert deploy[-3:] == ["--plan-token", token, "--execute"]
    with pytest.raises(module.IntegrationQueueError, match="token is invalid"):
        module.test_deployment_commands(tmp_path, "b" * 40, "-unsafe")


def test_single_writer_lock_reports_an_active_integration(tmp_path):
    module = _load_module()
    first = module.IntegrationQueue(tmp_path / "queue")
    second = module.IntegrationQueue(tmp_path / "queue")

    with first.lock():
        with pytest.raises(module.IntegrationQueueError, match="already|active|another"):
            with second.lock():
                pass


def test_handoff_enqueue_rejects_mutable_or_non_slot_identity(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    invalid = _handoff("A", "first", queued_at="2026-07-22T01:00:00+00:00")
    invalid["head"] = "main"

    with pytest.raises(module.IntegrationQueueError, match="immutable handoff"):
        queue.enqueue(invalid)


def test_systemd_worker_can_only_run_the_test_only_coordinator():
    service = (ROOT / "deploy/systemd/allbot-ai-integration-queue.service").read_text(
        encoding="utf-8"
    )
    timer = (ROOT / "deploy/systemd/allbot-ai-integration-queue.timer").read_text(
        encoding="utf-8"
    )

    assert "auto_integrate_handoffs.py" in service
    assert "run-once --execute" in service
    assert "prod" not in service.lower()
    assert "OnUnitInactiveSec=1m" in timer


def test_modular_release_accepts_a_fail_closed_published_replay(tmp_path):
    module = _load_module()
    sha = "b" * 40
    calls: list[list[str]] = []

    def run_func(args, *, cwd, text, capture_output, check):
        calls.append(list(args))
        if args[:4] == [
            "gh",
            "run",
            "list",
            "--workflow",
        ]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    [
                        {
                            "status": "completed",
                            "conclusion": "failure",
                            "headSha": sha,
                        }
                    ]
                ),
                stderr="",
            )
        if args[:2] == ["oras", "pull"]:
            bundle_dir = Path(args[args.index("-o") + 1]) / "release-v2"
            bundle_dir.mkdir(parents=True)
            payloads = {
                "release-index.json": {
                    "source_sha": sha,
                    "release_channel": "main",
                    "source_ref": "refs/heads/main",
                    "ci_run": "https://github.com/giraffu/All_bot/actions/runs/123",
                },
                "control-plane-manifest.json": {"source_sha": sha},
                "test-execution-manifest.json": {"source_sha": sha},
                "gpu-execution-manifest.json": {
                    "source_sha": sha,
                    "completeness": "complete",
                    "missing_artifacts": [],
                },
            }
            for name, payload in payloads.items():
                (bundle_dir / name).write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args[:3] == ["gh", "run", "view"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "headSha": sha,
                    }
                ),
                stderr="",
            )
        raise AssertionError(args)

    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
        run_func=run_func,
    )

    coordinator._wait_workflow("modular-release-v2.yml", sha, timeout_seconds=1)

    assert any(call[:2] == ["oras", "pull"] for call in calls)


def test_modular_release_replay_rejects_a_bundle_for_another_sha(tmp_path):
    module = _load_module()
    sha = "b" * 40

    def run_func(args, *, cwd, text, capture_output, check):
        if args[:2] == ["oras", "pull"]:
            bundle_dir = Path(args[args.index("-o") + 1]) / "release-v2"
            bundle_dir.mkdir(parents=True)
            for name in (
                "release-index.json",
                "control-plane-manifest.json",
                "test-execution-manifest.json",
                "gpu-execution-manifest.json",
            ):
                payload = {"source_sha": "c" * 40}
                if name == "release-index.json":
                    payload.update(
                        {
                            "release_channel": "main",
                            "source_ref": "refs/heads/main",
                            "ci_run": (
                                "https://github.com/giraffu/All_bot/actions/runs/123"
                            ),
                        }
                    )
                if name == "gpu-execution-manifest.json":
                    payload.update(
                        {"completeness": "complete", "missing_artifacts": []}
                    )
                (bundle_dir / name).write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                [
                    {
                        "status": "completed",
                        "conclusion": "failure",
                        "headSha": sha,
                    }
                ]
            ),
            stderr="",
        )

    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
        run_func=run_func,
    )

    with pytest.raises(
        module.IntegrationQueueError,
        match="modular-release-v2.yml failed",
    ):
        coordinator._wait_workflow(
            "modular-release-v2.yml", sha, timeout_seconds=1
        )


def test_queue_reuses_the_repository_change_scope_policy():
    module = _load_module()

    assert module.classify_paths(["docs/example.md", "tests/ops/test_example.py"]) == "lightweight"
    assert module.classify_paths(["src/core/task_core.py"]) == "runtime"
    assert module.classify_paths(["scripts/release.py"]) == "release-tooling"


def test_nonruntime_scopes_skip_shared_test_deployment():
    module = _load_module()

    assert module.scope_skips_test_deploy("lightweight")
    assert module.scope_skips_test_deploy("release-tooling")
    assert not module.scope_skips_test_deploy("runtime")
    assert not module.scope_skips_test_deploy("operator")


@pytest.mark.parametrize("stage", ["waiting-main-ci", "deploying-test"])
def test_release_tooling_batch_completes_without_test_deploy(tmp_path, stage):
    module = _load_module()
    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
    )
    coordinator._validate_members = lambda _members: None
    coordinator._git = lambda *_args, **_kwargs: ""
    workflows = []
    coordinator._wait_workflow = lambda workflow, sha: workflows.append(
        (workflow, sha)
    )
    sha = "b" * 40
    batch = {
        "batch": "20260727-203219-8470b3b4",
        "status": "running",
        "stage": stage,
        "scope": "release-tooling",
        "branch": "codex/release-batch-20260727-203219-8470b3b4",
        "pr_url": "https://github.com/giraffu/All_bot/pull/364",
        "main_sha": sha,
        "members": [
            _handoff("D", "release-tooling", queued_at="2026-07-27T20:32:19+00:00")
        ],
    }

    result = coordinator.process(batch)

    assert workflows == (
        [("control-plane-release.yml", sha)]
        if stage == "waiting-main-ci"
        else []
    )
    assert result["test_status"] == "skipped-release-tooling"


def test_workflow_wait_filters_head_sha_without_version_specific_commit_flag(
    tmp_path,
):
    module = _load_module()
    sha = "b" * 40
    calls = []

    def run_func(args, *, cwd, text, capture_output, check):
        calls.append(list(args))
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps(
                [
                    {
                        "databaseId": 1,
                        "status": "completed",
                        "conclusion": "success",
                        "headSha": "c" * 40,
                    },
                    {
                        "databaseId": 2,
                        "status": "completed",
                        "conclusion": "success",
                        "headSha": sha,
                    },
                ]
            ),
            stderr="",
        )

    coordinator = module.Coordinator(
        tmp_path,
        module.IntegrationQueue(tmp_path / "queue"),
        run_func=run_func,
    )
    coordinator._wait_workflow("control-plane-release.yml", sha)

    assert "--commit" not in calls[0]
    assert "headSha" in calls[0][calls[0].index("--json") + 1]


def test_real_coordinator_subprocess_prefers_the_target_checkout_python_path(
    monkeypatch,
    tmp_path,
):
    module = _load_module()
    captured = {}

    def fake_subprocess_run(args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)
    coordinator = module.Coordinator(
        tmp_path, module.IntegrationQueue(tmp_path / "queue")
    )
    coordinator.run_func = module.subprocess.run

    assert coordinator._run(["python", "-V"], cwd=tmp_path) == "ok"
    assert captured["env"]["PYTHONPATH"].split(":")[0] == str(
        tmp_path.resolve()
    )


def test_reconcile_merged_moves_stale_pending_and_superseded_test_failure(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    merged = _handoff("A", "merged", queued_at="2026-07-22T01:00:00+00:00")
    pending = _handoff("B", "pending", queued_at="2026-07-22T02:00:00+00:00")
    queue.enqueue(merged)
    queue.enqueue(pending)
    failed_path = queue.failed / "old-test-failure.json"
    module._atomic_json(
        failed_path,
        {
            "batch": "old-test-failure",
            "status": "failed",
            "stage": "deploying-test",
            "main_sha": "c" * 40,
            "members": [],
            "path": str(failed_path),
        },
    )

    result = queue.reconcile_merged(
        current_main="d" * 40,
        is_ancestor=lambda head, _main: head in {merged["head"], "c" * 40},
        superseding_bundle_ready=True,
    )

    assert result["merged_pending"] == [merged["head"]]
    assert result["superseded_failed"] == ["old-test-failure"]
    assert (queue.pending / f"{pending['head']}.json").is_file()
    assert not (queue.pending / f"{merged['head']}.json").exists()
    completed = json.loads(
        (queue.completed / "reconciled-old-test-failure.json").read_text(
            encoding="utf-8"
        )
    )
    assert completed["status"] == "superseded"
    assert completed["superseded_by_main"] == "d" * 40


def test_reconcile_keeps_test_failure_when_newer_main_has_no_bundle(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    failed_path = queue.failed / "old-test-failure.json"
    module._atomic_json(
        failed_path,
        {
            "batch": "old-test-failure",
            "status": "failed",
            "stage": "deploying-test",
            "main_sha": "c" * 40,
            "members": [],
            "path": str(failed_path),
        },
    )

    result = queue.reconcile_merged(
        current_main="d" * 40,
        is_ancestor=lambda _head, _main: True,
        superseding_bundle_ready=False,
    )

    assert result["superseded_failed"] == []
    assert failed_path.is_file()
