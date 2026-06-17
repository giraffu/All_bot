#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env.cloud.test"
COMPOSE_FILE="$ROOT_DIR/workers/docker-compose-cloud-worker-test.yml"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 未找到 $ENV_FILE"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ 未找到 $COMPOSE_FILE"
    exit 1
fi

read_env_value() {
    local key=$1
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

CLOUD_TEST_CONTROL_HOST_VALUE="${CLOUD_TEST_CONTROL_HOST:-$(read_env_value CLOUD_TEST_CONTROL_HOST)}"
CLOUD_TEST_TAILSCALE_IP_VALUE="${CLOUD_TEST_TAILSCALE_IP:-$(read_env_value CLOUD_TEST_TAILSCALE_IP)}"
if [ -z "$CLOUD_TEST_CONTROL_HOST_VALUE" ]; then
    CLOUD_TEST_CONTROL_HOST_VALUE="$CLOUD_TEST_TAILSCALE_IP_VALUE"
fi
if [ -z "$CLOUD_TEST_CONTROL_HOST_VALUE" ]; then
    echo "❌ 未配置 CLOUD_TEST_CONTROL_HOST 或 CLOUD_TEST_TAILSCALE_IP。"
    exit 1
fi
export CLOUD_TEST_CONTROL_HOST="$CLOUD_TEST_CONTROL_HOST_VALUE"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

echo "🔎 检查云测试 Central API: http://${CLOUD_TEST_CONTROL_HOST_VALUE}:8004/health"
curl --noproxy '*' -fsS "http://${CLOUD_TEST_CONTROL_HOST_VALUE}:8004/health" >/dev/null

MINIO_SECURE_VALUE="${MINIO_SECURE:-$(read_env_value MINIO_SECURE)}"
MINIO_ENDPOINT_VALUE="${MINIO_ENDPOINT:-$(read_env_value MINIO_ENDPOINT)}"
MINIO_BUCKET_VALUE="${MINIO_BUCKET:-$(read_env_value MINIO_BUCKET)}"

if [ "$MINIO_SECURE_VALUE" = "true" ]; then
    echo "🔎 检查云测试 R2/S3 配置: ${MINIO_ENDPOINT_VALUE}/${MINIO_BUCKET_VALUE}"
    python3 - "$ENV_FILE" <<'PY' >/dev/null
from pathlib import Path
import sys

import boto3
from botocore.config import Config

env = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    env[k] = v.strip().strip('"').strip("'")

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
PY
else
    echo "🔎 检查云测试 MinIO: http://${CLOUD_TEST_TAILSCALE_IP_VALUE}:59000/minio/health/live"
    curl --noproxy '*' -fsS "http://${CLOUD_TEST_TAILSCALE_IP_VALUE}:59000/minio/health/live" >/dev/null
fi

echo "🚀 启动本地 GPU cloud-worker 测试栈..."
if [ "${COMPOSE_CMD[0]}" = "docker-compose" ]; then
    docker ps -aq --filter "name=cloud-worker-relay-test" | xargs -r docker rm -f >/dev/null 2>&1 || true
    docker ps -aq --filter "name=cloud-comfy-agent-test" | xargs -r docker rm -f >/dev/null 2>&1 || true
fi
"${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
AGENT_SECRET_TOKEN_VALUE="${AGENT_SECRET_TOKEN:-$(read_env_value AGENT_SECRET_TOKEN)}"
if [ -z "$AGENT_SECRET_TOKEN_VALUE" ]; then
    echo "❌ 未配置 AGENT_SECRET_TOKEN，无法设置 SCAIL-2 测试 worker 初始 disabled。"
    exit 1
fi
echo "🔒 设置 SCAIL-2 测试 worker 初始 disabled: cloud_worker_test_08"
curl --noproxy '*' -fsS \
    -X POST "http://${CLOUD_TEST_CONTROL_HOST_VALUE}:8004/api/agent/task/control/cloud_worker_test_08" \
    -H "Authorization: Bearer ${AGENT_SECRET_TOKEN_VALUE}" \
    -H "Content-Type: application/json" \
    --data '{"state":"disabled","reason":"scail2_test_initial_disabled","ttl_seconds":null}' \
    >/dev/null
echo "✅ cloud-worker 测试栈已启动。"
