#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="${1:-status}"
MODE="dry-run"

SSH_HOST="${PORNMASTER_FLUX2_TEST_SSH_HOST:-allbot-gpu-252}"
REMOTE_DIR="${PORNMASTER_FLUX2_TEST_REMOTE_DIR:-/home/user/allbot-pornmaster-flux2-edit-aio-test}"
HOST_PORT="${PORNMASTER_FLUX2_TEST_HOST_PORT:-8192}"
CONTAINER_NAME="${PORNMASTER_FLUX2_TEST_CONTAINER_NAME:-allbot-lan-aio-gpu-252-gpu0-pornmaster-flux2-edit-test}"
TEST_AGENT_ID="${PORNMASTER_FLUX2_TEST_AGENT_ID:-lan_aio_test_gpu252_gpu0_pornmaster_flux2_edit_01}"
PROD_SLOT="${PORNMASTER_FLUX2_PROD_SLOT:-gpu-252-gpu0-img2img_lora}"
PROD_CONTAINER="${PORNMASTER_FLUX2_PROD_CONTAINER:-allbot-lan-aio-gpu-252-gpu0-img2img_lora-prod}"
ASSIGNMENT="${PORNMASTER_FLUX2_TEST_ASSIGNMENT:-lan-252-8188-worker-04}"
PROFILE="${PORNMASTER_FLUX2_TEST_PROFILE:-pornmaster_flux2_edit}"
ENVIRONMENT="${PORNMASTER_FLUX2_TEST_ENVIRONMENT:-cloud-test}"
ENV_FILE="${PORNMASTER_FLUX2_TEST_ENV_FILE:-.env.cloud.test}"
MODEL_MANIFEST="${PORNMASTER_FLUX2_MODEL_MANIFEST:-/srv/allbot/model-registry/bundles/pornmaster_flux2_edit_baseline/2026-06-27/manifest.yml}"
REMOTE_WORKERS_MOUNT="${PORNMASTER_FLUX2_REMOTE_WORKERS_MOUNT:-/workspace/remote_workers}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_pornmaster_flux2_edit_aio_test.sh <action> [--execute]

Actions:
  status             Read current prod slot status and test AIO container status.
  render             Render the cloud-test all-in-one compose to stdout.
  plan               Print runtime dry-run plan.
  preflight          Verify local manifest and render/plan shape.
  start              Drain/disable prod img2img_lora slot, stop prod container, start test AIO disabled.
  enable-test-agent  Enable the cloud-test PornMaster Flux2 test agent.
  disable-test-agent Disable the cloud-test PornMaster Flux2 test agent.
  restore            Disable test agent, stop test AIO, restart and re-enable prod img2img_lora slot.

Options:
  --execute          Perform mutations. Default is dry-run.
  -h, --help         Show this help.

This helper only targets cloud-test AIO canary on gpu-252 port 8192. It does not
deploy cloud-prod code or modify production compose files.
USAGE
}

log() {
  printf '[lan-pornmaster-flux2-test] %s\n' "$*"
}

run() {
  if [[ "$MODE" == "execute" ]]; then
    "$@"
  else
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
  fi
}

render_compose() {
  (
    cd "$ROOT_DIR"
    PYTHONPATH=. python -m ops.gpu_pool_controller.cli runtime-render \
      --assignment "$ASSIGNMENT" \
      --profile "$PROFILE" \
      --host-port "$HOST_PORT" \
      --container-name "$CONTAINER_NAME" \
      --runtime-shape runpod_all_in_one \
      --agent-id "$TEST_AGENT_ID" \
      --environment "$ENVIRONMENT"
  )
}

render_compose_with_local_bundle() {
  local remote_bundle_dir="$1"
  local rendered_compose
  rendered_compose="$(mktemp /tmp/pornmaster-flux2-edit-render.XXXXXX.yml)"
  render_compose > "$rendered_compose"
  python3 - "$remote_bundle_dir" "$REMOTE_WORKERS_MOUNT" "$rendered_compose" <<'PY'
import sys
from pathlib import Path

import yaml

remote_bundle_dir = sys.argv[1]
container_bundle_dir = sys.argv[2]
rendered_compose = Path(sys.argv[3])
data = yaml.safe_load(rendered_compose.read_text())
services = data.get("services") or {}
if len(services) != 1:
    raise SystemExit(f"expected one service in rendered compose, got {len(services)}")
service = next(iter(services.values()))
environment = service.setdefault("environment", {})
environment["RUNPOD_REMOTE_WORKER_ROOT"] = container_bundle_dir
environment["PYTHONPATH"] = f"{container_bundle_dir}:${{PYTHONPATH:-}}"
volumes = service.setdefault("volumes", [])
mount = f"{remote_bundle_dir}:{container_bundle_dir}:rw"
if mount not in volumes:
    volumes.append(mount)
print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
PY
  rm -f "$rendered_compose"
}

