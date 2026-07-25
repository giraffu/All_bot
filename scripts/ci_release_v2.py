#!/usr/bin/env python3
"""Build changed control/test artifacts and publish one immutable v2 bundle.

GPU artifacts are produced by profile workflows.  Profiles whose inputs changed
without same-SHA canary evidence are omitted and recorded as unavailable in the
bundle; GPU deployment remains gated by the profile-specific manifest.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping

try:
    from scripts.assemble_release_v2 import assemble
    from scripts.release_artifacts_v2 import (
        build_matrix,
        load_catalog,
        plan_builds,
        plan_selected_builds,
    )
    from scripts.release_manifest_v2 import load_release_index
except ModuleNotFoundError:
    from assemble_release_v2 import assemble  # type: ignore[no-redef]
    from release_artifacts_v2 import (  # type: ignore[no-redef]
        build_matrix,
        load_catalog,
        plan_builds,
        plan_selected_builds,
    )
    from release_manifest_v2 import load_release_index  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]


class CIReleaseError(RuntimeError):
    pass


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def _run(command: list[str], *, cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        raise CIReleaseError(detail[0] if detail else f"command failed: {command[0]}")
    return result.stdout.strip()


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _record_artifacts(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    results: dict[str, dict[str, Any]],
    results_dir: Path,
) -> None:
    """Materialize validated artifacts for both planning and final assembly."""

    for name, raw_artifact in artifacts.items():
        artifact = dict(raw_artifact)
        _write_result(results_dir / f"{name}.json", artifact)
        results[name] = artifact


def _digest(ref: str) -> str:
    value = _run(["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{.Manifest.Digest}}"])
    if not value.startswith("sha256:"):
        raise CIReleaseError(f"registry returned an invalid digest for {ref}")
    return value


def _registry_ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref],
        cwd=ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _unavailable_gpu_artifacts(
    catalog: dict[str, dict[str, Any]],
    *,
    planned_builds: set[str],
    available_results: set[str],
    evidence_results: set[str],
) -> set[str]:
    """Carry prior GPU gaps forward and invalidate changed profiles without evidence."""

    gpu_artifacts = {
        name for name, metadata in catalog.items()
        if metadata["track"] == "gpu-execution"
    }
    return (gpu_artifacts - available_results) | (
        planned_builds - evidence_results
    )


def _validated_gpu_evidence(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Mapping[str, Any]],
    source_sha: str,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Validate the profile manifest and identify exact-source attestations."""

    if document.get("track") != "gpu-execution":
        raise CIReleaseError("GPU evidence manifest has the wrong track")
    if document.get("source_sha") != source_sha:
        raise CIReleaseError("GPU evidence manifest source SHA does not match")
    raw_artifacts = document.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        raise CIReleaseError("GPU evidence manifest artifacts are invalid")
    artifacts: dict[str, dict[str, Any]] = {}
    exact_source: set[str] = set()
    for raw_name, raw_artifact in raw_artifacts.items():
        name = str(raw_name)
        if name not in catalog or catalog[name].get("track") != "gpu-execution":
            raise CIReleaseError(f"GPU evidence contains an unknown profile: {name}")
        if not isinstance(raw_artifact, Mapping):
            raise CIReleaseError(f"GPU evidence profile is invalid: {name}")
        artifact = dict(raw_artifact)
        artifacts[name] = artifact
        if artifact.get("source_sha") == source_sha:
            exact_source.add(name)
    return artifacts, exact_source


