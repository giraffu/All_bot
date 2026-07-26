#!/usr/bin/env python3
"""Serialize immutable workspace handoffs into main and the shared test track.

The coordinator intentionally exposes no production environment option.  A failed
batch remains visible and blocks later work until an operator explicitly requeues
or removes it after fixing the cause.
"""

from __future__ import annotations

import argparse
import importlib.util
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_ROOT = (
    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "allbot"
    / "ai-integration-queue"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PLAN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
BRANCH_RE = re.compile(r"^codex/([a-h])-([a-z0-9]+(?:-[a-z0-9]+)*)$")


class IntegrationQueueError(RuntimeError):
    """The queue cannot safely advance."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    queued_at = str(raw.get("queued_at") or _now())
    return {
        "slot": slot,
        "branch": branch,
        "head": head,
        "base_sha": base_sha,
        "queued_at": queued_at,
    }


class IntegrationQueue:
    """File-backed queue shared by all local A-H workspaces."""

    def __init__(self, root: Path = DEFAULT_QUEUE_ROOT) -> None:
        self.root = root.expanduser().resolve()
        self.pending = self.root / "pending"
        self.running = self.root / "running"
        self.completed = self.root / "completed"
        self.failed = self.root / "failed"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        for directory in (self.pending, self.running, self.completed, self.failed):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)

    @contextmanager
    def lock(self, *, blocking: bool = False) -> Iterator[None]:
        lock_path = self.root / "coordinator.lock"
        handle = lock_path.open("a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            try:
                fcntl.flock(handle.fileno(), flags)
            except BlockingIOError as exc:
                raise IntegrationQueueError("another integration or test deployment is active") from exc
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def enqueue(self, raw: Mapping[str, Any]) -> dict[str, str]:
        handoff = _validate_handoff(raw)
        identity = f"{handoff['head']}.json"
        if (self.pending / identity).exists():
            return {"status": "already-queued", "path": str(self.pending / identity)}
        for directory in (self.running, self.completed, self.failed):
            for batch_path in directory.glob("*.json"):
                batch = json.loads(batch_path.read_text(encoding="utf-8"))
                if any(
                    member.get("head") == handoff["head"]
                    for member in batch.get("members", ())
                ):
                    return {"status": "already-queued", "path": str(batch_path)}
        path = self.pending / identity
        temporary = self.pending / f".{identity}.{os.getpid()}.tmp"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(handoff, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                return {"status": "already-queued", "path": str(path)}
        finally:
            temporary.unlink(missing_ok=True)
        return {"status": "queued", "path": str(path)}

    def status(self) -> dict[str, Any]:
        return {
            name: sorted(path.name for path in directory.glob("*.json"))
            for name, directory in (
                ("pending", self.pending),
                ("running", self.running),
                ("completed", self.completed),
                ("failed", self.failed),
            )
        }

    def freeze_pending(self) -> dict[str, Any] | None:
        failed = sorted(self.failed.glob("*.json"))
        if failed:
            raise IntegrationQueueError(
                f"failed batch blocks the queue: {failed[0].name}"
            )
        already_running = sorted(self.running.glob("*.json"))
        if already_running:
            batch = json.loads(already_running[0].read_text(encoding="utf-8"))
            for member in batch.get("members", ()):
                (self.pending / f"{member.get('head', '')}.json").unlink(missing_ok=True)
            return batch
        members = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in self.pending.glob("*.json")
        ]
        if not members:
            return None
        members = sorted((_validate_handoff(item) for item in members), key=lambda item: (item["queued_at"], item["head"]))
        batch_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + members[0]["head"][:8]
        path = self.running / f"{batch_id}.json"
        payload: dict[str, Any] = {
            "batch": batch_id,
            "status": "running",
            "created_at": _now(),
            "members": members,
            "path": str(path),
        }
        _atomic_json(path, payload)
        for member in members:
            (self.pending / f"{member['head']}.json").unlink(missing_ok=True)
        return payload

    def update_batch(self, batch: dict[str, Any], **changes: Any) -> None:
        batch.update(changes)
        _atomic_json(Path(batch["path"]), batch)

    def _finish(self, batch: dict[str, Any], target: Path, **changes: Any) -> None:
        source = Path(batch["path"])
        destination = target / source.name
        batch.update(changes, finished_at=_now(), path=str(destination))
        _atomic_json(source, batch)
        os.replace(source, destination)

    def complete_batch(self, batch: dict[str, Any], **changes: Any) -> None:
        self._finish(batch, self.completed, status="completed", **changes)

    def fail_batch(self, batch: dict[str, Any], error: str) -> None:
        self._finish(batch, self.failed, status="failed", error=error)

    def retry_batch(self, batch_id: str) -> dict[str, Any]:
        if list(self.running.glob("*.json")):
            raise IntegrationQueueError("cannot retry while another batch is running")
        source = self.failed / f"{batch_id}.json"
        if not source.is_file():
            raise IntegrationQueueError(f"failed batch does not exist: {batch_id}")
        batch = json.loads(source.read_text(encoding="utf-8"))
        destination = self.running / source.name
        batch.update(status="running", path=str(destination), retried_at=_now())
        batch.pop("error", None)
        batch.pop("finished_at", None)
        _atomic_json(source, batch)
        os.replace(source, destination)
        return batch


def test_deployment_commands(
    checkout: Path, sha: str, plan_token: str | None = None
) -> list[list[str]]:
    if not FULL_SHA_RE.fullmatch(sha):
        raise IntegrationQueueError("test deployment requires an exact main SHA")
    release = str(checkout / "scripts" / "release.py")
    common = ["--env", "test", "--track", "control-plane", "--sha", sha]
    deploy = ["python", release, "deploy", *common]
    if plan_token is not None:
        if not PLAN_TOKEN_RE.fullmatch(plan_token):
            raise IntegrationQueueError("test deployment plan token is invalid")
        deploy.extend(["--plan-token", plan_token])
    deploy.append("--execute")
    return [["python", release, "plan", *common], deploy]


def classify_paths(paths: Sequence[str]) -> str:
    """Reuse the repository's fail-closed CI classifier without duplicating policy."""

    module_path = ROOT / "scripts" / "classify_ci_change.py"
    spec = importlib.util.spec_from_file_location("allbot_classify_ci_change", module_path)
    if spec is None or spec.loader is None:
        raise IntegrationQueueError("change-scope classifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.classify_change_scope(paths).scope)


class Coordinator:
    """Single-writer orchestration seam; subprocess execution is injectable."""

    def __init__(self, repo: Path, queue: IntegrationQueue, *, run_func=subprocess.run) -> None:
        self.repo = repo.resolve()
        self.queue = queue
        self.run_func = run_func

    def _run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        capture: bool = True,
    ) -> str:
        result = self.run_func(
            list(args),
            cwd=cwd or self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or args[0]).strip().splitlines()[-1]
            raise IntegrationQueueError(detail)
        if not capture:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        return (result.stdout or "").strip()

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        return self._run(["git", *args], cwd=cwd)

    def _published_modular_bundle_is_attested(self, sha: str) -> bool:
        """Accept a protected full replay whose trigger SHA differs from its source.

        Manual modular replays run trusted release tooling from the current main
        ref while packaging an older, still-main-reachable source SHA.  In that
        case GitHub's run head is the tooling SHA, so the immutable bundle and its
        exact-SHA upstream CI run are the fail-closed attestation.
        """

        bundle_ref = f"ghcr.io/giraffu/allbot-release-v2:{sha}"
        try:
            with tempfile.TemporaryDirectory(
                prefix="allbot-modular-release-attestation-"
            ) as temporary:
                output = Path(temporary)
                self._run(["oras", "pull", bundle_ref, "-o", str(output)])
                release_dir = output / "release-v2"
                payloads = {
                    name: json.loads(
                        (release_dir / name).read_text(encoding="utf-8")
                    )
                    for name in (
                        "release-index.json",
                        "control-plane-manifest.json",
                        "test-execution-manifest.json",
                        "gpu-execution-manifest.json",
                    )
                }
        except (
            IntegrationQueueError,
            OSError,
            json.JSONDecodeError,
            TypeError,
        ):
            return False

        if any(
            not isinstance(payload, Mapping)
            or payload.get("source_sha") != sha
            for payload in payloads.values()
        ):
            return False
        release_index = payloads["release-index.json"]
        gpu_manifest = payloads["gpu-execution-manifest.json"]
        if (
            release_index.get("release_channel") != "main"
            or release_index.get("source_ref") != "refs/heads/main"
            or gpu_manifest.get("completeness") != "complete"
            or gpu_manifest.get("missing_artifacts") not in (None, [])
        ):
            return False
        match = re.fullmatch(
            r"https://github\.com/giraffu/All_bot/actions/runs/([0-9]+)",
            str(release_index.get("ci_run", "")),
        )
        if match is None:
            return False
        try:
            upstream = json.loads(
                self._run(
                    [
                        "gh",
                        "run",
                        "view",
                        match.group(1),
                        "--repo",
                        "giraffu/All_bot",
                        "--json",
                        "status,conclusion,headSha",
                    ]
                )
            )
        except (IntegrationQueueError, json.JSONDecodeError):
            return False
        return (
            isinstance(upstream, Mapping)
            and upstream.get("status") == "completed"
            and upstream.get("conclusion") == "success"
            and upstream.get("headSha") == sha
        )

    def _wait_workflow(self, workflow: str, sha: str, timeout_seconds: int = 7200) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            raw = self._run(
                [
                    "gh", "run", "list", "--workflow", workflow, "--commit", sha,
                    "--json", "databaseId,status,conclusion", "--limit", "1",
                ]
            )
            runs = json.loads(raw or "[]")
            if runs:
                run = runs[0]
                if run.get("status") == "completed":
                    if run.get("conclusion") != "success":
                        if (
                            workflow == "modular-release-v2.yml"
                            and self._published_modular_bundle_is_attested(sha)
                        ):
                            return
                        raise IntegrationQueueError(f"{workflow} failed for {sha}")
                    return
            time.sleep(20)
        raise IntegrationQueueError(f"timed out waiting for {workflow} at {sha}")

    def _wait_pr_merged(self, pr_url: str, *, cwd: Path, timeout_seconds: int = 3600) -> str:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            view = json.loads(
                self._run(
                    ["gh", "pr", "view", pr_url, "--json", "state,mergeCommit"],
                    cwd=cwd,
                )
            )
            if view.get("state") == "MERGED" and view.get("mergeCommit", {}).get("oid"):
                return str(view["mergeCommit"]["oid"])
            if view.get("state") == "CLOSED":
                raise IntegrationQueueError("batch PR closed without merging")
            time.sleep(15)
        raise IntegrationQueueError("timed out waiting for batch PR merge queue")

    def _wait_pr_checks(self, pr_url: str, *, cwd: Path, timeout_seconds: int = 7200) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                self._run(
                    ["gh", "pr", "checks", "--watch", "--fail-fast", pr_url],
                    cwd=cwd,
                    capture=True,
                )
                return
            except IntegrationQueueError as exc:
                if "no checks" not in str(exc).lower():
                    raise
                time.sleep(15)
        raise IntegrationQueueError("timed out waiting for batch PR checks to start")

    def _validate_members(self, members: Sequence[Mapping[str, Any]]) -> None:
        self._git("fetch", "--prune", "origin", "main")
        for raw in members:
            member = _validate_handoff(raw)
            self._git("fetch", "--prune", "origin", member["branch"])
            remote_head = self._git("rev-parse", f"origin/{member['branch']}")
            if remote_head != member["head"]:
                raise IntegrationQueueError(
                    f"handoff head changed after enqueue: {member['branch']}"
                )
            self._run(
                ["git", "merge-base", "--is-ancestor", member["base_sha"], member["head"]]
            )
            self._run(
                ["git", "merge-base", "--is-ancestor", member["base_sha"], "origin/main"]
            )

    def process(self, batch: dict[str, Any]) -> dict[str, Any]:
        members = batch["members"]
        self._validate_members(members)
        temp_root = Path(tempfile.mkdtemp(prefix="allbot-integration-"))
        checkout = temp_root / "checkout"
        branch = str(batch.get("branch") or f"codex/release-batch-{batch['batch']}")
        worktree_added = False
        try:
            self._git("worktree", "add", "--detach", str(checkout), "origin/main")
            worktree_added = True
            stage = str(batch.get("stage") or "queued")
            if stage == "queued":
                self._git("switch", "-c", branch, cwd=checkout)
                for member in members:
                    self._git("merge", "--no-ff", "--no-edit", member["head"], cwd=checkout)
                changed_paths = self._git(
                    "diff", "--name-only", "origin/main...HEAD", cwd=checkout
                ).splitlines()
                scope = classify_paths(changed_paths)
                if scope != "lightweight":
                    plan_path = checkout / "deploy" / "release-batches" / f"{batch['batch']}.json"
                    plan = {
                        "batch": batch["batch"],
                        "base_ref": "origin/main",
                        "base_sha": self._git("rev-parse", "origin/main", cwd=checkout),
                        "members": members,
                        "integration_branch": branch,
                        "pr_base": "main",
                        "container_build_trigger": "main-merge",
                    }
                    _atomic_json(plan_path, plan)
                    self._git("add", str(plan_path.relative_to(checkout)), cwd=checkout)
                    self._git("commit", "-m", f"chore: record integration batch {batch['batch']}", cwd=checkout)
                batch_head = self._git("rev-parse", "HEAD", cwd=checkout)
                self._git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=checkout)
                self.queue.update_batch(
                    batch,
                    stage="creating-pr",
                    branch=branch,
                    batch_head=batch_head,
                    scope=scope,
                )
                stage = "creating-pr"
            if stage == "creating-pr":
                body = "Immutable handoffs:\n" + "\n".join(
                    f"- {item['slot']} `{item['branch']}@{item['head']}`" for item in members
                ) + "\n\nAutomated target: protected `main` then shared `test` only. Production is out of scope."
                existing = json.loads(
                    self._run(
                        [
                            "gh", "pr", "list", "--head", branch, "--state", "all",
                            "--json", "url", "--limit", "1",
                        ],
                        cwd=checkout,
                    )
                )
                pr_url = (
                    str(existing[0]["url"])
                    if existing
                    else self._run(
                        [
                            "gh", "pr", "create", "--base", "main", "--head", branch,
                            "--title", f"chore: integrate {batch['batch']}", "--body", body,
                        ],
                        cwd=checkout,
                    )
                )
                self.queue.update_batch(
                    batch,
                    stage="waiting-pr-ci",
                    pr_url=pr_url,
                )
                stage = "waiting-pr-ci"
            if stage == "waiting-pr-ci":
                pr_url = str(batch["pr_url"])
                view = json.loads(
                    self._run(
                        ["gh", "pr", "view", pr_url, "--json", "state,mergeCommit"],
                        cwd=checkout,
                    )
                )
                if view.get("state") != "MERGED":
                    self._wait_pr_checks(pr_url, cwd=checkout)
                    self._run(
                        [
                            "gh", "pr", "merge", pr_url, "--merge",
                            "--match-head-commit", str(batch["batch_head"]),
                        ],
                        cwd=checkout,
                        capture=False,
                    )
                    view = json.loads(
                        self._run(
                            ["gh", "pr", "view", pr_url, "--json", "state,mergeCommit"],
                            cwd=checkout,
                        )
                    )
                main_sha = self._wait_pr_merged(pr_url, cwd=checkout)
                self.queue.update_batch(batch, stage="waiting-main-ci", main_sha=main_sha)
                stage = "waiting-main-ci"
            main_sha = str(batch["main_sha"])
            if stage == "waiting-main-ci":
                self._wait_workflow("control-plane-release.yml", main_sha)
                if batch.get("scope") == "lightweight":
                    return {
                        "branch": branch,
                        "pr_url": str(batch["pr_url"]),
                        "main_sha": main_sha,
                        "test_status": "skipped-lightweight",
                    }
                self._wait_workflow("modular-release-v2.yml", main_sha)
                self.queue.update_batch(batch, stage="deploying-test")
            self._git("fetch", "origin", "main", cwd=checkout)
            self._git("checkout", "--detach", main_sha, cwd=checkout)
            plan_command, deploy_command = test_deployment_commands(
                checkout, main_sha
            )
            try:
                plan = json.loads(
                    self._run(plan_command, cwd=checkout, capture=True)
                )
            except json.JSONDecodeError as exc:
                raise IntegrationQueueError(
                    "release plan output is invalid"
                ) from exc
            plan_token = plan.get("plan_token") if isinstance(plan, Mapping) else None
            if not isinstance(plan_token, str) or not PLAN_TOKEN_RE.fullmatch(
                plan_token
            ):
                raise IntegrationQueueError(
                    "release plan did not return a reusable plan token"
                )
            deploy_command = test_deployment_commands(
                checkout, main_sha, plan_token
            )[1]
            self._run(deploy_command, cwd=checkout, capture=False)
            return {
                "branch": branch,
                "pr_url": str(batch["pr_url"]),
                "main_sha": main_sha,
            }
        finally:
            if worktree_added:
                try:
                    self._git("worktree", "remove", "--force", str(checkout), cwd=self.repo)
                except IntegrationQueueError:
                    pass
            shutil.rmtree(temp_root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--queue-root", type=Path, default=DEFAULT_QUEUE_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    run = subparsers.add_parser("run-once")
    run.add_argument("--execute", action="store_true")
    retry = subparsers.add_parser("retry-failed")
    retry.add_argument("--batch", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    queue = IntegrationQueue(args.queue_root)
    try:
        if args.command == "status":
            result = queue.status()
        elif args.command == "retry-failed":
            queue.retry_batch(args.batch)
            result = {"status": "requeued", "batch": args.batch}
        elif not args.execute:
            result = {"status": "dry-run", "queue": queue.status()}
        else:
            with queue.lock():
                try:
                    batch = queue.freeze_pending()
                except IntegrationQueueError as exc:
                    if "failed batch blocks" not in str(exc):
                        raise
                    result = {"status": "blocked", "reason": str(exc)}
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    return 0
                if batch is None:
                    result = {"status": "idle"}
                else:
                    try:
                        completed = Coordinator(args.repo, queue).process(batch)
                    except Exception as exc:
                        queue.fail_batch(batch, str(exc))
                        raise
                    queue.complete_batch(batch, **completed)
                    result = {"status": "completed", **completed}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except IntegrationQueueError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
