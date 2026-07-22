import importlib.util
import json
from pathlib import Path

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


def test_test_deployment_commands_are_fixed_to_test_and_exact_sha(tmp_path):
    module = _load_module()
    sha = "b" * 40

    commands = module.test_deployment_commands(tmp_path, sha)

    assert [command[2] for command in commands] == ["plan", "deploy"]
    assert all(command[-1] in {sha, "--execute"} for command in commands)
    assert commands[1][-3:] == ["--sha", sha, "--execute"]
    flattened = " ".join(part for command in commands for part in command)
    assert "--env test" in flattened
    assert "preflight" not in flattened
    assert "prod" not in flattened
    assert "promote" not in flattened


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


def test_queue_reuses_the_repository_change_scope_policy():
    module = _load_module()

    assert module.classify_paths(["docs/example.md", "tests/ops/test_example.py"]) == "lightweight"
    assert module.classify_paths(["src/core/task_core.py"]) == "runtime"
