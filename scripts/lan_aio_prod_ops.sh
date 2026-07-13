#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="${ROOT_DIR}/scripts/lan_runpod_aio_prod_canary.sh"

ACTION="status"
MODE="dry-run"
PROD_ENV_FILE=".env.cloud.prod"
AIO_ENV_FILE=".env.lan-aio-prod"
MODEL_ENV_FILE=".env.lan.model-cache"
CONTROL_TTL="3600"
SSH_HOST="allbot-gpu-002"

LEGACY_AGENTS=(cloud_prod_worker_06 cloud_prod_worker_07)
AIO_AGENTS=(
  lan_aio_prod_gpu002_gpu0_img2img_lora_01
  lan_aio_prod_gpu002_gpu1_image_to_video_01
)

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_aio_prod_ops.sh <action> [options]

Actions:
  status       Read-only production AIO status for gpu-002 slot0/slot1.
  enable-aio   Drain legacy worker 06/07, wait idle, then enable AIO agents.
  disable-aio  Drain AIO agents, wait current AIO work done, then disable AIO.
  rollback     Start old ComfyUI + old agents, restore legacy workers, disable AIO.
  stop-old     Stop old comfy0/comfy1 and cloud-prod-comfy-agent-6/7; never delete.

Options:
  --dry-run               Print guarded mutation plan only. Default.
  --execute               Execute the selected mutation.
  --prod-env-file <path>  Cloud prod env file used by underlying helper.
  --aio-env-file <path>   LAN AIO prod env overlay. Default .env.lan-aio-prod.
  --model-env-file <p>    LAN model cache env file. Default .env.lan.model-cache.
  --control-ttl <sec>     TTL used by underlying helper. Default 3600.
  -h, --help              Show this help.
USAGE
}

run_helper() {
  "$HELPER" \
    --prod-env-file "$PROD_ENV_FILE" \
    --aio-env-file "$AIO_ENV_FILE" \
    --model-env-file "$MODEL_ENV_FILE" \
    --control-ttl "$CONTROL_TTL" \
    "$@"
}

dry_run_plan() {
  case "$ACTION" in
    enable-aio)
      cat <<'PLAN'
[dry-run] Would verify AIO 8190/8191 health.
[dry-run] Would set cloud_prod_worker_06/07 to draining.
[dry-run] Would wait until legacy workers and old 8188/8189 queues are idle.
[dry-run] Would disable cloud_prod_worker_06/07 and enable both LAN AIO agents.
PLAN
      ;;
    disable-aio)
      cat <<'PLAN'
[dry-run] Would set both LAN AIO agents to draining.
[dry-run] Would wait until both AIO agents finish current tasks.
[dry-run] Would set both LAN AIO agents to disabled.
[dry-run] Legacy cloud_prod_worker_06/07 would remain disabled.
PLAN
      ;;
    rollback)
      cat <<'PLAN'
[dry-run] Would set both LAN AIO agents to draining.
[dry-run] Would wait until both AIO agents finish current tasks.
[dry-run] Would start old gpu-002 comfy0/comfy1.
[dry-run] Would verify old 8188/8189 system_stats and queue.
[dry-run] Would start cloud-prod-comfy-agent-6/7.
[dry-run] Would restore legacy worker controls and disable AIO controls.
PLAN
      ;;
    stop-old)
      cat <<'PLAN'
[dry-run] Would verify AIO agents are enabled and healthy.
[dry-run] Would verify cloud_prod_worker_06/07 controls are disabled.
[dry-run] Would docker stop gpu-002 comfy0/comfy1 and local cloud-prod-comfy-agent-6/7.
[dry-run] Would not delete any container.
PLAN
      ;;
    *)
      echo "Unsupported dry-run action: $ACTION" >&2
      exit 2
      ;;
  esac
}

