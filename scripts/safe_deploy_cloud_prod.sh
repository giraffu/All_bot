#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${CLOUD_PROD_ENV_FILE:-$ROOT_DIR/.env.cloud.prod}"
COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose-cloud-prod.yml"
MODE="preflight"
WITH_DB_UPGRADE=false
SKIP_NETWORK_CHECKS=false

usage() {
    cat <<'EOF'
Usage: scripts/safe_deploy_cloud_prod.sh [--preflight-only] [--start-control-plane] [--with-db-upgrade] [--skip-network-checks]

Default mode is --preflight-only.

This script prepares or starts the cloud production control plane only. It never
starts cloud-tg-bot-prod and never changes edge Nginx/DNS routing.

Options:
  --preflight-only       Validate env, compose rendering, R2 and Telegram API reachability.
  --start-control-plane  Build and start Central/Web/Payment/Dashboard/imgproxy.
  --with-db-upgrade      With --start-control-plane, run alembic upgrade head on the configured cloud DB.
  --skip-network-checks  Skip R2 and Telegram Local Bot API probes.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --preflight-only)
            MODE="preflight"
            ;;
        --start-control-plane)
            MODE="start"
            ;;
        --with-db-upgrade)
            WITH_DB_UPGRADE=true
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

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required on the cloud control plane."
    exit 1
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

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
        *'<'*'>'*|*CHANGE_ME*|*REPLACE_ME*|*replace-me*|your_secure_token_here|super_secret_agent_token_2026|super-secret-jwt-key-change-in-production)
            echo "Env key $key still contains a placeholder value."
            exit 1
            ;;
    esac
}

check_duplicate_env_keys() {
    local duplicates
    duplicates="$(
        awk -F= '
            /^[[:space:]]*($|#)/ { next }
            {
                key=$1
                sub(/^[[:space:]]+/, "", key)
                sub(/[[:space:]]+$/, "", key)
                seen[key]++
            }
            END {
                for (key in seen) {
                    if (seen[key] > 1) print key
                }
            }
        ' "$ENV_FILE"
    )"
    if [ -n "$duplicates" ]; then
        echo "Duplicate keys found in $ENV_FILE:"
        echo "$duplicates"
        exit 1
    fi
}

