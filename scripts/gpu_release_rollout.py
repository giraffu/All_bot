#!/usr/bin/env python3
"""Resolve an attested GPU profile for guarded single-slot rollout operators."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

try:
    from scripts.release_manifest_v2 import load_release_index, select_artifacts
    from scripts.release_strategy import validate_gpu_artifact_assurance
except ModuleNotFoundError:  # direct script execution
    from release_manifest_v2 import load_release_index, select_artifacts  # type: ignore[no-redef]
    from release_strategy import validate_gpu_artifact_assurance  # type: ignore[no-redef]


PROFILE_IMAGE_ENV = {
    "img2img": "RUNPOD_IMAGE_NAME_IMG2IMG_LORA",
    "image_to_video": "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
    "wan22_video_v2": "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2",
    "i2i_pro": "RUNPOD_IMAGE_NAME_I2I_PRO",
    "face_swap": "RUNPOD_IMAGE_NAME_FACE_SWAP",
    "scail2": "RUNPOD_IMAGE_NAME_SCAIL2",
    "ltx_video": "RUNPOD_IMAGE_NAME_LTX_VIDEO",
    "pornmaster_flux2_edit": "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    "pornmaster_flux2_edit_bf16": "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
}
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GPURolloutError(RuntimeError):
    pass


def resolve_gpu_artifact(
    index_path: Path,
    *,
    source_sha: str,
    profile: str,
    strategy: str,
) -> dict[str, Any]:
    if strategy not in {"direct", "standard"}:
        raise GPURolloutError("GPU rollout strategy must be direct or standard")
    if not FULL_SHA_RE.fullmatch(source_sha):
        raise GPURolloutError("GPU rollout source SHA must be a full Git SHA")
    try:
        release = load_release_index(index_path, expected_sha=source_sha)
        artifact = dict(select_artifacts(release, "gpu-execution", [profile])[profile])
        validate_gpu_artifact_assurance(strategy, {profile: artifact})
    except (KeyError, RuntimeError) as exc:
        raise GPURolloutError(str(exc)) from exc
    if artifact.get("source_sha") != source_sha:
        raise GPURolloutError("GPU profile was not built from the requested release SHA")
    image_env = PROFILE_IMAGE_ENV.get(profile)
    if not image_env:
        raise GPURolloutError(f"GPU profile has no RunPod image mapping: {profile}")
    return {
        "profile": profile,
        "source_sha": source_sha,
        "strategy": strategy,
        "ref": artifact["ref"],
        "digest": artifact["digest"],
        "oci_revision": artifact["oci_revision"],
        "baked_agent_revision": artifact["baked_agent_revision"],
        "baked_workflow_revision": artifact["baked_workflow_revision"],
        "model_manifest_sha256": artifact["model_manifest"]["sha256"],
        "model_manifest_key": artifact["model_manifest"]["key"],
        "validation_level": artifact.get("validation_level", "canary-verified"),
        "artifact_attestation": artifact.get("artifact_attestation", "verified"),
        "canary_evidence": artifact.get("canary_evidence", "verified"),
        "runpod_image_env": image_env,
    }


def rollout_plan(resolved: dict[str, Any], *, slot: str, operator: str) -> dict[str, Any]:
    if operator not in {"runpod", "lan"}:
        raise GPURolloutError("GPU rollout operator must be runpod or lan")
    if not slot.strip():
        raise GPURolloutError("GPU rollout requires exactly one slot")
    return {
        **resolved,
        "operator": operator,
        "slot": slot,
        "scope": "single-slot",
        "steps": [
            "capture old exact image reference",
            "disable and drain selected slot",
            "start target digest while disabled",
            "verify actual digest and OCI revision",
            "verify process health and disabled heartbeat",
            "enable selected slot",
        ],
        "failure_policy": (
            "stop rollout, restore this slot's old exact image, and keep disabled "
            "if recovery cannot be verified"
        ),
        "forbidden": [
            "whole-host restart",
            "cross-slot batch cleanup",
            "on-host image build",
            "mutable image tag",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-index", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--strategy", choices=("direct", "standard"), required=True)
    parser.add_argument("--operator", choices=("runpod", "lan"), required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument(
        "--field",
        choices=("ref", "digest", "oci_revision", "runpod_image_env"),
    )
    args = parser.parse_args()
    resolved = resolve_gpu_artifact(
        args.release_index,
        source_sha=args.sha,
        profile=args.profile,
        strategy=args.strategy,
    )
    if args.field:
        print(resolved[args.field])
    else:
        print(json.dumps(rollout_plan(resolved, slot=args.slot, operator=args.operator), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GPURolloutError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