runtime_plan() {
  (
    cd "$ROOT_DIR"
    PYTHONPATH=. python -m ops.gpu_pool_controller.cli runtime-plan \
      --assignment "$ASSIGNMENT" \
      --profile "$PROFILE" \
      --host-port "$HOST_PORT" \
      --container-name "$CONTAINER_NAME" \
      --runtime-shape runpod_all_in_one \
      --agent-id "$TEST_AGENT_ID" \
      --environment "$ENVIRONMENT"
  )
}

load_env_value() {
  local key="$1"
  load_env_value_from_file "$ROOT_DIR/$ENV_FILE" "$key"
}

load_env_value_from_file() {
  local path="$1"
  local key="$2"
  python3 - "$path" "$key" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
for raw in path.read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.removeprefix("export ").strip() == key:
        print(value.strip().strip('"').strip("'"))
        break
PY
}

write_compose_env() {
  local output="$1"
  local agent_token minio_endpoint minio_access minio_secret model_access model_secret
  agent_token="${LAN_AIO_AGENT_SECRET_TOKEN:-${AGENT_SECRET_TOKEN:-$(load_env_value AGENT_SECRET_TOKEN)}}"
  minio_endpoint="${LAN_AIO_MINIO_ENDPOINT:-$(load_env_value MINIO_ENDPOINT)}"
  minio_access="${LAN_AIO_MINIO_ACCESS_KEY:-$(load_env_value MINIO_ACCESS_KEY)}"
  minio_secret="${LAN_AIO_MINIO_SECRET_KEY:-$(load_env_value MINIO_SECRET_KEY)}"
  model_access="${LAN_MODEL_CACHE_ACCESS_KEY:-$(load_env_value_from_file "$ROOT_DIR/.env.lan.model-cache" LAN_MODEL_CACHE_ACCESS_KEY)}"
  model_secret="${LAN_MODEL_CACHE_SECRET_KEY:-$(load_env_value_from_file "$ROOT_DIR/.env.lan.model-cache" LAN_MODEL_CACHE_SECRET_KEY)}"

  [[ -n "$agent_token" ]] || { log "missing AGENT_SECRET_TOKEN or LAN_AIO_AGENT_SECRET_TOKEN"; return 1; }
  [[ -n "$minio_endpoint" ]] || { log "missing MINIO_ENDPOINT or LAN_AIO_MINIO_ENDPOINT"; return 1; }
  [[ -n "$minio_access" ]] || { log "missing MINIO_ACCESS_KEY or LAN_AIO_MINIO_ACCESS_KEY"; return 1; }
  [[ -n "$minio_secret" ]] || { log "missing MINIO_SECRET_KEY or LAN_AIO_MINIO_SECRET_KEY"; return 1; }
  [[ -n "$model_access" ]] || { log "missing LAN_MODEL_CACHE_ACCESS_KEY"; return 1; }
  [[ -n "$model_secret" ]] || { log "missing LAN_MODEL_CACHE_SECRET_KEY"; return 1; }

  {
    printf 'LAN_AIO_AGENT_SECRET_TOKEN=%s\n' "$agent_token"
    printf 'LAN_AIO_MINIO_ENDPOINT=%s\n' "$minio_endpoint"
    printf 'LAN_AIO_MINIO_ACCESS_KEY=%s\n' "$minio_access"
    printf 'LAN_AIO_MINIO_SECRET_KEY=%s\n' "$minio_secret"
    printf 'LAN_MODEL_CACHE_ACCESS_KEY=%s\n' "$model_access"
    printf 'LAN_MODEL_CACHE_SECRET_KEY=%s\n' "$model_secret"
  } > "$output"
}

