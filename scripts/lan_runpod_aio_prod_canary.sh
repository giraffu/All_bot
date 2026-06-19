#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
ACTION="preflight"
SLOT="slot0"
PROD_ENV_FILE=".env.cloud.prod"
MODEL_ENV_FILE=".env.lan.model-cache"
AIO_ENV_FILE=".env.lan-aio-prod"
COMPOSE_OUT=""
KEEP_CONTAINER="false"
CONTROL_TTL="3600"

CENTRAL_URL="${LAN_AIO_PROD_CENTRAL_URL:-https://worker-central.aivison.it.com}"
WEB_HEALTH_URL="${LAN_AIO_PROD_WEB_HEALTH_URL:-https://api.aivison.it.com/api/health}"
SSH_HOST="allbot-gpu-002"
REMOTE_BASE="${LAN_AIO_PROD_REMOTE_BASE:-/home/chuzeyu/allbot-runpod-aio-prod-canary}"
REMOTE_WORKERS_SOURCE_DIR="${LAN_AIO_REMOTE_WORKERS_SOURCE_DIR:-remote_workers}"
REMOTE_WORKERS_TARGET_DIR="/workspace/allbot/remote_workers"
REGISTRY_HOST="192.168.1.115:5000"
MODEL_CACHE_READY_URL="http://192.168.1.115:9010/minio/health/ready"

IMG2IMG_IMAGE="${REGISTRY_HOST}/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946"
I2I_PRO_IMAGE="${REGISTRY_HOST}/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh"
WAN22_IMAGE="${REGISTRY_HOST}/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd"

ASSIGNMENT=""
PROFILE=""
HOST_PORT=""
TEMP_AGENT_ID=""
LEGACY_AGENT_ID=""
REMOTE_DIR=""
REMOTE_COMPOSE_FILE=""
REMOTE_ENV_FILE=""
CONTAINER_NAME=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_runpod_aio_prod_canary.sh [options]

Options:
  --action <name>         preflight, render, drain, wait-idle, configure-registry,
                          pull-images, start-heartbeat, enable-canary, drain-temp,
                          restore, stop, status.
  --slot <name>           slot0, slot1, or both for drain/wait-idle/status. Default slot0.
  --dry-run               Print guarded operations only. Default.
  --execute               Run the selected operation.
  --prod-env-file <path>  Cloud prod env file; loaded with an allowlist only.
  --model-env-file <p>    LAN model cache env file; loaded with an allowlist only.
  --aio-env-file <path>   Optional overlay with LAN_AIO_* names. Default .env.lan-aio-prod.
  --compose-out <path>    With --action render --execute, write rendered compose.
  --keep-container        With restore, leave the AIO container running.
  --control-ttl <sec>     TTL for disabled/draining controls. Default 3600.
  -h, --help              Show this help.

Fixed production scope:
  slot0: cloud_prod_worker_06 -> lan_aio_prod_gpu002_gpu0_img2img_lora_01 on 8190
  slot1: cloud_prod_worker_07 -> lan_aio_prod_gpu002_gpu1_image_to_video_01 on 8191
USAGE
}

slot_config() {
  case "$1" in
    slot0)
      ASSIGNMENT="lan-002-8188-worker-06"
      PROFILE="img2img_lora"
      HOST_PORT="8190"
      TEMP_AGENT_ID="lan_aio_prod_gpu002_gpu0_img2img_lora_01"
      LEGACY_AGENT_ID="cloud_prod_worker_06"
      REMOTE_DIR="${REMOTE_BASE}/gpu002-img2img-lora"
      CONTAINER_NAME="allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary"
      ;;
    slot1)
      ASSIGNMENT="lan-002-8189-worker-07"
      PROFILE="image_to_video"
      HOST_PORT="8191"
      TEMP_AGENT_ID="lan_aio_prod_gpu002_gpu1_image_to_video_01"
      LEGACY_AGENT_ID="cloud_prod_worker_07"
      REMOTE_DIR="${REMOTE_BASE}/gpu002-image-to-video"
      CONTAINER_NAME="allbot-lan-aio-gpu-002-gpu1-image_to_video-canary"
      ;;
    *)
      echo "Unsupported slot: $1" >&2
      exit 2
      ;;
  esac
  REMOTE_COMPOSE_FILE="${REMOTE_DIR}/docker-compose.yml"
  REMOTE_ENV_FILE="${REMOTE_DIR}/.env.lan-aio-prod"
}

selected_slots() {
  case "$SLOT" in
    slot0|slot1) printf '%s\n' "$SLOT" ;;
    both) printf '%s\n%s\n' slot0 slot1 ;;
    *)
      echo "Unsupported slot: ${SLOT}" >&2
      exit 2
      ;;
  esac
}

