#!/usr/bin/env python3
"""Assemble three environment-neutral manifests from immutable build results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.release_artifacts_v2 import load_catalog
    from scripts.release_manifest_v2 import TRACKS, load_release_index
except ModuleNotFoundError:
    from release_artifacts_v2 import load_catalog  # type: ignore[no-redef]
    from release_manifest_v2 import TRACKS, load_release_index  # type: ignore[no-redef]


class AssembleError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssembleError(f"invalid artifact result: {path}") from exc
    if not isinstance(value, dict):
        raise AssembleError(f"artifact result must be an object: {path}")
    return value


def assemble(
    *,
    catalog_path: Path,
    results_dir: Path,
    output_dir: Path,
    source_sha: str,
    ci_run: str,
    previous_index: Path | None = None,
) -> Path:
    catalog = load_catalog(catalog_path)
    previous: dict[str, Mapping[str, Any]] = {}
    if previous_index:
        previous_document = _read(previous_index)
        previous_release = load_release_index(
            previous_index, expected_sha=str(previous_document.get("source_sha", ""))
        )
        previous = {
            name: artifact
            for manifest in previous_release.manifests.values()
            for name, artifact in manifest["artifacts"].items()
        }

    artifacts: dict[str, dict[str, Any]] = {}
    for name, metadata in catalog.items():
        result_path = results_dir / f"{name}.json"
        if result_path.is_file():
            artifact = _read(result_path)
        elif name in previous:
            artifact = dict(previous[name])
        else:
            raise AssembleError(f"missing build result for {name}")
        artifact.setdefault("dependency_closure", metadata.get("dependency_closure", []))
        base_name = metadata.get("base")
        if base_name:
            if base_name not in artifacts:
                raise AssembleError(f"{name} base result is not ordered before its descendant")
            expected_base = artifacts[base_name].get("digest")
            if artifact.get("base_image_digest") not in {None, expected_base}:
                raise AssembleError(f"{name} was built from a stale base digest")
            artifact["base_image_digest"] = expected_base
        if metadata.get("kind") == "gpu-image":
            profile = metadata["profile"]
            artifact.update(
                {
                    "task_types": profile["task_types"],
                    "baked_agent_revision": artifact.get(
                        "baked_agent_revision", artifact.get("source_sha")
                    ),
                    "baked_workflow_revision": artifact.get(
                        "baked_workflow_revision", artifact.get("source_sha")
                    ),
                    "target_gpu": profile["target_gpu"],
                    "startup_args": profile["startup_args"],
                }
            )
            if "model_manifest" not in artifact:
                raise AssembleError(f"{name} is missing model_manifest evidence")
        artifacts[name] = artifact

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_names = {
        "control-plane": "control-plane-manifest.json",
        "test-execution": "test-execution-manifest.json",
        "gpu-execution": "gpu-execution-manifest.json",
    }
    for track in TRACKS:
        document = {
            "schema_version": 2,
            "track": track,
            "source_sha": source_sha,
            "artifacts": {
                name: artifacts[name]
                for name, metadata in catalog.items()
                if metadata["track"] == track
            },
        }
        (output_dir / manifest_names[track]).write_text(
            json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    index = {
        "schema_version": 2,
        "source_sha": source_sha,
        "ci_run": ci_run,
        "manifests": manifest_names,
    }
    index_path = output_dir / "release-index.json"
    index_path.write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    load_release_index(index_path, expected_sha=source_sha)
    return index_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("deploy/release-artifacts-v2.json"))
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--previous-index", type=Path)
    args = parser.parse_args()
    path = assemble(
        catalog_path=args.catalog,
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        source_sha=args.source_sha,
        ci_run=args.ci_run,
        previous_index=args.previous_index,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
