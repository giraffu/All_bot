#!/usr/bin/env python3
"""Fail closed for the retired release-integrated test config synchronizer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import sys


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha")
    parser.add_argument("--execute", action="store_true")
    parser.parse_args(argv)
    print(
        "ERROR: sync_test_release_config.py is retired because release.py no "
        "longer owns environment projection commands. Use runtime_env_contract.py "
        "inspect/activate/rollback through an explicitly authorized config SOP.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
