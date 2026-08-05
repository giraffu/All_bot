#!/usr/bin/env bash
set -euo pipefail
echo "RETIRED: cloud production full-stack builds are forbidden. Use scripts/release.py build, then deploy|status|rollback one exact-digest module with --confirm-prod." >&2
exit 2
