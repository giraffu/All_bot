#!/usr/bin/env bash
set -euo pipefail
echo "ERROR: retired. Build an explicit main SHA module, then use scripts/release.py deploy|status|rollback with an exact digest and --confirm-prod." >&2
exit 2
