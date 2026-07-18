#!/usr/bin/env python3
"""Coordinate the single shared AllBot test-train release lane."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Mapping, Protocol, Sequence

try:
    from scripts.release_manifest_v2 import load_release_index
    from scripts.release_promotion_v2 import PromotionError, build_release_approval
except ModuleNotFoundError:
    from release_manifest_v2 import load_release_index  # type: ignore[no-redef]
    from release_promotion_v2 import (  # type: ignore[no-redef]
        PromotionError,
        build_release_approval,
    )


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLOTS = {"A", "B", "C", "D", "E", "F", "G", "H"}
DEFAULT_STATE_ROOT = Path.home() / ".local" / "state" / "allbot" / "test-train"
DEFAULT_BUNDLE_CACHE = (
    Path.home() / ".cache" / "allbot" / "releases" / "test-candidate"
)
CANDIDATE_BUNDLE_REPOSITORY = (
    "ghcr.io/giraffu/allbot-release-v2-test-candidate"
)
MAIN_BUNDLE_REPOSITORY = "ghcr.io/giraffu/allbot-release-v2"
PROMOTION_REPOSITORY = "ghcr.io/giraffu/allbot-release-v2-promotions"
TRACKS = ("control-plane", "test-execution", "gpu-execution")


class TestTrainError(RuntimeError):
    """The shared test train cannot transition safely."""

    __test__ = False


class ReleaseRunner(Protocol):
    def plan(self, sha: str, track: str) -> dict[str, Any]: ...

    def preflight(self, sha: str, track: str) -> None: ...

    def deploy(self, sha: str, track: str) -> None: ...

    def rollback(self, sha: str, track: str) -> None: ...


class PromotionProvider(Protocol):
    def candidate_snapshot(self, sha: str) -> dict[str, Any]: ...

    def test_runtime_state(self) -> dict[str, Any]: ...

    def publish_approval(self, sha: str, path: Path) -> str: ...


class ReleaseCLI:
    """Small adapter over release.py for the test-candidate lane."""

    def __init__(
        self,
        *,
        repo: Path,
        bundle_cache: Path = DEFAULT_BUNDLE_CACHE,
        env_file: Path | None = None,
        test_state_host: str = "allbot-do-sgp1-test-control",
    ) -> None:
        self.repo = repo.resolve()
        self.bundle_cache = bundle_cache.expanduser().resolve()
        self.env_file = env_file.expanduser().resolve() if env_file else None
        self.test_state_host = test_state_host
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

    def _run(self, args: Sequence[str], *, cwd: Path | None = None) -> str:
        result = subprocess.run(
            list(args),
            cwd=cwd or self.repo,
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

    def candidate_snapshot(self, sha: str) -> dict[str, Any]:
        sha = TestTrainCoordinator._sha(sha)
        index_path = self._manifest_path(sha)
        release = load_release_index(index_path, expected_sha=sha)
        if release.index.get("release_channel") != "test-candidate":
            raise TestTrainError("freeze source must be a test-candidate bundle")
        if release.index.get("validation") != {"mode": "full", "tests": "passed"}:
            raise TestTrainError("candidate bundle has not passed full CI")
        descriptor = self._run(
            [
                "oras",
                "manifest",
                "fetch",
                "--descriptor",
                f"{CANDIDATE_BUNDLE_REPOSITORY}:{sha}",
            ]
        )
        try:
            bundle_digest = json.loads(descriptor)["digest"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise TestTrainError("candidate bundle descriptor is invalid") from exc
        artifacts: dict[str, dict[str, str]] = {}
        # Promotion v1 intentionally covers only the control-plane and Public
        # Web artifact set. test-execution and gpu-execution keep their existing
        # operator/canary release paths.
        for name, raw_artifact in release.manifests["control-plane"].get(
            "artifacts", {}
        ).items():
            if not isinstance(raw_artifact, Mapping):
                continue
            digest = raw_artifact.get("digest") or raw_artifact.get("sha256")
            source_sha = raw_artifact.get("source_sha")
            if isinstance(digest, str) and isinstance(source_sha, str):
                artifacts[str(name)] = {
                    "digest": digest,
                    "source_sha": source_sha,
                }
        if not artifacts:
            raise TestTrainError("candidate bundle contains no promotable artifacts")
        return {
            "schema_version": 1,
            "candidate_sha": sha,
            "candidate_bundle_digest": bundle_digest,
            "artifacts": artifacts,
        }

    def test_runtime_state(self) -> dict[str, Any]:
        output = self._run(
            [
                "ssh",
                self.test_state_host,
                "cat /var/lib/allbot/deployments/test/control-plane/current.json",
            ]
        )
        try:
            state = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TestTrainError("test runtime state is invalid") from exc
        if not isinstance(state, dict):
            raise TestTrainError("test runtime state is invalid")
        return state

    def publish_approval(self, sha: str, path: Path) -> str:
        sha = TestTrainCoordinator._sha(sha)
        reference = f"{PROMOTION_REPOSITORY}:{sha}"
        existing = subprocess.run(
            ["oras", "manifest", "fetch", "--descriptor", reference],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if existing.returncode == 0:
            with tempfile.TemporaryDirectory(prefix="allbot-approval-") as temp:
                pulled = subprocess.run(
                    ["oras", "pull", reference, "-o", temp],
                    cwd=self.repo,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                remote = Path(temp) / path.name
                if pulled.returncode != 0 or not remote.is_file():
                    raise TestTrainError("existing promotion approval cannot be verified")
                if remote.read_bytes() != path.read_bytes():
                    raise TestTrainError("promotion approval tag already contains different bytes")
            return reference
        self._run(
            [
                "oras",
                "push",
                reference,
                f"{path.name}:application/vnd.allbot.release-approval.v1+json",
            ],
            cwd=path.parent,
        )
        return reference


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

    def record_ready_for_acceptance(
        self,
        sha: str,
        *,
        pr: int,
        slot: str,
        tracks: Sequence[str],
        deployment_mode: str,
        deferred_tracks: Sequence[str] = (),
    ) -> None:
        sha = self._sha(sha)
        slot = slot.upper()
        if (
            slot not in SLOTS
            or pr <= 0
            or not tracks
            or deployment_mode not in {"non-runtime", "test-not-required"}
        ):
            raise TestTrainError("acceptance audit metadata is invalid")
        self._write_state(
            {
                "status": "ready-for-acceptance",
                "sha": sha,
                "pr": pr,
                "slot": slot,
                "tracks": list(dict.fromkeys(tracks)),
                "deployment_mode": deployment_mode,
                "deferred_tracks": list(dict.fromkeys(deferred_tracks)),
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
        with_test_execution: bool = False,
    ) -> None:
        sha = self._sha(sha)
        slot = slot.upper()
        if slot not in SLOTS or pr <= 0:
            raise TestTrainError("deployment audit metadata is invalid")
        with self.acquire_lock():
            current = self.status()
            if current.get("status") in {"frozen", "release-approved"}:
                raise TestTrainError(
                    "test train is frozen; abort the unapproved freeze or start a new batch"
                )
            if current.get("status") == "blocked" and current.get("slot") != slot:
                raise TestTrainError(
                    "test train is blocked; only the original slot may deploy its forward-fix"
                )
            document = self._plan_candidate(sha, runner=runner)
            plans = document["plans"]
            runtime_affected = [
                track
                for track in ("control-plane", "test-execution")
                if plans[track].get("artifacts") or plans[track].get("services")
            ]
            control_plan = plans["control-plane"]
            control_test_required = control_plan.get("test_required", True) is not False
            affected = [
                track
                for track in runtime_affected
                if (track == "control-plane" and control_test_required)
                or (track == "test-execution" and with_test_execution)
            ]
            if not affected:
                control_is_non_runtime = (
                    not control_plan.get("artifacts")
                    and not control_plan.get("services")
                )
                deferred_tracks = [
                    track
                    for track in runtime_affected
                    if track == "test-execution" and not with_test_execution
                ]
                control_test_not_required = (
                    bool(control_plan.get("artifacts") or control_plan.get("services"))
                    and not control_test_required
                )
                if not control_is_non_runtime and not control_test_not_required:
                    raise TestTrainError(
                        "candidate has no selected control-plane or test-execution changes"
                    )
                self.record_ready_for_acceptance(
                    sha,
                    pr=pr,
                    slot=slot,
                    tracks=["control-plane"],
                    deployment_mode=(
                        "non-runtime" if control_is_non_runtime else "test-not-required"
                    ),
                    deferred_tracks=deferred_tracks,
                )
                return
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
                    "candidate deployment failed and completed tracks were recovered: "
                    + str(exc)
                ) from exc
            self.record_deployed(sha, pr=pr, slot=slot, tracks=affected)

    def freeze(self, sha: str, *, provider: PromotionProvider) -> None:
        sha = self._sha(sha)
        with self.acquire_lock():
            current = self.status()
            if current.get("status") != "accepted" or current.get("sha") != sha:
                raise TestTrainError("only the currently accepted candidate can be frozen")
            snapshot = provider.candidate_snapshot(sha)
            if snapshot.get("candidate_sha") != sha:
                raise TestTrainError("candidate snapshot SHA mismatch")
            if not isinstance(snapshot.get("artifacts"), Mapping) or not snapshot["artifacts"]:
                raise TestTrainError("candidate snapshot has no artifacts")
            runtime_state = provider.test_runtime_state()
            snapshot = {
                **snapshot,
                "test_runtime_state_digest": self._document_digest(runtime_state),
            }
            frozen_at = datetime.now().astimezone().isoformat()
            self._write_state(
                {
                    **current,
                    "status": "frozen",
                    "accepted_state": current,
                    "frozen": snapshot,
                    "frozen_at": frozen_at,
                    "updated_at": frozen_at,
                }
            )

    def abort_freeze(self) -> None:
        with self.acquire_lock():
            current = self.status()
            if current.get("status") == "release-approved":
                raise TestTrainError("an approved freeze is immutable and cannot be aborted")
            accepted = current.get("accepted_state")
            if current.get("status") != "frozen" or not isinstance(accepted, Mapping):
                raise TestTrainError("there is no unapproved freeze to abort")
            restored = dict(accepted)
            restored["status"] = "accepted"
            restored["updated_at"] = datetime.now().astimezone().isoformat()
            self._write_state(restored)

    @staticmethod
    def _document_digest(document: Mapping[str, Any]) -> str:
        payload = json.dumps(
            dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def approve_release(
        self,
        sha: str,
        evidence_path: Path,
        *,
        approved_by: str,
        provider: PromotionProvider,
    ) -> None:
        sha = self._sha(sha)
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TestTrainError("release evidence is invalid") from exc
        if not isinstance(evidence, dict):
            raise TestTrainError("release evidence is invalid")
        with self.acquire_lock():
            current = self.status()
            frozen = current.get("frozen")
            if (
                current.get("status") != "frozen"
                or current.get("sha") != sha
                or not isinstance(frozen, Mapping)
            ):
                raise TestTrainError("only the matching frozen candidate can be approved")
            runtime_state = provider.test_runtime_state()
            runtime_digest = self._document_digest(runtime_state)
            if frozen.get("test_runtime_state_digest") != runtime_digest:
                raise TestTrainError("test runtime state changed after candidate freeze")
            if evidence.get("test_runtime_state_digest") != runtime_digest:
                raise TestTrainError("test runtime state changed after evidence was recorded")
            runtime_artifacts = runtime_state.get("artifacts")
            if not isinstance(runtime_artifacts, Mapping):
                raise TestTrainError("test runtime state has no artifact digest evidence")
            evidence_artifacts = evidence.get("artifacts")
            if not isinstance(evidence_artifacts, Mapping):
                raise TestTrainError("release evidence artifacts are invalid")
            for name, raw in evidence_artifacts.items():
                if not isinstance(raw, Mapping) or raw.get("status") != "verified":
                    continue
                actual = runtime_artifacts.get(name)
                if not isinstance(actual, Mapping) or actual.get("digest") != raw.get(
                    "digest"
                ):
                    raise TestTrainError(
                        f"{name} verified digest is not running in the test environment"
                    )
            try:
                approval = build_release_approval(
                    frozen=frozen, evidence=evidence, approved_by=approved_by
                )
            except PromotionError as exc:
                raise TestTrainError(str(exc)) from exc
            approval_dir = self.state_root / "approvals"
            approval_dir.mkdir(parents=True, exist_ok=True)
            approval_path = approval_dir / f"{sha}.json"
            if approval_path.exists():
                try:
                    existing = json.loads(approval_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise TestTrainError("existing release approval is invalid") from exc
                if existing != approval:
                    raise TestTrainError("release approval already exists with different content")
            else:
                temp = approval_path.with_suffix(".tmp")
                temp.write_text(
                    json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                temp.replace(approval_path)
            approval_ref = provider.publish_approval(sha, approval_path)
            self._write_state(
                {
                    **current,
                    "status": "release-approved",
                    "approval": str(approval_path.resolve()),
                    "approval_ref": approval_ref,
                    "approved_by": approved_by.strip(),
                    "updated_at": datetime.now().astimezone().isoformat(),
                }
            )

    def block(self, sha: str, reason: str) -> None:
        sha = self._sha(sha)
        if not reason.strip():
            raise TestTrainError("block reason is required")
        with self.acquire_lock():
            current = self.status()
            if current.get("status") in {"frozen", "release-approved"}:
                raise TestTrainError("frozen release batches cannot be blocked or rewritten")
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
                "ready-for-acceptance",
            }:
                raise TestTrainError(
                    "only the current deployed or non-runtime-ready candidate can be accepted"
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
                    **current,
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
    parser.add_argument(
        "--test-state-host", default="allbot-do-sgp1-test-control"
    )
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
        "--with-test-execution",
        action="store_true",
        help="Also deploy the optional test Worker diagnostics track.",
    )
    accept = subparsers.add_parser("accept")
    accept.add_argument("--sha", required=True)
    accept.add_argument("--evidence", type=Path, required=True)
    block = subparsers.add_parser("block")
    block.add_argument("--sha", required=True)
    block.add_argument("--reason", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--sha", required=True)
    approve = subparsers.add_parser("approve-release")
    approve.add_argument("--sha", required=True)
    approve.add_argument("--evidence", type=Path, required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--execute", action="store_true")
    subparsers.add_parser("abort-freeze")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    coordinator = TestTrainCoordinator(state_root=args.state_root)
    runner = ReleaseCLI(
        repo=args.repo,
        bundle_cache=args.bundle_cache,
        env_file=args.env_file,
        test_state_host=args.test_state_host,
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
                with_test_execution=args.with_test_execution,
            )
            result = coordinator.status()
        elif args.command == "accept":
            coordinator.accept(args.sha, args.evidence)
            result = coordinator.status()
        elif args.command == "freeze":
            coordinator.freeze(args.sha, provider=runner)
            result = coordinator.status()
        elif args.command == "approve-release":
            if not args.execute:
                raise TestTrainError("release approval publication requires --execute")
            coordinator.approve_release(
                args.sha,
                args.evidence,
                approved_by=args.approved_by,
                provider=runner,
            )
            result = coordinator.status()
        elif args.command == "abort-freeze":
            coordinator.abort_freeze()
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