validate_prod_scope() {
  case "$ACTION" in
    preflight|drain|wait-idle|configure-registry|pull-images|status)
      ;;
    render|start-heartbeat|enable-canary|drain-temp|restore|stop)
      if [ "$SLOT" = "both" ]; then
        echo "--slot both is not supported for action ${ACTION}" >&2
        exit 2
      fi
      ;;
    *)
      echo "Unknown action: ${ACTION}" >&2
      usage >&2
      exit 2
      ;;
  esac
  case "$CENTRAL_URL" in
    *test*|*100.82.124.91*)
      echo "Refusing production helper with test Central URL: ${CENTRAL_URL}" >&2
      exit 2
      ;;
  esac
  [ "$SSH_HOST" = "allbot-gpu-002" ] || {
    echo "Refusing unsupported SSH host: ${SSH_HOST}" >&2
    exit 2
  }
}

strip_quotes() {
  local value="$1"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf '%s' "$value"
}

load_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in
      ""|\#*) continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#export }"
    case "$key" in
      AGENT_SECRET_TOKEN|MINIO_ENDPOINT|MINIO_ACCESS_KEY|MINIO_SECRET_KEY|MINIO_SECURE|\
      LAN_AIO_AGENT_SECRET_TOKEN|LAN_AIO_MINIO_ENDPOINT|LAN_AIO_MINIO_ACCESS_KEY|\
      LAN_AIO_MINIO_SECRET_KEY|LAN_MODEL_CACHE_ACCESS_KEY|LAN_MODEL_CACHE_SECRET_KEY)
        value="$(strip_quotes "$value")"
        export "${key}=${value}"
        ;;
    esac
  done < "$file"
}

load_runtime_env() {
  load_env_file "$PROD_ENV_FILE"
  load_env_file "$MODEL_ENV_FILE"
  load_env_file "$AIO_ENV_FILE"
  export LAN_AIO_AGENT_SECRET_TOKEN="${LAN_AIO_AGENT_SECRET_TOKEN:-${AGENT_SECRET_TOKEN:-}}"
  export LAN_AIO_MINIO_ENDPOINT="${LAN_AIO_MINIO_ENDPOINT:-${MINIO_ENDPOINT:-}}"
  export LAN_AIO_MINIO_ACCESS_KEY="${LAN_AIO_MINIO_ACCESS_KEY:-${MINIO_ACCESS_KEY:-}}"
  export LAN_AIO_MINIO_SECRET_KEY="${LAN_AIO_MINIO_SECRET_KEY:-${MINIO_SECRET_KEY:-}}"
}

require_runtime_env() {
  : "${LAN_AIO_AGENT_SECRET_TOKEN:?LAN_AIO_AGENT_SECRET_TOKEN or AGENT_SECRET_TOKEN is required}"
  : "${LAN_AIO_MINIO_ENDPOINT:?LAN_AIO_MINIO_ENDPOINT or MINIO_ENDPOINT is required}"
  : "${LAN_AIO_MINIO_ACCESS_KEY:?LAN_AIO_MINIO_ACCESS_KEY or MINIO_ACCESS_KEY is required}"
  : "${LAN_AIO_MINIO_SECRET_KEY:?LAN_AIO_MINIO_SECRET_KEY or MINIO_SECRET_KEY is required}"
  : "${LAN_MODEL_CACHE_ACCESS_KEY:?LAN_MODEL_CACHE_ACCESS_KEY is required}"
  : "${LAN_MODEL_CACHE_SECRET_KEY:?LAN_MODEL_CACHE_SECRET_KEY is required}"
}

write_runtime_env_file() {
  local out="$1"
  require_runtime_env
  local key value
  for key in \
    LAN_AIO_AGENT_SECRET_TOKEN LAN_AIO_MINIO_ENDPOINT LAN_AIO_MINIO_ACCESS_KEY \
    LAN_AIO_MINIO_SECRET_KEY LAN_MODEL_CACHE_ACCESS_KEY LAN_MODEL_CACHE_SECRET_KEY
  do
    value="${!key}"
    case "$value" in
      *$'\n'*|*$'\r'*)
        echo "Refusing newline in env value for ${key}" >&2
        exit 2
        ;;
    esac
  done
  {
    printf 'LAN_AIO_AGENT_SECRET_TOKEN=%s\n' "$LAN_AIO_AGENT_SECRET_TOKEN"
    printf 'LAN_AIO_MINIO_ENDPOINT=%s\n' "$LAN_AIO_MINIO_ENDPOINT"
    printf 'LAN_AIO_MINIO_ACCESS_KEY=%s\n' "$LAN_AIO_MINIO_ACCESS_KEY"
    printf 'LAN_AIO_MINIO_SECRET_KEY=%s\n' "$LAN_AIO_MINIO_SECRET_KEY"
    printf 'LAN_MODEL_CACHE_ACCESS_KEY=%s\n' "$LAN_MODEL_CACHE_ACCESS_KEY"
    printf 'LAN_MODEL_CACHE_SECRET_KEY=%s\n' "$LAN_MODEL_CACHE_SECRET_KEY"
  } > "$out"
}

