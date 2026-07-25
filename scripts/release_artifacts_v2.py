#!/usr/bin/env python3
"""Plan schema-v2 artifact builds and base-image fan-out."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


class ArtifactPlanError(RuntimeError):
    pass


class BuildPlan:
    def __init__(self, *, build: Iterable[str], reuse: Iterable[str], resolve: Iterable[str]):
        self.build = set(build)
        self.reuse = set(reuse)
        self.resolve = set(resolve)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "build": sorted(self.build),
            "reuse": sorted(self.reuse),
            "resolve": sorted(self.resolve),
        }


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactPlanError(f"invalid artifact catalog: {path}") from exc
    if document.get("schema_version") != 2 or not isinstance(document.get("artifacts"), dict):
        raise ArtifactPlanError("artifact catalog schema_version must be 2")
    catalog = document["artifacts"]
    for name, artifact in catalog.items():
        if artifact.get("track") not in {
            "control-plane",
            "test-execution",
            "gpu-execution",
        }:
            raise ArtifactPlanError(f"{name} has an invalid track")
        base = artifact.get("base")
        if base is not None and base not in catalog:
            raise ArtifactPlanError(f"{name} has an unknown base: {base}")
    return catalog


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path.removeprefix("./"), pattern) for pattern in patterns)


def _expand_bases(
    catalog: Mapping[str, Mapping[str, Any]], selected: set[str]
) -> set[str]:
    result = set(selected)
    changed = True
    while changed:
        changed = False
        for name, artifact in catalog.items():
            if name not in result and artifact.get("base") in result:
                result.add(name)
                changed = True
    return result


def plan_selected_builds(
    catalog: Mapping[str, Mapping[str, Any]],
    selected: Iterable[str],
    *,
    has_previous: bool,
) -> BuildPlan:
    """Build an explicit control-plane artifact against the inherited base."""

    requested = set(selected)
    if not has_previous:
        raise ArtifactPlanError("selected release scope requires a previous bundle")
    unknown = requested - set(catalog)
    if unknown:
        raise ArtifactPlanError(
            "selected release scope contains unknown artifacts: "
            + ", ".join(sorted(unknown))
        )
    invalid = {
        name
        for name in requested
        if catalog[name].get("track") != "control-plane"
        or catalog[name].get("kind") == "external-image"
    }
    if invalid:
        raise ArtifactPlanError(
            "selected release scope must contain built control-plane artifacts: "
            + ", ".join(sorted(invalid))
        )
    build = requested
    owned = {
        name
        for name, artifact in catalog.items()
        if artifact.get("kind") != "external-image"
    }
    external = set(catalog) - owned
    return BuildPlan(build=build, reuse=owned - build, resolve=external)


def plan_builds(
    catalog: Mapping[str, Mapping[str, Any]],
    changed_paths: Iterable[str],
    *,
    has_previous: bool,
    previous_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> BuildPlan:
    changed_paths = tuple(changed_paths)
    owned = {
        name
        for name, artifact in catalog.items()
        if artifact.get("kind") != "external-image"
    }
    external = {
        name
        for name, artifact in catalog.items()
        if artifact.get("kind") == "external-image"
    }
    if not has_previous:
        return BuildPlan(build=owned, reuse=(), resolve=external)
    normalized_paths = {path.removeprefix("./") for path in changed_paths}
    catalog_changed = "deploy/release-artifacts-v2.json" in normalized_paths
    if catalog_changed and previous_catalog is None:
        return BuildPlan(build=owned, reuse=(), resolve=external)
    direct = {
        name
        for name, artifact in catalog.items()
        if name in owned
        and any(
            _matches(
                path,
                [
                    *artifact.get("inputs", []),
                    *([artifact["dockerfile"]] if artifact.get("dockerfile") else []),
                ],
            )
            for path in changed_paths
        )
    }
    if catalog_changed:
        direct.update(
            name
            for name in owned
            if previous_catalog.get(name) != catalog.get(name)
        )
    build = _expand_bases(catalog, direct) & owned
    return BuildPlan(build=build, reuse=owned - build, resolve=external)


def build_matrix(
    catalog: Mapping[str, Mapping[str, Any]], plan: BuildPlan
) -> list[dict[str, Any]]:
    pending = set(plan.build)
    ordered: list[str] = []
    while pending:
        ready = sorted(
            name
            for name in pending
            if catalog[name].get("base") not in pending
        )
        if not ready:
            raise ArtifactPlanError("artifact base graph contains a cycle")
        ordered.extend(ready)
        pending.difference_update(ready)
    return [dict(name=name, **catalog[name]) for name in ordered]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("deploy/release-artifacts-v2.json"))
    parser.add_argument("--previous-catalog", type=Path)
    parser.add_argument("--changed-file", type=Path)
    parser.add_argument("--no-previous", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    previous_catalog = (
        load_catalog(args.previous_catalog)
        if args.previous_catalog and args.previous_catalog.is_file()
        else None
    )
    changed = []
    if args.changed_file and args.changed_file.is_file():
        changed = args.changed_file.read_text(encoding="utf-8").splitlines()
    plan = plan_builds(
        catalog,
        changed,
        has_previous=not args.no_previous,
        previous_catalog=previous_catalog,
    )
    document = {**plan.as_dict(), "matrix": {"include": build_matrix(catalog, plan)}}
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"plan={payload}\n")
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
