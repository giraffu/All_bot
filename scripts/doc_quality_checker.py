#!/usr/bin/env python3
"""Lightweight docs quality checks for local markdown assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
README = ROOT / "README.md"
MARKDOWN_FILES = sorted(DOCS_DIR.glob("*.md")) + ([README] if README.exists() else [])
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _normalize_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if not target or target.startswith(
        ("http://", "https://", "mailto:", "file://", "#", "/")
    ):
        return None

    target = target.split("#", 1)[0].strip()
    if not target:
        return None

    return (source.parent / target).resolve()


def _check_heading(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [f"{path.relative_to(ROOT)}: empty markdown file"]
    if not lines[0].startswith("# "):
        return [f"{path.relative_to(ROOT)}: first line must be a level-1 heading"]
    return []


def _check_links(path: Path) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    for raw_target in LINK_RE.findall(content):
        normalized = _normalize_target(path, raw_target)
        if normalized is None:
            continue
        if not normalized.exists():
            errors.append(
                f"{path.relative_to(ROOT)}: broken local link -> {raw_target}"
            )
    return errors


def main() -> int:
    errors: list[str] = []

    if not DOCS_DIR.exists():
        print("docs directory not found", file=sys.stderr)
        return 1

    for markdown_file in MARKDOWN_FILES:
        errors.extend(_check_heading(markdown_file))
        errors.extend(_check_links(markdown_file))

    if errors:
        print("Docs quality check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Docs quality check passed for {len(MARKDOWN_FILES)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
