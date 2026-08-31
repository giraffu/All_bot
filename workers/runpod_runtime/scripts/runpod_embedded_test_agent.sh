#!/usr/bin/env bash
set -euo pipefail

if [ "${RUNPOD_EMBEDDED_TEST_AGENT_ENABLED:-false}" != "true" ]; then
    exit 0
fi

required=(
    RUNPOD_TEST_CENTRAL_API_URL
    RUNPOD_TEST_AGENT_SECRET_TOKEN
    RUNPOD_TEST_MINIO_ENDPOINT
    RUNPOD_TEST_MINIO_ACCESS_KEY
    RUNPOD_TEST_MINIO_SECRET_KEY
)
for name in "${required[@]}"; do
    if [ -z "${!name:-}" ]; then
        echo "Embedded test agent requires ${name}." >&2
        exit 78
    fi
done

worker_root="${RUNPOD_WORKER_ROOT:-${ALLBOT_RUNPOD_WORKER_DIR:-/opt/allbot/runtime/runpod_worker}}"
relay_host="127.0.0.1"
relay_port="${RUNPOD_TEST_LOCAL_RELAY_PORT:-8014}"
pod_id="${RUNPOD_POD_ID:-${POD_ID:-pending}}"
agent_id="${RUNPOD_TEST_AGENT_ID_PREFIX:-runpod_test_ltx25_video_upscale}_${pod_id}"
bucket="${RUNPOD_TEST_MINIO_BUCKET:-user-data-test}"
spool_dir="${RUNPOD_TEST_RESULT_SPOOL_DIR:-./spool/${agent_id}}"
prefetch_dir="${RUNPOD_TEST_PREFETCH_CACHE_DIR:-./prefetch-cache/${agent_id}}"

export CENTRAL_API_URL="$RUNPOD_TEST_CENTRAL_API_URL"
export AGENT_SECRET_TOKEN="$RUNPOD_TEST_AGENT_SECRET_TOKEN"
export MINIO_ENDPOINT="$RUNPOD_TEST_MINIO_ENDPOINT"
export MINIO_ACCESS_KEY="$RUNPOD_TEST_MINIO_ACCESS_KEY"
export MINIO_SECRET_KEY="$RUNPOD_TEST_MINIO_SECRET_KEY"
export MINIO_BUCKET="$bucket"
export MINIO_INPUT_BUCKET="$bucket"
export MINIO_RESULT_BUCKET="$bucket"
export MINIO_TEMPLATE_BUCKET="$bucket"
export LOCAL_RELAY_HOST="$relay_host"
export LOCAL_RELAY_PORT="$relay_port"
export MASTER_API_URL="http://${relay_host}:${relay_port}"
export UPLOAD_SIDECAR_URL="$MASTER_API_URL"
export AGENT_ID="$agent_id"
export SUPPORTED_TASK_TYPES="${RUNPOD_TEST_SUPPORTED_TASK_TYPES:-ltx25_video_upscale}"
export POOL_MANAGED="false"
export POOL_PROVIDER="runpod"
export POOL_NODE_ID="${RUNPOD_TEST_NODE_ID:-runpod-cloud-prod-shared-test}"
export POOL_GPU_INDEX="0"
export POOL_RUNTIME_PROFILE="${RUNPOD_TEST_RUNTIME_PROFILE:-ltx25_video_upscale}"
export PREFETCH_ENABLED="false"
export PIPELINE_ENABLED="false"
export PIPELINE_MAX_RUNNING_TASKS="1"
export RESULT_SPOOL_DIR="$spool_dir"
export PREFETCH_CACHE_DIR="$prefetch_dir"
export COMFY_API_URL="http://127.0.0.1:8188"
export COMFY_WS_URL="ws://127.0.0.1:8188/ws"

mkdir -p "$spool_dir" "$prefetch_dir"
cd "$worker_root"

shutdown_children() {
    local status="${1:-0}"
    trap - INT TERM
    for pid in "${test_agent_pid:-}" "${test_relay_pid:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
    for pid in "${test_agent_pid:-}" "${test_relay_pid:-}"; do
        if [ -n "$pid" ]; then
            wait "$pid" >/dev/null 2>&1 || true
        fi
    done
    exit "$status"
}
trap 'shutdown_children 143' INT TERM

python3 -m runpod_relay.relay_main &
test_relay_pid="$!"
deadline=$(( $(date +%s) + ${RUNPOD_TEST_RELAY_READY_TIMEOUT_SECONDS:-120} ))
until curl -fsS "http://${relay_host}:${relay_port}/ready" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "Embedded test relay did not become ready." >&2
        shutdown_children 75
    fi
    sleep 2
done

python3 "$worker_root/comfy_agent/agent_main.py" &
test_agent_pid="$!"
echo "Embedded LTX25 test worker started agent=${agent_id} relay=${relay_port}"

set +e
wait -n "$test_agent_pid" "$test_relay_pid"
status="$?"
set -e
echo "Embedded LTX25 test worker exited with status ${status}." >&2
shutdown_children "$status"
