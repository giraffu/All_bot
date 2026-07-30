#!/usr/bin/env python3
"""Fail-closed notice for the retired global release environment validator."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "ERROR: validate-env is retired. The module release CLI validates only the "
        "selected build/deploy target; use scripts/release.py --help.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