control_states() {
  LAN_AIO_OPS_PROD_ENV_FILE="$PROD_ENV_FILE" \
  LAN_AIO_OPS_AIO_ENV_FILE="$AIO_ENV_FILE" \
  python3 - "$@" <<'PY'
import json
import os
import sys
import urllib.request

from pathlib import Path

def load_env(path):
    values = {}
    if not path or not Path(path).exists():
        return values
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values

prod_env = load_env(os.environ.get("LAN_AIO_OPS_PROD_ENV_FILE", ""))
aio_env = load_env(os.environ.get("LAN_AIO_OPS_AIO_ENV_FILE", ""))
token = (
    os.environ.get("LAN_AIO_AGENT_SECRET_TOKEN")
    or aio_env.get("LAN_AIO_AGENT_SECRET_TOKEN")
    or os.environ.get("AGENT_SECRET_TOKEN")
    or prod_env.get("AGENT_SECRET_TOKEN")
)
if not token:
    print("control_state=unknown reason=missing_agent_token")
    raise SystemExit(0)

central = os.environ.get("LAN_AIO_PROD_CENTRAL_URL", "https://worker-central.aivison.it.com").rstrip("/")
headers = {"Authorization": f"Bearer {token}", "User-Agent": "allbot-lan-aio-prod-ops/1.0"}

def state_from(payload):
    for candidate in (
        payload,
        payload.get("control") if isinstance(payload.get("control"), dict) else {},
        payload.get("data") if isinstance(payload.get("data"), dict) else {},
    ):
        if isinstance(candidate, dict) and candidate.get("state"):
            return str(candidate["state"])
    return "unknown"

for agent_id in sys.argv[1:]:
    request = urllib.request.Request(f"{central}/api/agent/task/control/{agent_id}", headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    print(f"{agent_id}={state_from(payload)}")
PY
}

set_control() {
  local agent_id="$1"
  local state="$2"
  local reason="$3"
  LAN_AIO_OPS_PROD_ENV_FILE="$PROD_ENV_FILE" \
  LAN_AIO_OPS_AIO_ENV_FILE="$AIO_ENV_FILE" \
  python3 - "$agent_id" "$state" "$reason" <<'PY'
import json
import os
import sys
import urllib.request
from pathlib import Path

def load_env(path):
    values = {}
    if not path or not Path(path).exists():
        return values
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values

prod_env = load_env(os.environ.get("LAN_AIO_OPS_PROD_ENV_FILE", ""))
aio_env = load_env(os.environ.get("LAN_AIO_OPS_AIO_ENV_FILE", ""))
token = (
    os.environ.get("LAN_AIO_AGENT_SECRET_TOKEN")
    or aio_env.get("LAN_AIO_AGENT_SECRET_TOKEN")
    or os.environ.get("AGENT_SECRET_TOKEN")
    or prod_env.get("AGENT_SECRET_TOKEN")
)
if not token:
    raise SystemExit("missing AGENT_SECRET_TOKEN/LAN_AIO_AGENT_SECRET_TOKEN")
agent_id, state, reason = sys.argv[1:4]
central = os.environ.get("LAN_AIO_PROD_CENTRAL_URL", "https://worker-central.aivison.it.com").rstrip("/")
body = json.dumps({"state": state, "reason": reason}).encode("utf-8")
request = urllib.request.Request(
    f"{central}/api/agent/task/control/{agent_id}",
    data=body,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "allbot-lan-aio-prod-ops/1.0",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    response.read()
print(f"{agent_id}={state}")
PY
}

assert_control_state() {
  local expected_legacy="$1"
  local expected_aio="$2"
  local states
  states="$(control_states "${LEGACY_AGENTS[@]}" "${AIO_AGENTS[@]}")"
  printf '%s\n' "$states"
  for agent in "${LEGACY_AGENTS[@]}"; do
    grep -q "^${agent}=${expected_legacy}$" <<<"$states" || {
      echo "Expected ${agent}=${expected_legacy}" >&2
      exit 1
    }
  done
  for agent in "${AIO_AGENTS[@]}"; do
    grep -q "^${agent}=${expected_aio}$" <<<"$states" || {
      echo "Expected ${agent}=${expected_aio}" >&2
      exit 1
    }
  done
}

verify_aio_health() {
  ssh "$SSH_HOST" 'set -euo pipefail
for port in 8190 8191; do
  curl -fsS --max-time 8 "http://127.0.0.1:${port}/system_stats" >/dev/null
  curl -fsS --max-time 8 "http://127.0.0.1:${port}/queue" >/dev/null
done
docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" \
  allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary \
  allbot-lan-aio-gpu-002-gpu1-image_to_video-canary | grep -qx healthy'
  echo "AIO health OK for 8190/8191."
}

verify_old_comfy_health() {
  ssh "$SSH_HOST" 'set -euo pipefail
for port in 8188 8189; do
  curl -fsS --max-time 8 "http://127.0.0.1:${port}/system_stats" >/dev/null
  curl -fsS --max-time 8 "http://127.0.0.1:${port}/queue" >/dev/null
done'
  echo "Old ComfyUI health OK for 8188/8189."
}

wait_aio_idle() {
  python3 - "${AIO_AGENTS[@]}" <<'PY'
import json
import sys
import time
import urllib.request

agents = set(sys.argv[1:])
central = "https://worker-central.aivison.it.com"
deadline = time.time() + 3600
while time.time() < deadline:
    request = urllib.request.Request(
        f"{central}/system/workers",
        headers={"User-Agent": "allbot-lan-aio-prod-ops/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    busy = []
    for worker in payload.get("workers", []):
        if worker.get("agent_id") not in agents:
            continue
        status = str(worker.get("status") or "").lower()
        current_type = worker.get("current_task_type")
        if status == "running" or current_type:
            busy.append(worker.get("agent_id"))
    if not busy:
        print("AIO agents are idle.")
        raise SystemExit(0)
    print("Waiting for AIO agents to finish: " + ", ".join(sorted(busy)))
    time.sleep(10)
raise SystemExit("Timed out waiting for AIO agents to become idle")
PY
}

central_worker_status() {
  python3 - "${LEGACY_AGENTS[@]}" "${AIO_AGENTS[@]}" <<'PY'
import json
import sys
import urllib.request

agents = set(sys.argv[1:])
central = "https://worker-central.aivison.it.com"
request = urllib.request.Request(
    f"{central}/system/workers",
    headers={"User-Agent": "allbot-lan-aio-prod-ops/1.0"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    payload = json.loads(response.read().decode("utf-8"))
for worker in payload.get("workers", []):
    if worker.get("agent_id") not in agents:
        continue
    print(
        json.dumps(
            {
                "agent_id": worker.get("agent_id"),
                "status": worker.get("status"),
                "current_task_id": worker.get("current_task_id"),
                "current_task_type": worker.get("current_task_type"),
                "node_id": worker.get("node_id"),
                "runtime_profile": worker.get("runtime_profile"),
                "pool_managed": worker.get("pool_managed"),
            },
            ensure_ascii=False,
        )
    )
PY
}

show_status() {
  echo "== Central worker status =="
  central_worker_status
  echo "== Central control state =="
  control_states "${LEGACY_AGENTS[@]}" "${AIO_AGENTS[@]}"
  echo "== Local legacy worker containers =="
  docker ps -a --format '{{.Names}} {{.Status}}' | grep -E '^cloud-prod-comfy-agent-[67]\b|^cloud-prod-worker-relay\b' || true
  echo "== gpu-002 runtime containers =="
  ssh "$SSH_HOST" 'docker ps -a --format "{{.Names}} {{.Status}} {{.Ports}}" | grep -E "^allbot-lan-aio|^comfy[01]\b|node_exporter|dcgm_exporter" || true'
}

enable_aio() {
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi
  verify_aio_health
  run_helper --action drain --slot both --execute
  run_helper --action wait-idle --slot both --execute
  run_helper --action enable-canary --slot slot0 --execute
  run_helper --action enable-canary --slot slot1 --execute
  show_status
}

disable_aio() {
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi
  run_helper --action drain-temp --slot slot0 --execute
  run_helper --action drain-temp --slot slot1 --execute
  wait_aio_idle
  for agent in "${AIO_AGENTS[@]}"; do
    set_control "$agent" disabled lan_aio_prod_ops_disable_aio
  done
  show_status
}

rollback() {
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi
  run_helper --action drain-temp --slot slot0 --execute
  run_helper --action drain-temp --slot slot1 --execute
  wait_aio_idle
  for agent in "${AIO_AGENTS[@]}"; do
    set_control "$agent" disabled lan_aio_prod_ops_rollback
  done
  ssh "$SSH_HOST" 'docker start comfy0 comfy1 >/dev/null'
  verify_old_comfy_health
  docker start cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7 >/dev/null
  run_helper --action restore --slot slot0 --keep-container --execute
  run_helper --action restore --slot slot1 --keep-container --execute
  show_status
}

stop_old() {
  verify_aio_health
  assert_control_state disabled enabled
  if [ "$MODE" != "execute" ]; then
    dry_run_plan
    return
  fi
  ssh "$SSH_HOST" 'docker stop comfy0 comfy1 >/dev/null || true'
  docker stop cloud-prod-comfy-agent-6 cloud-prod-comfy-agent-7 >/dev/null || true
  show_status
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    status|enable-aio|disable-aio|rollback|stop-old)
      ACTION="$1"
      shift
      ;;
    --action)
      ACTION="${2:?missing value for --action}"
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
    --aio-env-file)
      AIO_ENV_FILE="${2:?missing value for --aio-env-file}"
      shift 2
      ;;
    --model-env-file)
      MODEL_ENV_FILE="${2:?missing value for --model-env-file}"
      shift 2
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

case "$ACTION" in
  status)
    show_status
    ;;
  enable-aio)
    enable_aio
    ;;
  disable-aio)
    disable_aio
    ;;
  rollback)
    rollback
    ;;
  stop-old)
    stop_old
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 2
    ;;
esac