control_agent() {
  local agent_id="$1"
  local state="$2"
  local reason="$3"
  local ttl="${4:-}"
  if [ "$MODE" != "execute" ]; then
    if [ -n "$ttl" ] && [ "$state" != "enabled" ]; then
      echo "[dry-run] Would set prod Central control ${agent_id}=${state} ttl=${ttl}"
    else
      echo "[dry-run] Would set prod Central control ${agent_id}=${state}"
    fi
    return 0
  fi
  require_runtime_env
  local body
  if [ -n "$ttl" ] && [ "$state" != "enabled" ]; then
    body="$(printf '{"state":"%s","reason":"%s","ttl_seconds":%s}' "$state" "$reason" "$ttl")"
  else
    body="$(printf '{"state":"%s","reason":"%s"}' "$state" "$reason")"
  fi
  curl -fsS \
    -X POST \
    -H "Authorization: Bearer ${LAN_AIO_AGENT_SECRET_TOKEN}" \
    -H "Content-Type: application/json" \
    --data "$body" \
    "${CENTRAL_URL}/api/agent/task/control/${agent_id}" >/dev/null
}

render_args() {
  printf '%q ' \
    python scripts/gpu_pool_controller.py runtime-render \
    --assignment "$ASSIGNMENT" \
    --profile "$PROFILE" \
    --host-port "$HOST_PORT" \
    --runtime-shape runpod_all_in_one \
    --agent-id "$TEMP_AGENT_ID" \
    --environment cloud-prod
}

patch_compose_remote_workers_mount() {
  local file="$1"
  python3 - "$file" "$CONTAINER_NAME" "${REMOTE_DIR}/remote_workers" "$REMOTE_WORKERS_TARGET_DIR" <<'PY'
from pathlib import Path
import sys

import yaml

path = Path(sys.argv[1])
container_name = sys.argv[2]
source_dir = sys.argv[3]
target_dir = sys.argv[4]

compose = yaml.safe_load(path.read_text()) or {}
service = compose.get("services", {}).get(container_name)
if not isinstance(service, dict):
    raise SystemExit(f"compose service not found: {container_name}")

environment = service.setdefault("environment", {})
environment["RUNPOD_REMOTE_WORKER_ROOT"] = target_dir
environment["PYTHONPATH"] = target_dir
environment["PYTHONDONTWRITEBYTECODE"] = "1"

mount = f"{source_dir}:{target_dir}"
volumes = service.setdefault("volumes", [])
if mount not in volumes:
    volumes.append(mount)

runtime = compose.setdefault("x-allbot-runtime", {})
runtime["remote_workers_bundle"] = {
    "source": source_dir,
    "target": target_dir,
    "mode": "host_mount_current_bundle",
}

path.write_text(yaml.safe_dump(compose, allow_unicode=True, sort_keys=False))
PY
}

render_compose_to() {
  local out="$1"
  python scripts/gpu_pool_controller.py runtime-render \
    --assignment "$ASSIGNMENT" \
    --profile "$PROFILE" \
    --host-port "$HOST_PORT" \
    --runtime-shape runpod_all_in_one \
    --agent-id "$TEMP_AGENT_ID" \
    --environment cloud-prod > "$out"
  patch_compose_remote_workers_mount "$out"
  assert_prod_compose "$out"
}

assert_prod_compose() {
  local file="$1"
  grep -q "RUNPOD_ENVIRONMENT: cloud-prod" "$file"
  grep -q "CENTRAL_API_URL: https://worker-central.aivison.it.com" "$file"
  grep -q "MINIO_RESULT_BUCKET: user-data-prod" "$file"
  grep -q "production_port_unchanged: true" "$file"
  if grep -q "cloud-test\\|user-data-test" "$file"; then
    echo "Refusing compose containing cloud-test/user-data-test" >&2
    exit 2
  fi
}

remote_compose() {
  local op="$1"
  ssh "$SSH_HOST" \
    "cd '${REMOTE_DIR}' && if docker compose version >/dev/null 2>&1; then docker compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; else docker-compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; fi"
}