check_env_contract() {
    check_duplicate_env_keys

    local required_keys=(
        BOT_TYPE
        REDIS_PREFIX
        CLOUD_PROD_BIND_IP
        CLOUD_PROD_TAILSCALE_IP
        CLOUD_PROD_DATABASE_URL
        CLOUD_PROD_DATABASE_URL_SYNC
        CLOUD_PROD_REDIS_URL
        CLOUD_PROD_WORKER_REDIS_URL
        API_TOKEN
        AUTH_TOKEN
        AGENT_SECRET_TOKEN
        JWT_SECRET_KEY
        MINIO_ENDPOINT
        MINIO_ACCESS_KEY
        MINIO_SECRET_KEY
        MINIO_BUCKET
        MINIO_INPUT_BUCKET
        MINIO_RESULT_BUCKET
        MINIO_TEMPLATE_BUCKET
        MINIO_SECURE
        R2_ENDPOINT
        R2_ACCESS_KEY
        R2_SECRET_KEY
        R2_BUCKET
        R2_PUBLIC_DOMAIN
        HUANYUY_NOTIFY_URL
        HUANYUY_RETURN_URL
        DASHBOARD_ADMIN_USERNAME
        DASHBOARD_ADMIN_PASSWORD_HASH
        DASHBOARD_SECRET_KEY
        BOT_TOKEN
    )

    local key
    for key in "${required_keys[@]}"; do
        require_env_value "$key"
    done

    if [ "$(read_env_value BOT_TYPE)" != "PROD" ]; then
        echo "BOT_TYPE must be PROD."
        exit 1
    fi
    if [ "$(read_env_value REDIS_PREFIX)" != "prod_bot_" ]; then
        echo "REDIS_PREFIX must be prod_bot_."
        exit 1
    fi
    if [ "$(read_env_value API_TOKEN)" != "$(read_env_value AUTH_TOKEN)" ]; then
        echo "API_TOKEN and AUTH_TOKEN must be identical."
        exit 1
    fi
    if [ "$(read_env_value MINIO_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_INPUT_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_RESULT_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value MINIO_TEMPLATE_BUCKET)" != "user-data-prod" ] ||
       [ "$(read_env_value R2_BUCKET)" != "user-data-prod" ]; then
        echo "All online storage buckets must be user-data-prod."
        exit 1
    fi
    if [ "$(read_env_value MINIO_SECURE)" != "true" ]; then
        echo "MINIO_SECURE must be true for R2."
        exit 1
    fi
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

check_telegram_local_api() {
    python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import json
import sys
import urllib.request

env = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    env[key] = value.strip().strip('"').strip("'")

api_base = env.get("TELEGRAM_API_BASE_URL", "http://69.63.220.115:8081").rstrip("/")
file_base = env.get("TELEGRAM_FILE_API_BASE_URL", "http://69.63.220.115:8082").rstrip("/")
token = env["BOT_TOKEN"]

with urllib.request.urlopen(f"{api_base}/bot{token}/getMe", timeout=10) as response:
    payload = json.load(response)
    if not payload.get("ok"):
        raise RuntimeError("Telegram getMe returned ok=false")

with urllib.request.urlopen(f"{file_base}/", timeout=10) as response:
    if response.status >= 500:
        raise RuntimeError(f"Telegram file API returned {response.status}")

print("Telegram Local Bot API ok")
PY
}

wait_for_http_ready() {
    local service_name=$1
    local url=$2
    local max_retries=${3:-40}
    local sleep_seconds=${4:-5}
    local attempt=1

    echo "Waiting for ${service_name}: ${url}"
    while [ "$attempt" -le "$max_retries" ]; do
        if curl --noproxy '*' -fsS "$url" >/dev/null 2>&1; then
            echo "${service_name} is ready."
            return 0
        fi
        echo "${service_name} not ready yet (${attempt}/${max_retries}); retrying in ${sleep_seconds}s..."
        sleep "$sleep_seconds"
        attempt=$((attempt + 1))
    done

    echo "${service_name} did not become ready."
    return 1
}

echo "Cloud prod control-plane mode: ${MODE}"
echo "Using env file: ${ENV_FILE}"

check_env_contract

echo "Rendering cloud production compose config..."
compose config >/dev/null

if [ "$SKIP_NETWORK_CHECKS" != "true" ]; then
    echo "Checking R2/S3 access..."
    check_r2_access
    echo "Checking Telegram Local Bot API reachability..."
    check_telegram_local_api
else
    echo "Skipping network checks by request."
fi

if [ "$MODE" = "preflight" ]; then
    echo "Cloud production preflight passed. No services were started."
    exit 0
fi

mkdir -p "$ROOT_DIR/logs/cloud-prod"

echo "Building cloud production control-plane images..."
compose build central-api-prod web-api-prod payment-api-prod dashboard-backend-prod

echo "Checking Alembic head count..."
HEAD_COUNT="$(compose run --rm --no-deps web-api-prod sh -lc 'alembic heads | wc -l' | tr -d '[:space:]')"
if [ "$HEAD_COUNT" != "1" ]; then
    echo "Alembic head count is not 1: ${HEAD_COUNT}"
    compose run --rm --no-deps web-api-prod alembic heads || true
    exit 1
fi

if [ "$WITH_DB_UPGRADE" = "true" ]; then
    echo "Running Alembic upgrade head on the configured cloud production database..."
    compose run --rm --no-deps web-api-prod alembic upgrade head
else
    echo "Skipping Alembic upgrade. Pass --with-db-upgrade only after dry-run restore is approved."
fi

echo "Starting cloud production control plane without Telegram bot profile..."
compose up -d --force-recreate central-api-prod web-api-prod payment-api-prod dashboard-backend-prod imgproxy-prod

CLOUD_PROD_HEALTH_HOST="$(read_env_value CLOUD_PROD_BIND_IP)"
CLOUD_PROD_HEALTH_HOST="${CLOUD_PROD_HEALTH_HOST:-127.0.0.1}"

wait_for_http_ready "Central API" "http://${CLOUD_PROD_HEALTH_HOST}:8003/health" 40 5
wait_for_http_ready "Web API" "http://${CLOUD_PROD_HEALTH_HOST}:8000/api/health" 40 5
wait_for_http_ready "Payment API" "http://${CLOUD_PROD_HEALTH_HOST}:8021/pay/result" 40 5
wait_for_http_ready "Dashboard API" "http://${CLOUD_PROD_HEALTH_HOST}:8043/api/health" 40 5

echo "Cloud production control plane is ready. Bot polling and edge routing were not changed."
