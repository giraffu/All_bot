#!/usr/bin/env python3
"""Compatibility entry for the redacting release environment validator."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    return subprocess.call(
        [sys.executable, str(ROOT / "scripts/release.py"), "validate-env", *sys.argv[1:]],
        cwd=ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
