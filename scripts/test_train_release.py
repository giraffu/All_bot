#!/usr/bin/env python3
"""Coordinate the single shared AllBot test-train release lane."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterator, Mapping, Protocol, Sequence


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLOTS = {"A", "B", "C", "D"}
DEFAULT_STATE_ROOT = Path.home() / ".local" / "state" / "allbot" / "test-train"
DEFAULT_BUNDLE_CACHE = (
    Path.home() / ".cache" / "allbot" / "releases" / "test-candidate"
)
CANDIDATE_BUNDLE_REPOSITORY = (
    "ghcr.io/giraffu/allbot-release-v2-test-candidate"
)
MAIN_BUNDLE_REPOSITORY = "ghcr.io/giraffu/allbot-release-v2"
TRACKS = ("control-plane", "test-execution", "gpu-execution")


class TestTrainError(RuntimeError):
    """The shared test train cannot transition safely."""

    __test__ = False


class ReleaseRunner(Protocol):
    def plan(self, sha: str, track: str) -> dict[str, Any]: ...

    def preflight(self, sha: str, track: str) -> None: ...

    def deploy(self, sha: str, track: str) -> None: ...

    def rollback(self, sha: str, track: str) -> None: ...


class ReleaseCLI:
    """Small adapter over release.py for the test-candidate lane."""

    def __init__(
        self,
        *,
        repo: Path,
        bundle_cache: Path = DEFAULT_BUNDLE_CACHE,
        env_file: Path | None = None,
    ) -> None:
        self.repo = repo.resolve()
        self.bundle_cache = bundle_cache.expanduser().resolve()
        self.env_file = env_file.expanduser().resolve() if env_file else None
        self.release_script = self.repo / "scripts" / "release.py"

    def _base(self, command: str, sha: str, track: str) -> list[str]:
        args = [
            sys.executable,
            str(self.release_script),
            command,
            "--env",
            "test",
            "--track",
            track,
            "--sha",
            sha,
            "--bundle-cache",
            str(self.bundle_cache),
            "--bundle-repository",
            CANDIDATE_BUNDLE_REPOSITORY,
        ]
        if self.env_file:
            args.extend(["--env-file", str(self.env_file)])
        return args

    def _run(self, args: Sequence[str]) -> str:
        result = subprocess.run(
            list(args),
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or args[0]
            raise TestTrainError(detail.splitlines()[-1])
        return result.stdout

    def plan(self, sha: str, track: str) -> dict[str, Any]:
        try:
            output = self._run(self._base("plan", sha, track))
        except TestTrainError as exc:
            unavailable = f"{track} track has no available artifacts"
            if track == "gpu-execution" and unavailable in str(exc):
                return {
                    "track": track,
                    "artifacts": {},
                    "services": [],
                    "availability": "unavailable",
                    "reason": unavailable,
                }
            raise
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TestTrainError("release plan output is invalid") from exc
        if not isinstance(value, dict):
            raise TestTrainError("release plan output is invalid")
        return value

    def preflight(self, sha: str, track: str) -> None:
        self._run(self._base("preflight", sha, track))

    def deploy(self, sha: str, track: str) -> None:
        self._run([*self._base("deploy", sha, track), "--execute"])

    def _manifest_path(self, sha: str) -> Path:
        candidates = (
            self.bundle_cache / sha / "release-index.json",
            self.bundle_cache / sha / "release-v2" / "release-index.json",
            self.bundle_cache / sha / "release" / "release-index.json",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        target = self.bundle_cache / sha
        target.mkdir(parents=True, exist_ok=True)
        for repository in (CANDIDATE_BUNDLE_REPOSITORY, MAIN_BUNDLE_REPOSITORY):
            result = subprocess.run(
                ["oras", "pull", f"{repository}:{sha}", "-o", str(target)],
                cwd=self.repo,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                for candidate in candidates:
                    if candidate.is_file():
                        return candidate
        raise TestTrainError(f"rollback bundle is unavailable: {sha}")

    def rollback(self, sha: str, track: str) -> None:
        manifest = self._manifest_path(sha)
        args = self._base("rollback", sha, track)
        args.extend(["--manifest", str(manifest), "--execute"])
        self._run(args)


class TestTrainCoordinator:
    __test__ = False

    def __init__(self, *, state_root: Path = DEFAULT_STATE_ROOT) -> None:
        self.state_root = state_root
        self.state_path = state_root / "current.json"
        self.lock_path = state_root.parent / "test-train.lock"

    @staticmethod
    def _sha(value: str) -> str:
        if not FULL_SHA_RE.fullmatch(value):
            raise TestTrainError("sha must be a full lowercase Git SHA")
        return value

    def _write_state(self, document: Mapping[str, Any]) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(self.state_path)

    @contextmanager
    def acquire_lock(self) -> Iterator[None]:
        self.state_root.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+", encoding="utf-8")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TestTrainError("test train is locked by another integrator") from exc
            handle.seek(0)
            handle.truncate()
            handle.write(str(__import__("os").getpid()))
            handle.flush()
            yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def status(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"status": "idle"}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TestTrainError("test train state is invalid") from exc
        if not isinstance(value, dict):
            raise TestTrainError("test train state is invalid")
        return value

    def record_deployed(
        self, sha: str, *, pr: int, slot: str, tracks: Sequence[str]
    ) -> None:
        sha = self._sha(sha)
        slot = slot.upper()
        if slot not in SLOTS or pr <= 0 or not tracks:
            raise TestTrainError("deployment audit metadata is invalid")
        self._write_state(
            {
                "status": "deployed",
                "sha": sha,
                "pr": pr,
                "slot": slot,
                "tracks": list(dict.fromkeys(tracks)),
                "updated_at": datetime.now().astimezone().isoformat(),
            }
        )

    def _plan_candidate(self, sha: str, *, runner: ReleaseRunner) -> dict[str, Any]:
        sha = self._sha(sha)
        plans = {track: runner.plan(sha, track) for track in TRACKS}
        return {
            "sha": sha,
            "release_channel": "test-candidate",
            "plans": plans,
        }

    def plan_candidate(self, sha: str, *, runner: ReleaseRunner) -> dict[str, Any]:
        with self.acquire_lock():
            return self._plan_candidate(sha, runner=runner)

    def deploy_candidate(
        self,
        sha: str,
        *,
        pr: int,
        slot: str,
        runner: ReleaseRunner,
        skip_test_execution: bool = False,
    ) -> None:
        sha = self._sha(sha)
        slot = slot.upper()
        if slot not in SLOTS or pr <= 0:
            raise TestTrainError("deployment audit metadata is invalid")
        with self.acquire_lock():
            current = self.status()
            if current.get("status") == "blocked" and current.get("slot") != slot:
                raise TestTrainError(
                    "test train is blocked; only the original slot may deploy its forward-fix"
                )
            document = self._plan_candidate(sha, runner=runner)
            plans = document["plans"]
            gpu_artifacts = plans["gpu-execution"].get("artifacts")
            if isinstance(gpu_artifacts, Mapping) and gpu_artifacts:
                raise TestTrainError(
                    "GPU candidate requires its profile canary/operator; shared test train will not mutate it"
                )
            affected = [
                track
                for track in ("control-plane", "test-execution")
                if plans[track].get("artifacts") or plans[track].get("services")
            ]
            if skip_test_execution:
                affected = [track for track in affected if track != "test-execution"]
            if not affected:
                raise TestTrainError("candidate has no control-plane or test-execution changes")
            completed: list[str] = []
            try:
                for track in affected:
                    runner.preflight(sha, track)
                    runner.deploy(sha, track)
                    completed.append(track)
            except Exception as exc:
                rollback_failures: list[str] = []
                for track in reversed(completed):
                    previous_sha = str(plans[track].get("previous_sha") or "")
                    if not FULL_SHA_RE.fullmatch(previous_sha):
                        rollback_failures.append(track)
                        continue
                    try:
                        runner.rollback(previous_sha, track)
                    except Exception:
                        rollback_failures.append(track)
                if rollback_failures:
                    raise TestTrainError(
                        "candidate deployment failed and cross-track rollback is incomplete: "
                        + ", ".join(rollback_failures)
                    ) from exc
                raise TestTrainError(
                    "candidate deployment failed and completed tracks were recovered"
                ) from exc
            self.record_deployed(sha, pr=pr, slot=slot, tracks=affected)

    def block(self, sha: str, reason: str) -> None:
        sha = self._sha(sha)
        if not reason.strip():
            raise TestTrainError("block reason is required")
        with self.acquire_lock():
            current = self.status()
            if current.get("sha") != sha:
                raise TestTrainError("only the currently deployed candidate can be blocked")
            current.update(
                {
                    "status": "blocked",
                    "reason": reason.strip(),
                    "updated_at": datetime.now().astimezone().isoformat(),
                }
            )
            self._write_state(current)

    def accept(self, sha: str, evidence_path: Path) -> None:
        sha = self._sha(sha)
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TestTrainError("candidate evidence is invalid") from exc
        if not isinstance(evidence, dict) or evidence.get("sha") != sha:
            raise TestTrainError("candidate evidence SHA mismatch")
        if (
            evidence.get("slot") not in SLOTS
            or not isinstance(evidence.get("pr"), int)
            or evidence["pr"] <= 0
        ):
            raise TestTrainError("candidate evidence task metadata is invalid")
        tracks = evidence.get("tracks")
        modules = evidence.get("modules")
        if (
            not isinstance(tracks, list)
            or not tracks
            or not all(track in TRACKS for track in tracks)
            or not isinstance(modules, list)
            or not all(isinstance(module, str) and module for module in modules)
        ):
            raise TestTrainError("candidate evidence tracks/modules are invalid")
        smoke = evidence.get("smoke")
        if not isinstance(smoke, dict) or not smoke or not all(value is True for value in smoke.values()):
            raise TestTrainError("all candidate smoke checks must pass")
        for field in ("tested_by", "started_at", "completed_at"):
            if not str(evidence.get(field, "")).strip():
                raise TestTrainError(f"candidate evidence requires {field}")
        try:
            started = datetime.fromisoformat(str(evidence["started_at"]))
            completed = datetime.fromisoformat(str(evidence["completed_at"]))
        except ValueError as exc:
            raise TestTrainError("candidate evidence timestamps are invalid") from exc
        if started.tzinfo is None or completed.tzinfo is None or completed < started:
            raise TestTrainError("candidate evidence timestamps are invalid")
        with self.acquire_lock():
            current = self.status()
            if current.get("sha") != sha or current.get("status") not in {
                "deployed",
                "blocked",
            }:
                raise TestTrainError(
                    "only the currently deployed candidate can be accepted"
                )
            if (
                current.get("pr") != evidence["pr"]
                or current.get("slot") != evidence["slot"]
                or set(current.get("tracks", [])) != set(tracks)
            ):
                raise TestTrainError(
                    "candidate evidence does not match deployment metadata"
                )
            self._write_state(
                {
                    **evidence,
                    "status": "accepted",
                    "evidence": str(evidence_path.resolve()),
                    "updated_at": datetime.now().astimezone().isoformat(),
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle-cache", type=Path, default=DEFAULT_BUNDLE_CACHE)
    parser.add_argument("--env-file", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    plan = subparsers.add_parser("plan")
    plan.add_argument("--sha", required=True)
    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--sha", required=True)
    deploy.add_argument("--pr", type=int, required=True)
    deploy.add_argument("--slot", required=True)
    deploy.add_argument("--execute", action="store_true")
    deploy.add_argument(
        "--skip-test-execution",
        action="store_true",
        help="Deploy only the control-plane and defer test Worker mutation.",
    )
    accept = subparsers.add_parser("accept")
    accept.add_argument("--sha", required=True)
    accept.add_argument("--evidence", type=Path, required=True)
    block = subparsers.add_parser("block")
    block.add_argument("--sha", required=True)
    block.add_argument("--reason", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    coordinator = TestTrainCoordinator(state_root=args.state_root)
    runner = ReleaseCLI(
        repo=args.repo,
        bundle_cache=args.bundle_cache,
        env_file=args.env_file,
    )
    try:
        if args.command == "status":
            result = coordinator.status()
        elif args.command == "plan":
            result = coordinator.plan_candidate(args.sha, runner=runner)
        elif args.command == "deploy":
            if not args.execute:
                raise TestTrainError("candidate deployment requires --execute")
            coordinator.deploy_candidate(
                args.sha,
                pr=args.pr,
                slot=args.slot,
                runner=runner,
                skip_test_execution=args.skip_test_execution,
            )
            result = coordinator.status()
        elif args.command == "accept":
            coordinator.accept(args.sha, args.evidence)
            result = coordinator.status()
        else:
            coordinator.block(args.sha, args.reason)
            result = coordinator.status()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except TestTrainError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
