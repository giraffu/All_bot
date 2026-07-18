#!/usr/bin/env python3
"""Gate one GPU profile artifact on profile-specific canary evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

try:
    from scripts.release_artifacts_v2 import load_catalog
except ModuleNotFoundError:
    from release_artifacts_v2 import load_catalog  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
DIGEST_REF_RE = re.compile(r"^[^\s@]+@(sha256:[0-9a-f]{64})$")
ATTESTATION_CHECKS = {
    "actual_image_digest",
    "baked_agent_revision",
    "baked_workflow_revision",
    "model_manifest_checksum",
}
CANARY_CHECKS = ATTESTATION_CHECKS | {
    "central_task_type",
    "input_download",
    "output_upload",
    "terminal_callback",
    "rollback_drill",
}


class GPUProfileReleaseError(RuntimeError):
    pass


def _validate_profile_evidence(
    evidence: Mapping[str, Any],
    *,
    profile: str,
    source_sha: str,
    image_ref: str,
    required_checks: set[str],
    validation_level: str,
) -> dict[str, Any]:
    match = DIGEST_REF_RE.fullmatch(image_ref)
    if not match:
        raise GPUProfileReleaseError("GPU image must be digest-pinned")
    digest = match.group(1)
    if evidence.get("profile") != profile or evidence.get("source_sha") != source_sha:
        raise GPUProfileReleaseError("canary profile/source SHA does not match")
    if evidence.get("image_digest") != digest:
        raise GPUProfileReleaseError("canary image digest does not match")
    checks = evidence.get("checks")
    missing = sorted(
        name
        for name in required_checks
        if not isinstance(checks, Mapping) or checks.get(name) is not True
    )
    if missing:
        raise GPUProfileReleaseError(
            f"incomplete GPU {validation_level} checks: " + ", ".join(missing)
        )
    model = evidence.get("model_manifest")
    if (
        not isinstance(model, Mapping)
        or not str(model.get("key", ""))
        or not isinstance(model.get("size"), int)
        or model["size"] <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", str(model.get("sha256", "")))
    ):
        raise GPUProfileReleaseError("model manifest evidence is invalid")
    rollback = str(evidence.get("rollback_target", ""))
    if not DIGEST_REF_RE.fullmatch(rollback):
        raise GPUProfileReleaseError("rollback_target must be digest-pinned")
    catalog = load_catalog(ROOT / "deploy/release-artifacts-v2.json")
    if profile not in catalog or catalog[profile].get("track") != "gpu-execution":
        raise GPUProfileReleaseError(f"unknown GPU profile: {profile}")
    profile_contract = catalog[profile]["profile"]
    return {
        "kind": "image",
        "ref": image_ref,
        "digest": digest,
        "source_sha": source_sha,
        "oci_revision": source_sha,
        "dependency_closure": [],
        "task_types": profile_contract["task_types"],
        "baked_agent_revision": source_sha,
        "baked_workflow_revision": source_sha,
        "model_manifest": dict(model),
        "target_gpu": profile_contract["target_gpu"],
        "startup_args": profile_contract["startup_args"],
        "rollback_target": rollback,
        "artifact_attestation": "verified",
        "validation_level": validation_level,
        "canary_evidence": (
            "verified" if validation_level == "canary-verified" else "waived"
        ),
    }


def validate_artifact_attestation(
    evidence: Mapping[str, Any],
    *,
    profile: str,
    source_sha: str,
    image_ref: str,
) -> dict[str, Any]:
    return _validate_profile_evidence(
        evidence,
        profile=profile,
        source_sha=source_sha,
        image_ref=image_ref,
        required_checks=ATTESTATION_CHECKS,
        validation_level="attested",
    )


def validate_canary_evidence(
    evidence: Mapping[str, Any],
    *,
    profile: str,
    source_sha: str,
    image_ref: str,
) -> dict[str, Any]:
    return _validate_profile_evidence(
        evidence,
        profile=profile,
        source_sha=source_sha,
        image_ref=image_ref,
        required_checks=CANARY_CHECKS,
        validation_level="canary-verified",
    )


def merge_gpu_manifest(
    previous: Mapping[str, Any] | None,
    profile: str,
    result: Mapping[str, Any],
    *,
    source_sha: str,
) -> dict[str, Any]:
    artifacts = dict((previous or {}).get("artifacts", {}))
    artifacts[profile] = dict(result)
    catalog = load_catalog(ROOT / "deploy/release-artifacts-v2.json")
    expected = {
        name for name, metadata in catalog.items() if metadata["track"] == "gpu-execution"
    }
    missing = sorted(expected - set(artifacts))
    return {
        "schema_version": 2,
        "track": "gpu-execution",
        "source_sha": source_sha,
        "artifacts": artifacts,
        "completeness": "incomplete" if missing else "complete",
        "missing_artifacts": missing,
    }


def publish_gpu_manifest(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
    publish_ref: str,
    source_sha: str,
    run_func: Any = subprocess.run,
) -> None:
    """Publish the complete profile manifest to an immutable SHA-tagged OCI ref."""

    if (
        manifest.get("source_sha") != source_sha
        or manifest.get("completeness") != "complete"
        or manifest.get("missing_artifacts") not in ([], ())
    ):
        raise GPUProfileReleaseError("GPU manifest must be complete for the source SHA")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts or any(
        not isinstance(artifact, Mapping)
        or artifact.get("source_sha") != source_sha
        for artifact in artifacts.values()
    ):
        raise GPUProfileReleaseError(
            "GPU manifest artifacts must use the same source SHA"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise GPUProfileReleaseError("source_sha must be a full Git SHA")
    if not publish_ref.endswith(f":{source_sha}"):
        raise GPUProfileReleaseError("GPU manifest ref must use the source SHA tag")
    if not manifest_path.is_file():
        raise GPUProfileReleaseError("GPU manifest output file is missing")
    existing = run_func(
        ["oras", "manifest", "fetch", publish_ref],
        text=True,
        capture_output=True,
        check=False,
    )
    if existing.returncode == 0:
        raise GPUProfileReleaseError("GPU manifest OCI target already exists")
    pushed = run_func(
        [
            "oras",
            "push",
            publish_ref,
            "--artifact-type",
            "application/vnd.allbot.gpu-release-manifest.v2",
            (
                f"{manifest_path.name}:"
                "application/vnd.allbot.release-manifest.v2+json"
            ),
        ],
        cwd=manifest_path.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    if pushed.returncode != 0:
        detail = (
            pushed.stderr.strip().splitlines()[-1:]
            or pushed.stdout.strip().splitlines()[-1:]
        )
        raise GPUProfileReleaseError(
            detail[0] if detail else "failed to publish GPU manifest"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--publish-ref",
        help="Immutable OCI ref ending in :<source-sha>; requires a complete manifest.",
    )
    parser.add_argument(
        "--validation-level",
        choices=("attested", "canary-verified"),
        default="canary-verified",
    )
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    validator = (
        validate_artifact_attestation
        if args.validation_level == "attested"
        else validate_canary_evidence
    )
    result = validator(
        evidence,
        profile=args.profile,
        source_sha=args.source_sha,
        image_ref=args.image_ref,
    )
    previous = (
        json.loads(args.previous_manifest.read_text(encoding="utf-8"))
        if args.previous_manifest
        else None
    )
    manifest = merge_gpu_manifest(
        previous, args.profile, result, source_sha=args.source_sha
    )
    args.output.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if args.publish_ref:
        publish_gpu_manifest(
            manifest,
            manifest_path=args.output,
            publish_ref=args.publish_ref,
            source_sha=args.source_sha,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
