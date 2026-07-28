#!/usr/bin/env python3
"""Serialize immutable handoffs into main without release or CI gates."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_ROOT = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "allbot"
    / "ai-integration-queue"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BRANCH_RE = re.compile(r"^codex/([a-h])-([a-z0-9]+(?:-[a-z0-9]+)*)$")


class IntegrationQueueError(RuntimeError):
    pass


class IntegrationResult:
    def __init__(
        self,
        *,
        status: str,
        main_sha: str,
        conflict_files: Sequence[str] = (),
        reason: str = "",
    ) -> None:
        self.status = status
        self.main_sha = main_sha
        self.conflict_files = tuple(conflict_files)
        self.reason = reason


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _validate_handoff(raw: Mapping[str, Any]) -> dict[str, str]:
    slot = str(raw.get("slot", "")).upper()
    branch = str(raw.get("branch", ""))
    head = str(raw.get("head", ""))
    base_sha = str(raw.get("base_sha", ""))
    match = BRANCH_RE.fullmatch(branch)
    if (
        slot not in tuple("ABCDEFGH")
        or match is None
        or match.group(1) != slot.lower()
        or not FULL_SHA_RE.fullmatch(head)
        or not FULL_SHA_RE.fullmatch(base_sha)
    ):
        raise IntegrationQueueError("immutable handoff identity is invalid")
    result = {
        "slot": slot,
        "branch": branch,
        "head": head,
        "base_sha": base_sha,
        "queued_at": str(raw.get("queued_at") or _now()),
    }
    supersedes = str(raw.get("supersedes", ""))
    if supersedes:
        if not FULL_SHA_RE.fullmatch(supersedes):
            raise IntegrationQueueError("superseded handoff identity is invalid")
        result["supersedes"] = supersedes
    return result


class IntegrationQueue:
    def __init__(self, root: Path = DEFAULT_QUEUE_ROOT) -> None:
        self.root = root.expanduser().resolve()
        self.pending = self.root / "pending"
        self.integrating = self.root / "integrating"
        self.completed = self.root / "completed"
        self.needs_rebase_dir = self.root / "needs-rebase"
        for directory in (
            self.root,
            self.pending,
            self.integrating,
            self.completed,
            self.needs_rebase_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
        self._migrate_legacy_batches()

    def _migrate_legacy_batches(self) -> None:
        """Copy recoverable members out of old batch state without altering evidence."""

        marker = self.root / ".module-flow-migrated"
        if marker.exists():
            return
        for legacy_name in ("running", "failed"):
            legacy_dir = self.root / legacy_name
            if not legacy_dir.is_dir():
                continue
            for path in sorted(legacy_dir.glob("*.json")):
                try:
                    batch = json.loads(path.read_text(encoding="utf-8"))
                    members = [
                        _validate_handoff(member)
                        for member in batch.get("members", ())
                    ]
                except (OSError, json.JSONDecodeError, IntegrationQueueError):
                    continue
                conflict = (
                    legacy_name == "failed"
                    and len(members) == 1
                    and "conflict" in str(batch.get("error", "")).lower()
                )
                for handoff in members:
                    identity = f"{handoff['head']}.json"
                    destinations = (
                        self.pending,
                        self.integrating,
                        self.completed,
                        self.needs_rebase_dir,
                    )
                    if any((directory / identity).exists() for directory in destinations):
                        continue
                    payload: dict[str, Any] = {
                        **handoff,
                        "migrated_from": str(path),
                    }
                    if conflict:
                        payload.update(
                            status="needs-rebase",
                            reason="legacy-batch-conflict",
                            main_sha=str(batch.get("main_sha") or "0" * 40),
                        )
                        _atomic_json(self.needs_rebase_dir / identity, payload)
                    else:
                        payload["status"] = "pending"
                        _atomic_json(self.pending / identity, payload)
        _atomic_json(marker, {"migrated_at": _now()})

    @contextmanager
    def lock(self, *, blocking: bool = False) -> Iterator[None]:
        handle = (self.root / "coordinator.lock").open("a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as exc:
                raise IntegrationQueueError("another main integration is active") from exc
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def enqueue(self, raw: Mapping[str, Any]) -> dict[str, str]:
        handoff = _validate_handoff(raw)
        identity = f"{handoff['head']}.json"
        for directory in (
            self.pending,
            self.integrating,
            self.completed,
            self.needs_rebase_dir,
        ):
            if (directory / identity).exists():
                return {"status": "already-queued", "path": str(directory / identity)}
        supersedes = handoff.get("supersedes")
        if supersedes:
            old_path = self.needs_rebase_dir / f"{supersedes}.json"
            if not old_path.is_file():
                raise IntegrationQueueError("superseded needs-rebase handoff is missing")
            old = json.loads(old_path.read_text(encoding="utf-8"))
            if old.get("status") != "needs-rebase":
                raise IntegrationQueueError("superseded handoff is not active")
            old.update(
                status="superseded",
                superseded_by=handoff["head"],
                superseded_at=_now(),
            )
            _atomic_json(old_path, old)
        payload = {**handoff, "status": "pending"}
        path = self.pending / identity
        _atomic_json(path, payload)
        return {"status": "queued", "path": str(path)}

    def claim_next(self) -> dict[str, Any] | None:
        candidates = []
        for path in self.pending.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            candidates.append((str(payload.get("queued_at", "")), path, payload))
        if not candidates:
            return None
        _queued_at, source, payload = sorted(candidates, key=lambda item: item[0])[0]
        destination = self.integrating / source.name
        payload.update(status="integrating", started_at=_now(), path=str(destination))
        _atomic_json(source, payload)
        os.replace(source, destination)
        return payload

    def recover_incomplete(self) -> list[str]:
        recovered = []
        for source in sorted(self.integrating.glob("*.json")):
            payload = json.loads(source.read_text(encoding="utf-8"))
            destination = self.pending / source.name
            payload.update(
                status="pending",
                recovered_at=_now(),
                path=str(destination),
            )
            _atomic_json(source, payload)
            os.replace(source, destination)
            recovered.append(source.stem)
        return recovered

    def complete(self, handoff: Mapping[str, Any], *, main_sha: str) -> None:
        self._finish(
            handoff,
            self.completed,
            status="completed",
            main_sha=main_sha,
            completed_at=_now(),
        )

    def needs_rebase(
        self,
        handoff: Mapping[str, Any],
        *,
        main_sha: str,
        conflict_files: Sequence[str],
        reason: str = "merge-conflict",
    ) -> None:
        self._finish(
            handoff,
            self.needs_rebase_dir,
            status="needs-rebase",
            main_sha=main_sha,
            conflict_files=sorted(set(conflict_files)),
            reason=reason,
            completed_at=_now(),
        )

    def _finish(
        self,
        handoff: Mapping[str, Any],
        directory: Path,
        **updates: Any,
    ) -> None:
        source = Path(str(handoff["path"]))
        destination = directory / source.name
        payload = dict(handoff)
        payload.update(updates, path=str(destination))
        _atomic_json(source, payload)
        os.replace(source, destination)

    def status(self) -> dict[str, list[str]]:
        return {
            name: sorted(path.name for path in directory.glob("*.json"))
            for name, directory in (
                ("pending", self.pending),
                ("integrating", self.integrating),
                ("completed", self.completed),
                ("needs-rebase", self.needs_rebase_dir),
            )
        }


class Coordinator:
    def __init__(
        self,
        repo: Path,
        queue: IntegrationQueue,
        *,
        run_func=subprocess.run,
    ) -> None:
        self.repo = repo.resolve()
        self.queue = queue
        self.run_func = run_func

    def _run(self, args: Sequence[str], *, cwd: Path | None = None):
        return self.run_func(
            list(args),
            cwd=(cwd or self.repo),
            text=True,
            capture_output=True,
            check=False,
        )

    def integrate(self, handoff: Mapping[str, Any]) -> IntegrationResult:
        self._run(["git", "fetch", "--prune", "origin", "main"])
        self._run(["git", "fetch", "--prune", "origin", str(handoff["branch"])])
        remote = self._run(["git", "rev-parse", f"origin/{handoff['branch']}"])
        if remote.returncode or remote.stdout.strip() != handoff["head"]:
            main = self._run(["git", "rev-parse", "origin/main"]).stdout.strip()
            return IntegrationResult(
                status="needs-rebase",
                main_sha=main if FULL_SHA_RE.fullmatch(main) else "0" * 40,
                reason="remote-head-drift",
            )

        for _attempt in range(3):
            self._run(["git", "fetch", "--prune", "origin", "main"])
            main_sha = self._run(["git", "rev-parse", "origin/main"]).stdout.strip()
            temporary = Path(tempfile.mkdtemp(prefix="allbot-main-integration-"))
            checkout = temporary / "checkout"
            added = False
            try:
                added_result = self._run(
                    ["git", "worktree", "add", "--detach", str(checkout), "origin/main"]
                )
                if added_result.returncode:
                    raise IntegrationQueueError("failed to create integration worktree")
                added = True
                merged = self._run(
                    [
                        "git",
                        "-c",
                        "user.name=AllBot Main Integrator",
                        "-c",
                        "user.email=allbot-integrator@localhost",
                        "merge",
                        "--no-ff",
                        "--no-edit",
                        str(handoff["head"]),
                    ],
                    cwd=checkout,
                )
                if merged.returncode:
                    conflicts = self._run(
                        ["git", "diff", "--name-only", "--diff-filter=U"],
                        cwd=checkout,
                    ).stdout.splitlines()
                    self._run(["git", "merge", "--abort"], cwd=checkout)
                    return IntegrationResult(
                        status="needs-rebase",
                        main_sha=main_sha,
                        conflict_files=conflicts,
                    )
                new_main = self._run(["git", "rev-parse", "HEAD"], cwd=checkout).stdout.strip()
                pushed = self._run(
                    ["git", "push", "origin", "HEAD:refs/heads/main"],
                    cwd=checkout,
                )
                if pushed.returncode == 0:
                    return IntegrationResult(status="completed", main_sha=new_main)
                self._run(["git", "fetch", "--prune", "origin", "main"])
                advanced = self._run(
                    ["git", "rev-parse", "origin/main"]
                ).stdout.strip()
                if advanced == main_sha:
                    raise IntegrationQueueError("failed to push main")
            finally:
                if added:
                    self._run(["git", "worktree", "remove", "--force", str(checkout)])
                shutil.rmtree(temporary, ignore_errors=True)
        return IntegrationResult(
            status="needs-rebase",
            main_sha=main_sha,
            reason="main-advanced-repeatedly",
        )

    def run_all(self) -> dict[str, Any]:
        completed: list[str] = []
        needs_rebase: list[str] = []
        while True:
            handoff = self.queue.claim_next()
            if handoff is None:
                break
            result = self.integrate(handoff)
            if result.status == "completed":
                self.queue.complete(handoff, main_sha=result.main_sha)
                completed.append(str(handoff["head"]))
            else:
                self.queue.needs_rebase(
                    handoff,
                    main_sha=result.main_sha,
                    conflict_files=result.conflict_files,
                    reason=result.reason or "merge-conflict",
                )
                needs_rebase.append(str(handoff["head"]))
        return {
            "status": "completed",
            "completed": completed,
            "needs_rebase": needs_rebase,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--queue-root", type=Path, default=DEFAULT_QUEUE_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    run = subparsers.add_parser("run-once")
    run.add_argument("--execute", action="store_true")
    integrate_all = subparsers.add_parser("integrate-all")
    integrate_all.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    queue = IntegrationQueue(args.queue_root)
    try:
        if args.command == "status":
            result = queue.status()
        elif not args.execute:
            result = {"status": "dry-run", "queue": queue.status()}
        else:
            with queue.lock():
                queue.recover_incomplete()
                coordinator = Coordinator(args.repo, queue)
                if args.command == "run-once":
                    handoff = queue.claim_next()
                    if handoff is None:
                        result = {"status": "idle"}
                    else:
                        outcome = coordinator.integrate(handoff)
                        if outcome.status == "completed":
                            queue.complete(handoff, main_sha=outcome.main_sha)
                        else:
                            queue.needs_rebase(
                                handoff,
                                main_sha=outcome.main_sha,
                                conflict_files=outcome.conflict_files,
                                reason=outcome.reason or "merge-conflict",
                            )
                        result = {
                            "status": outcome.status,
                            "head": handoff["head"],
                            "main_sha": outcome.main_sha,
                        }
                else:
                    result = coordinator.run_all()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except IntegrationQueueError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