preseed_slot_hot_caches() {
  if [ "$SLOT" != "slot1" ]; then
    return 0
  fi
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would preseed gpu-002 slot1 RIFE cache into ${CONTAINER_NAME}"
    return 0
  fi
  ssh "$SSH_HOST" "bash -s" <<REMOTE
set -euo pipefail
container='${CONTAINER_NAME}'
src='/data/comfy/inst1/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth'
fallback='/data/comfy/models/upscale_models/rife49.pth'
tmp="/tmp/allbot-\${container}-rife49.pth"
if [ ! -s "\$src" ] && [ -s "\$fallback" ]; then
  src="\$fallback"
fi
if [ ! -s "\$src" ]; then
  echo "Missing gpu-002 slot1 RIFE hot cache: \$src" >&2
  exit 1
fi
cp "\$src" "\$tmp"
for dst in \
  /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth \
  /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth
do
  dst_dir="\$(dirname "\$dst")"
  docker exec "\$container" bash -lc "mkdir -p \"\$dst_dir\""
  docker cp "\$tmp" "\$container:\$dst"
  docker exec "\$container" chmod 0644 "\$dst"
  docker exec "\$container" test -s "\$dst"
done
rm -f "\$tmp"
docker exec "\$container" sh -lc 'ls -lh /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI_Fill-Nodes/nodes/cache/rife_models/rife49.pth /default-comfyui-bundle/ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/rife49.pth'
REMOTE
}

sync_remote_workers_bundle() {
  if [ ! -d "$REMOTE_WORKERS_SOURCE_DIR/comfy_agent" ] || [ ! -d "$REMOTE_WORKERS_SOURCE_DIR/remote_relay" ]; then
    echo "remote_workers bundle source is invalid: ${REMOTE_WORKERS_SOURCE_DIR}" >&2
    exit 2
  fi
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would sync ${REMOTE_WORKERS_SOURCE_DIR} to ${SSH_HOST}:${REMOTE_DIR}/remote_workers"
    return 0
  fi
  if [ -n "${LAN_AIO_GPU_SUDO_PASSWORD:-}" ]; then
    {
      printf '%s\n' "$LAN_AIO_GPU_SUDO_PASSWORD"
      cat <<REMOTE
set -euo pipefail
sudo_cmd() {
  if sudo -n true >/dev/null 2>&1; then
    sudo "\$@"
    return
  fi
  printf '%s\n' "\$LAN_AIO_GPU_SUDO_PASSWORD" | sudo -S -p '' "\$@"
}
mkdir -p '${REMOTE_DIR}'
chmod 700 '${REMOTE_DIR}'
rm -rf '${REMOTE_DIR}/remote_workers.tmp' '${REMOTE_DIR}/remote_workers' 2>/dev/null || sudo_cmd rm -rf '${REMOTE_DIR}/remote_workers.tmp' '${REMOTE_DIR}/remote_workers'
mkdir -p '${REMOTE_DIR}/remote_workers.tmp'
REMOTE
    } | ssh "$SSH_HOST" 'IFS= read -r LAN_AIO_GPU_SUDO_PASSWORD; export LAN_AIO_GPU_SUDO_PASSWORD; bash -s'
  else
    ssh "$SSH_HOST" "set -euo pipefail; mkdir -p '${REMOTE_DIR}'; chmod 700 '${REMOTE_DIR}'; rm -rf '${REMOTE_DIR}/remote_workers.tmp' '${REMOTE_DIR}/remote_workers'; mkdir -p '${REMOTE_DIR}/remote_workers.tmp'"
  fi
  tar \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='*.pyc' \
    --exclude='.mypy_cache' \
    -C "$REMOTE_WORKERS_SOURCE_DIR" \
    -czf - . | ssh "$SSH_HOST" "set -euo pipefail; tar -xzf - -C '${REMOTE_DIR}/remote_workers.tmp'; mv '${REMOTE_DIR}/remote_workers.tmp' '${REMOTE_DIR}/remote_workers'; chmod -R u+rwX,go-rwx '${REMOTE_DIR}/remote_workers'"
}

