#!/usr/bin/env bash
set -euo pipefail

runtime_root="${ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime}"
worker_root="${ALLBOT_RUNPOD_REMOTE_WORKERS_DIR:-${runtime_root}/remote_workers}"

test -f "${worker_root}/comfy_agent/agent_main.py"
test -d "${worker_root}/comfy_agent/workflows"
test -f "${worker_root}/requirements.txt"

export ALLBOT_RUNPOD_REPO_DIR="$runtime_root"
export ALLBOT_RUNPOD_REMOTE_WORKERS_DIR="$worker_root"
exec bash /opt/allbot/runpod_bootstrap_from_git.sh