def _validated_gpu_baseline(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate a complete historical GPU manifest for unchanged-profile reuse.

    The workflow separately proves that the bundle is an immutable main-channel
    ancestor.  This validator deliberately preserves each artifact's original
    source/OCI revision; inherited GPU images are not relabelled as target-SHA
    builds or same-SHA canary evidence.
    """

    if document.get("schema_version") != 2:
        raise CIReleaseError("GPU baseline manifest has the wrong schema")
    if document.get("track") != "gpu-execution":
        raise CIReleaseError("GPU baseline manifest has the wrong track")
    raw_artifacts = document.get("artifacts")
    if not isinstance(raw_artifacts, Mapping):
        raise CIReleaseError("GPU baseline manifest artifacts are invalid")
    expected = {
        name
        for name, metadata in catalog.items()
        if metadata.get("track") == "gpu-execution"
    }
    actual = {str(name) for name in raw_artifacts}
    if actual != expected:
        raise CIReleaseError("GPU baseline profiles must exactly match the catalog")

    artifacts: dict[str, dict[str, Any]] = {}
    for name in sorted(expected):
        raw_artifact = raw_artifacts[name]
        if not isinstance(raw_artifact, Mapping):
            raise CIReleaseError(f"GPU baseline profile is invalid: {name}")
        artifact = dict(raw_artifact)
        digest = str(artifact.get("digest", ""))
        ref = str(artifact.get("ref", ""))
        source_sha = str(artifact.get("source_sha", ""))
        oci_revision = str(artifact.get("oci_revision", ""))
        if artifact.get("kind") != "image":
            raise CIReleaseError(f"GPU baseline profile is not an image: {name}")
        if not _SHA256_RE.fullmatch(digest) or ref.count("@") != 1:
            raise CIReleaseError(f"GPU baseline profile is not digest-pinned: {name}")
        ref_digest = ref.rsplit("@", 1)[1]
        if not _SHA256_RE.fullmatch(ref_digest):
            raise CIReleaseError(f"GPU baseline profile is not digest-pinned: {name}")
        if digest != ref_digest:
            raise CIReleaseError(f"GPU baseline digest does not match ref: {name}")
        if not _GIT_SHA_RE.fullmatch(source_sha) or oci_revision != source_sha:
            raise CIReleaseError(f"GPU baseline revision is invalid: {name}")
        model_manifest = artifact.get("model_manifest")
        if not isinstance(model_manifest, Mapping):
            raise CIReleaseError(f"GPU baseline model manifest is missing: {name}")
        model_sha = str(model_manifest.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", model_sha):
            raise CIReleaseError(f"GPU baseline model manifest is invalid: {name}")
        artifacts[name] = artifact
    return artifacts


def _require_gpu_release_ready(
    release_channel: str,
    unavailable_gpu: set[str],
) -> None:
    if release_channel == "main" and unavailable_gpu:
        raise CIReleaseError(
            "main GPU release is incomplete: " + ", ".join(sorted(unavailable_gpu))
        )


def _build_image(
    *,
    name: str,
    metadata: dict[str, Any],
    source_sha: str,
    image_prefix: str,
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tag = f"{image_prefix}/{metadata['image']}:{source_sha}"
    if _registry_ref_exists(tag):
        raise CIReleaseError(f"immutable image tag already exists: {tag}")
    command = [
        "docker", "buildx", "build", "--push", "-f", metadata["dockerfile"],
        "--build-arg", f"ALLBOT_GIT_SHA={source_sha}", "--tag", tag,
        "--cache-from", f"type=gha,scope={name}",
        "--cache-to", f"type=gha,mode=max,scope={name}",
    ]
    if metadata.get("target"):
        command.extend(["--target", metadata["target"]])
    base = metadata.get("base")
    if base:
        base_ref = results[base]["ref"]
        command.extend(["--build-arg", f"RUNTIME_BASE_IMAGE={base_ref}"])
    command.append(".")
    _run(command)
    digest = _digest(tag)
    return {
        "kind": "image",
        "ref": f"{image_prefix}/{metadata['image']}@{digest}",
        "digest": digest,
        "source_sha": source_sha,
        "oci_revision": source_sha,
        "dependency_closure": metadata.get("dependency_closure", []),
        **({"base_image_digest": results[base]["digest"]} if base else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument(
        "--release-channel", choices=("main", "test-candidate"), default="main"
    )
    parser.add_argument("--source-ref", default="refs/heads/main")
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--changed-file", type=Path, required=True)
    parser.add_argument("--previous-index", type=Path)
    parser.add_argument("--previous-bundle-dir", type=Path)
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--gpu-manifest", type=Path)
    parser.add_argument("--gpu-baseline-manifest", type=Path)
    parser.add_argument("--require-complete-gpu", action="store_true")
    parser.add_argument(
        "--release-artifact",
        action="append",
        default=[],
        help="Build only this control-plane artifact against inherited dependencies.",
    )
    parser.add_argument(
        "--validation-mode",
        choices=("full", "build-only"),
        default="full",
        help="Record whether the upstream test suite ran or was explicitly skipped.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("release-v2"))
    args = parser.parse_args()

    catalog_path = ROOT / "deploy/release-artifacts-v2.json"
    catalog = load_catalog(catalog_path)
    changed = args.changed_file.read_text(encoding="utf-8").splitlines()
    has_previous = bool(args.previous_index and args.previous_index.is_file())
    previous_catalog = (
        load_catalog(args.previous_catalog)
        if args.previous_catalog and args.previous_catalog.is_file()
        else None
    )
    if args.release_artifact:
        plan = plan_selected_builds(
            catalog,
            args.release_artifact,
            has_previous=has_previous,
        )
    else:
        plan = plan_builds(
            catalog,
            changed,
            has_previous=has_previous,
            previous_catalog=previous_catalog,
        )
    gpu_builds = {
        name for name in plan.build
        if catalog[name]["track"] == "gpu-execution"
    }

    output = args.output_dir
    results_dir = output / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    if has_previous:
        previous_document = json.loads(args.previous_index.read_text(encoding="utf-8"))
        previous = load_release_index(
            args.previous_index,
            expected_sha=previous_document["source_sha"],
        )
        results.update(
            {
                name: dict(artifact)
                for manifest in previous.manifests.values()
                for name, artifact in manifest["artifacts"].items()
            }
        )

    evidence_results: set[str] = set()
    if args.gpu_baseline_manifest:
        gpu_baseline_document = json.loads(
            args.gpu_baseline_manifest.read_text(encoding="utf-8")
        )
        gpu_baseline_artifacts = _validated_gpu_baseline(
            gpu_baseline_document,
            catalog=catalog,
        )
        _record_artifacts(
            gpu_baseline_artifacts,
            results=results,
            results_dir=results_dir,
        )

    if args.gpu_manifest:
        gpu_document = json.loads(args.gpu_manifest.read_text(encoding="utf-8"))
        gpu_artifacts, evidence_results = _validated_gpu_evidence(
            gpu_document,
            catalog=catalog,
            source_sha=args.sha,
        )
        _record_artifacts(
            gpu_artifacts,
            results=results,
            results_dir=results_dir,
        )

    unavailable_gpu = _unavailable_gpu_artifacts(
        catalog,
        planned_builds=gpu_builds,
        available_results=set(results),
        evidence_results=evidence_results,
    )
    if unavailable_gpu:
        print(
            "GPU profiles omitted pending profile canary evidence: "
            + ", ".join(sorted(unavailable_gpu))
        )
    if args.require_complete_gpu:
        _require_gpu_release_ready(args.release_channel, unavailable_gpu)

    for row in build_matrix(catalog, plan):
        name = row["name"]
        if row["track"] == "gpu-execution":
            if name in unavailable_gpu:
                continue
            if name not in results:
                raise CIReleaseError(f"GPU manifest does not contain rebuilt profile {name}")
            continue
        if row["kind"] == "tar":
            _run(["npm", "ci"], cwd=ROOT / "frontend")
            _run(["npm", "run", "build"], cwd=ROOT / "frontend")
            archive = output / "public-web-dist.tgz"
            _run(["tar", "-czf", str(archive), "-C", "frontend", "dist"])
            checksum = _run(["sha256sum", str(archive)]).split()[0]
            result = {
                "kind": "tar",
                "ref": archive.name,
                "sha256": checksum,
                "source_sha": args.sha,
                "dependency_closure": [],
            }
        else:
            result = _build_image(
                name=name,
                metadata=row,
                source_sha=args.sha,
                image_prefix=args.image_prefix,
                results=results,
            )
        results[name] = result
        _write_result(results_dir / f"{name}.json", result)

    for name in plan.resolve:
        metadata = catalog[name]
        digest = _digest(metadata["ref"])
        repository = metadata["ref"].split(":", 1)[0]
        result = {
            "kind": "external-image",
            "ref": f"{repository}@{digest}",
            "digest": digest,
            "dependency_closure": [],
        }
        results[name] = result
        _write_result(results_dir / f"{name}.json", result)

    if "public-web" in plan.reuse:
        if not args.previous_bundle_dir:
            raise CIReleaseError("reused public Web artifact requires the previous bundle")
        shutil.copy2(
            args.previous_bundle_dir / "public-web-dist.tgz",
            output / "public-web-dist.tgz",
        )

    index = assemble(
        catalog_path=catalog_path,
        results_dir=results_dir,
        output_dir=output,
        source_sha=args.sha,
        ci_run=args.ci_run,
        release_channel=args.release_channel,
        source_ref=args.source_ref,
        previous_index=args.previous_index,
        unavailable_artifacts=unavailable_gpu,
        validation_mode=args.validation_mode,
    )
    print(index)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CIReleaseError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        raise SystemExit(2)