verify_disabled_heartbeat() {
  python3 - "$CENTRAL_URL" "$TEMP_AGENT_ID" "$PROFILE" <<'PY'
import json
import os
import sys
import time
import urllib.error
import urllib.request

central = sys.argv[1].rstrip("/")
agent_id = sys.argv[2]
profile = sys.argv[3]
token = os.environ.get("LAN_AIO_AGENT_SECRET_TOKEN")
if not token:
    raise SystemExit("LAN_AIO_AGENT_SECRET_TOKEN is required for heartbeat verification")

headers = {"User-Agent": "allbot-lan-aio-prod-canary/1.0"}
auth_headers = {**headers, "Authorization": f"Bearer {token}"}


def load_json(path, headers_):
    request = urllib.request.Request(f"{central}{path}", headers=headers_)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def control_state(payload):
    for candidate in (
        payload,
        payload.get("control") if isinstance(payload.get("control"), dict) else {},
        payload.get("data") if isinstance(payload.get("data"), dict) else {},
    ):
        state = candidate.get("state") if isinstance(candidate, dict) else None
        if state:
            return str(state)
    return None


def find_worker(payload):
    workers = payload.get("workers") or []
    for worker in workers:
        if isinstance(worker, dict) and worker.get("agent_id") == agent_id:
            return worker
    return None


deadline = time.time() + 180
last_seen = None
while time.time() < deadline:
    try:
        control_payload = load_json(f"/api/agent/task/control/{agent_id}", auth_headers)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Failed to read temp agent control state: HTTP {exc.code}") from exc
    state = control_state(control_payload)
    if state != "disabled":
        raise SystemExit(f"Temp agent control is {state!r}; expected 'disabled'")

    workers_payload = load_json("/system/workers", headers)
    worker = find_worker(workers_payload)
    if worker is None:
        marker = "waiting-for-worker"
        if marker != last_seen:
            print(f"Waiting for disabled heartbeat from {agent_id}...")
            last_seen = marker
        time.sleep(5)
        continue

    current_task_type = worker.get("current_task_type")
    status = str(worker.get("status") or "").lower()
    if status == "running" or current_task_type:
        raise SystemExit(
            f"Temp agent {agent_id} picked a task while disabled; "
            f"status={worker.get('status')!r}, "
            f"current_task_type={current_task_type!r}, "
            f"current_task_id={worker.get('current_task_id')!r}. "
            "Restore only after it is safe."
        )

    errors = []
    if worker.get("node_id") != "gpu-002":
        errors.append(f"node_id={worker.get('node_id')!r}")
    if worker.get("provider") != "lan_ssh":
        errors.append(f"provider={worker.get('provider')!r}")
    if worker.get("runtime_profile") != profile:
        errors.append(f"runtime_profile={worker.get('runtime_profile')!r}")
    pool_managed = worker.get("pool_managed")
    if pool_managed not in (True, "true", "True", "1", 1):
        errors.append(f"pool_managed={pool_managed!r}")
    if errors:
        raise SystemExit(
            "Temp agent heartbeat is missing required GPU pool metadata: "
            + ", ".join(errors)
        )

    print(f"Disabled heartbeat verified for {agent_id}.")
    sys.exit(0)

raise SystemExit(f"Timed out waiting for disabled heartbeat from {agent_id}")
PY
}

run_preflight() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would verify prod Central ${CENTRAL_URL}/health"
    echo "[dry-run] Would verify prod Web ${WEB_HEALTH_URL}"
    echo "[dry-run] Would verify ${REGISTRY_HOST}/v2/ and LAN model cache"
    echo "[dry-run] Would verify gpu-002 8188/8189 system_stats and queue"
    echo "[dry-run] Would verify prod /system/workers for cloud_prod_worker_06/07"
    return 0
  fi
  curl -fsS "${CENTRAL_URL}/health" >/dev/null
  curl -fsS "${WEB_HEALTH_URL}" >/dev/null
  curl -fsS "http://${REGISTRY_HOST}/v2/" >/dev/null
  curl -fsS "${MODEL_CACHE_READY_URL}" >/dev/null
  ssh "$SSH_HOST" '
    set -euo pipefail
    curl -fsS http://127.0.0.1:8188/system_stats >/dev/null
    curl -fsS http://127.0.0.1:8188/queue >/dev/null
    curl -fsS http://127.0.0.1:8189/system_stats >/dev/null
    curl -fsS http://127.0.0.1:8189/queue >/dev/null
  '
  curl -fsS "${CENTRAL_URL}/system/workers" >/dev/null
  echo "LAN AIO prod preflight passed."
}

run_render() {
  if [ "$SLOT" = "both" ]; then
    echo "render requires --slot slot0 or --slot slot1" >&2
    exit 2
  fi
  slot_config "$SLOT"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would render production compose:"
    render_args
    echo
    return 0
  fi
  if [ -n "$COMPOSE_OUT" ]; then
    render_compose_to "$COMPOSE_OUT"
    echo "Rendered prod LAN AIO compose to ${COMPOSE_OUT}"
  else
    local tmp_compose
    tmp_compose="$(mktemp)"
    render_compose_to "$tmp_compose"
    cat "$tmp_compose"
    rm -f "$tmp_compose"
  fi
}

run_drain() {
  local slot
  for slot in $(selected_slots); do
    slot_config "$slot"
    control_agent "$LEGACY_AGENT_ID" "draining" "lan_aio_prod_drain_before_canary" "$CONTROL_TTL"
  done
}

run_wait_idle() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would wait until selected legacy workers have no current_task_id"
    echo "[dry-run] Would wait until gpu-002 selected ComfyUI queues are empty"
    return 0
  fi
  python3 - "$CENTRAL_URL" "$(selected_slots | tr '\n' ',' | sed 's/,$//')" <<'PY'
