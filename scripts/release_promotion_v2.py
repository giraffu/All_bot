#!/usr/bin/env python3
"""Validate a frozen test candidate and reuse its exact artifacts on main."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

try:
    from scripts.release_manifest_v2 import TRACKS, load_release_index
except ModuleNotFoundError:
    from release_manifest_v2 import TRACKS, load_release_index  # type: ignore[no-redef]


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_STATUSES = {"verified", "approved-direct"}
REQUIRED_RELEASE_CHECKS = {
    "combination_tests",
    "health",
    "rollback_drill",
    "manual_acceptance",
}
MANIFEST_NAMES = {
    "control-plane": "control-plane-manifest.json",
    "test-execution": "test-execution-manifest.json",
    "gpu-execution": "gpu-execution-manifest.json",
}


class PromotionError(RuntimeError):
    """A candidate cannot be safely promoted without rebuilding."""


def _sha(value: Any, field: str) -> str:
    text = str(value)
    if not FULL_SHA_RE.fullmatch(text):
        raise PromotionError(f"{field} must be a full lowercase Git SHA")
    return text


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise PromotionError(f"{label} must be an object")
    return value


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_promotion_relationship(*, is_ancestor: bool, tree_equal: bool) -> None:
    if not is_ancestor:
        raise PromotionError("approved candidate is not an ancestor of main")
    if not tree_equal:
        raise PromotionError("main tree differs from the approved candidate tree")


def verify_git_promotion(repo: Path, *, main_sha: str, candidate_sha: str) -> None:
    main_sha = _sha(main_sha, "main_sha")
    candidate_sha = _sha(candidate_sha, "candidate_sha")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate_sha, main_sha],
        cwd=repo,
        check=False,
    ).returncode == 0
    tree_equal = subprocess.run(
        ["git", "diff", "--quiet", candidate_sha, main_sha, "--"],
        cwd=repo,
        check=False,
    ).returncode == 0
    validate_promotion_relationship(is_ancestor=ancestor, tree_equal=tree_equal)


def build_release_approval(
    *, frozen: Mapping[str, Any], evidence: Mapping[str, Any], approved_by: str
) -> dict[str, Any]:
    candidate_sha = _sha(frozen.get("candidate_sha"), "candidate_sha")
    if evidence.get("candidate_sha") != candidate_sha:
        raise PromotionError("release evidence candidate SHA does not match frozen batch")
    bundle_digest = str(frozen.get("candidate_bundle_digest", ""))
    if not DIGEST_RE.fullmatch(bundle_digest):
        raise PromotionError("frozen candidate bundle digest is invalid")
    if evidence.get("candidate_bundle_digest") != bundle_digest:
        raise PromotionError("release evidence bundle digest does not match frozen batch")
    runtime_digest = str(evidence.get("test_runtime_state_digest", ""))
    if not DIGEST_RE.fullmatch(runtime_digest):
        raise PromotionError("test runtime state digest is invalid")
    frozen_artifacts = frozen.get("artifacts")
    evidence_artifacts = evidence.get("artifacts")
    if not isinstance(frozen_artifacts, Mapping) or not isinstance(
        evidence_artifacts, Mapping
    ):
        raise PromotionError("release approval artifacts are invalid")
    if set(frozen_artifacts) != set(evidence_artifacts):
        raise PromotionError("release evidence artifact set does not match frozen batch")
    artifacts: dict[str, dict[str, Any]] = {}
    for name, raw_frozen in frozen_artifacts.items():
        raw_evidence = evidence_artifacts.get(name)
        if not isinstance(raw_frozen, Mapping) or not isinstance(raw_evidence, Mapping):
            raise PromotionError(f"{name} approval metadata is invalid")
        expected_digest = str(raw_frozen.get("digest", ""))
        if raw_evidence.get("digest") != expected_digest:
            raise PromotionError(f"{name} digest does not match frozen batch")
        expected_source = _sha(raw_frozen.get("source_sha"), f"{name} source_sha")
        if raw_evidence.get("source_sha") != expected_source:
            raise PromotionError(f"{name} source SHA does not match frozen batch")
        status = str(raw_evidence.get("status", ""))
        if status not in APPROVAL_STATUSES:
            raise PromotionError(f"{name} approval status is invalid")
        evidence_source = str(raw_evidence.get("evidence_source", "")).strip()
        if not evidence_source:
            raise PromotionError(f"{name} evidence_source is required")
        artifacts[str(name)] = {
            "digest": expected_digest,
            "source_sha": expected_source,
            "status": status,
            "evidence_source": evidence_source,
        }
    checks = evidence.get("checks")
    if not isinstance(checks, Mapping) or not checks or not all(
        value is True for value in checks.values()
    ):
        raise PromotionError("all final candidate checks must pass")
    missing_checks = sorted(REQUIRED_RELEASE_CHECKS - set(checks))
    if missing_checks:
        raise PromotionError(
            "release evidence is missing final checks: " + ", ".join(missing_checks)
        )
    try:
        started = datetime.fromisoformat(str(evidence.get("started_at", "")))
        completed = datetime.fromisoformat(str(evidence.get("completed_at", "")))
    except ValueError as exc:
        raise PromotionError("release evidence timestamps are invalid") from exc
    if (
        started.tzinfo is None
        or completed.tzinfo is None
        or completed <= started
    ):
        raise PromotionError("release evidence timestamps are invalid")
    approver = approved_by.strip()
    if not approver:
        raise PromotionError("approved_by is required")
    return {
        "schema_version": 1,
        "status": "approved",
        "candidate_sha": candidate_sha,
        "candidate_bundle_digest": bundle_digest,
        "test_runtime_state_digest": runtime_digest,
        "started_at": str(evidence["started_at"]),
        "completed_at": str(evidence["completed_at"]),
        "approved_by": approver,
        "checks": dict(checks),
        "artifacts": artifacts,
    }


def validate_candidate_approval(
    *,
    candidate_index_path: Path,
    approval_path: Path,
    candidate_sha: str,
    candidate_bundle_digest: str,
) -> dict[str, Any]:
    """Validate that an approval covers the exact immutable candidate bundle."""
    candidate_sha = _sha(candidate_sha, "candidate_sha")
    if not DIGEST_RE.fullmatch(candidate_bundle_digest):
        raise PromotionError("candidate bundle digest is invalid")
    release = load_release_index(candidate_index_path, expected_sha=candidate_sha)
    if release.index.get("release_channel") != "test-candidate":
        raise PromotionError("promotion source must be a test-candidate bundle")
    if release.index.get("validation") != {"mode": "full", "tests": "passed"}:
        raise PromotionError("promotion source must have passed the full candidate CI")
    approval = _read_object(approval_path, "promotion approval")
    if (
        approval.get("status") != "approved"
        or approval.get("candidate_sha") != candidate_sha
        or approval.get("candidate_bundle_digest") != candidate_bundle_digest
    ):
        raise PromotionError("promotion approval does not match the candidate bundle")
    runtime_digest = str(approval.get("test_runtime_state_digest", ""))
    if not DIGEST_RE.fullmatch(runtime_digest):
        raise PromotionError("promotion approval runtime state digest is invalid")
    checks = approval.get("checks")
    if not isinstance(checks, Mapping) or not all(
        checks.get(name) is True for name in REQUIRED_RELEASE_CHECKS
    ):
        raise PromotionError("promotion approval is missing required passed checks")
    if not str(approval.get("approved_by", "")).strip():
        raise PromotionError("promotion approval has no approver")
    control_artifacts = release.manifests["control-plane"].get("artifacts")
    approval_artifacts = approval.get("artifacts")
    if not isinstance(control_artifacts, Mapping) or not isinstance(
        approval_artifacts, Mapping
    ):
        raise PromotionError("promotion approval artifact set is invalid")
    if set(control_artifacts) != set(approval_artifacts):
        raise PromotionError("promotion approval does not cover the control-plane artifact set")
    for name, artifact in control_artifacts.items():
        evidence = approval_artifacts.get(name)
        expected_digest = artifact.get("digest") or artifact.get("sha256")
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("digest") != expected_digest
            or evidence.get("source_sha") != artifact.get("source_sha")
            or evidence.get("status") not in APPROVAL_STATUSES
            or not str(evidence.get("evidence_source", "")).strip()
        ):
            raise PromotionError(
                f"promotion approval does not match candidate artifact: {name}"
            )
    return approval


def assemble_promoted_release(
    *,
    candidate_index_path: Path,
    approval_path: Path,
    output_dir: Path,
    main_sha: str,
    candidate_sha: str,
    candidate_bundle_digest: str,
    ci_run: str,
) -> Path:
    main_sha = _sha(main_sha, "main_sha")
    candidate_sha = _sha(candidate_sha, "candidate_sha")
    if not DIGEST_RE.fullmatch(candidate_bundle_digest):
        raise PromotionError("candidate bundle digest is invalid")
    release = load_release_index(candidate_index_path, expected_sha=candidate_sha)
    approval = validate_candidate_approval(
        candidate_index_path=candidate_index_path,
        approval_path=approval_path,
        candidate_sha=candidate_sha,
        candidate_bundle_digest=candidate_bundle_digest,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for track in TRACKS:
        document = dict(release.manifests[track])
        document["source_sha"] = main_sha
        (output_dir / MANIFEST_NAMES[track]).write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    web_source = candidate_index_path.parent / "public-web-dist.tgz"
    web_artifact = release.manifests["control-plane"]["artifacts"].get("public-web")
    if not isinstance(web_artifact, Mapping):
        raise PromotionError("candidate bundle has no public Web artifact")
    if not web_source.is_file() or file_sha256(web_source) != web_artifact.get("sha256"):
        raise PromotionError("candidate public Web bytes do not match its checksum")
    shutil.copy2(web_source, output_dir / "public-web-dist.tgz")
    approval_target = output_dir / "promotion-approval.json"
    shutil.copy2(approval_path, approval_target)
    approval_checksum = file_sha256(approval_target)
    index = {
        "schema_version": 2,
        "source_sha": main_sha,
        "ci_run": ci_run,
        "release_channel": "main",
        "source_ref": "refs/heads/main",
        "validation": {"mode": "promoted", "tests": "candidate-passed"},
        "promotion": {
            "mode": "candidate-digest-reuse",
            "candidate_sha": candidate_sha,
            "candidate_bundle_digest": candidate_bundle_digest,
            "approval_path": approval_target.name,
            "approval_sha256": approval_checksum,
            "approval_document_sha256": _canonical_sha256(approval),
            "tree_equivalent": True,
        },
        "manifests": MANIFEST_NAMES,
    }
    index_path = output_dir / "release-index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_release_index(index_path, expected_sha=main_sha)
    return index_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-index", type=Path, required=True)
    parser.add_argument("--candidate-bundle-digest", required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        verify_git_promotion(
            args.repo, main_sha=args.main_sha, candidate_sha=args.candidate_sha
        )
        path = assemble_promoted_release(
            candidate_index_path=args.candidate_index,
            approval_path=args.approval,
            output_dir=args.output_dir,
            main_sha=args.main_sha,
            candidate_sha=args.candidate_sha,
            candidate_bundle_digest=args.candidate_bundle_digest,
            ci_run=args.ci_run,
        )
        print(path)
        return 0
    except PromotionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
