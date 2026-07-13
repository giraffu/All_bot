#!/usr/bin/env bash
set -euo pipefail
echo "ERROR: single-file/single-service sync is disabled. Use scripts/release.py; dependency scope is computed by deploy/release-policy.yml." >&2
exit 2
