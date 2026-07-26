#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ACTION="status"
MODE="dry-run"
PROD_ENV_FILE=".env.cloud.prod"
MODEL_ENV_FILE=".env.lan.model-cache"
AIO_ENV_FILE=".env.lan-aio-prod"
CONTROL_TTL="3600"

SSH_HOST="${SCAIL2_PROD_SSH_HOST:-allbot-gpu-002}"
PUBLIC_HOST="${SCAIL2_PROD_PUBLIC_HOST:-192.168.1.2}"
CENTRAL_URL="${SCAIL2_PROD_CENTRAL_URL:-https://worker-central.aivison.it.com}"
WEB_HEALTH_URL="${SCAIL2_PROD_WEB_HEALTH_URL:-https://api.aivison.it.com/api/health}"
REGISTRY_HOST="${SCAIL2_PROD_REGISTRY_HOST:-192.168.1.115:5000}"
MODEL_CACHE_READY_URL="${SCAIL2_PROD_MODEL_CACHE_READY_URL:-http://192.168.1.115:9010/minio/health/ready}"

ASSIGNMENT="lan-002-8188-worker-06"
PROFILE="scail2"
HOST_PORT="8190"
CONTAINER_NAME="${SCAIL2_PROD_CONTAINER_NAME:-allbot-lan-aio-gpu-002-gpu0-scail2-prod}"
TEMP_AGENT_ID="${SCAIL2_PROD_AGENT_ID:-lan_aio_prod_gpu002_gpu0_scail2_01}"
OLD_AIO_AGENT_ID="${SCAIL2_PROD_OLD_AIO_AGENT_ID:-lan_aio_prod_gpu002_gpu0_img2img_lora_01}"
OLD_AIO_CONTAINER="${SCAIL2_PROD_OLD_AIO_CONTAINER:-allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary}"
REMOTE_DIR="${SCAIL2_PROD_REMOTE_DIR:-/home/chuzeyu/allbot-scail2-aio-prod/gpu002-slot0}"
REMOTE_COMPOSE_FILE="${REMOTE_DIR}/docker-compose.yml"
REMOTE_ENV_FILE="${REMOTE_DIR}/.env.lan-scail2-prod"
SCAIL2_PROD_SUPPORTED_TASK_TYPES="${SCAIL2_PROD_SUPPORTED_TASK_TYPES:-scail2_action_transfer,scail2_action_transfer_long,scail2_video_replacement,scail2_face_swap_v2}"
SCAIL2_PROD_TASK_TYPE_WORKFLOW_OVERRIDES="${SCAIL2_PROD_TASK_TYPE_WORKFLOW_OVERRIDES:-{\"scail2_action_transfer\":\"SCAIL-2_Animation_multi-char_audio.api.json\",\"scail2_action_transfer_long\":\"SCAIL-2_Animation_WAN-Context-Windows.api.json\",\"scail2_video_replacement\":\"SCAIL-2_Replacement_audio.api.json\",\"scail2_face_swap_v2\":\"SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json\"}}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_scail2_aio_prod.sh <action> [options]

Actions:
  status          Read-only status for prod SCAIL-2 slot0 and old slot0 AIO.
  render          Render the cloud-prod SCAIL-2 slot0 compose locally.
  preflight       Verify prod URLs, LAN registry/cache, render guardrails and gpu-002 basics.
  start-disabled  Drain old slot0 AIO, stop its container, start SCAIL-2 prod AIO disabled.
  restart-disabled Drain SCAIL-2, recreate the prod AIO, leave the agent disabled.
  verify          Verify SCAIL-2 ComfyUI health, required nodes and disabled heartbeat metadata.
  enable          Enable SCAIL-2 prod agent.
  drain-scail2    Drain SCAIL-2 prod agent and wait until idle.
  rollback        Drain SCAIL-2, stop it, restart old slot0 img2img_lora AIO and enable old agent.