import json
import sys
import time
import urllib.request

central = sys.argv[1].rstrip("/")
slots = [slot for slot in sys.argv[2].split(",") if slot]
legacy = {
    "slot0": "cloud_prod_worker_06",
    "slot1": "cloud_prod_worker_07",
}
targets = {legacy[slot] for slot in slots}
deadline = time.time() + 7200
last = None
while time.time() < deadline:
    request = urllib.request.Request(
        f"{central}/system/workers",
        headers={"User-Agent": "allbot-lan-aio-prod-canary/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    workers = {
        item.get("agent_id"): item
        for item in payload.get("workers", [])
        if isinstance(item, dict)
    }
    busy = {}
    for agent_id in targets:
        worker = workers.get(agent_id, {})
        current_task_type = worker.get("current_task_type")
        current_task_id = worker.get("current_task_id")
        status = str(worker.get("status") or "")
        if current_task_type or status == "running":
            busy[agent_id] = current_task_id or current_task_type or status
    if not busy:
        print("Selected legacy workers are idle.")
        sys.exit(0)
    if busy != last:
        print("Waiting for legacy workers to finish:", sorted(busy))
        last = busy
    time.sleep(15)
raise SystemExit("Timed out waiting for legacy workers to become idle")
PY
  local remote_ports="8188"
  if [ "$SLOT" = "slot1" ]; then
    remote_ports="8189"
  elif [ "$SLOT" = "both" ]; then
    remote_ports="8188 8189"
  fi
  ssh "$SSH_HOST" "python3 - ${remote_ports}" <<'PY'
import json
import sys
import time
import urllib.request

ports = [int(item) for item in sys.argv[1:]]
deadline = time.time() + 900
while time.time() < deadline:
    busy = {}
    for port in ports:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/queue", timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        running = payload.get("queue_running") or []
        pending = payload.get("queue_pending") or []
        if running or pending:
            busy[port] = {"running": len(running), "pending": len(pending)}
    if not busy:
        print("Selected gpu-002 ComfyUI queues are empty.")
        sys.exit(0)
    print("Waiting for ComfyUI queues:", busy)
    time.sleep(10)
raise SystemExit("Timed out waiting for ComfyUI queues to empty")
PY
}

run_configure_registry() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would backup gpu-002 /etc/docker/daemon.json"
    echo "[dry-run] Would add insecure registry ${REGISTRY_HOST} and restart Docker"
    echo "[dry-run] Would verify comfy0/comfy1/node_exporter/dcgm_exporter recover"
    return 0
  fi
  if [ -n "${LAN_AIO_GPU_SUDO_PASSWORD:-}" ]; then
    {
      printf '%s\n' "$LAN_AIO_GPU_SUDO_PASSWORD"
      cat <<'REMOTE'
set -euo pipefail
sudo_cmd() {
  if sudo -n true >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  if [ -z "${LAN_AIO_GPU_SUDO_PASSWORD:-}" ]; then
    echo "sudo password is required to update Docker daemon" >&2
    return 1
  fi
  printf '%s\n' "$LAN_AIO_GPU_SUDO_PASSWORD" | sudo -S -p '' "$@"
}
backup="/etc/docker/daemon.json.allbot-lan-aio-prod-$(date +%Y%m%d%H%M%S).bak"
if [ -f /etc/docker/daemon.json ]; then
  sudo_cmd cp -a /etc/docker/daemon.json "$backup"
fi
python3 - <<'PY' >/tmp/allbot-daemon.json
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
if path.exists():
    data = json.loads(path.read_text() or "{}")
else:
    data = {}
registries = list(data.get("insecure-registries") or [])
if "192.168.1.115:5000" not in registries:
    registries.append("192.168.1.115:5000")
data["insecure-registries"] = sorted(registries)
print(json.dumps(data, indent=2, sort_keys=True))
PY
sudo_cmd install -m 0644 /tmp/allbot-daemon.json /etc/docker/daemon.json
sudo_cmd systemctl restart docker
REMOTE
    } | ssh "$SSH_HOST" 'IFS= read -r LAN_AIO_GPU_SUDO_PASSWORD; export LAN_AIO_GPU_SUDO_PASSWORD; bash -s'
  else
    ssh "$SSH_HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo_cmd() {
  if sudo -n true >/dev/null 2>&1; then
    sudo "$@"
    return
  fi
  echo "sudo password is required to update Docker daemon; set LAN_AIO_GPU_SUDO_PASSWORD for this command" >&2
  return 1
}
backup="/etc/docker/daemon.json.allbot-lan-aio-prod-$(date +%Y%m%d%H%M%S).bak"
if [ -f /etc/docker/daemon.json ]; then
  sudo_cmd cp -a /etc/docker/daemon.json "$backup"
