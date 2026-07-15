import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "manage_ai_workspaces.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("manage_ai_workspaces", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "origin.git"
    source = tmp_path / "source"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-b", "main", str(source)], check=True)
    _git("config", "user.name", "AllBot Tests", cwd=source)
    _git("config", "user.email", "tests@example.com", cwd=source)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    _git("add", "README.md", cwd=source)
    _git("commit", "-m", "base", cwd=source)
    _git("remote", "add", "origin", str(remote), cwd=source)
    _git("push", "-u", "origin", "main", cwd=source)
    _git("switch", "-c", "codex/test-train", cwd=source)
    _git("push", "-u", "origin", "codex/test-train", cwd=source)
    return source, remote


def test_init_creates_four_clean_detached_slots(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    workspace_root = tmp_path / "workspaces"
    manager = module.WorkspaceManager(repo=repo, workspace_root=workspace_root)

    manager.init()
    manager.init()

    rows = manager.status()
    assert [row["slot"] for row in rows] == ["A", "B", "C", "D"]
    assert all(row["branch"] is None for row in rows)
    assert all(row["clean"] and row["safe_to_assign"] for row in rows)
    assert all((workspace_root / row["slot"]).is_dir() for row in rows)


def test_assign_refuses_stale_or_dirty_slot_and_park_requires_remote_copy(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    manager = module.WorkspaceManager(repo=repo, workspace_root=tmp_path / "workspaces")
    manager.init()

    branch = manager.assign("A", "billing-ledger")
    slot = tmp_path / "workspaces" / "A"
    assert branch == "codex/a-billing-ledger"
    assert _git("branch", "--show-current", cwd=slot) == branch

    (slot / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(module.WorkspaceError, match="dirty"):
        manager.park("A")
    (slot / "dirty.txt").unlink()

    (slot / "README.md").write_text("task\n", encoding="utf-8")
    _git("add", "README.md", cwd=slot)
    _git("-c", "user.name=AllBot Tests", "-c", "user.email=tests@example.com", "commit", "-m", "task", cwd=slot)
    with pytest.raises(module.WorkspaceError, match="pushed"):
        manager.park("A")

    _git("push", "-u", "origin", branch, cwd=slot)
    manager.park("A")
    assert _git("branch", "--show-current", cwd=slot) == ""


def test_assign_requires_refresh_after_test_train_advances(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    manager = module.WorkspaceManager(repo=repo, workspace_root=tmp_path / "workspaces")
    manager.init()

    (repo / "next.txt").write_text("next\n", encoding="utf-8")
    _git("add", "next.txt", cwd=repo)
    _git("-c", "user.name=AllBot Tests", "-c", "user.email=tests@example.com", "commit", "-m", "next", cwd=repo)
    _git("push", "origin", "codex/test-train", cwd=repo)

    with pytest.raises(module.WorkspaceError, match="refresh"):
        manager.assign("B", "new-task")

    manager.refresh("B")
    assert manager.assign("B", "new-task") == "codex/b-new-task"


def test_claim_automatically_uses_the_next_free_slot(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    manager = module.WorkspaceManager(
        repo=repo,
        workspace_root=tmp_path / "workspaces",
        lock_path=tmp_path / "workspace.lock",
    )
    manager.init()

    first = manager.claim("billing-page")
    second = manager.claim("gallery-search")

    assert first == {
        "slot": "A",
        "path": str(tmp_path / "workspaces" / "A"),
        "branch": "codex/a-billing-page",
        "base_sha": first["base_sha"],
    }
    assert second["slot"] == "B"
    assert second["branch"] == "codex/b-gallery-search"
    assert _git("branch", "--show-current", cwd=tmp_path / "workspaces" / "A") == first["branch"]
    assert _git("branch", "--show-current", cwd=tmp_path / "workspaces" / "B") == second["branch"]


def test_claim_refreshes_an_idle_stale_slot_before_assignment(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    manager = module.WorkspaceManager(
        repo=repo,
        workspace_root=tmp_path / "workspaces",
        lock_path=tmp_path / "workspace.lock",
    )
    manager.init()

    (repo / "next.txt").write_text("next\n", encoding="utf-8")
    _git("add", "next.txt", cwd=repo)
    _git(
        "-c",
        "user.name=AllBot Tests",
        "-c",
        "user.email=tests@example.com",
        "commit",
        "-m",
        "next",
        cwd=repo,
    )
    _git("push", "origin", "codex/test-train", cwd=repo)

    claimed = manager.claim("fresh-task")

    assert claimed["slot"] == "A"
    assert _git("rev-parse", "HEAD", cwd=tmp_path / "workspaces" / "A") == _git(
        "rev-parse", "origin/codex/test-train", cwd=repo
    )


def test_claim_skips_dirty_or_occupied_slots_and_fails_when_all_are_busy(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    workspace_root = tmp_path / "workspaces"
    manager = module.WorkspaceManager(
        repo=repo,
        workspace_root=workspace_root,
        lock_path=tmp_path / "workspace.lock",
    )
    manager.init()
    (workspace_root / "A" / "uncommitted.txt").write_text(
        "reserved\n", encoding="utf-8"
    )

    assert manager.claim("second-slot")["slot"] == "B"
    assert manager.claim("third-slot")["slot"] == "C"
    assert manager.claim("fourth-slot")["slot"] == "D"

    with pytest.raises(module.WorkspaceError, match="no available workspace slot"):
        manager.claim("overflow-task")


def test_concurrent_claim_commands_receive_distinct_slots(tmp_path):
    module = _load_module()
    repo, _ = _repository(tmp_path)
    workspace_root = tmp_path / "workspaces"
    lock_path = tmp_path / "workspace.lock"
    manager = module.WorkspaceManager(
        repo=repo,
        workspace_root=workspace_root,
        lock_path=lock_path,
    )
    manager.init()
    common = [
        sys.executable,
        str(MODULE_PATH),
        "--repo",
        str(repo),
        "--workspace-root",
        str(workspace_root),
        "--lock-path",
        str(lock_path),
        "claim",
        "--task",
    ]

    first = subprocess.Popen(
        [*common, "first-window"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    second = subprocess.Popen(
        [*common, "second-window"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    first_out, first_err = first.communicate(timeout=20)
    second_out, second_err = second.communicate(timeout=20)

    assert first.returncode == 0, first_err
    assert second.returncode == 0, second_err
    claims = [json.loads(first_out), json.loads(second_out)]
    assert {claim["slot"] for claim in claims} == {"A", "B"}
    assert {claim["branch"] for claim in claims} == {
        "codex/a-first-window",
        "codex/b-second-window",
    } or {claim["branch"] for claim in claims} == {
        "codex/a-second-window",
        "codex/b-first-window",
    }
