import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "auto_integrate_handoffs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("auto_integrate_handoffs", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _handoff(slot: str, digit: str, queued_at: str) -> dict[str, str]:
    return {
        "slot": slot,
        "branch": f"codex/{slot.lower()}-task-{digit}",
        "head": digit * 40,
        "base_sha": "a" * 40,
        "queued_at": queued_at,
    }


def test_queue_claims_one_handoff_at_a_time_in_order(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    later = _handoff("B", "2", "2026-07-22T02:00:00+00:00")
    earlier = _handoff("A", "1", "2026-07-22T01:00:00+00:00")

    queue.enqueue(later)
    queue.enqueue(earlier)

    claimed = queue.claim_next()

    assert claimed["head"] == earlier["head"]
    assert Path(claimed["path"]).parent.name == "integrating"
    assert (queue.pending / f"{later['head']}.json").is_file()


def test_conflict_moves_only_that_handoff_to_needs_rebase(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    first = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    second = _handoff("B", "2", "2026-07-22T02:00:00+00:00")
    queue.enqueue(first)
    queue.enqueue(second)

    claimed = queue.claim_next()
    queue.needs_rebase(
        claimed,
        main_sha="b" * 40,
        conflict_files=["src/example.py"],
    )

    assert queue.claim_next()["head"] == second["head"]
    record = json.loads(
        (queue.needs_rebase_dir / f"{first['head']}.json").read_text()
    )
    assert record["status"] == "needs-rebase"
    assert record["conflict_files"] == ["src/example.py"]


def test_new_handoff_supersedes_needs_rebase_identity(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    old = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    queue.enqueue(old)
    claimed = queue.claim_next()
    queue.needs_rebase(claimed, main_sha="b" * 40, conflict_files=["x.py"])

    new = _handoff("A", "3", "2026-07-22T03:00:00+00:00")
    new["supersedes"] = old["head"]
    queue.enqueue(new)

    old_record = json.loads(
        (queue.needs_rebase_dir / f"{old['head']}.json").read_text()
    )
    assert old_record["status"] == "superseded"
    assert old_record["superseded_by"] == new["head"]


def test_coordinator_conflict_does_not_stop_next_handoff(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    queue.enqueue(_handoff("A", "1", "2026-07-22T01:00:00+00:00"))
    queue.enqueue(_handoff("B", "2", "2026-07-22T02:00:00+00:00"))
    outcomes = iter(
        [
            module.IntegrationResult(
                status="needs-rebase",
                main_sha="b" * 40,
                conflict_files=("src/conflict.py",),
            ),
            module.IntegrationResult(status="completed", main_sha="c" * 40),
        ]
    )
    coordinator = module.Coordinator(tmp_path, queue)
    coordinator.integrate = lambda _handoff: next(outcomes)

    result = coordinator.run_all()

    assert result["needs_rebase"] == ["1" * 40]
    assert result["completed"] == ["2" * 40]


def test_coordinator_integrates_only_explicit_selected_handoffs(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    first = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    selected = _handoff("B", "2", "2026-07-22T02:00:00+00:00")
    queue.enqueue(first)
    queue.enqueue(selected)
    coordinator = module.Coordinator(tmp_path, queue)
    integrated = []

    def integrate(handoff):
        integrated.append(handoff["head"])
        return module.IntegrationResult(status="completed", main_sha="c" * 40)

    coordinator.integrate = integrate

    result = coordinator.run_all(selected_heads={selected["head"]})

    assert result["completed"] == [selected["head"]]
    assert integrated == [selected["head"]]
    assert (queue.pending / f"{first['head']}.json").is_file()


def test_remote_head_drift_is_isolated_as_needs_rebase(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    handoff = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    calls = []

    def run_func(args, **kwargs):
        calls.append(args)
        if args[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args, 0, stdout="9" * 40 + "\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    coordinator = module.Coordinator(tmp_path, queue, run_func=run_func)
    result = coordinator.integrate(handoff)

    assert result.status == "needs-rebase"
    assert result.reason == "remote-head-drift"
    assert calls


def test_restart_recovers_integrating_without_duplicate_identity(tmp_path):
    module = _load_module()
    queue = module.IntegrationQueue(tmp_path / "queue")
    handoff = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    queue.enqueue(handoff)
    claimed = queue.claim_next()

    recovered = queue.recover_incomplete()

    assert recovered == [handoff["head"]]
    assert not Path(claimed["path"]).exists()
    assert (queue.pending / f"{handoff['head']}.json").is_file()


def test_legacy_failed_conflict_is_migrated_to_needs_rebase_read_only(tmp_path):
    module = _load_module()
    root = tmp_path / "queue"
    failed = root / "failed"
    failed.mkdir(parents=True)
    handoff = _handoff("A", "1", "2026-07-22T01:00:00+00:00")
    legacy = failed / "old-batch.json"
    legacy.write_text(
        json.dumps(
            {
                "members": [handoff],
                "error": "merge conflict",
                "main_sha": "b" * 40,
            }
        )
    )

    queue = module.IntegrationQueue(root)

    assert legacy.is_file()
    record = json.loads(
        (queue.needs_rebase_dir / f"{handoff['head']}.json").read_text()
    )
    assert record["reason"] == "legacy-batch-conflict"
