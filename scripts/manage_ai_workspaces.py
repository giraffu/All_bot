#!/usr/bin/env python3
"""Manage the four persistent AllBot AI development worktree slots."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterator, Sequence


SLOTS = ("A", "B", "C", "D")
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_ROOT = Path("/home/hfy/APP/All_bot-workspaces")
DEFAULT_BASE_REF = "origin/codex/test-train"
DEFAULT_LOCK_PATH = Path.home() / ".local" / "state" / "allbot" / "ai-workspaces.lock"
TASK_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class WorkspaceError(RuntimeError):
    """A slot transition would risk losing or mixing task work."""


class WorkspaceManager:
    def __init__(
        self,
        *,
        repo: Path = DEFAULT_REPO,
        workspace_root: Path = DEFAULT_WORKSPACE_ROOT,
        base_ref: str = DEFAULT_BASE_REF,
        lock_path: Path = DEFAULT_LOCK_PATH,
    ) -> None:
        self.repo = repo.resolve()
        self.workspace_root = workspace_root.resolve()
        self.base_ref = base_ref
        self.lock_path = lock_path.expanduser().resolve()

    @contextmanager
    def _workspace_lock(self) -> Iterator[None]:
        """Serialize slot transitions across parallel AI windows."""

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            handle.truncate()
            handle.write(str(__import__("os").getpid()))
            handle.flush()
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def _run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            cwd=cwd or self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or args[0]
            raise WorkspaceError(detail.splitlines()[-1])
        return result

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        return self._run(["git", *args], cwd=cwd, check=check).stdout.strip()

    @staticmethod
    def _slot(value: str) -> str:
        slot = value.upper()
        if slot not in SLOTS:
            raise WorkspaceError("slot must be one of A, B, C, or D")
        return slot

    def _path(self, slot: str) -> Path:
        return self.workspace_root / self._slot(slot)

    def _fetch_base(self) -> None:
        remote_branch = self.base_ref.removeprefix("origin/")
        self._git("fetch", "--prune", "origin", remote_branch)
        self._git("rev-parse", "--verify", self.base_ref)

    def _registered_worktrees(self) -> set[Path]:
        paths: set[Path] = set()
        for line in self._git("worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                paths.add(Path(line.removeprefix("worktree ")).resolve())
        return paths

    def _require_initialized(self, slot: str) -> Path:
        path = self._path(slot)
        if path not in self._registered_worktrees() or not path.is_dir():
            raise WorkspaceError(f"slot {slot} is not initialized")
        return path

    def _require_clean(self, path: Path) -> None:
        if self._git("status", "--porcelain", cwd=path):
            raise WorkspaceError(f"workspace is dirty: {path}")
        git_dir = Path(self._git("rev-parse", "--absolute-git-dir", cwd=path))
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
            if (git_dir / marker).exists():
                raise WorkspaceError(f"workspace has an unfinished Git operation: {marker}")

    def init(self) -> list[dict[str, Any]]:
        with self._workspace_lock():
            self._fetch_base()
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            registered = self._registered_worktrees()
            for slot in SLOTS:
                path = self._path(slot)
                if path in registered:
                    self._require_clean(path)
                    continue
                if path.exists():
                    raise WorkspaceError(
                        f"slot path exists but is not a Git worktree: {path}"
                    )
                self._git("worktree", "add", "--detach", str(path), self.base_ref)
            return self.status()

    def status(self) -> list[dict[str, Any]]:
        registered = self._registered_worktrees()
        base_sha = self._git("rev-parse", "--verify", self.base_ref, check=False)
        rows: list[dict[str, Any]] = []
        for slot in SLOTS:
            path = self._path(slot)
            initialized = path in registered and path.is_dir()
            if not initialized:
                rows.append(
                    {
                        "slot": slot,
                        "path": str(path),
                        "initialized": False,
                        "branch": None,
                        "head": None,
                        "clean": False,
                        "at_base": False,
                        "safe_to_assign": False,
                    }
                )
                continue
            branch = self._git("branch", "--show-current", cwd=path) or None
            head = self._git("rev-parse", "HEAD", cwd=path)
            clean = not bool(self._git("status", "--porcelain", cwd=path))
            at_base = bool(base_sha) and head == base_sha
            rows.append(
                {
                    "slot": slot,
                    "path": str(path),
                    "initialized": True,
                    "branch": branch,
                    "head": head,
                    "clean": clean,
                    "at_base": at_base,
                    "safe_to_assign": branch is None and clean and at_base,
                }
            )
        return rows

    @staticmethod
    def _task(task: str) -> str:
        task = task.lower()
        if not TASK_RE.fullmatch(task):
            raise WorkspaceError("task must be a lowercase kebab-case slug")
        return task

    def _assign_unlocked(self, slot: str, task: str, *, fetch: bool = True) -> str:
        slot = self._slot(slot)
        task = self._task(task)
        path = self._require_initialized(slot)
        self._require_clean(path)
        if self._git("branch", "--show-current", cwd=path):
            raise WorkspaceError("slot is not parked; park it before assigning another task")
        if fetch:
            self._fetch_base()
        head = self._git("rev-parse", "HEAD", cwd=path)
        base = self._git("rev-parse", self.base_ref)
        if head != base:
            raise WorkspaceError("slot base is stale; refresh it before assignment")
        branch = f"codex/{slot.lower()}-{task}"
        if self._git("show-ref", "--verify", f"refs/heads/{branch}", check=False):
            raise WorkspaceError(f"task branch already exists: {branch}")
        self._git("switch", "-c", branch, self.base_ref, cwd=path)
        return branch

    def assign(self, slot: str, task: str) -> str:
        with self._workspace_lock():
            return self._assign_unlocked(slot, task)

    def claim(self, task: str) -> dict[str, str]:
        """Atomically select and assign the first safe A-D slot."""

        task = self._task(task)
        with self._workspace_lock():
            self._fetch_base()
            existing = self._git(
                "for-each-ref",
                "--format=%(refname:short)",
                f"refs/heads/codex/*-{task}",
            ).splitlines()
            if existing:
                raise WorkspaceError(
                    f"task is already claimed by branch: {existing[0]}"
                )
            registered = self._registered_worktrees()
            base_sha = self._git("rev-parse", self.base_ref)
            for slot in SLOTS:
                path = self._path(slot)
                if path not in registered or not path.is_dir():
                    continue
                if self._git("branch", "--show-current", cwd=path):
                    continue
                try:
                    self._require_clean(path)
                except WorkspaceError:
                    continue
                if self._git("rev-parse", "HEAD", cwd=path) != base_sha:
                    self._git("switch", "--detach", self.base_ref, cwd=path)
                branch = self._assign_unlocked(slot, task, fetch=False)
                return {
                    "slot": slot,
                    "path": str(path),
                    "branch": branch,
                    "base_sha": base_sha,
                }
        raise WorkspaceError(
            "no available workspace slot; A-D are occupied, dirty, or uninitialized"
        )

    def park(self, slot: str) -> None:
        with self._workspace_lock():
            slot = self._slot(slot)
            path = self._require_initialized(slot)
            self._require_clean(path)
            branch = self._git("branch", "--show-current", cwd=path)
            if not branch:
                return
            head = self._git("rev-parse", "HEAD", cwd=path)
            remote_refs = {
                line.strip()
                for line in self._git(
                    "branch", "-r", "--contains", head, cwd=path
                ).splitlines()
            }
            if f"origin/{branch}" not in remote_refs:
                raise WorkspaceError(
                    "task branch must be pushed before the slot can be parked"
                )
            self._fetch_base()
            self._git("switch", "--detach", self.base_ref, cwd=path)

    def refresh(self, slot: str) -> None:
        with self._workspace_lock():
            slot = self._slot(slot)
            path = self._require_initialized(slot)
            self._require_clean(path)
            if self._git("branch", "--show-current", cwd=path):
                raise WorkspaceError("only a parked detached slot can be refreshed")
            self._fetch_base()
            self._git("switch", "--detach", self.base_ref, cwd=path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    subparsers.add_parser("status")
    assign = subparsers.add_parser("assign")
    assign.add_argument("--slot", required=True)
    assign.add_argument("--task", required=True)
    claim = subparsers.add_parser("claim")
    claim.add_argument("--task", required=True)
    for name in ("park", "refresh"):
        child = subparsers.add_parser(name)
        child.add_argument("--slot", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = WorkspaceManager(
        repo=args.repo,
        workspace_root=args.workspace_root,
        base_ref=args.base_ref,
        lock_path=args.lock_path,
    )
    try:
        if args.command == "init":
            result: Any = manager.init()
        elif args.command == "status":
            result = manager.status()
        elif args.command == "assign":
            result = {"slot": args.slot.upper(), "branch": manager.assign(args.slot, args.task)}
        elif args.command == "claim":
            result = manager.claim(args.task)
        elif args.command == "park":
            manager.park(args.slot)
            result = {"slot": args.slot.upper(), "status": "parked"}
        else:
            manager.refresh(args.slot)
            result = {"slot": args.slot.upper(), "status": "refreshed"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except WorkspaceError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