Options:
  --execute               Execute mutations. Default dry-run.
  --prod-env-file <path>  Cloud prod env file. Default .env.cloud.prod.
  --model-env-file <p>    LAN model cache env file. Default .env.lan.model-cache.
  --aio-env-file <path>   Optional LAN AIO overlay. Default .env.lan-aio-prod.
  --control-ttl <sec>     Drain control TTL. Default 3600.
  -h, --help              Show this help.

Scope guard:
  Only gpu-002 slot0 / port 8190 is touched. This helper does not rebuild
  cloud-prod-comfy-agent-1..7 and does not create/start/stop RunPod pods.
USAGE
}

log() {
  printf '[lan-scail2-prod] %s\n' "$*"
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

render_compose_to() {
  local out="$1"
  local image_override="${SCAIL2_PROD_IMAGE_REF:-}"
  python scripts/gpu_pool_controller.py runtime-render \
    --assignment "$ASSIGNMENT" \
    --profile "$PROFILE" \
    --host-port "$HOST_PORT" \
    --container-name "$CONTAINER_NAME" \
    --runtime-shape runpod_all_in_one \
    --agent-id "$TEMP_AGENT_ID" \
    --environment cloud-prod > "$out"
  if [ -n "$image_override" ]; then
    python3 - "$out" "$CONTAINER_NAME" "$image_override" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
container_name = sys.argv[2]
image_ref = sys.argv[3]
compose = yaml.safe_load(path.read_text()) or {}
service = compose["services"][container_name]
service["image"] = image_ref
service["environment"]["POOL_IMAGE_REF"] = image_ref
compose["x-allbot-runtime"]["image_ref"] = image_ref
path.write_text(yaml.safe_dump(compose, allow_unicode=True, sort_keys=False))
PY
  fi
  patch_scail2_prod_overrides "$out"
  assert_prod_compose "$out"
}

patch_scail2_prod_overrides() {
  local file="$1"
  python3 - "$file" "$CONTAINER_NAME" \
    "$SCAIL2_PROD_SUPPORTED_TASK_TYPES" \
    "$SCAIL2_PROD_TASK_TYPE_WORKFLOW_OVERRIDES" <<'PY'
from pathlib import Path
import json
import sys
import yaml

path = Path(sys.argv[1])
container_name = sys.argv[2]
supported_task_types = sys.argv[3]
workflow_overrides = sys.argv[4]

required_tasks = {
    "scail2_action_transfer",
    "scail2_action_transfer_long",
    "scail2_video_replacement",
    "scail2_face_swap_v2",
}
declared_tasks = {item.strip() for item in supported_task_types.split(",") if item.strip()}
if declared_tasks != required_tasks:
    raise SystemExit(
        "SCAIL2_PROD_SUPPORTED_TASK_TYPES must be exactly "
        + ",".join(sorted(required_tasks))
    )

overrides = json.loads(workflow_overrides)
if not isinstance(overrides, dict):
    raise SystemExit("SCAIL2_PROD_TASK_TYPE_WORKFLOW_OVERRIDES must be a JSON object")
required_overrides = {
    "scail2_action_transfer": "SCAIL-2_Animation_multi-char_audio.api.json",
    "scail2_action_transfer_long": "SCAIL-2_Animation_WAN-Context-Windows.api.json",
    "scail2_video_replacement": "SCAIL-2_Replacement_audio.api.json",
    "scail2_face_swap_v2": "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json",
}
if overrides != required_overrides:
    raise SystemExit(
        "SCAIL2_PROD_TASK_TYPE_WORKFLOW_OVERRIDES must match the verified audio/context-window/v10 mapping"
    )
compose = yaml.safe_load(path.read_text()) or {}
service = compose.get("services", {}).get(container_name)
if not isinstance(service, dict):
    raise SystemExit(f"compose service not found: {container_name}")
environment = service.setdefault("environment", {})
environment["SUPPORTED_TASK_TYPES"] = supported_task_types
environment["TASK_TYPE_WORKFLOW_OVERRIDES"] = json.dumps(
    overrides, ensure_ascii=False, separators=(",", ":")
)
runtime = compose.setdefault("x-allbot-runtime", {})
runtime["prod_scail2_supported_task_types"] = sorted(required_tasks)
runtime["prod_scail2_workflow_overrides"] = overrides
path.write_text(yaml.safe_dump(compose, allow_unicode=True, sort_keys=False))
PY
}

assert_prod_compose() {
  local file="$1"
  grep -q "RUNPOD_ENVIRONMENT: cloud-prod" "$file"
  grep -q "CENTRAL_API_URL: https://worker-central.aivison.it.com" "$file"
  grep -q "SUPPORTED_TASK_TYPES: scail2_action_transfer,scail2_action_transfer_long,scail2_video_replacement,scail2_face_swap_v2" "$file"
  grep -q "SCAIL-2_Animation_multi-char_audio.api.json" "$file"
  grep -q "SCAIL-2_Animation_WAN-Context-Windows.api.json" "$file"
  grep -q "SCAIL-2_Replacement_audio.api.json" "$file"
  grep -q "SCAIL-2_FaceSwap_v10_firstframe_faceswap_replacement_audio.api.json" "$file"
  grep -q "MINIO_RESULT_BUCKET: user-data-prod" "$file"
  grep -q "RUNPOD_MODEL_PREFIX: scail2/2026-06-17-test" "$file"
  grep -q "production_port_unchanged: true" "$file"
  if grep -q "cloud-test\\|user-data-test" "$file"; then
    echo "Refusing compose containing cloud-test/user-data-test" >&2
    exit 2
  fi
  if grep -q "host_mount_current_bundle\\|/remote_workers:" "$file"; then
    echo "Refusing production compose with host-mounted remote_workers" >&2
    exit 2
  fi
}

remote_compose() {
  local op="$1"
  ssh "$SSH_HOST" \
    "cd '${REMOTE_DIR}' && if docker compose version >/dev/null 2>&1; then docker compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; else docker-compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; fi"
}

wait_agent_idle() {
  local agent_id="$1"
  python3 - "$CENTRAL_URL" "$agent_id" <<'PY'
import json
import sys
import time
import urllib.request

central = sys.argv[1].rstrip("/")
agent_id = sys.argv[2]
deadline = time.time() + 7200
while time.time() < deadline:
    request = urllib.request.Request(
        f"{central}/system/workers",
        headers={"User-Agent": "allbot-lan-scail2-prod/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    worker = next(
        (
            item for item in payload.get("workers", [])
            if isinstance(item, dict) and item.get("agent_id") == agent_id
        ),
        {},
    )
    status = str(worker.get("status") or "").lower()
    current_task_type = worker.get("current_task_type")
    if status != "running" and not current_task_type:
        print(f"{agent_id} is idle.")
        raise SystemExit(0)
    print(
        f"waiting {agent_id}: status={worker.get('status')!r} "
        f"current_task_id={worker.get('current_task_id')!r} "
        f"current_task_type={current_task_type!r}",
        flush=True,
    )
    time.sleep(15)
raise SystemExit(f"timed out waiting for {agent_id} to become idle")
PY
}

wait_remote_port_ready() {
  local port="$1"
  ssh "$SSH_HOST" "python3 - ${port}" <<'PY'
import sys
import time
import urllib.request

port = int(sys.argv[1])
deadline = time.time() + 1800
while time.time() < deadline:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/system_stats", timeout=10).read()
        urllib.request.urlopen(f"http://127.0.0.1:{port}/queue", timeout=10).read()
        print(f"port {port} ready")
        raise SystemExit(0)
    except Exception as exc:
        print(f"waiting port {port}: {exc}", flush=True)
        time.sleep(10)
raise SystemExit(f"timed out waiting for port {port}")
PY
}

verify_disabled_heartbeat() {
  python3 - "$CENTRAL_URL" "$TEMP_AGENT_ID" <<'PY'
import json
import os
import sys
import time
import urllib.request

central = sys.argv[1].rstrip("/")
agent_id = sys.argv[2]
token = os.environ.get("LAN_AIO_AGENT_SECRET_TOKEN")
if not token:
    raise SystemExit("LAN_AIO_AGENT_SECRET_TOKEN is required")

headers = {"User-Agent": "allbot-lan-scail2-prod/1.0"}
auth_headers = {**headers, "Authorization": f"Bearer {token}"}

def load_json(path, headers_):
    request = urllib.request.Request(f"{central}{path}", headers=headers_)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))

def state_from(payload):
    for candidate in (
        payload,
        payload.get("control") if isinstance(payload.get("control"), dict) else {},
        payload.get("data") if isinstance(payload.get("data"), dict) else {},
    ):
        if isinstance(candidate, dict) and candidate.get("state"):
            return str(candidate["state"])
    return None

deadline = time.time() + 240
while time.time() < deadline:
    control_payload = load_json(f"/api/agent/task/control/{agent_id}", auth_headers)
    if state_from(control_payload) != "disabled":
        raise SystemExit(f"{agent_id} is not disabled")
    workers_payload = load_json("/system/workers", headers)
    worker = next(
        (
            item for item in workers_payload.get("workers", [])
            if isinstance(item, dict) and item.get("agent_id") == agent_id
        ),
        None,
    )
    if worker is None:
        print(f"waiting heartbeat from {agent_id}", flush=True)
        time.sleep(5)
        continue
    errors = []
    if worker.get("node_id") != "gpu-002":
        errors.append(f"node_id={worker.get('node_id')!r}")
    if worker.get("provider") != "lan_ssh":
        errors.append(f"provider={worker.get('provider')!r}")
    if worker.get("runtime_profile") != "scail2":
        errors.append(f"runtime_profile={worker.get('runtime_profile')!r}")
    if str(worker.get("status") or "").lower() == "running" or worker.get("current_task_type"):
        errors.append("worker has current task while disabled")
    if errors:
        raise SystemExit("; ".join(errors))
    print(f"disabled heartbeat verified for {agent_id}")
    raise SystemExit(0)
raise SystemExit(f"timed out waiting for heartbeat from {agent_id}")
PY
}

