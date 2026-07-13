#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
ACTION="render"
ENV_FILE=".env.lan-aio-test"
COMPOSE_OUT=""
KEEP_CONTAINER="false"

ASSIGNMENT="lan-002-8188-worker-06"
PROFILE="img2img_lora"
HOST_PORT="8190"
TEMP_AGENT_ID="lan_aio_test_gpu002_gpu0_img2img_lora_01"
LEGACY_AGENT_ID="cloud_worker_test_06"
CENTRAL_URL="https://worker-central-test.aivison.it.com"
SSH_HOST="allbot-gpu-002"
REMOTE_DIR="${LAN_AIO_REMOTE_DIR:-/home/chuzeyu/allbot-runpod-aio-canary/gpu002-img2img-lora}"
REMOTE_COMPOSE_FILE="${REMOTE_DIR}/docker-compose.yml"
REMOTE_ENV_FILE="${REMOTE_DIR}/.env.lan-aio-test"

usage() {
  cat <<'USAGE'
Usage:
  scripts/lan_runpod_aio_canary.sh [options]

Options:
  --action <name>     render, preflight, start-heartbeat, enable-canary, restore, stop.
  --dry-run           Print the guarded operations only. Default.
  --execute           Run the selected operation.
  --env-file <path>   Ignored env file with LAN/Cloud-test runtime secrets.
  --compose-out <p>   With --action render --execute, write rendered compose to this path.
  --keep-container    With --action restore, leave the canary container running.
  -h, --help          Show this help.

Scope is intentionally fixed to gpu-002 slot0/img2img_lora:
  assignment: lan-002-8188-worker-06
  temp agent: lan_aio_test_gpu002_gpu0_img2img_lora_01
  host port: 8190
USAGE
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
    case "$key" in
      LAN_AIO_AGENT_SECRET_TOKEN)
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "${key}=${value}"
        ;;
    esac
  done < "$file"
}

redacted_compose_command() {
  printf '%s\n' \
    "cd ${REMOTE_DIR} && docker compose --env-file ${REMOTE_ENV_FILE} -f ${REMOTE_COMPOSE_FILE} <up|down>"
}

render_args() {
  printf '%q ' \
    python scripts/gpu_pool_controller.py runtime-render \
    --assignment "$ASSIGNMENT" \
    --profile "$PROFILE" \
    --host-port "$HOST_PORT" \
    --runtime-shape runpod_all_in_one \
    --agent-id "$TEMP_AGENT_ID" \
    --central-url "$CENTRAL_URL"
}

validate_scope() {
  [ "$ASSIGNMENT" = "lan-002-8188-worker-06" ] || {
    echo "Refusing unsupported assignment: ${ASSIGNMENT}" >&2
    exit 2
  }
  [ "$PROFILE" = "img2img_lora" ] || {
    echo "Refusing unsupported profile: ${PROFILE}" >&2
    exit 2
  }
  [ "$HOST_PORT" = "8190" ] || {
    echo "Refusing unsupported canary host port: ${HOST_PORT}" >&2
    exit 2
  }
  [ "$TEMP_AGENT_ID" = "lan_aio_test_gpu002_gpu0_img2img_lora_01" ] || {
    echo "Refusing unsupported temp agent: ${TEMP_AGENT_ID}" >&2
    exit 2
  }
  [ "$LEGACY_AGENT_ID" = "cloud_worker_test_06" ] || {
    echo "Refusing unsupported legacy agent: ${LEGACY_AGENT_ID}" >&2
    exit 2
  }
  [ "$SSH_HOST" = "allbot-gpu-002" ] || {
    echo "Refusing unsupported SSH host: ${SSH_HOST}" >&2
    exit 2
  }
}

control_agent() {
  local agent_id="$1"
  local state="$2"
  local reason="$3"
  local ttl="${4:-}"
  if [ "$MODE" != "execute" ]; then
    if [ -n "$ttl" ]; then
      echo "[dry-run] Would set Central control ${agent_id}=${state} ttl=${ttl}"
    else
      echo "[dry-run] Would set Central control ${agent_id}=${state}"
    fi
    return 0
  fi
  : "${LAN_AIO_AGENT_SECRET_TOKEN:?LAN_AIO_AGENT_SECRET_TOKEN is required}"
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

run_preflight() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would verify ${CENTRAL_URL}/health"
    echo "[dry-run] Would verify http://192.168.1.115:5000/v2/"
    echo "[dry-run] Would verify http://192.168.1.115:9010/minio/health/ready"
    echo "[dry-run] Would verify http://192.168.1.2:8188/system_stats and /queue"
    echo "[dry-run] Would verify current workers through ${CENTRAL_URL}/system/workers"
    return 0
  fi
  curl -fsS "${CENTRAL_URL}/health" >/dev/null
  curl -fsS "http://192.168.1.115:5000/v2/" >/dev/null
  curl -fsS "http://192.168.1.115:9010/minio/health/ready" >/dev/null
  curl -fsS "http://192.168.1.2:8188/system_stats" >/dev/null
  curl -fsS "http://192.168.1.2:8188/queue" >/dev/null
  curl -fsS "${CENTRAL_URL}/system/workers" >/dev/null
  echo "LAN AIO canary preflight passed."
}

