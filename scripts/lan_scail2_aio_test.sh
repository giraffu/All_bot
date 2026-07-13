#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="status"
MODE="dry-run"
SSH_HOST="${SCAIL2_SSH_HOST:-allbot-gpu-002}"
PUBLIC_HOST="${SCAIL2_PUBLIC_HOST:-192.168.1.2}"
REGISTRY_HOST="${SCAIL2_REGISTRY_HOST:-192.168.1.115:5000}"
IMAGE_TAG="${SCAIL2_IMAGE_TAG:-20260617-scail2-cu128-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"
IMAGE_REF="${SCAIL2_IMAGE_REF:-${REGISTRY_HOST}/allbot/comfy-runpod-scail2:${IMAGE_TAG}}"
REMOTE_DIR="${SCAIL2_REMOTE_DIR:-/home/chuzeyu/allbot-scail2-aio-test}"
WORKSPACE="${SCAIL2_WORKSPACE:-/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles/scail2/workspace}"
CONTAINER_NAME="${SCAIL2_CONTAINER_NAME:-allbot-lan-aio-gpu-002-gpu0-scail2-test}"
OLD_SLOT0_CONTAINER="${SCAIL2_OLD_SLOT0_CONTAINER:-allbot-lan-aio-gpu-002-gpu0-img2img_lora-canary}"
SLOT1_CONTAINER="${SCAIL2_SLOT1_CONTAINER:-allbot-lan-aio-gpu-002-gpu1-image_to_video-canary}"
HOST_PORT="${SCAIL2_HOST_PORT:-8190}"
RESULT_ROOT="${SCAIL2_RESULT_ROOT:-/root/scail2-test-results}"
PROD_ENV_FILE="${SCAIL2_PROD_ENV_FILE:-.env.cloud.prod}"
MODEL_ENV_FILE="${SCAIL2_MODEL_ENV_FILE:-.env.lan.model-cache}"
CONTROL_TTL="${SCAIL2_CONTROL_TTL:-3600}"
COMFY_URL="${SCAIL2_COMFY_URL:-http://${PUBLIC_HOST}:${HOST_PORT}}"
COMFYUI_REF="${SCAIL2_COMFYUI_REF:-f026b01ba576d98442839861a0eb0046bc2250d3}"
BASE_IMAGE="${SCAIL2_BASE_IMAGE:-yanwk/comfyui-boot:cu128-slim}"
AIO_AGENT_SLOT0="lan_aio_prod_gpu002_gpu0_img2img_lora_01"
LEGACY_AGENT_SLOT0="cloud_prod_worker_06"

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_scail2_aio_test.sh <action> [options]

Actions:
  status       Read-only status for slot0 replacement and slot1.
  preflight    Verify disk, registry, manifest and Central states.
  build-image  Build the test-only SCAIL-2 ComfyUI image locally.
  push-image   Push the image to the LAN registry.
  start        Drain/disable slot0 img2img AIO, stop it, start SCAIL-2 test container.
  verify       Verify ComfyUI health, required nodes, model enums and four workflows.
  run-sample   Submit SCAIL-2_Animation.json and copy the newest mp4 to gpu-002:/root.
  copy-result  Copy the newest SCAIL-2*.mp4 to gpu-002:/root without submitting.
  restore      Stop SCAIL-2 test container and restore original slot0 img2img AIO.
  all          preflight, build-image, push-image, start, verify, run-sample.

Options:
  --execute               Execute production mutations for start/restore. Default dry-run.
  --image-ref <ref>       Override image ref.
  --image-tag <tag>       Override default LAN registry tag.
  --ssh-host <host>       Default allbot-gpu-002.
  --host-port <port>      Default 8190.
  --prod-env-file <path>  Default .env.cloud.prod.
  --model-env-file <p>    Default .env.lan.model-cache.
  -h, --help              Show this help.

This helper is test-only. It does not set AGENT_ID, CENTRAL_API_URL or
SUPPORTED_TASK_TYPES in the SCAIL-2 container.
USAGE
}

log() {
  printf '[lan-scail2] %s\n' "$*"
}

