#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "$ROOT_DIR/.env.test" ]; then
    echo "❌ 未找到 $ROOT_DIR/.env.test"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

stop_stack() {
    local compose_file=$1
    local label=$2

    if [ ! -f "$compose_file" ]; then
        echo "⚠️  跳过 ${label}: 未找到 ${compose_file}"
        return
    fi

    echo "⏸️  停止 ${label}，保留容器、镜像、volume 和数据..."
    "${COMPOSE_CMD[@]}" --env-file "$ROOT_DIR/.env.test" -f "$compose_file" stop
}

echo "🚦 停止本地主服务器测试环境（保留数据）..."
stop_stack "$ROOT_DIR/deploy/docker-compose-test.yml" "测试入口服务"
stop_stack "$ROOT_DIR/backend/docker-compose-test.yml" "测试 Central API"
stop_stack "$ROOT_DIR/workers/docker-compose-test.yml" "测试 GPU workers"
echo "✅ 本地测试环境已停止，数据和容器均已保留。"