fi
python3 - <<'PY' >/tmp/allbot-daemon.json
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
if path.exists():
    data = json.loads(path.read_text() or "{}")
else:
    data = {}
registries = list(data.get("insecure-registries") or [])
if "192.168.1.115:5000" not in registries:
    registries.append("192.168.1.115:5000")
data["insecure-registries"] = sorted(registries)
print(json.dumps(data, indent=2, sort_keys=True))
PY
sudo_cmd install -m 0644 /tmp/allbot-daemon.json /etc/docker/daemon.json
sudo_cmd systemctl restart docker
REMOTE
  fi
  ssh "$SSH_HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
deadline=$((SECONDS + 240))
while [ "$SECONDS" -lt "$deadline" ]; do
  if docker info 2>/dev/null | grep -q "192.168.1.115:5000"; then
    break
  fi
  sleep 3
done
docker info 2>/dev/null | grep -q "192.168.1.115:5000"
for name in comfy0 comfy1 node_exporter dcgm_exporter; do
  deadline=$((SECONDS + 300))
  while [ "$SECONDS" -lt "$deadline" ]; do
    status="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
    [ "$status" = "running" ] && break
    sleep 5
  done
  status="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || true)"
  if [ "$status" != "running" ]; then
    echo "Container $name did not recover; attempting start" >&2
    docker start "$name" >/dev/null
  fi
done
curl -fsS http://127.0.0.1:8188/system_stats >/dev/null
curl -fsS http://127.0.0.1:8189/system_stats >/dev/null
REMOTE
  echo "gpu-002 Docker insecure registry configured and base containers recovered."
}

run_pull_images() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would docker pull ${IMG2IMG_IMAGE}"
    echo "[dry-run] Would docker pull ${I2I_PRO_IMAGE}"
    echo "[dry-run] Would docker pull ${WAN22_IMAGE}"
    return 0
  fi
  ssh "$SSH_HOST" "docker pull '${IMG2IMG_IMAGE}' && docker pull '${I2I_PRO_IMAGE}' && docker pull '${WAN22_IMAGE}'"
  echo "gpu-002 LAN registry image pulls passed."
}

