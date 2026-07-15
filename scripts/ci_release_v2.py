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
import shutil
import subprocess
from typing import Any

try:
    from scripts.assemble_release_v2 import assemble
    from scripts.release_artifacts_v2 import build_matrix, load_catalog, plan_builds
    from scripts.release_manifest_v2 import load_release_index
except ModuleNotFoundError:
    from assemble_release_v2 import assemble  # type: ignore[no-redef]
    from release_artifacts_v2 import build_matrix, load_catalog, plan_builds  # type: ignore[no-redef]
    from release_manifest_v2 import load_release_index  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]


class CIReleaseError(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path = ROOT) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        raise CIReleaseError(detail[0] if detail else f"command failed: {command[0]}")
    return result.stdout.strip()


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


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
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--changed-file", type=Path, required=True)
    parser.add_argument("--previous-index", type=Path)
    parser.add_argument("--previous-bundle-dir", type=Path)
    parser.add_argument("--gpu-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("release-v2"))
    args = parser.parse_args()

    catalog_path = ROOT / "deploy/release-artifacts-v2.json"
    catalog = load_catalog(catalog_path)
    changed = args.changed_file.read_text(encoding="utf-8").splitlines()
    has_previous = bool(args.previous_index and args.previous_index.is_file())
    plan = plan_builds(catalog, changed, has_previous=has_previous)
    gpu_builds = sorted(name for name in plan.build if catalog[name]["track"] == "gpu-execution")
    unavailable_gpu = set(gpu_builds) if not args.gpu_manifest else set()
    if unavailable_gpu:
        print(
            "GPU profiles omitted pending profile canary evidence: "
            + ", ".join(sorted(unavailable_gpu))
        )

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

    if args.gpu_manifest:
        gpu_document = json.loads(args.gpu_manifest.read_text(encoding="utf-8"))
        for name, artifact in gpu_document["artifacts"].items():
            _write_result(results_dir / f"{name}.json", artifact)
            results[name] = artifact

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
        previous_index=args.previous_index,
        unavailable_artifacts=unavailable_gpu,
    )
    print(index)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CIReleaseError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        raise SystemExit(2)
