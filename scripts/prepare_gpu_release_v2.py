#!/usr/bin/env python3
"""Build and attest every GPU profile required by one exact main SHA."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
BUNDLE_REPOSITORY = "ghcr.io/giraffu/allbot-release-v2"
GPU_MANIFEST_REPOSITORY = "ghcr.io/giraffu/allbot-gpu-release-manifests"

WORKFLOWS = {
    "face_swap": (
        "runpod_face_swap_profile_image.yml",
        "ghcr.io/giraffu/allbot-gpu-face-swap",
    ),
    "i2i_pro": (
        "runpod_i2i_pro_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro",
    ),
    "img2img": (
        "runpod_img2img_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-img2img",
    ),
    "ltx_t2v": (
        "runpod_ltx_t2v_profile_image.yml",
        "ghcr.io/giraffu/allbot-gpu-ltx-t2v",
    ),
    "ltx_video": (
        "runpod_ltx_video_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2",
    ),
    "pornmaster_flux2_edit_bf16": (
        "runpod_pornmaster_flux2_edit_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-pornmaster-flux2-edit-baked",
    ),
    "scail2": (
        "runpod_scail2_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-scail2",
    ),
    "image_to_video": (
        "runpod_wan22_profile_image.yml",
        "ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video",
    ),
}
SHARED_IMAGE_PROFILES = {"image_to_video": ("image_to_video", "wan22_video_v2")}


class GPUReleasePreparationError(RuntimeError):
    pass


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise GPUReleasePreparationError(
            detail[-1] if detail else f"command failed: {args[0]}"
        )
    return result.stdout.strip()


def _workflow_inputs(profile: str, sha: str) -> list[str]:
    if profile == "ltx_t2v":
        return ["-f", f"source_sha={sha}", "-f", "verify_public_pull=true"]
    return [
        "-f",
        f"image_tag={sha}",
        "-f",
        "push_image=true",
        "-f",
        "verify_public_pull=true",
    ]


def _find_bundle_dir(root: Path) -> Path:
    for candidate in (root, root / "release-v2", root / "promoted-release"):
        if (candidate / "release-index.json").is_file():
            return candidate
    raise GPUReleasePreparationError("previous release bundle is invalid")


class GPUReleasePreparer:
    def __init__(self, repo: Path, source_sha: str):
        self.repo = repo
        self.source_sha = source_sha
        self.runs: dict[str, int] = {}

    def _remote_exists(self, ref: str) -> bool:
        return subprocess.run(
            ["oras", "manifest", "fetch", ref],
            cwd=self.repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0

    def _workflow_runs(self, workflow: str) -> list[dict[str, Any]]:
        raw = _run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                workflow,
                "--json",
                "databaseId,status,conclusion,headSha",
                "--limit",
                "50",
            ],
            cwd=self.repo,
        )
        value = json.loads(raw or "[]")
        return [
            row
            for row in value
            if isinstance(row, Mapping)
            and row.get("headSha") == self.source_sha
        ]

    def _dispatch_missing_images(self) -> dict[str, set[int]]:
        before: dict[str, set[int]] = {}
        for profile, (workflow, repository) in WORKFLOWS.items():
            ref = f"{repository}:{self.source_sha}"
            existing_runs = self._workflow_runs(workflow)
            before[profile] = {
                int(row["databaseId"])
                for row in existing_runs
                if row.get("databaseId") is not None
            }
            if self._remote_exists(ref):
                successful = next(
                    (
                        row
                        for row in existing_runs
                        if row.get("status") == "completed"
                        and row.get("conclusion") == "success"
                    ),
                    None,
                )
                if successful is None:
                    raise GPUReleasePreparationError(
                        f"{profile} image exists without a successful exact-SHA workflow"
                    )
                self.runs[profile] = int(successful["databaseId"])
                continue
            if any(
                row.get("status") in {"queued", "in_progress", "waiting"}
                for row in existing_runs
            ):
                # Resume observation of the exact-SHA run already in flight.
                # Do not exclude its ID as a pre-dispatch historical run.
                before[profile] = set()
                continue
            _run(
                [
                    "gh",
                    "workflow",
                    "run",
                    workflow,
                    "--ref",
                    "main",
                    *_workflow_inputs(profile, self.source_sha),
                ],
                cwd=self.repo,
            )
        return before

    def _wait_images(
        self,
        before: Mapping[str, set[int]],
        *,
        timeout_seconds: int,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pending = []
            for profile, (workflow, repository) in WORKFLOWS.items():
                if profile in self.runs:
                    continue
                candidates = [
                    row
                    for row in self._workflow_runs(workflow)
                    if int(row.get("databaseId") or 0) not in before[profile]
                ]
                if not candidates:
                    pending.append(profile)
                    continue
                run = candidates[0]
                if run.get("status") != "completed":
                    pending.append(profile)
                    continue
                if run.get("conclusion") != "success":
                    raise GPUReleasePreparationError(
                        f"{profile} image workflow failed"
                    )
                ref = f"{repository}:{self.source_sha}"
                if not self._remote_exists(ref):
                    raise GPUReleasePreparationError(
                        f"{profile} workflow succeeded without an immutable image"
                    )
                self.runs[profile] = int(run["databaseId"])
            if not pending:
                return
            time.sleep(20)
        raise GPUReleasePreparationError(
            "timed out waiting for GPU images: "
            + ", ".join(sorted(set(WORKFLOWS) - set(self.runs)))
        )

    def _previous_gpu_manifest(self, checkout: Path, temp_root: Path) -> dict:
        tags = set(
            _run(["oras", "repo", "tags", BUNDLE_REPOSITORY], cwd=checkout)
            .splitlines()
        )
        ancestry = _run(
            ["git", "rev-list", f"{self.source_sha}^"], cwd=checkout
        ).splitlines()
        previous_sha = next((sha for sha in ancestry if sha in tags), None)
        if previous_sha is None:
            raise GPUReleasePreparationError(
                "no trusted GPU baseline exists in main ancestry"
            )
        target = temp_root / "previous"
        target.mkdir()
        _run(
            [
                "oras",
                "pull",
                f"{BUNDLE_REPOSITORY}:{previous_sha}",
                "-o",
                str(target),
            ],
            cwd=checkout,
        )
        path = _find_bundle_dir(target) / "gpu-execution-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            value.get("completeness") != "complete"
            or value.get("missing_artifacts") not in ([], None)
        ):
            raise GPUReleasePreparationError("previous GPU manifest is incomplete")
        return value

    def _assemble_manifest(
        self,
        checkout: Path,
        temp_root: Path,
        previous: Mapping[str, Any],
    ) -> Path:
        prior_artifacts = previous.get("artifacts")
        if not isinstance(prior_artifacts, Mapping):
            raise GPUReleasePreparationError("previous GPU artifacts are invalid")
        output: Path | None = None
        for build_profile, (_workflow, repository) in WORKFLOWS.items():
            digest = _run(
                ["oras", "resolve", f"{repository}:{self.source_sha}"],
                cwd=checkout,
            )
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise GPUReleasePreparationError(
                    f"{build_profile} image digest is invalid"
                )
            for profile in SHARED_IMAGE_PROFILES.get(
                build_profile, (build_profile,)
            ):
                previous_artifact = prior_artifacts.get(profile)
                if not isinstance(previous_artifact, Mapping):
                    raise GPUReleasePreparationError(
                        f"{profile} is missing from the trusted GPU baseline"
                    )
                evidence = {
                    "profile": profile,
                    "source_sha": self.source_sha,
                    "image_digest": digest,
                    "checks": {
                        "actual_image_digest": True,
                        "baked_agent_revision": True,
                        "baked_workflow_revision": True,
                        "model_manifest_checksum": True,
                    },
                    "model_manifest": previous_artifact.get("model_manifest"),
                    "rollback_target": previous_artifact.get("ref"),
                }
                evidence_path = temp_root / f"{profile}-evidence.json"
                evidence_path.write_text(
                    json.dumps(evidence, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                next_output = temp_root / f"{profile}-manifest.json"
                command = [
                    "python",
                    str(checkout / "scripts/gpu_profile_release_v2.py"),
                    "--profile",
                    profile,
                    "--source-sha",
                    self.source_sha,
                    "--image-ref",
                    f"{repository}@{digest}",
                    "--evidence",
                    str(evidence_path),
                    "--output",
                    str(next_output),
                    "--validation-level",
                    "attested",
                ]
                if output is not None:
                    command.extend(["--previous-manifest", str(output)])
                _run(command, cwd=checkout)
                output = next_output
        if output is None:
            raise GPUReleasePreparationError("GPU manifest was not assembled")
        return output

    def _wait_new_workflow(
        self,
        workflow: str,
        before: set[int],
        *,
        timeout_seconds: int,
    ) -> int:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            candidates = [
                row
                for row in self._workflow_runs(workflow)
                if int(row.get("databaseId") or 0) not in before
            ]
            if candidates:
                run = candidates[0]
                if run.get("status") == "completed":
                    if run.get("conclusion") != "success":
                        raise GPUReleasePreparationError(
                            f"{workflow} failed for {self.source_sha}"
                        )
                    return int(run["databaseId"])
            time.sleep(20)
        raise GPUReleasePreparationError(
            f"timed out waiting for {workflow}"
        )

    def _publish_manifest(self, manifest: Path) -> int | None:
        ref = f"{GPU_MANIFEST_REPOSITORY}:{self.source_sha}"
        if self._remote_exists(ref):
            return None
        workflow = "publish-gpu-release-manifest.yml"
        before = {
            int(row["databaseId"])
            for row in self._workflow_runs(workflow)
            if row.get("databaseId") is not None
        }
        payload = manifest.read_bytes()
        _run(
            [
                "gh",
                "workflow",
                "run",
                workflow,
                "--ref",
                "main",
                "-f",
                f"source_sha={self.source_sha}",
                "-f",
                f"manifest_base64={base64.b64encode(payload).decode()}",
                "-f",
                f"manifest_sha256={hashlib.sha256(payload).hexdigest()}",
            ],
            cwd=self.repo,
        )
        run_id = self._wait_new_workflow(
            workflow, before, timeout_seconds=1800
        )
        if not self._remote_exists(ref):
            raise GPUReleasePreparationError(
                "GPU manifest workflow succeeded without publishing the manifest"
            )
        return run_id

    def _successful_control_plane_run(self) -> int:
        runs = self._workflow_runs("control-plane-release.yml")
        successful = next(
            (
                row
                for row in runs
                if row.get("status") == "completed"
                and row.get("conclusion") == "success"
            ),
            None,
        )
        if successful is None:
            raise GPUReleasePreparationError(
                "successful exact-SHA control-plane CI is missing"
            )
        return int(successful["databaseId"])

    def _build_bundle(self) -> int | None:
        if self._remote_exists(f"{BUNDLE_REPOSITORY}:{self.source_sha}"):
            return None
        workflow = "modular-release-v2.yml"
        before = {
            int(row["databaseId"])
            for row in self._workflow_runs(workflow)
            if row.get("databaseId") is not None
        }
        _run(
            [
                "gh",
                "workflow",
                "run",
                workflow,
                "--ref",
                "main",
                "-f",
                f"source_sha={self.source_sha}",
                "-f",
                "release_channel=main",
                "-f",
                (
                    "gpu_manifest_ref="
                    f"{GPU_MANIFEST_REPOSITORY}:{self.source_sha}"
                ),
                "-f",
                "validation_mode=full",
                "-f",
                f"upstream_run_id={self._successful_control_plane_run()}",
            ],
            cwd=self.repo,
        )
        return self._wait_new_workflow(
            workflow, before, timeout_seconds=14400
        )

    def execute(self, *, timeout_seconds: int) -> dict[str, Any]:
        _run(["git", "fetch", "--prune", "origin", "main"], cwd=self.repo)
        current_main = _run(
            ["git", "rev-parse", "origin/main"], cwd=self.repo
        )
        if current_main != self.source_sha:
            raise GPUReleasePreparationError("source SHA is not current main")
        temp_root = Path(tempfile.mkdtemp(prefix="allbot-gpu-release-"))
        checkout = temp_root / "checkout"
        worktree_added = False
        try:
            _run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(checkout),
                    self.source_sha,
                ],
                cwd=self.repo,
            )
            worktree_added = True
            manifest_ref = (
                f"{GPU_MANIFEST_REPOSITORY}:{self.source_sha}"
            )
            publish_run = None
            if not self._remote_exists(manifest_ref):
                previous = self._previous_gpu_manifest(
                    checkout, temp_root
                )
                before = self._dispatch_missing_images()
                self._wait_images(before, timeout_seconds=timeout_seconds)
                manifest = self._assemble_manifest(
                    checkout, temp_root, previous
                )
                publish_run = self._publish_manifest(manifest)
            bundle_run = self._build_bundle()
            if not self._remote_exists(
                f"{BUNDLE_REPOSITORY}:{self.source_sha}"
            ):
                raise GPUReleasePreparationError(
                    "immutable release bundle is missing after successful build"
                )
            return {
                "status": "ready",
                "source_sha": self.source_sha,
                "gpu_manifest_ref": manifest_ref,
                "image_workflow_runs": self.runs,
                "publish_manifest_run": publish_run,
                "bundle_run": bundle_run,
                "production_deployed": False,
            }
        finally:
            if worktree_added:
                subprocess.run(
                    [
                        "git",
                        "worktree",
                        "remove",
                        "--force",
                        str(checkout),
                    ],
                    cwd=self.repo,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=14400)
    args = parser.parse_args(argv)
    if not SHA_RE.fullmatch(args.source_sha):
        parser.error("--source-sha must be a full lowercase Git SHA")
    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "source_sha": args.source_sha,
                    "profiles": sorted(WORKFLOWS),
                    "production_deployed": False,
                },
                indent=2,
            )
        )
        return 0
    try:
        result = GPUReleasePreparer(
            args.repo, args.source_sha
        ).execute(timeout_seconds=args.timeout_seconds)
    except GPUReleasePreparationError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
