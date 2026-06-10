#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_NAME=""
MODE="dry-run"
COOLDOWN_SECONDS=300
STATE_DIR="$ROOT_DIR/logs/worker-recovery-watchdog"
CURL_TIMEOUT_SECONDS=5
COMFY_TIMEOUT_SECONDS=3

usage() {
    cat <<'EOF'
Usage: scripts/watch_cloud_worker_recovery.sh --env cloud-test|cloud-prod [--mode dry-run|execute]

Safely checks local cloud worker relay/agents and restarts only exact unhealthy
containers when running in execute mode. Default mode is dry-run.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --env)
            ENV_NAME="${2:-}"
            shift
            ;;
        --mode)
            MODE="${2:-}"
            shift
            ;;
        --cooldown-seconds)
            COOLDOWN_SECONDS="${2:-}"
            shift
            ;;
        --state-dir)
            STATE_DIR="${2:-}"
            shift
            ;;
        --curl-timeout-seconds)
            CURL_TIMEOUT_SECONDS="${2:-}"
            shift
            ;;
        --comfy-timeout-seconds)
            COMFY_TIMEOUT_SECONDS="${2:-}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            exit 2
            ;;
    esac
    shift
done

if [ "$ENV_NAME" != "cloud-test" ] && [ "$ENV_NAME" != "cloud-prod" ]; then
    echo "--env must be cloud-test or cloud-prod" >&2
    exit 2
fi

if [ "$MODE" != "dry-run" ] && [ "$MODE" != "execute" ]; then
    echo "--mode must be dry-run or execute" >&2
    exit 2
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

read_env_value() {
    local env_file=$1
    local key=$2
    sed -n "s/^${key}=//p" "$env_file" | tail -n 1 | sed "s/^['\"]//; s/['\"]$//"
}

if [ "$ENV_NAME" = "cloud-test" ]; then
    ENV_FILE="${CLOUD_WORKER_RECOVERY_ENV_FILE:-$ROOT_DIR/.env.cloud.test}"
    COMPOSE_FILE="${CLOUD_WORKER_RECOVERY_COMPOSE_FILE:-$ROOT_DIR/workers/docker-compose-cloud-worker-test.yml}"
    CENTRAL_HOST="${CLOUD_TEST_CONTROL_HOST:-}"
    if [ -z "$CENTRAL_HOST" ] && [ -f "$ENV_FILE" ]; then
        CENTRAL_HOST="$(read_env_value "$ENV_FILE" CLOUD_TEST_CONTROL_HOST)"
    fi
    if [ -z "$CENTRAL_HOST" ] && [ -f "$ENV_FILE" ]; then
        CENTRAL_HOST="$(read_env_value "$ENV_FILE" CLOUD_TEST_TAILSCALE_IP)"
    fi
    CENTRAL_PORT=8004
    RELAY_PORT="${CLOUD_TEST_LOCAL_RELAY_PORT:-}"
    if [ -z "$RELAY_PORT" ] && [ -f "$ENV_FILE" ]; then
        RELAY_PORT="$(read_env_value "$ENV_FILE" CLOUD_TEST_LOCAL_RELAY_PORT)"
    fi
    RELAY_PORT="${RELAY_PORT:-8014}"
    RELAY_SERVICE="cloud-worker-relay-test"
    AGENT_PREFIX="cloud_worker_test_"
    SERVICE_PREFIX="cloud-comfy-agent-test-"
else
    ENV_FILE="${CLOUD_WORKER_RECOVERY_ENV_FILE:-$ROOT_DIR/.env.cloud.prod}"
    COMPOSE_FILE="${CLOUD_WORKER_RECOVERY_COMPOSE_FILE:-$ROOT_DIR/workers/docker-compose-cloud-prod-worker.yml}"
    CENTRAL_HOST="${CLOUD_PROD_TAILSCALE_IP:-}"
    if [ -z "$CENTRAL_HOST" ] && [ -f "$ENV_FILE" ]; then
        CENTRAL_HOST="$(read_env_value "$ENV_FILE" CLOUD_PROD_TAILSCALE_IP)"
    fi
    CENTRAL_PORT=8003
    RELAY_PORT="${CLOUD_PROD_LOCAL_RELAY_PORT:-}"
    if [ -z "$RELAY_PORT" ] && [ -f "$ENV_FILE" ]; then
        RELAY_PORT="$(read_env_value "$ENV_FILE" CLOUD_PROD_LOCAL_RELAY_PORT)"
    fi
    RELAY_PORT="${RELAY_PORT:-8013}"
    RELAY_SERVICE="cloud-prod-worker-relay"
    AGENT_PREFIX="cloud_prod_worker_"
    SERVICE_PREFIX="cloud-prod-comfy-agent-"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Missing env file: $ENV_FILE" >&2
    exit 1
fi
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Missing compose file: $COMPOSE_FILE" >&2
    exit 1
fi
if [ -z "$CENTRAL_HOST" ]; then
    echo "Missing Central host for $ENV_NAME" >&2
    exit 1
fi

CENTRAL_URL="http://${CENTRAL_HOST}:${CENTRAL_PORT}"
RELAY_READY_URL="http://127.0.0.1:${RELAY_PORT}/ready"
COMFY_URLS=(
    "http://192.168.1.226:8188/system_stats"
    "http://192.168.1.177:8188/system_stats"
    "http://192.168.1.177:8189/system_stats"
    "http://192.168.1.252:8188/system_stats"
    "http://192.168.1.252:8189/system_stats"
    "http://192.168.1.2:8188/system_stats"
    "http://192.168.1.2:8189/system_stats"
)