load_env_allowlist() {
  local path="$1"
  shift
  [ -f "$path" ] || return 0
  local allowed=" $* "
  local raw key value
  while IFS= read -r raw || [ -n "$raw" ]; do
    raw="${raw#"${raw%%[![:space:]]*}"}"
    case "$raw" in
      ""|\#*) continue ;;
    esac
    [ "${raw#*=}" != "$raw" ] || continue
    key="${raw%%=*}"
    key="${key#export }"
    key="${key//[[:space:]]/}"
    case "$allowed" in
      *" ${key} "*)
        value="${raw#*=}"
        value="${value%$'\r'}"
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "${key}=${value}"
        ;;
    esac
  done < "$path"
}

load_model_env() {
  load_env_allowlist "$MODEL_ENV_FILE" LAN_MODEL_CACHE_ACCESS_KEY LAN_MODEL_CACHE_SECRET_KEY
  : "${LAN_MODEL_CACHE_ACCESS_KEY:?LAN_MODEL_CACHE_ACCESS_KEY is required}"
  : "${LAN_MODEL_CACHE_SECRET_KEY:?LAN_MODEL_CACHE_SECRET_KEY is required}"
}

control_state() {
  SCAIL2_PROD_ENV_FILE="$PROD_ENV_FILE" python3 - "$@" <<'PY'
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

prod_env = load_env(os.environ.get("SCAIL2_PROD_ENV_FILE", ""))
token = os.environ.get("AGENT_SECRET_TOKEN") or prod_env.get("AGENT_SECRET_TOKEN")
if not token:
    raise SystemExit("missing AGENT_SECRET_TOKEN in environment or prod env file")
central = os.environ.get("LAN_AIO_PROD_CENTRAL_URL", "https://worker-central.aivison.it.com").rstrip("/")
headers = {"Authorization": f"Bearer {token}", "User-Agent": "allbot-lan-scail2-test/1.0"}

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
  SCAIL2_PROD_ENV_FILE="$PROD_ENV_FILE" python3 - "$agent_id" "$state" "$reason" "$CONTROL_TTL" <<'PY'
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

prod_env = load_env(os.environ.get("SCAIL2_PROD_ENV_FILE", ""))
token = os.environ.get("AGENT_SECRET_TOKEN") or prod_env.get("AGENT_SECRET_TOKEN")
if not token:
    raise SystemExit("missing AGENT_SECRET_TOKEN in environment or prod env file")
agent_id, state, reason, ttl = sys.argv[1:5]
central = os.environ.get("LAN_AIO_PROD_CENTRAL_URL", "https://worker-central.aivison.it.com").rstrip("/")
payload = {"state": state, "reason": reason}
if state == "draining":
    payload["ttl_seconds"] = int(ttl)
request = urllib.request.Request(
    f"{central}/api/agent/task/control/{agent_id}",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "allbot-lan-scail2-test/1.0",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    response.read()
print(f"{agent_id}={state}")
PY
}

central_worker_status() {
  python3 - "$AIO_AGENT_SLOT0" "$LEGACY_AGENT_SLOT0" <<'PY'
import json
import sys
import urllib.request

agents = set(sys.argv[1:])
request = urllib.request.Request(
    "https://worker-central.aivison.it.com/system/workers",
    headers={"User-Agent": "allbot-lan-scail2-test/1.0"},
)
with urllib.request.urlopen(request, timeout=15) as response:
    payload = json.loads(response.read().decode("utf-8"))
for worker in payload.get("workers", []):
    if worker.get("agent_id") in agents:
        print(json.dumps({
            "agent_id": worker.get("agent_id"),
            "status": worker.get("status"),
            "current_task_id": worker.get("current_task_id"),
            "current_task_type": worker.get("current_task_type"),
            "runtime_profile": worker.get("runtime_profile"),
            "node_id": worker.get("node_id"),
        }, ensure_ascii=False))
PY
}

wait_slot0_idle() {
  python3 - "$AIO_AGENT_SLOT0" <<'PY'
import json
import sys
import time
import urllib.request

agent_id = sys.argv[1]
deadline = time.time() + 7200
while time.time() < deadline:
    request = urllib.request.Request(
        "https://worker-central.aivison.it.com/system/workers",
        headers={"User-Agent": "allbot-lan-scail2-test/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    busy = []
    for worker in payload.get("workers", []):
        if worker.get("agent_id") != agent_id:
            continue
        status = str(worker.get("status") or "").lower()
        current_type = worker.get("current_task_type")
        if status == "running" or current_type:
            busy.append({
                "status": worker.get("status"),
                "current_task_id": worker.get("current_task_id"),
                "current_task_type": current_type,
            })
    if not busy:
        print("slot0 AIO agent is idle.")
        raise SystemExit(0)
    print("waiting slot0 AIO task to finish: " + json.dumps(busy, ensure_ascii=False), flush=True)
    time.sleep(15)
raise SystemExit("timed out waiting for slot0 AIO agent to become idle")
PY
  ssh "$SSH_HOST" "python3 - <<'PY'
import json
import time
import urllib.request

deadline = time.time() + 900
while time.time() < deadline:
    with urllib.request.urlopen('http://127.0.0.1:${HOST_PORT}/queue', timeout=10) as response:
        payload = json.loads(response.read().decode('utf-8'))
    running = payload.get('queue_running') or []
    pending = payload.get('queue_pending') or []
    if not running and not pending:
        print('slot0 ComfyUI queue is empty.')
        raise SystemExit(0)
    print(f'waiting slot0 ComfyUI queue running={len(running)} pending={len(pending)}', flush=True)
    time.sleep(10)
raise SystemExit('timed out waiting for slot0 ComfyUI queue')
PY"
}

verify_manifest() {
  load_model_env
  LAN_MODEL_CACHE_ACCESS_KEY="$LAN_MODEL_CACHE_ACCESS_KEY" \
  LAN_MODEL_CACHE_SECRET_KEY="$LAN_MODEL_CACHE_SECRET_KEY" \
  python3 - <<'PY'
import json
import os
from minio import Minio

client = Minio(
    "192.168.1.115:9010",
    access_key=os.environ["LAN_MODEL_CACHE_ACCESS_KEY"],
    secret_key=os.environ["LAN_MODEL_CACHE_SECRET_KEY"],
    secure=False,
)
bucket = "allbot-model-cache"
key = "scail2/2026-06-17-test/manifest.json"
response = client.get_object(bucket, key)
try:
    manifest = json.loads(response.read().decode("utf-8"))
finally:
    response.close()
    response.release_conn()
files = manifest.get("files") or []
if len(files) != 6:
    raise SystemExit(f"expected 6 files in {key}, got {len(files)}")
required = {
    "checkpoints/sam3.1_multiplex_fp16.safetensors",
    "clip_vision/clip_vision_h.safetensors",
    "diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors",
    "loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
    "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "vae/wan_2.1_vae.safetensors",
}
seen = {item["relative_path"] for item in files}
missing = required - seen
if missing:
    raise SystemExit("manifest missing: " + ", ".join(sorted(missing)))
for item in files:
    object_key = item.get("key") or f"scail2/2026-06-17-test/models/{item['relative_path']}"
    stat = client.stat_object(bucket, object_key)
    if stat.size != int(item["size_bytes"]):
        raise SystemExit(f"size mismatch for {item['relative_path']}: {stat.size} != {item['size_bytes']}")
print(f"manifest OK: {key}, files={len(files)}")
PY
}

preflight() {
  log "checking gpu-002 disk space"
  ssh "$SSH_HOST" "df -BG / | awk 'NR==2 {gsub(\"G\", \"\", \$4); available=\$4 + 0; print \"available GiB=\" available; if (available < 80) exit 1}'"
  log "checking LAN model cache manifest"
  verify_manifest
  log "checking LAN registry"
  curl -fsS --max-time 8 "http://${REGISTRY_HOST}/v2/" >/dev/null
  log "checking current Central state"
  central_worker_status
  control_state "$AIO_AGENT_SLOT0" "$LEGACY_AGENT_SLOT0"
  log "checking slot1 remains healthy"
  ssh "$SSH_HOST" "curl -fsS --max-time 8 http://127.0.0.1:8191/system_stats >/dev/null && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' '${SLOT1_CONTAINER}'"
  log "preflight passed"
}

build_image() {
  local build_args=()
  if curl -fsS --max-time 4 --proxy http://127.0.0.1:7890 https://github.com/ >/dev/null 2>&1; then
    log "using local proxy on 127.0.0.1:7890 for docker build"
    build_args+=(--network host)
    build_args+=(--build-arg HTTP_PROXY=http://127.0.0.1:7890)
    build_args+=(--build-arg HTTPS_PROXY=http://127.0.0.1:7890)
    build_args+=(--build-arg ALL_PROXY=socks5h://127.0.0.1:7890)
    build_args+=(--build-arg NO_PROXY=localhost,127.0.0.1,192.168.0.0/16)
  fi
  log "building ${IMAGE_REF}"
  docker build \
    "${build_args[@]}" \
    -f "${ROOT_DIR}/remote_workers/docker/runpod_profiles/scail2/Dockerfile" \
    --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
    --build-arg "COMFYUI_REF=${COMFYUI_REF}" \
    --label "allbot.runpod.profile=scail2" \
    --label "allbot.runpod.model_sync=external-lan-manifest" \
    -t "$IMAGE_REF" \
    "$ROOT_DIR"
  log "smoke testing image layout"
  docker run --rm --entrypoint bash "$IMAGE_REF" -lc '
set -euo pipefail
comfyui_dir="$(cat /opt/allbot-comfyui-dir)"
test -f "${comfyui_dir}/main.py"
test -f "${comfyui_dir}/comfy_extras/nodes_scail.py"
grep -R "WanSCAILToVideo" "${comfyui_dir}/comfy_extras/nodes_scail.py" >/dev/null
grep -R "SCAIL2ColoredMask" "${comfyui_dir}/comfy_extras/nodes_scail.py" >/dev/null
test -d "${comfyui_dir}/custom_nodes/ComfyUI-KJNodes"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-VideoHelperSuite"
test -d "${comfyui_dir}/custom_nodes/rgthree-comfy"
test -d "${comfyui_dir}/custom_nodes/ComfyUI-Frame-Interpolation"
test -d "${comfyui_dir}/custom_nodes/ComfyUI_Fill-Nodes"
test -x /opt/allbot/lan_scail2_comfyui_entrypoint.sh
test -f /opt/allbot/scail2-workflows/SCAIL-2_Animation.json
command -v ffmpeg >/dev/null
if find "${comfyui_dir}/models" -type f -name "*.safetensors" -print -quit | grep -q .; then
  echo "model weights must not be baked into the image" >&2
  exit 1
fi
echo "SCAIL2_IMAGE_LAYOUT_OK=true"
'
}

push_image() {
  log "pushing ${IMAGE_REF}"
  docker push "$IMAGE_REF"
}

download_samples_to_remote() {
  local tmp
  tmp="$(mktemp -d)"
  mkdir -p "${tmp}/pasted"
  local curl_args=(-fL --retry 3 --retry-delay 2)
  if curl -fsS --max-time 4 --proxy http://127.0.0.1:7890 https://i.gyazo.com/ >/dev/null 2>&1; then
    curl_args+=(--proxy http://127.0.0.1:7890)
  fi
  log "downloading Nomadoor sample assets"
  curl "${curl_args[@]}" -o "${tmp}/pexels-photo-31438123.jpg" \
    "https://i.gyazo.com/ce9827f452cdc3cf7d47de8b12996f28/max_size/1200.jpg"
  curl "${curl_args[@]}" -o "${tmp}/14637751_2160_3840_30fps.mp4" \
    "https://i.gyazo.com/f14aef04ac197a4b92680e05c4fbd178.mp4"
  curl "${curl_args[@]}" -o "${tmp}/pasted/image (4).png" \
    "https://i.gyazo.com/567acaf722ca9e839ec7cb834c1ed344/max_size/1200.jpg"
  curl "${curl_args[@]}" -o "${tmp}/8281169-hd_1080_1920_24fps.mp4" \
    "https://i.gyazo.com/53461ca17746349fbd11e69798460ea6.mp4"
  tar -C "$tmp" -cf - . | ssh "$SSH_HOST" "mkdir -p '${WORKSPACE}/ComfyUI/input' && tar -C '${WORKSPACE}/ComfyUI/input' -xf -"
  rm -rf "$tmp"
}

write_remote_compose() {
  load_model_env
  local tmp
  tmp="$(mktemp -d)"
  cat > "${tmp}/docker-compose.yml" <<YAML
name: allbot-scail2-aio-test
services:
  scail2-comfy:
    image: ${IMAGE_REF}
    container_name: ${CONTAINER_NAME}
    restart: unless-stopped
    ports:
      - "${HOST_PORT}:8188"
    environment:
      TZ: Asia/Shanghai
      NVIDIA_VISIBLE_DEVICES: "0"
      NVIDIA_DRIVER_CAPABILITIES: compute,utility,video
      RUNPOD_WORKSPACE_DIR: /workspace
      RUNPOD_VOLUME_COMFYUI_DIR: /workspace/ComfyUI
      RUNPOD_MODEL_SYNC_ENABLED: "true"
      RUNPOD_MODEL_ENDPOINT: 192.168.1.115:9010
      RUNPOD_MODEL_ACCESS_KEY: \${LAN_MODEL_CACHE_ACCESS_KEY:?}
      RUNPOD_MODEL_SECRET_KEY: \${LAN_MODEL_CACHE_SECRET_KEY:?}
      RUNPOD_MODEL_BUCKET: allbot-model-cache
      RUNPOD_MODEL_PREFIX: scail2/2026-06-17-test
      RUNPOD_MODEL_MANIFEST_KEY: scail2/2026-06-17-test/manifest.json
      RUNPOD_MODEL_TARGET_DIR: /workspace/ComfyUI/models
      RUNPOD_MODEL_SECURE: "false"
      RUNPOD_MODEL_DOWNLOAD_MAX_ATTEMPTS: "12"
      RUNPOD_MODEL_DOWNLOAD_PROGRESS_SECONDS: "30"
      RUNPOD_KEEPALIVE_ON_BOOTSTRAP_FAILURE: "true"
      COMFY_HOST: 0.0.0.0
      COMFY_PORT: "8188"
    volumes:
      - ${WORKSPACE}:/workspace
    labels:
      allbot.gpu_pool.managed: "false"
      allbot.gpu_pool.node_id: gpu-002
      allbot.gpu_pool.runtime_profile: scail2
      allbot.gpu_pool.test_only: "true"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8188/system_stats >/dev/null || exit 1"]
      interval: 30s
      timeout: 8s
      retries: 5
      start_period: 180s
    gpus:
      - driver: nvidia
        device_ids: ["0"]
        capabilities: ["gpu"]
YAML
  {
    printf 'LAN_MODEL_CACHE_ACCESS_KEY=%s\n' "$LAN_MODEL_CACHE_ACCESS_KEY"
    printf 'LAN_MODEL_CACHE_SECRET_KEY=%s\n' "$LAN_MODEL_CACHE_SECRET_KEY"
  } > "${tmp}/.env"
  ssh "$SSH_HOST" "mkdir -p '${REMOTE_DIR}'"
  local profiles_root="/srv/allbot/runpod-runtime/slots/gpu-002-gpu0/profiles"
  ssh "$SSH_HOST" "mkdir -p '${WORKSPACE}/scail2-workflows' '${WORKSPACE}/ComfyUI/input' '${WORKSPACE}/ComfyUI/output' 2>/dev/null || docker run --rm -v '${profiles_root}:/profiles' yanwk/comfyui-boot:cu128-slim bash -lc 'mkdir -p /profiles/scail2/workspace/scail2-workflows /profiles/scail2/workspace/ComfyUI/input /profiles/scail2/workspace/ComfyUI/output && chown -R $(id -u):$(id -g) /profiles/scail2'"
  scp "${tmp}/docker-compose.yml" "${SSH_HOST}:${REMOTE_DIR}/docker-compose.yml" >/dev/null
  scp "${tmp}/.env" "${SSH_HOST}:${REMOTE_DIR}/.env" >/dev/null
  (cd "${ROOT_DIR}/remote_workers/comfy_agent/workflows" && tar -cf - SCAIL-2_*.json) | \
    ssh "$SSH_HOST" "tar -C '${WORKSPACE}/scail2-workflows' -xf -"
  rm -rf "$tmp"
}

remote_compose() {
  local op="$1"
  ssh "$SSH_HOST" "cd '${REMOTE_DIR}' && if docker compose version >/dev/null 2>&1; then docker compose --env-file .env -f docker-compose.yml ${op}; else docker-compose --env-file .env -f docker-compose.yml ${op}; fi"
}

wait_scail2_health() {
  local deadline=$((SECONDS + 1800))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS --max-time 8 "${COMFY_URL}/system_stats" >/dev/null 2>&1; then
      log "SCAIL-2 ComfyUI is healthy at ${COMFY_URL}"
      return 0
    fi
    sleep 10
  done
  ssh "$SSH_HOST" "docker logs --tail 200 '${CONTAINER_NAME}'" || true
  echo "Timed out waiting for ${COMFY_URL}/system_stats" >&2
  return 1
}

verify_runtime() {
  log "checking ${COMFY_URL}/system_stats"
  curl -fsS --max-time 15 "${COMFY_URL}/system_stats" >/dev/null
  log "checking object_info nodes and model enums"
  python3 - "$COMFY_URL" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1].rstrip("/")
with urllib.request.urlopen(f"{url}/object_info", timeout=30) as response:
    info = json.loads(response.read().decode("utf-8"))
required_nodes = {
    "WanSCAILToVideo",
    "SCAIL2ColoredMask",
    "SAM3_VideoTrack",
    "WanContextWindowsManual",
    "VHS_LoadVideo",
    "VHS_VideoCombine",
}
missing = sorted(required_nodes - set(info))
if missing:
    raise SystemExit("missing nodes: " + ", ".join(missing))

def enum_values(class_name, input_name):
    spec = (info[class_name].get("input") or {}).get("required", {}).get(input_name)
    if spec is None:
        spec = (info[class_name].get("input") or {}).get("optional", {}).get(input_name)
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
    ("LoraLoaderModelOnly", "lora_name", "Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors"),
]
missing_models = []
for class_name, input_name, expected in checks:
    values = enum_values(class_name, input_name)
    if expected not in values:
        missing_models.append(f"{class_name}.{input_name}:{expected}")
if missing_models:
    raise SystemExit("missing model enum values: " + ", ".join(missing_models))
print("object_info OK")
PY
  for workflow in \
    SCAIL-2_Animation.json \
    SCAIL-2_Replacement.json \
    SCAIL-2_Animation_multi-char.json \
    SCAIL-2_Animation_WAN-Context-Windows.json
  do
    python3 "${ROOT_DIR}/scripts/scail2_submit_smoke.py" \
      --comfy-url "$COMFY_URL" \
      --workflow "${ROOT_DIR}/workers/comfy_agent/workflows/${workflow}" \
      --dry-run >/dev/null
    log "workflow API conversion OK: ${workflow}"
  done
  log "verify passed"
}

start_scail2() {
  if [ "$MODE" != "execute" ]; then
    cat <<PLAN
[dry-run] Would set ${AIO_AGENT_SLOT0}=draining and ${LEGACY_AGENT_SLOT0}=disabled.
[dry-run] Would wait until slot0 current img2img_lora task and ComfyUI queue are idle.
[dry-run] Would stop ${OLD_SLOT0_CONTAINER}, keep slot1 running, then start ${CONTAINER_NAME} on ${HOST_PORT}:8188.
[dry-run] Image ref: ${IMAGE_REF}
PLAN
    return
  fi
  preflight
  set_control "$AIO_AGENT_SLOT0" draining scail2_test_replacing_slot0 "$CONTROL_TTL"
  set_control "$LEGACY_AGENT_SLOT0" disabled scail2_test_keep_legacy_disabled
  wait_slot0_idle
  set_control "$AIO_AGENT_SLOT0" disabled scail2_test_slot0_disabled
  write_remote_compose
  download_samples_to_remote
  ssh "$SSH_HOST" "docker stop '${OLD_SLOT0_CONTAINER}' >/dev/null || true"
  remote_compose "pull"
  remote_compose "up -d"
  wait_scail2_health
}

copy_latest_result_to_root() {
  local timestamp
  timestamp="$(date +%Y%m%d-%H%M%S)"
  local remote_result="${RESULT_ROOT}/${timestamp}"
  local remote_script
  remote_script="$(cat <<EOS
set -euo pipefail
latest=\$(find '${WORKSPACE}/ComfyUI/output' -type f -name 'SCAIL-2*.mp4' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
if [ -z "\$latest" ]; then
  echo 'no SCAIL-2 mp4 output found' >&2
  exit 1
fi
mkdir -p '${remote_result}'
cp "\$latest" '${remote_result}/'
ls -lh '${remote_result}'
EOS
)"
  if ssh "$SSH_HOST" "sudo -n true" >/dev/null 2>&1; then
    printf '%s\n' "$remote_script" | ssh "$SSH_HOST" "sudo bash -s"
  else
    local docker_script="${remote_script//${WORKSPACE}/\/host${WORKSPACE}}"
    docker_script="${docker_script//${RESULT_ROOT}/\/host${RESULT_ROOT}}"
    ssh "$SSH_HOST" "docker run --rm -v /:/host yanwk/comfyui-boot:cu128-slim bash -lc $(printf '%q' "$docker_script")"
  fi
  log "result copied to ${SSH_HOST}:${remote_result}"
}

run_sample() {
  download_samples_to_remote
  python3 "${ROOT_DIR}/scripts/scail2_submit_smoke.py" \
    --comfy-url "$COMFY_URL" \
    --workflow "${ROOT_DIR}/workers/comfy_agent/workflows/SCAIL-2_Animation.json" \
    --timeout-seconds "${SCAIL2_SMOKE_TIMEOUT_SECONDS:-7200}" \
    --poll-seconds 15
  copy_latest_result_to_root
}

restore_slot0() {
  if [ "$MODE" != "execute" ]; then
    cat <<PLAN
[dry-run] Would stop ${CONTAINER_NAME}.
[dry-run] Would start ${OLD_SLOT0_CONTAINER}.
[dry-run] Would set ${LEGACY_AGENT_SLOT0}=disabled and ${AIO_AGENT_SLOT0}=enabled.
PLAN
    return
  fi
  remote_compose "down" || ssh "$SSH_HOST" "docker stop '${CONTAINER_NAME}' >/dev/null || true"
  ssh "$SSH_HOST" "docker start '${OLD_SLOT0_CONTAINER}' >/dev/null"
  local deadline=$((SECONDS + 900))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -fsS --max-time 8 "${COMFY_URL}/system_stats" >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  curl -fsS --max-time 15 "${COMFY_URL}/system_stats" >/dev/null
  set_control "$LEGACY_AGENT_SLOT0" disabled scail2_restore_keep_legacy_disabled
  set_control "$AIO_AGENT_SLOT0" enabled scail2_restore_slot0_aio
  log "slot0 img2img AIO restored at ${COMFY_URL}"
}

show_status() {
  echo "== Central worker status =="
  central_worker_status || true
  echo "== Central control state =="
  control_state "$AIO_AGENT_SLOT0" "$LEGACY_AGENT_SLOT0" || true
  echo "== gpu-002 containers =="
  ssh "$SSH_HOST" "docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}' | grep -E '^(${CONTAINER_NAME}|${OLD_SLOT0_CONTAINER}|${SLOT1_CONTAINER})\\b' || true"
  echo "== Comfy endpoints =="
  curl -fsS --max-time 5 "${COMFY_URL}/system_stats" >/dev/null && echo "${COMFY_URL}/system_stats OK" || echo "${COMFY_URL}/system_stats unavailable"
  curl -fsS --max-time 5 "http://${PUBLIC_HOST}:8191/system_stats" >/dev/null && echo "http://${PUBLIC_HOST}:8191/system_stats OK" || echo "http://${PUBLIC_HOST}:8191/system_stats unavailable"
}

run_all() {
  preflight
  build_image
  push_image
  start_scail2
  verify_runtime
  run_sample
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    status|preflight|build-image|push-image|start|verify|run-sample|copy-result|restore|all)
      ACTION="$1"
      shift
      ;;
    --execute)
      MODE="execute"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --image-ref)
      IMAGE_REF="${2:?missing value for --image-ref}"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="${2:?missing value for --image-tag}"
      IMAGE_REF="${REGISTRY_HOST}/allbot/comfy-runpod-scail2:${IMAGE_TAG}"
      shift 2
      ;;
    --ssh-host)
      SSH_HOST="${2:?missing value for --ssh-host}"
      shift 2
      ;;
    --host-port)
      HOST_PORT="${2:?missing value for --host-port}"
      COMFY_URL="http://${PUBLIC_HOST}:${HOST_PORT}"
      shift 2
      ;;
    --prod-env-file)
      PROD_ENV_FILE="${2:?missing value for --prod-env-file}"
      shift 2
      ;;
    --model-env-file)
      MODEL_ENV_FILE="${2:?missing value for --model-env-file}"
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
  preflight)
    preflight
    ;;
  build-image)
    build_image
    ;;
  push-image)
    push_image
    ;;
  start)
    start_scail2
    ;;
  verify)
    verify_runtime
    ;;
  run-sample)
    run_sample
    ;;
  copy-result)
    copy_latest_result_to_root
    ;;
  restore)
    restore_slot0
    ;;
  all)
    run_all
    ;;
  *)
    echo "Unknown action: $ACTION" >&2
    usage >&2
    exit 2
    ;;
esac
