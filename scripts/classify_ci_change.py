#!/usr/bin/env python3
"""Classify repository-only changes that do not need runtime CI or release bundles."""

from __future__ import annotations

import argparse
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
    "scripts/classify_ci_change.py",
    "scripts/doc_quality_checker.py",
    "scripts/manage_ai_workspaces.py",
    "scripts/release_strategy.py",
    "scripts/validate_upstream_ci_run.py",
)


class ChangeScopeDecision:
    def __init__(self, *, scope: str, runtime_paths: Iterable[str]) -> None:
        self.scope = scope
        self.runtime_paths = tuple(sorted(set(runtime_paths)))

    @property
    def requires_full_ci(self) -> bool:
        return self.scope != "lightweight"

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "requires_full_ci": self.requires_full_ci,
            "runtime_paths": list(self.runtime_paths),
        }


def _is_lightweight(path: str) -> bool:
    normalized = path.removeprefix("./")
    return any(
        fnmatch.fnmatchcase(normalized, pattern) for pattern in LIGHTWEIGHT_PATTERNS
    )


def classify_change_scope(paths: Iterable[str]) -> ChangeScopeDecision:
    normalized = tuple(
        dict.fromkeys(
            path.removeprefix("./").strip()
            for path in paths
            if path and path.strip()
        )
    )
    if not normalized:
        return ChangeScopeDecision(
            scope="runtime", runtime_paths=("<empty-change-set>",)
        )
    runtime_paths = tuple(path for path in normalized if not _is_lightweight(path))
    return ChangeScopeDecision(
        scope="runtime" if runtime_paths else "lightweight",
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
