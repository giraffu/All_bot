#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${CLOUD_PROD_ENV_FILE:-$ROOT_DIR/.env.cloud.prod}"
COMPOSE_FILE="$ROOT_DIR/workers/docker-compose-cloud-prod-worker.yml"
MODE="preflight"
ALLOW_TEST_WORKERS=false
SKIP_NETWORK_CHECKS=false

usage() {
    cat <<'EOF'
Usage: scripts/start_cloud_prod_worker.sh [--preflight-only] [--start] [--allow-test-workers] [--skip-network-checks]

Default mode is --preflight-only.

This script validates or starts the 7 local cloud production GPU workers. It
does not stop local production entry services and does not touch edge routing.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --preflight-only)
            MODE="preflight"
            ;;
        --start)
            MODE="start"
            ;;
        --allow-test-workers)
            ALLOW_TEST_WORKERS=true
            ;;
        --skip-network-checks)
            SKIP_NETWORK_CHECKS=true
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

if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE. Copy .env.cloud.prod.example to .env.cloud.prod first."
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Missing $COMPOSE_FILE."
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

read_env_value() {
    local key=$1
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

require_env_value() {
    local key=$1
    local value
    value="$(read_env_value "$key")"
    if [ -z "$value" ]; then
        echo "Missing required env key: $key"
        exit 1
    fi
    case "$value" in
        *'<'*'>'*|*CHANGE_ME*|*REPLACE_ME*|*replace-me*|super_secret_agent_token_2026)
            echo "Env key $key still contains a placeholder value."
            exit 1
            ;;
    esac
}

check_env_contract() {
    local required_keys=(
        CLOUD_PROD_TAILSCALE_IP
        AGENT_SECRET_TOKEN
        MINIO_ENDPOINT
        MINIO_ACCESS_KEY
        MINIO_SECRET_KEY
        MINIO_BUCKET
        MINIO_INPUT_BUCKET
        MINIO_RESULT_BUCKET
        MINIO_TEMPLATE_BUCKET
        MINIO_SECURE
    )

    local key
    for key in "${required_keys[@]}"; do
        require_env_value "$key"
    done

    if [ "$(read_env_value MINIO_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_INPUT_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_RESULT_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_TEMPLATE_BUCKET)" != "user-data-prod" ]; then
        echo "All worker storage buckets must be user-data-prod."
        exit 1
    fi
    if [ "$(read_env_value MINIO_SECURE)" != "true" ]; then
        echo "MINIO_SECURE must be true for R2."
        exit 1
    fi
}

check_test_workers() {
    local running_test_workers
    running_test_workers="$(docker ps --format '{{.Names}}' --filter 'name=cloud-comfy-agent-test' || true)"
    if [ -n "$running_test_workers" ] && [ "$ALLOW_TEST_WORKERS" != "true" ]; then
        echo "cloud-comfy-agent-test containers are still running:"
        echo "$running_test_workers"
        echo "Stop or limit test workers first, or pass --allow-test-workers after accepting GPU contention risk."
        exit 1
    fi
}

check_central_health() {
    local tailscale_ip
    tailscale_ip="$(read_env_value CLOUD_PROD_TAILSCALE_IP)"
    curl --noproxy '*' -fsS "http://${tailscale_ip}:8003/health" >/dev/null
}

check_r2_access() {
    python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

import boto3
from botocore.config import Config

env = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    env[key] = value.strip().strip('"').strip("'")

endpoint = env["MINIO_ENDPOINT"]
endpoint_url = endpoint if endpoint.startswith(("http://", "https://")) else f"https://{endpoint}"
client = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=env["MINIO_ACCESS_KEY"],
    aws_secret_access_key=env["MINIO_SECRET_KEY"],
    config=Config(
        signature_version="s3v4",
        retries={"max_attempts": 1},
        connect_timeout=5,
        read_timeout=10,
    ),
)
client.list_objects_v2(Bucket=env["MINIO_BUCKET"], MaxKeys=1)
print("R2 list_objects_v2 ok")
PY
}

check_worker_compose_services() {
    local count
    count="$("${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --services | grep -c '^cloud-prod-comfy-agent-' | tr -d '[:space:]')"
    if [ "$count" != "7" ]; then
        echo "Expected 7 cloud production worker services, got $count."
        exit 1
    fi
}

echo "Cloud prod worker mode: ${MODE}"
echo "Using env file: ${ENV_FILE}"

check_env_contract
check_test_workers
check_worker_compose_services

if [ "$SKIP_NETWORK_CHECKS" != "true" ]; then
    echo "Checking cloud production Central API reachability..."
    check_central_health
    echo "Checking R2/S3 access..."
    check_r2_access
else
    echo "Skipping network checks by request."
fi

if [ "$MODE" = "preflight" ]; then
    echo "Cloud production worker preflight passed. No workers were started."
    exit 0
fi

mkdir -p "$ROOT_DIR/logs/workers-cloud-prod"

echo "Starting 7 cloud production GPU workers..."
"${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

echo "Worker containers:"
docker ps --format 'table {{.Names}}\t{{.Status}}' --filter 'name=cloud-prod-comfy-agent-'

echo "Central worker view:"
curl --noproxy '*' -fsS "http://$(read_env_value CLOUD_PROD_TAILSCALE_IP):8003/system/workers" || true
echo
echo "Cloud production workers started. Verify heartbeats and supported task types before any edge cutover."