set_test_agent_control() {
  local state="$1"
  local token
  token="${AGENT_SECRET_TOKEN:-$(load_env_value AGENT_SECRET_TOKEN)}"
  if [[ -z "$token" ]]; then
    log "AGENT_SECRET_TOKEN missing from environment or $ENV_FILE"
    return 1
  fi
  if [[ "$MODE" != "execute" ]]; then
    log "[dry-run] set cloud-test agent $TEST_AGENT_ID control=$state"
    return 0
  fi
  python3 - "$TEST_AGENT_ID" "$state" "$token" <<'PY'
import json
import sys
import urllib.request

agent_id, state, token = sys.argv[1:4]
payload = json.dumps({
    "state": state,
    "reason": "pornmaster_flux2_edit_cloud_test_canary",
}).encode("utf-8")
request = urllib.request.Request(
    f"https://worker-central-test.aivison.it.com/api/agent/task/control/{agent_id}",
    data=payload,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "allbot-pornmaster-flux2-test/1.0",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    response.read()
print(f"{agent_id}={state}")
PY
}

preflight() {
  [[ -f "$MODEL_MANIFEST" ]] || {
    log "missing local model manifest: $MODEL_MANIFEST"
    return 1
  }
  runtime_plan
}

start_test_aio() {
  preflight
  set_test_agent_control disabled
  run "$ROOT_DIR/scripts/lan_aio_fleet_prod_ops.py" drain-aio --slot "$PROD_SLOT" --include-disabled --execute
  run "$ROOT_DIR/scripts/lan_aio_fleet_prod_ops.py" wait-idle --slot "$PROD_SLOT" --include-disabled --execute
  run "$ROOT_DIR/scripts/lan_aio_fleet_prod_ops.py" disable-aio --slot "$PROD_SLOT" --include-disabled --execute
  run ssh "$SSH_HOST" bash -lc "docker stop '$PROD_CONTAINER' >/dev/null 2>&1 || true"

  local local_compose
  local local_env
  local_compose="$(mktemp /tmp/pornmaster-flux2-edit-aio.XXXXXX.yml)"
  local_env="$(mktemp /tmp/pornmaster-flux2-edit-aio.XXXXXX.env)"
  render_compose_with_local_bundle "$REMOTE_DIR/remote_workers" > "$local_compose"
  write_compose_env "$local_env"
  run ssh "$SSH_HOST" mkdir -p "$REMOTE_DIR"
  run rsync -az --delete \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    "$ROOT_DIR/remote_workers/" \
    "$SSH_HOST:$REMOTE_DIR/remote_workers/"
  run scp "$local_compose" "$SSH_HOST:$REMOTE_DIR/docker-compose.yml"
  run scp "$local_env" "$SSH_HOST:$REMOTE_DIR/.env"
  rm -f "$local_compose"
  rm -f "$local_env"
  run ssh "$SSH_HOST" docker compose --env-file "$REMOTE_DIR/.env" -f "$REMOTE_DIR/docker-compose.yml" up -d
}

restore_prod_aio() {
  set_test_agent_control disabled
  run ssh "$SSH_HOST" docker compose --env-file "$REMOTE_DIR/.env" -f "$REMOTE_DIR/docker-compose.yml" down
  run ssh "$SSH_HOST" docker start "$PROD_CONTAINER"
  run "$ROOT_DIR/scripts/lan_aio_fleet_prod_ops.py" enable-aio --slot "$PROD_SLOT" --include-disabled --execute
}

shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      MODE="execute"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "unknown option: $1"
      usage
      exit 2
      ;;
  esac
  shift
done

case "$ACTION" in
  status)
    "$ROOT_DIR/scripts/lan_aio_fleet_prod_ops.py" status --slot "$PROD_SLOT" --include-disabled
    ssh "$SSH_HOST" "docker ps -a --filter name=$CONTAINER_NAME --format '{{.Names}} {{.Status}}'"
    ;;
  render)
    render_compose
    ;;
  plan)
    runtime_plan
    ;;
  preflight)
    preflight
    ;;
  start)
    start_test_aio
    ;;
  enable-test-agent)
    set_test_agent_control enabled
    ;;
  disable-test-agent)
    set_test_agent_control disabled
    ;;
  restore)
    restore_prod_aio
    ;;
  -h|--help)
    usage
    ;;
  *)
    log "unknown action: $ACTION"
    usage
    exit 2
    ;;
esac
