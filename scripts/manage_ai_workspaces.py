#!/usr/bin/env python3
"""Manage the eight persistent AllBot AI development worktree slots."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Iterator, Mapping, Sequence


SLOTS = ("A", "B", "C", "D", "E", "F", "G", "H")
DEFAULT_REPO = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_ROOT = Path("/home/hfy/APP/All_bot-workspaces")
DEFAULT_BASE_REF = "origin/main"
DEFAULT_LOCK_PATH = Path.home() / ".local" / "state" / "allbot" / "ai-workspaces.lock"
DEFAULT_INTEGRATION_QUEUE_ROOT = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "allbot"
    / "ai-integration-queue"
)
TASK_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


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
            raise WorkspaceError("slot must be one of A, B, C, D, E, F, G, or H")
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
        """Atomically select and assign the first safe A-H slot."""

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
            "no available workspace slot; A-H are occupied, dirty, or uninitialized"
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

    def handoff(
        self,
        slot: str,
        *,
        enqueue: Callable[[Mapping[str, str]], Any] | None = None,
    ) -> dict[str, str]:
        """Freeze one pushed task head and release its slot for new work."""

        with self._workspace_lock():
            slot = self._slot(slot)
            path = self._require_initialized(slot)
            self._require_clean(path)
            branch = self._git("branch", "--show-current", cwd=path)
            if not branch or not branch.startswith(f"codex/{slot.lower()}-"):
                raise WorkspaceError("slot does not contain its assigned task branch")
            head = self._git("rev-parse", "HEAD", cwd=path)
            self._git("fetch", "--prune", "origin", branch)
            remote_head = self._git("rev-parse", f"origin/{branch}", cwd=path)
            if remote_head != head:
                raise WorkspaceError("task branch head must be pushed exactly before handoff")
            self._fetch_base()
            base_sha = self._git("merge-base", head, self.base_ref, cwd=path)
            if not FULL_SHA_RE.fullmatch(base_sha):
                raise WorkspaceError("task branch has no trusted main base")
            result = {
                "slot": slot,
                "branch": branch,
                "head": head,
                "base_sha": base_sha,
            }
            if enqueue is not None:
                enqueue(result)
            self._git("switch", "--detach", self.base_ref, cwd=path)
            return result

    def plan_batch(
        self, batch: str, members: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        """Validate immutable handoffs for one integration PR targeting main."""

        batch = self._task(batch)
        if not members:
            raise WorkspaceError("integration batch requires at least one handoff")
        with self._workspace_lock():
            self._fetch_base()
            base_sha = self._git("rev-parse", self.base_ref)
            frozen: list[dict[str, str]] = []
            identities: set[tuple[str, str]] = set()
            for raw in members:
                slot = self._slot(str(raw.get("slot", "")))
                branch = str(raw.get("branch", ""))
                head = str(raw.get("head", ""))
                if (
                    not branch.startswith(f"codex/{slot.lower()}-")
                    or not FULL_SHA_RE.fullmatch(head)
                ):
                    raise WorkspaceError("integration batch handoff identity is invalid")
                identity = (slot, branch)
                if identity in identities:
                    raise WorkspaceError("integration batch contains a duplicate handoff")
                identities.add(identity)
                self._git("fetch", "--prune", "origin", branch)
                remote_head = self._git("rev-parse", f"origin/{branch}")
                if remote_head != head:
                    raise WorkspaceError(
                        f"handoff head changed after freeze: {slot} {branch}"
                    )
                member_base = str(raw.get("base_sha", ""))
                if not member_base:
                    member_base = self._git("merge-base", head, self.base_ref)
                if not FULL_SHA_RE.fullmatch(member_base):
                    raise WorkspaceError("integration batch member base is invalid")
                if self._run(
                    ["git", "merge-base", "--is-ancestor", member_base, head],
                    check=False,
                ).returncode:
                    raise WorkspaceError("handoff head does not descend from its recorded base")
                if self._run(
                    ["git", "merge-base", "--is-ancestor", member_base, self.base_ref],
                    check=False,
                ).returncode:
                    raise WorkspaceError("handoff base is not reachable from current main")
                frozen.append(
                    {
                        "slot": slot,
                        "branch": branch,
                        "head": head,
                        "base_sha": member_base,
                    }
                )
            return {
                "batch": batch,
                "base_ref": self.base_ref,
                "base_sha": base_sha,
                "members": frozen,
                "integration_branch": f"codex/release-batch-{batch}",
                "pr_base": "main",
                "container_build_trigger": "main-merge",
            }

    def refresh(self, slot: str) -> None:
        with self._workspace_lock():
            slot = self._slot(slot)
            path = self._require_initialized(slot)
            self._require_clean(path)
            if self._git("branch", "--show-current", cwd=path):
                raise WorkspaceError("only a parked detached slot can be refreshed")
            self._fetch_base()
            self._git("switch", "--detach", self.base_ref, cwd=path)

    def align_merged(self) -> dict[str, Any]:
        """Park merged task branches and refresh clean detached slots.

        Dirty workspaces and branches not yet contained by main are reported and
        left byte-for-byte untouched.
        """

        with self._workspace_lock():
            self._fetch_base()
            main_sha = self._git("rev-parse", self.base_ref)
            registered = self._registered_worktrees()
            rows: list[dict[str, Any]] = []
            for slot in SLOTS:
                path = self._path(slot)
                if path not in registered or not path.is_dir():
                    rows.append({"slot": slot, "status": "blocked_uninitialized"})
                    continue
                branch = self._git("branch", "--show-current", cwd=path) or None
                head = self._git("rev-parse", "HEAD", cwd=path)
                if self._git("status", "--porcelain", cwd=path):
                    rows.append(
                        {
                            "slot": slot,
                            "status": "blocked_dirty",
                            "branch": branch,
                            "head": head,
                        }
                    )
                    continue
                if branch and self._run(
                    ["git", "merge-base", "--is-ancestor", head, self.base_ref],
                    cwd=path,
                    check=False,
                ).returncode:
                    rows.append(
                        {
                            "slot": slot,
                            "status": "blocked_unmerged",
                            "branch": branch,
                            "head": head,
                        }
                    )
                    continue
                self._git("switch", "--detach", self.base_ref, cwd=path)
                rows.append(
                    {
                        "slot": slot,
                        "status": "aligned",
                        "branch": None,
                        "head": main_sha,
                    }
                )
            return {"main_sha": main_sha, "slots": rows}


def write_batch_plan(path: Path, plan: Mapping[str, Any]) -> None:
    """Persist one frozen batch plan without allowing replacement."""

    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise WorkspaceError(f"batch plan output already exists: {output}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        output.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument(
        "--queue-root", type=Path, default=DEFAULT_INTEGRATION_QUEUE_ROOT
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    subparsers.add_parser("status")
    assign = subparsers.add_parser("assign")
    assign.add_argument("--slot", required=True)
    assign.add_argument("--task", required=True)
    claim = subparsers.add_parser("claim")
    claim.add_argument("--task", required=True)
    handoff = subparsers.add_parser("handoff")
    handoff.add_argument("--slot", required=True)
    handoff.add_argument(
        "--no-enqueue",
        action="store_true",
        help="freeze and release without adding the handoff to automatic integration",
    )
    batch = subparsers.add_parser("batch-plan")
    batch.add_argument("--batch", required=True)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument(
        "--member",
        action="append",
        default=[],
        help="Frozen handoff in SLOT:codex/branch@40-char-sha form.",
    )
    for name in ("park", "refresh"):
        child = subparsers.add_parser(name)
        child.add_argument("--slot", required=True)
    subparsers.add_parser("align-merged")
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
        elif args.command == "handoff":
            enqueue = None
            if not args.no_enqueue:
                from auto_integrate_handoffs import (
                    IntegrationQueue,
                    IntegrationQueueError,
                )

                queue = IntegrationQueue(args.queue_root)

                def enqueue_handoff(handoff: Mapping[str, str]) -> Any:
                    try:
                        return queue.enqueue(handoff)
                    except IntegrationQueueError as exc:
                        raise WorkspaceError(f"integration queue unavailable: {exc}") from exc

                enqueue = enqueue_handoff
            result = manager.handoff(args.slot, enqueue=enqueue)
            if enqueue is not None:
                result["integration_queue"] = str(args.queue_root.expanduser().resolve())
        elif args.command == "batch-plan":
            members = []
            for value in args.member:
                try:
                    slot, branch_head = value.split(":", 1)
                    branch, head = branch_head.rsplit("@", 1)
                except ValueError as exc:
                    raise WorkspaceError(
                        "member must use SLOT:codex/branch@40-char-sha"
                    ) from exc
                members.append({"slot": slot, "branch": branch, "head": head})
            result = manager.plan_batch(args.batch, members)
            write_batch_plan(args.output, result)
        elif args.command == "park":
            manager.park(args.slot)
            result = {"slot": args.slot.upper(), "status": "parked"}
        elif args.command == "refresh":
            manager.refresh(args.slot)
            result = {"slot": args.slot.upper(), "status": "refreshed"}
        else:
            result = manager.align_merged()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except WorkspaceError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