verify_scail2_object_info() {
  python3 - "$PUBLIC_HOST" "$HOST_PORT" <<'PY'
import json
import sys
import urllib.request

host, port = sys.argv[1:3]
with urllib.request.urlopen(f"http://{host}:{port}/object_info", timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))
required = [
    "WanSCAILToVideo",
    "SCAIL2ColoredMask",
    "SAM3_VideoTrack",
    "WanContextWindowsManual",
    "VHS_LoadVideo",
    "VHS_VideoCombine",
]
missing = [item for item in required if item not in payload]
if missing:
    raise SystemExit("missing required nodes: " + ", ".join(missing))

def enum_values(class_name, input_name):
    spec = (payload[class_name].get("input") or {}).get("required", {}).get(input_name)
    if spec is None:
        spec = (payload[class_name].get("input") or {}).get("optional", {}).get(input_name)
    if not spec or not isinstance(spec, list):
        return []
    values = spec[0]
    return values if isinstance(values, list) else []

checks = [
    ("UNETLoader", "unet_name", "wan2.1_14B_SCAIL_2_fp8_scaled.safetensors"),
    ("CheckpointLoaderSimple", "ckpt_name", "sam3.1_multiplex_fp16.safetensors"),
    ("CLIPVisionLoader", "clip_name", "clip_vision_h.safetensors"),
    ("VAELoader", "vae_name", "wan_2.1_vae.safetensors"),
    ("CLIPLoader", "clip_name", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    (
        "LoraLoaderModelOnly",
        "lora_name",
        "Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
    ),
]
missing_models = []
for class_name, input_name, expected in checks:
    values = enum_values(class_name, input_name)
    if expected not in values:
        missing_models.append(f"{class_name}.{input_name}:{expected}")
if missing_models:
    raise SystemExit("missing model enum values: " + ", ".join(missing_models))
print("SCAIL-2 required nodes and model enums OK")
PY
}

