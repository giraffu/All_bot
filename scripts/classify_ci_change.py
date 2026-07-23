#!/usr/bin/env python3
"""Classify lightweight, release-tooling, GPU-operator, and runtime changes."""

from __future__ import annotations

import argparse
import ast
import fnmatch
from pathlib import Path
from typing import Iterable, Sequence


LIGHTWEIGHT_PATTERNS = (
    ".codex/**",
    ".github/**",
    "docs/**",
    "tests/**",
    "AGENTS.md",
    "README.md",
    ".gitignore",
    ".markdownlint.yaml",
    "deploy/release-policy.yml",
    "deploy/release-batches/*.json",
    "deploy/test-acceptance.example.json",
    "scripts/doc_quality_checker.py",
    "scripts/manage_ai_workspaces.py",
)

RELEASE_TOOLING_PATTERNS = (
    "scripts/auto_integrate_handoffs.py",
    "scripts/classify_ci_change.py",
    "scripts/release.py",
    "scripts/runtime_env_contract.py",
    "scripts/validate_upstream_ci_run.py",
)

OPERATOR_PATTERNS = (
    "ops/gpu_pool_controller/**",
    "scripts/gpu_pool_controller.py",
    "scripts/gpu_release_rollout.py",
    "scripts/lan_aio_*.py",
    "scripts/lan_aio_*.sh",
    "scripts/lan_*_aio_*.sh",
    "scripts/runpod_prod_ops.sh",
)


class ChangeScopeDecision:
    def __init__(
        self,
        *,
        scope: str,
        release_paths: Iterable[str] = (),
        operator_paths: Iterable[str] = (),
        runtime_paths: Iterable[str] = (),
    ) -> None:
        self.scope = scope
        self.release_paths = tuple(sorted(set(release_paths)))
        self.operator_paths = tuple(sorted(set(operator_paths)))
        self.runtime_paths = tuple(sorted(set(runtime_paths)))

    @property
    def requires_full_ci(self) -> bool:
        return self.scope == "runtime"

    @property
    def requires_operator_ci(self) -> bool:
        return self.scope == "operator"

    @property
    def requires_release_ci(self) -> bool:
        return self.scope == "release-tooling"

    @property
    def requires_release_bundle(self) -> bool:
        return self.scope in {"operator", "runtime"}

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "requires_full_ci": self.requires_full_ci,
            "requires_release_ci": self.requires_release_ci,
            "requires_operator_ci": self.requires_operator_ci,
            "requires_release_bundle": self.requires_release_bundle,
            "release_paths": list(self.release_paths),
            "operator_paths": list(self.operator_paths),
            "runtime_paths": list(self.runtime_paths),
        }


def _is_lightweight(path: str) -> bool:
    normalized = path.removeprefix("./")
    return any(
        fnmatch.fnmatchcase(normalized, pattern) for pattern in LIGHTWEIGHT_PATTERNS
    )


def _is_operator(path: str) -> bool:
    normalized = path.removeprefix("./")
    return any(
        fnmatch.fnmatchcase(normalized, pattern) for pattern in OPERATOR_PATTERNS
    )


def _is_release_tooling(path: str) -> bool:
    normalized = path.removeprefix("./")
    return any(
        fnmatch.fnmatchcase(normalized, pattern)
        for pattern in RELEASE_TOOLING_PATTERNS
    )


def _normalize_changed_path(path: str) -> str:
    normalized = path.strip()
    if normalized.startswith('"') and normalized.endswith('"'):
        try:
            decoded = ast.literal_eval(normalized)
            if isinstance(decoded, str):
                normalized = decoded.encode("latin-1").decode("utf-8")
        except (SyntaxError, ValueError, UnicodeError):
            pass
    return normalized.removeprefix("./")


def classify_change_scope(paths: Iterable[str]) -> ChangeScopeDecision:
    normalized = tuple(
        dict.fromkeys(
            _normalize_changed_path(path) for path in paths if path and path.strip()
        )
    )
    if not normalized:
        return ChangeScopeDecision(
            scope="runtime", runtime_paths=("<empty-change-set>",)
        )
    release_paths = tuple(path for path in normalized if _is_release_tooling(path))
    operator_paths = tuple(path for path in normalized if _is_operator(path))
    runtime_paths = tuple(
        path
        for path in normalized
        if not _is_lightweight(path)
        and not _is_release_tooling(path)
        and not _is_operator(path)
    )
    mixed_focused_scopes = bool(release_paths and operator_paths)
    return ChangeScopeDecision(
        scope=(
            "runtime"
            if runtime_paths or mixed_focused_scopes
            else "operator"
            if operator_paths
            else "release-tooling"
            if release_paths
            else "lightweight"
        ),
        release_paths=release_paths,
        operator_paths=operator_paths,
        runtime_paths=runtime_paths,
    )


def _write_github_output(path: Path, decision: ChangeScopeDecision) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"scope={decision.scope}\n")
        output.write(
            "requires_full_ci="
            + ("true" if decision.requires_full_ci else "false")
            + "\n"
        )
        output.write(
            "requires_release_ci="
            + ("true" if decision.requires_release_ci else "false")
            + "\n"
        )
        output.write(
            "requires_operator_ci="
            + ("true" if decision.requires_operator_ci else "false")
            + "\n"
        )
        output.write(
            "requires_release_bundle="
            + ("true" if decision.requires_release_bundle else "false")
            + "\n"
        )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-file", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = (
        args.changed_file.read_text(encoding="utf-8").splitlines()
        if args.changed_file.is_file()
        else []
    )
    decision = classify_change_scope(paths)
    if args.github_output:
        _write_github_output(args.github_output, decision)
    print(decision.as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
