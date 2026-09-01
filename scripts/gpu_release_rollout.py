#!/usr/bin/env python3
"""Send one exact GPU image to one existing RunPod or LAN slot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:([0-9a-f]{64})$")
PROFILE_IMAGE_ENV = {
    "img2img": "RUNPOD_IMAGE_NAME_IMG2IMG_LORA",
    "image_to_video": "RUNPOD_IMAGE_NAME_IMAGE_TO_VIDEO",
    "wan22_video_v2": "RUNPOD_IMAGE_NAME_WAN22_VIDEO_V2",
    "i2i_pro": "RUNPOD_IMAGE_NAME_I2I_PRO",
    "face_swap": "RUNPOD_IMAGE_NAME_FACE_SWAP",
    "scail2": "RUNPOD_IMAGE_NAME_SCAIL2",
    "ltx_video": "RUNPOD_IMAGE_NAME_LTX_VIDEO",
    "ltx_t2v": "RUNPOD_IMAGE_NAME_LTX_T2V",
    "minimax_h3": "RUNPOD_IMAGE_NAME_MINIMAX_H3",
    "pornmaster_flux2_edit": "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
    "pornmaster_flux2_edit_bf16": "RUNPOD_IMAGE_NAME_PORNMASTER_FLUX2_EDIT",
}


class GPURolloutError(RuntimeError):
    pass


def resolve_gpu_artifact(artifact: str, *, profile: str) -> dict[str, Any]:
    match = DIGEST_REF_RE.fullmatch(artifact)
    if not match:
        raise GPURolloutError("GPU artifact must be an exact repository@sha256:digest")
    image_env = PROFILE_IMAGE_ENV.get(profile)
    return {
        "profile": profile,
        "ref": artifact,
        "digest": f"sha256:{match.group(1)}",
        "runpod_image_env": image_env,
    }


def rollout_plan(
    resolved: dict[str, Any], *, slot: str, operator: str
) -> dict[str, Any]:
    if operator not in {"runpod", "lan"}:
        raise GPURolloutError("GPU rollout operator must be runpod or lan")
    if not slot.strip():
        raise GPURolloutError("GPU rollout requires exactly one slot")
    return {
        **resolved,
        "operator": operator,
        "slot": slot,
        "scope": "single-slot",
        "checks": ["exact image identity", "container health", "worker heartbeat"],
        "failure_policy": "restore only this slot's previous exact image",
    }


def operator_command(
    resolved: dict[str, Any], *, slot: str, operator: str, execute: bool
) -> list[str]:
    if operator == "runpod":
        if not resolved.get("runpod_image_env"):
            raise GPURolloutError("GPU profile is not available on RunPod")
        command = [
            "bash",
            str(ROOT / "scripts" / "runpod_prod_ops.sh"),
            "rollout-artifact",
            "--profile",
            str(resolved["profile"]),
            "--slot",
            slot,
            "--artifact",
            str(resolved["ref"]),
        ]
    else:
        command = [
            "python",
            str(ROOT / "scripts" / "lan_aio_fleet_prod_ops.py"),
            "release-rollout",
            "--profile",
            str(resolved["profile"]),
            "--slot",
            slot,
            "--artifact",
            str(resolved["ref"]),
        ]
    if execute:
        command.append("--execute")
    return command


def run(command: Sequence[str]) -> int:
    return subprocess.run(list(command), check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--operator", choices=("runpod", "lan"), required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    resolved = resolve_gpu_artifact(args.artifact, profile=args.profile)
    plan = rollout_plan(resolved, slot=args.slot, operator=args.operator)
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    return run(
        operator_command(
            resolved,
            slot=args.slot,
            operator=args.operator,
            execute=True,
        )
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GPURolloutError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