run_render() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would render compose:"
    render_args
    echo
    return 0
  fi
  if [ -n "$COMPOSE_OUT" ]; then
    python scripts/gpu_pool_controller.py runtime-render \
      --assignment "$ASSIGNMENT" \
      --profile "$PROFILE" \
      --host-port "$HOST_PORT" \
      --runtime-shape runpod_all_in_one \
      --agent-id "$TEMP_AGENT_ID" \
      --central-url "$CENTRAL_URL" > "$COMPOSE_OUT"
    echo "Rendered LAN AIO compose to ${COMPOSE_OUT}"
  else
    python scripts/gpu_pool_controller.py runtime-render \
      --assignment "$ASSIGNMENT" \
      --profile "$PROFILE" \
      --host-port "$HOST_PORT" \
      --runtime-shape runpod_all_in_one \
      --agent-id "$TEMP_AGENT_ID" \
      --central-url "$CENTRAL_URL"
  fi
}

remote_compose() {
  local op="$1"
  ssh "$SSH_HOST" \
    "cd '${REMOTE_DIR}' && if docker compose version >/dev/null 2>&1; then docker compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; else docker-compose --env-file '${REMOTE_ENV_FILE}' -f '${REMOTE_COMPOSE_FILE}' ${op}; fi"
}

run_start_heartbeat() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would render compose and copy it to ${SSH_HOST}:${REMOTE_COMPOSE_FILE}"
    echo "[dry-run] Would copy ${ENV_FILE} to ${SSH_HOST}:${REMOTE_ENV_FILE}"
    control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_heartbeat_only" "3600"
    echo "[dry-run] Would run remote compose up -d:"
    redacted_compose_command
    return 0
  fi
  [ -f "$ENV_FILE" ] || {
    echo "Env file not found: ${ENV_FILE}" >&2
    exit 2
  }
  local tmp_compose
  tmp_compose="$(mktemp)"
  trap 'if [ -n "${tmp_compose:-}" ]; then rm -f "$tmp_compose"; fi' EXIT
  python scripts/gpu_pool_controller.py runtime-render \
    --assignment "$ASSIGNMENT" \
    --profile "$PROFILE" \
    --host-port "$HOST_PORT" \
    --runtime-shape runpod_all_in_one \
    --agent-id "$TEMP_AGENT_ID" \
    --central-url "$CENTRAL_URL" > "$tmp_compose"
  control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_heartbeat_only" "3600"
  ssh "$SSH_HOST" "mkdir -p '${REMOTE_DIR}' && chmod 700 '${REMOTE_DIR}'"
  scp "$tmp_compose" "${SSH_HOST}:${REMOTE_COMPOSE_FILE}" >/dev/null
  scp "$ENV_FILE" "${SSH_HOST}:${REMOTE_ENV_FILE}" >/dev/null
  ssh "$SSH_HOST" "chmod 600 '${REMOTE_ENV_FILE}'"
  remote_compose "up -d"
  echo "LAN AIO canary container started with temp agent disabled."
}

run_enable_canary() {
  control_agent "$LEGACY_AGENT_ID" "disabled" "lan_aio_canary_disable_legacy" "1800"
  control_agent "$TEMP_AGENT_ID" "enabled" "lan_aio_canary_enable_temp"
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would submit exactly one img2img_lora Web canary task manually after this point."
  else
    echo "Canary window opened: ${LEGACY_AGENT_ID}=disabled, ${TEMP_AGENT_ID}=enabled."
  fi
}

run_stop() {
  if [ "$MODE" != "execute" ]; then
    echo "[dry-run] Would run remote compose down:"
    redacted_compose_command
    return 0
  fi
  remote_compose "down"
  echo "LAN AIO canary container stopped."
}

run_restore() {
  control_agent "$TEMP_AGENT_ID" "disabled" "lan_aio_canary_restore_temp_disabled" "3600"
  control_agent "$LEGACY_AGENT_ID" "enabled" "lan_aio_canary_restore_legacy_enabled"
  if [ "$KEEP_CONTAINER" = "true" ]; then
    echo "Restore controls applied; canary container left running by request."
    return 0
  fi
  run_stop
}

while [ "$#" -gt 0 ]; do
  case "$1" in
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
    --env-file)
      ENV_FILE="${2:?missing value for --env-file}"
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

validate_scope
load_env_file "$ENV_FILE"

case "$ACTION" in
  render)
    run_render
    ;;
  preflight)
    run_preflight
    ;;
  start-heartbeat)
    run_start_heartbeat
    ;;
  enable-canary)
    run_enable_canary
    ;;
  restore)
    run_restore
    ;;
  stop)
    run_stop
    ;;
  *)
    echo "Unknown action: ${ACTION}" >&2
    usage >&2
    exit 2
    ;;
esac
