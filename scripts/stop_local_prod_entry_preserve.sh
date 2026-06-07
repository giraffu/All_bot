#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env"
EXECUTE=false
INCLUDE_WORKERS=false
INCLUDE_TEST_WORKERS=false

usage() {
    cat <<'EOF'
Usage: scripts/stop_local_prod_entry_preserve.sh [--dry-run] [--execute] [--include-workers] [--include-test-workers]

Default mode is --dry-run.

Stops local production entry services while preserving containers, images,
volumes, PostgreSQL, Redis, MinIO, and local data. This script never removes
resources and never runs docker compose down.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            EXECUTE=false
            ;;
        --execute)
            EXECUTE=true
            ;;
        --include-workers)
            INCLUDE_WORKERS=true
            ;;
        --include-test-workers)
            INCLUDE_TEST_WORKERS=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            exit 2
            ;;
    esac
    shift
done

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

compose_stop() {
    local compose_file=$1
    local label=$2
    shift 2
    local services=("$@")

    if [ ! -f "$compose_file" ]; then
        echo "Skip ${label}: missing ${compose_file}"
        return
    fi

    if [ "$EXECUTE" != "true" ]; then
        echo "[dry-run] ${COMPOSE_CMD[*]} --env-file ${ENV_FILE} -f ${compose_file} stop ${services[*]}"
        return
    fi

    echo "Stopping ${label}: ${services[*]}"
    if [ -f "$ENV_FILE" ]; then
        "${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$compose_file" stop "${services[@]}"
    else
        "${COMPOSE_CMD[@]}" -f "$compose_file" stop "${services[@]}"
    fi
}

echo "Local production stop mode: $([ "$EXECUTE" = "true" ] && echo execute || echo dry-run)"
echo "This preserves DB/Redis/MinIO data and does not remove containers or volumes."

compose_stop "$ROOT_DIR/deploy/docker-compose.yml" "local prod user entry services" \
    bot payment-api web-api imgproxy

compose_stop "$ROOT_DIR/backend/docker-compose.yml" "local prod Central API" \
    api

compose_stop "$ROOT_DIR/dashboard/docker-compose.yml" "local prod Dashboard" \
    dashboard-backend dashboard-frontend

if [ "$INCLUDE_WORKERS" = "true" ]; then
    compose_stop "$ROOT_DIR/workers/docker-compose.yml" "local prod GPU workers" \
        comfy-agent-1 comfy-agent-2 comfy-agent-3 comfy-agent-4 comfy-agent-5 comfy-agent-6 comfy-agent-7
else
    echo "Skipping local prod GPU workers. Pass --include-workers only after runtime queues are empty."
fi

if [ "$INCLUDE_TEST_WORKERS" = "true" ]; then
    if [ "$EXECUTE" != "true" ]; then
        echo "[dry-run] docker stop \$(docker ps -q --filter name=cloud-comfy-agent-test)"
    else
        docker ps -q --filter 'name=cloud-comfy-agent-test' | xargs -r docker stop
    fi
else
    echo "Skipping cloud test workers. Pass --include-test-workers if they must release GPU capacity."
fi

if [ "$EXECUTE" != "true" ]; then
    echo "Dry-run complete. Re-run with --execute during an approved maintenance window."
else
    echo "Local production entry services stopped with data preserved."
fi