mkdir -p "$STATE_DIR"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

curl_ok() {
    local url=$1
    local timeout=$2
    curl --noproxy '*' -fsS --max-time "$timeout" "$url" >/dev/null 2>&1
}

curl_status() {
    local url=$1
    local timeout=$2
    local status
    status="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --max-time "$timeout" "$url" 2>/dev/null || true)"
    printf '%s' "${status:-000}"
}

curl_text() {
    local url=$1
    local timeout=$2
    curl --noproxy '*' -fsS --max-time "$timeout" "$url"
}

service_cooldown_remaining() {
    local service=$1
    local state_file="$STATE_DIR/${ENV_NAME}_${service}.last"
    if [ ! -f "$state_file" ]; then
        echo 0
        return
    fi
    local last_ts now elapsed remaining
    last_ts="$(sed -n '1p' "$state_file" 2>/dev/null || true)"
    case "$last_ts" in
        ''|*[!0-9]*)
            echo 0
            return
            ;;
    esac
    now="$(date +%s)"
    elapsed=$((now - last_ts))
    remaining=$((COOLDOWN_SECONDS - elapsed))
    if [ "$remaining" -gt 0 ]; then
        echo "$remaining"
    else
        echo 0
    fi
}

mark_service_recovered() {
    local service=$1
    date +%s > "$STATE_DIR/${ENV_NAME}_${service}.last"
}

recover_service() {
    local service=$1
    local reason=$2
    local remaining
    remaining="$(service_cooldown_remaining "$service")"
    if [ "$remaining" != "0" ]; then
        log "cooldown service=${service} remaining=${remaining}s reason=${reason}"
        return
    fi

    if [ "$MODE" = "dry-run" ]; then
        log "[dry-run] would recover service=${service} reason=${reason}"
        return
    fi

    log "recovering service=${service} reason=${reason}"
    if [ "$(docker inspect -f '{{.State.Running}}' "$service" 2>/dev/null || true)" = "true" ]; then
        docker restart "$service" >/dev/null
    else
        "${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps "$service"
    fi
    mark_service_recovered "$service"
}

agent_id_for_index() {
    printf '%s%02d' "$AGENT_PREFIX" "$1"
}

service_for_index() {
    printf '%s%d' "$SERVICE_PREFIX" "$1"
}

extract_worker_statuses() {
    python3 -c '
import json
import sys

payload = json.load(sys.stdin)
workers = payload.get("workers") or []
for worker in workers:
    agent_id = str(worker.get("agent_id", ""))
    status = str(worker.get("status", "missing"))
    print(f"{agent_id}\t{status}")
'
}

worker_status_for_agent() {
    local statuses=$1
    local agent_id=$2
    local line
    line="$(printf '%s\n' "$statuses" | awk -F '\t' -v agent="$agent_id" '$1 == agent {print $2; exit}')"
    if [ -z "$line" ]; then
        echo "missing"
    else
        echo "$line"
    fi
}

log "checking env=${ENV_NAME} mode=${MODE} central=${CENTRAL_URL} relay=${RELAY_READY_URL}"

COMFY_OK=()
UNREACHABLE_COMFY=0
for url in "${COMFY_URLS[@]}"; do
    if curl_ok "$url" "$COMFY_TIMEOUT_SECONDS"; then
        COMFY_OK+=("1")
    else
        COMFY_OK+=("0")
        UNREACHABLE_COMFY=$((UNREACHABLE_COMFY + 1))
    fi
done

if ! curl_ok "${CENTRAL_URL}/health" "$CURL_TIMEOUT_SECONDS"; then
    if [ "$UNREACHABLE_COMFY" -ge 2 ]; then
        log "network_outage central_unreachable=true unreachable_comfy=${UNREACHABLE_COMFY}; no restart"
    else
        log "central_unreachable=true unreachable_comfy=${UNREACHABLE_COMFY}; no restart"
    fi
    exit 0
fi

RELAY_READY_STATUS="$(curl_status "$RELAY_READY_URL" "$CURL_TIMEOUT_SECONDS")"
case "$RELAY_READY_STATUS" in
    200)
        ;;
    404)
        log "relay_ready_endpoint_missing service=${RELAY_SERVICE} status=404; no restart"
        ;;
    *)
        recover_service "$RELAY_SERVICE" "relay_ready_failed_status_${RELAY_READY_STATUS}"
        ;;
esac

WORKERS_JSON="$(curl_text "${CENTRAL_URL}/system/workers" "$CURL_TIMEOUT_SECONDS" || true)"
if [ -z "$WORKERS_JSON" ]; then
    log "system_workers_unreachable=true; no worker restart"
    exit 0
fi

WORKER_STATUSES="$(printf '%s' "$WORKERS_JSON" | extract_worker_statuses)"

for idx in 1 2 3 4 5 6 7; do
    agent_id="$(agent_id_for_index "$idx")"
    service="$(service_for_index "$idx")"
    status="$(worker_status_for_agent "$WORKER_STATUSES" "$agent_id")"
    comfy_index=$((idx - 1))

    case "$status" in
        error|quarantined|missing)
            if [ "${COMFY_OK[$comfy_index]}" = "1" ]; then
                recover_service "$service" "worker_status_${status}"
            else
                log "skip service=${service} status=${status} reason=comfy_unreachable"
            fi
            ;;
        *)
            log "ok service=${service} agent=${agent_id} status=${status}"
            ;;
    esac
done

log "check complete env=${ENV_NAME} mode=${MODE}"
