#!/usr/bin/env bash
set -euo pipefail

runtime_root="${ALLBOT_RUNPOD_REPO_DIR:-/opt/allbot/runtime}"
worker_root="${ALLBOT_RUNPOD_WORKER_DIR:-${runtime_root}/runpod_worker}"

test -f "${worker_root}/comfy_agent/agent_main.py"
test -d "${worker_root}/comfy_agent/workflows"
test -f "${worker_root}/requirements.txt"

export ALLBOT_RUNPOD_REPO_DIR="$runtime_root"
export ALLBOT_RUNPOD_WORKER_DIR="$worker_root"
exec bash /opt/allbot/runpod_bootstrap_from_git.sh
