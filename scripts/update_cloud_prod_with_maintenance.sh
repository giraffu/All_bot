#!/usr/bin/env bash
set -euo pipefail
echo "ERROR: legacy rsync/build deployment is disabled. Use scripts/release.py plan|deploy|rollback with a CI release manifest." >&2
exit 2