run_start_heartbeat() {
  slot_config "$SLOT"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would render prod compose and copy it to ${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
    sync_remote_workers_bundle
    echo "[dry-run] Would generate a redacted runtime env file from ${PROD_ENV_FILE}, ${MODEL_ENV_FILE}, ${AIO_ENV_FILE}"
    control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_prod_heartbeat_only" "$CONTROL_TTL"
    echo "[dry-run] Would run docker compose up -d for ${CONTAINER_NAME}"
    preseed_slot_hot_caches
    return 0
  fi
  local tmp_compose tmp_env
  tmp_compose="$(mktemp)"
  tmp_env="$(mktemp)"
  trap 'rm -f "${tmp_compose:-}" "${tmp_env:-}"' EXIT
  render_compose_to "$tmp_compose"
  write_runtime_env_file "$tmp_env"
  control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_prod_heartbeat_only" "$CONTROL_TTL"
  sync_remote_workers_bundle
  ssh "$SSH_HOST" "mkdir -p '${REMOTE_DIR}' && chmod 700 '${REMOTE_DIR}'"
  scp "$tmp_compose" "${SSH_HOST}:${REMOTE_COMPOSE_FILE}" >/dev/null
  scp "$tmp_env" "${SSH_HOST}:${REMOTE_ENV_FILE}" >/dev/null
  ssh "$SSH_HOST" "chmod 600 '${REMOTE_ENV_FILE}'"
  remote_compose "up -d"
  ssh "$SSH_HOST" "bash -s" <<REMOTE
set -euo pipefail
deadline=\$((SECONDS + 1800))
while [ "\$SECONDS" -lt "\$deadline" ]; do
  health="\$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' '${CONTAINER_NAME}' 2>/dev/null || true)"
  if [ "\$health" = "healthy" ]; then
    break
  fi
  echo "Waiting for ${CONTAINER_NAME} health: \${health:-missing}"
  sleep 15
done
docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' '${CONTAINER_NAME}' | grep -q healthy
curl -fsS http://127.0.0.1:${HOST_PORT}/system_stats >/dev/null
docker exec '${CONTAINER_NAME}' bash -lc 'curl -fsS http://127.0.0.1:8013/ready >/dev/null || curl -fsS http://127.0.0.1:8013/health >/dev/null'
REMOTE
  preseed_slot_hot_caches
  verify_disabled_heartbeat
  echo "Prod LAN AIO heartbeat-only container is healthy with temp agent disabled."
}

run_enable_canary() {
  slot_config "$SLOT"
  control_agent "$LEGACY_AGENT_ID" "disabled" "lan_aio_prod_disable_legacy" "$CONTROL_TTL"
  control_agent "$TEMP_AGENT_ID" "enabled" "lan_aio_prod_enable_temp"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would observe production tasks for ${TEMP_AGENT_ID}; other prod workers are not changed."
  else
    echo "Production canary window opened for ${TEMP_AGENT_ID}."
  fi
}

run_drain_temp() {
  slot_config "$SLOT"
  control_agent "$TEMP_AGENT_ID" "draining" "lan_aio_prod_close_temp_after_target_picks" "$CONTROL_TTL"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would stop ${TEMP_AGENT_ID} from popping additional tasks while current work finishes."
  else
    echo "Production canary temp agent is draining for ${TEMP_AGENT_ID}."
  fi
}

run_stop() {
  slot_config "$SLOT"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would run docker compose down for ${CONTAINER_NAME}"
    return 0
  fi
  remote_compose "down"
  echo "Prod LAN AIO container stopped for ${SLOT}."
}

run_restore() {
  slot_config "$SLOT"
  control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_prod_restore_temp_disabled" "$CONTROL_TTL"
  control_agent "$LEGACY_AGENT_ID" "enabled" "lan_aio_prod_restore_legacy_enabled"
  if [ "$KEEP_CONTAINER" = "true" ]; then
    echo "Restore controls applied; container left running by request."
    return 0
  fi
  run_stop
}

run_status() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would show prod Central selected workers and gpu-002 AIO containers."
    return 0
  fi
  python3 - "$CENTRAL_URL" "$SLOT" <<'PY'
import json
import sys
import urllib.request

central = sys.argv[1].rstrip("/")
slot = sys.argv[2]
targets = {
    "slot0": {"cloud_prod_worker_06", "lan_aio_prod_gpu002_gpu0_img2img_lora_01"},
    "slot1": {"cloud_prod_worker_07", "lan_aio_prod_gpu002_gpu1_image_to_video_01"},
    "both": {
        "cloud_prod_worker_06",
        "cloud_prod_worker_07",
        "lan_aio_prod_gpu002_gpu0_img2img_lora_01",
        "lan_aio_prod_gpu002_gpu1_image_to_video_01",
    },
}[slot]
request = urllib.request.Request(
    f"{central}/system/workers",
    headers={"User-Agent": "allbot-lan-aio-prod-canary/1.0"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    payload = json.loads(response.read().decode("utf-8"))
for worker in payload.get("workers", []):
    if worker.get("agent_id") in targets:
        print(json.dumps({
            "agent_id": worker.get("agent_id"),
            "status": worker.get("status"),
            "current_task_id": worker.get("current_task_id"),
            "current_task_type": worker.get("current_task_type"),
            "node_id": worker.get("node_id"),
            "runtime_profile": worker.get("runtime_profile"),
        }, ensure_ascii=False))
PY
  ssh "$SSH_HOST" "docker ps --format '{{.Names}} {{.Status}} {{.Ports}}' | grep -E 'lan-aio|comfy0|comfy1|node_exporter|dcgm_exporter' || true"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --action)
      ACTION="${2:?missing value for --action}"
      shift 2
      ;;
    --slot)
      SLOT="${2:?missing value for --slot}"
      shift 2
      ;;
    --execute)
      MODE="execute"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --prod-env-file)
      PROD_ENV_FILE="${2:?missing value for --prod-env-file}"
      shift 2
      ;;
    --model-env-file)
      MODEL_ENV_FILE="${2:?missing value for --model-env-file}"
      shift 2
      ;;
    --aio-env-file)
      AIO_ENV_FILE="${2:?missing value for --aio-env-file}"
      shift 2
      ;;
    --compose-out)
      COMPOSE_OUT="${2:?missing value for --compose-out}"
      shift 2
      ;;
    --keep-container)
      KEEP_CONTAINER="true"
      shift
      ;;
    --control-ttl)
      CONTROL_TTL="${2:?missing value for --control-ttl}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

validate_prod_scope
load_runtime_env

case "$ACTION" in
  preflight)
    run_preflight
    ;;
  render)
    run_render
    ;;
  drain)
    run_drain
    ;;
  wait-idle)
    run_wait_idle
    ;;
  configure-registry)
    run_configure_registry
    ;;
  pull-images)
    run_pull_images
    ;;
  start-heartbeat)
    run_start_heartbeat
    ;;
  enable-canary)
    run_enable_canary
    ;;
  drain-temp)
    run_drain_temp
    ;;
  restore)
    run_restore
    ;;
  stop)
    run_stop
    ;;
  status)
    run_status
    ;;
esac
