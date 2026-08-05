#!/usr/bin/env bash
set -euo pipefail
echo "RETIRED: cloud test is an independent environment and must not be destroyed for production. Use scripts/release.py deploy|status|rollback with an exact-digest module." >&2
exit 2