run_status() {
  python3 - "$CENTRAL_URL" "$TEMP_AGENT_ID" "$OLD_AIO_AGENT_ID" <<'PY'
import json
import sys
import urllib.request

central = sys.argv[1].rstrip("/")
targets = set(sys.argv[2:])
request = urllib.request.Request(
    f"{central}/system/workers",
    headers={"User-Agent": "allbot-lan-scail2-prod/1.0"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    payload = json.loads(response.read().decode("utf-8"))
for worker in payload.get("workers", []):
    if isinstance(worker, dict) and worker.get("agent_id") in targets:
        print(json.dumps({
            "agent_id": worker.get("agent_id"),
            "status": worker.get("status"),
            "control": worker.get("control"),
            "current_task_id": worker.get("current_task_id"),
            "current_task_type": worker.get("current_task_type"),
            "runtime_profile": worker.get("runtime_profile"),
            "node_id": worker.get("node_id"),
        }, ensure_ascii=False))
PY
  ssh "$SSH_HOST" "docker ps -a --format '{{.Names}} {{.Status}}' | grep -E '^(${CONTAINER_NAME}|${OLD_AIO_CONTAINER})\\b' || true"
}

run_render() {
  local tmp
  tmp="$(mktemp)"
  render_compose_to "$tmp"
  cat "$tmp"
  rm -f "$tmp"
}

run_preflight() {
  local tmp
  tmp="$(mktemp)"
  render_compose_to "$tmp"
  rm -f "$tmp"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would verify prod Central ${CENTRAL_URL}/health"
    echo "[dry-run] Would verify prod Web ${WEB_HEALTH_URL}"
    echo "[dry-run] Would verify LAN registry ${REGISTRY_HOST}/v2/"
    echo "[dry-run] Would verify LAN model cache ${MODEL_CACHE_READY_URL}"
    echo "[dry-run] Would verify gpu-002 disk and old slot0 container"
    return 0
  fi
  curl -fsS "${CENTRAL_URL}/health" >/dev/null
  curl -fsS "${WEB_HEALTH_URL}" >/dev/null
  curl -fsS "http://${REGISTRY_HOST}/v2/" >/dev/null
  curl -fsS "${MODEL_CACHE_READY_URL}" >/dev/null
  ssh "$SSH_HOST" "set -euo pipefail; df -BG /srv/allbot /home/chuzeyu | awk 'NR==1 || \$4+0 >= 80 {print}'; docker inspect '${OLD_AIO_CONTAINER}' >/dev/null"
  log "preflight passed"
}

run_start_disabled() {
  control_agent "$OLD_AIO_AGENT_ID" "draining" "scail2_prod_slot0_replace_drain_old" "$CONTROL_TTL"
  if [ "$MODE" = "execute" ]; then
    wait_agent_idle "$OLD_AIO_AGENT_ID"
  else
    echo "[dry-run] Would wait until ${OLD_AIO_AGENT_ID} is idle"
  fi
  control_agent "$OLD_AIO_AGENT_ID" "disabled" "scail2_prod_slot0_replace_old_disabled"
  control_agent "$TEMP_AGENT_ID" "disabled" "scail2_prod_start_disabled"

  local tmp_compose tmp_env
  tmp_compose="$(mktemp)"
  tmp_env="$(mktemp)"
  render_compose_to "$tmp_compose"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would write compose to ${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
    echo "[dry-run] Would stop ${OLD_AIO_CONTAINER} and start ${CONTAINER_NAME}"
    rm -f "$tmp_compose" "$tmp_env"
    return 0
  fi
  write_runtime_env_file "$tmp_env"
  ssh "$SSH_HOST" "mkdir -p '${REMOTE_DIR}' && chmod 700 '${REMOTE_DIR}'"
  scp -q "$tmp_compose" "${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
  scp -q "$tmp_env" "${SSH_HOST}:${REMOTE_ENV_FILE}"
  rm -f "$tmp_compose" "$tmp_env"
  ssh "$SSH_HOST" "docker stop '${OLD_AIO_CONTAINER}' >/dev/null 2>&1 || true"
  remote_compose "up -d"
  wait_remote_port_ready "$HOST_PORT"
  verify_disabled_heartbeat
}

run_restart_disabled() {
  run_drain_scail2
  control_agent "$TEMP_AGENT_ID" "disabled" "scail2_prod_restart_disabled"

  local tmp_compose tmp_env
  tmp_compose="$(mktemp)"
  tmp_env="$(mktemp)"
  render_compose_to "$tmp_compose"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would use the remote_workers revision baked into the profile image"
    echo "[dry-run] Would write compose to ${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
    echo "[dry-run] Would recreate ${CONTAINER_NAME} and keep ${TEMP_AGENT_ID} disabled"
    rm -f "$tmp_compose" "$tmp_env"
    return 0
  fi
  write_runtime_env_file "$tmp_env"
  ssh "$SSH_HOST" "mkdir -p '${REMOTE_DIR}' && chmod 700 '${REMOTE_DIR}'"
  scp -q "$tmp_compose" "${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
  scp -q "$tmp_env" "${SSH_HOST}:${REMOTE_ENV_FILE}"
  rm -f "$tmp_compose" "$tmp_env"
  remote_compose "up -d --force-recreate"
  wait_remote_port_ready "$HOST_PORT"
  verify_disabled_heartbeat
}

run_verify() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would verify http://${PUBLIC_HOST}:${HOST_PORT}/system_stats and /object_info"
    echo "[dry-run] Would verify disabled heartbeat for ${TEMP_AGENT_ID}"
    return 0
  fi
  curl -fsS "http://${PUBLIC_HOST}:${HOST_PORT}/system_stats" >/dev/null
  curl -fsS "http://${PUBLIC_HOST}:${HOST_PORT}/queue" >/dev/null
  verify_scail2_object_info
  verify_disabled_heartbeat
}

run_enable() {
  control_agent "$TEMP_AGENT_ID" "enabled" "scail2_prod_canary_passed_enable"
}

run_drain_scail2() {
  control_agent "$TEMP_AGENT_ID" "draining" "scail2_prod_drain_before_rollback" "$CONTROL_TTL"
  if [ "$MODE" = "execute" ]; then
    wait_agent_idle "$TEMP_AGENT_ID"
  else
    echo "[dry-run] Would wait until ${TEMP_AGENT_ID} is idle"
  fi
}

run_rollback() {
  run_drain_scail2
  control_agent "$TEMP_AGENT_ID" "disabled" "scail2_prod_rollback_disabled"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would stop ${CONTAINER_NAME}, start ${OLD_AIO_CONTAINER}, verify 8190, enable ${OLD_AIO_AGENT_ID}"
    return 0
  fi
  ssh "$SSH_HOST" "docker stop '${CONTAINER_NAME}' >/dev/null 2>&1 || true; docker start '${OLD_AIO_CONTAINER}' >/dev/null"
  wait_remote_port_ready "$HOST_PORT"
  control_agent "$OLD_AIO_AGENT_ID" "enabled" "scail2_prod_rollback_restore_old_slot0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    status|render|preflight|start-disabled|restart-disabled|verify|enable|drain-scail2|rollback)
      ACTION="$1"
      ;;
    --execute)
      MODE="execute"
      ;;
    --dry-run)
      MODE="dry-run"
      ;;
    --prod-env-file)
      PROD_ENV_FILE="$2"
      shift
      ;;
    --model-env-file)
      MODEL_ENV_FILE="$2"
      shift
      ;;
    --aio-env-file)
      AIO_ENV_FILE="$2"
      shift
      ;;
    --control-ttl)
      CONTROL_TTL="$2"
      shift
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
  shift
done

case "$CENTRAL_URL" in
  *test*|*100.82.124.91*)
    echo "Refusing production helper with test Central URL: ${CENTRAL_URL}" >&2
    exit 2
    ;;
esac

load_runtime_env

case "$ACTION" in
  status) run_status ;;
  render) run_render ;;
  preflight) run_preflight ;;
  start-disabled) run_start_disabled ;;
  restart-disabled) run_restart_disabled ;;
  verify) run_verify ;;
  enable) run_enable ;;
  drain-scail2) run_drain_scail2 ;;
  rollback) run_rollback ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    usage >&2
    exit 2
    ;;
esac
