#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="$ROOT_DIR/.env.cloud.test"
COMPOSE_FILE="$ROOT_DIR/deploy/docker-compose-cloud-test.yml"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 未找到 $ENV_FILE，请先生成云测试环境变量。"
    exit 1
fi

read_env_value() {
    local key=$1
    sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

CLOUD_TEST_BIND_IP_VALUE="${CLOUD_TEST_BIND_IP:-$(read_env_value CLOUD_TEST_BIND_IP)}"
CLOUD_TEST_HEALTH_HOST="${CLOUD_TEST_BIND_IP_VALUE:-127.0.0.1}"
if [ "$CLOUD_TEST_HEALTH_HOST" = "0.0.0.0" ]; then
    CLOUD_TEST_HEALTH_HOST="127.0.0.1"
fi
CLOUD_TEST_DATABASE_URL_VALUE="${CLOUD_TEST_DATABASE_URL:-$(read_env_value CLOUD_TEST_DATABASE_URL)}"
CLOUD_TEST_REDIS_URL_VALUE="${CLOUD_TEST_REDIS_URL:-$(read_env_value CLOUD_TEST_REDIS_URL)}"
CLOUD_TEST_WORKER_REDIS_URL_VALUE="${CLOUD_TEST_WORKER_REDIS_URL:-$(read_env_value CLOUD_TEST_WORKER_REDIS_URL)}"
CLOUD_TEST_POSTGRES_DB_VALUE="${CLOUD_TEST_POSTGRES_DB:-$(read_env_value CLOUD_TEST_POSTGRES_DB)}"
CLOUD_TEST_POSTGRES_USER_VALUE="${CLOUD_TEST_POSTGRES_USER:-$(read_env_value CLOUD_TEST_POSTGRES_USER)}"
CLOUD_TEST_POSTGRES_PASSWORD_VALUE="${CLOUD_TEST_POSTGRES_PASSWORD:-$(read_env_value CLOUD_TEST_POSTGRES_PASSWORD)}"
CLOUD_TEST_REDIS_PASSWORD_VALUE="${CLOUD_TEST_REDIS_PASSWORD:-$(read_env_value CLOUD_TEST_REDIS_PASSWORD)}"
DASHBOARD_FRONTEND_TEST_PORT_VALUE="${DASHBOARD_FRONTEND_TEST_PORT:-$(read_env_value DASHBOARD_FRONTEND_TEST_PORT)}"
DASHBOARD_FRONTEND_TEST_PORT_VALUE="${DASHBOARD_FRONTEND_TEST_PORT_VALUE:-8087}"

if [ -z "$CLOUD_TEST_DATABASE_URL_VALUE" ]; then
    echo "❌ 未配置 CLOUD_TEST_DATABASE_URL。"
    exit 1
fi

if [ -z "$CLOUD_TEST_REDIS_URL_VALUE" ] || [ -z "$CLOUD_TEST_WORKER_REDIS_URL_VALUE" ]; then
    echo "❌ 未配置 CLOUD_TEST_REDIS_URL 或 CLOUD_TEST_WORKER_REDIS_URL。"
    exit 1
fi

if [ -z "$CLOUD_TEST_POSTGRES_PASSWORD_VALUE" ]; then
    echo "❌ 未配置 CLOUD_TEST_POSTGRES_PASSWORD。"
    exit 1
fi

if [ -z "$CLOUD_TEST_REDIS_PASSWORD_VALUE" ]; then
    echo "❌ 未配置 CLOUD_TEST_REDIS_PASSWORD。"
    exit 1
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    COMPOSE_CMD=(docker-compose)
fi

compose() {
    "${COMPOSE_CMD[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

wait_for_http_ready() {
    local service_name=$1
    local url=$2
    local max_retries=${3:-40}
    local sleep_seconds=${4:-5}
    local attempt=1

    echo "   👉 等待 ${service_name} 就绪: ${url}"
    while [ "$attempt" -le "$max_retries" ]; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            echo "   ✅ ${service_name} 已就绪。"
            return 0
        fi
        echo "   ⏳ ${service_name} 尚未就绪，${sleep_seconds}秒后重试 (${attempt}/${max_retries})..."
        sleep "$sleep_seconds"
        attempt=$((attempt + 1))
    done

    echo "   ❌ ${service_name} 在等待窗口内未就绪。"
    return 1
}

wait_for_container_ready() {
    local service_name=$1
    local command=$2
    local max_retries=${3:-40}
    local sleep_seconds=${4:-3}
    local attempt=1

    echo "   👉 等待 ${service_name} 就绪"
    while [ "$attempt" -le "$max_retries" ]; do
        if eval "$command" >/dev/null 2>&1; then
            echo "   ✅ ${service_name} 已就绪。"
            return 0
        fi
        echo "   ⏳ ${service_name} 尚未就绪，${sleep_seconds}秒后重试 (${attempt}/${max_retries})..."
        sleep "$sleep_seconds"
        attempt=$((attempt + 1))
    done

    echo "   ❌ ${service_name} 在等待窗口内未就绪。"
    return 1
}

remove_test_control_containers() {
    local filters=(
        cloud-central-api-test
        cloud-web-api-test
        cloud-dashboard-backend-test
        cloud-dashboard-frontend-test
        cloud-imgproxy-test
        web-api-test
        dashboard-backend-test
        dashboard-frontend-test
    )
    local name_filter

    for name_filter in "${filters[@]}"; do
        docker ps -aq --filter "name=${name_filter}" | xargs -r docker rm -f >/dev/null 2>&1 || true
    done
}

cloud_db_has_users_table() {
    compose run --rm --no-deps web-api-test python - <<'PY' | tail -n 1 | tr -d '[:space:]'
import asyncio

from sqlalchemy import text

from src.database.core import engine


async def main() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT to_regclass('public.users') IS NOT NULL")
        )
        print("1" if result.scalar() else "0")
    await engine.dispose()


asyncio.run(main())
PY
}

bootstrap_empty_cloud_db() {
    compose run --rm --no-deps web-api-test python - <<'PY'
import asyncio

from alembic import command
from alembic.config import Config

from src.database.core import engine, init_db
from src.database.models import Base


def stamp_head() -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "migrations")
    command.stamp(alembic_cfg, "head")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await asyncio.to_thread(stamp_head)
    await init_db()
    await engine.dispose()


asyncio.run(main())
PY
}

sync_cloud_seed_data() {
    compose run --rm --no-deps web-api-test python - <<'PY'
import asyncio

from src.database.core import init_db


asyncio.run(init_db())
PY
}

echo "🚀 开始部署云端测试控制面..."
echo "ℹ️ 默认不启动 Telegram test bot、不启动 GPU worker，避免与本地测试环境争抢 token/GPU。"
echo "ℹ️ 云测试服务绑定地址: ${CLOUD_TEST_HEALTH_HOST}"
echo "ℹ️ 云测试数据库和缓存使用本测试机内的 cloud-postgres-test/cloud-redis-test。"

mkdir -p "$ROOT_DIR/logs/cloud-test"

echo "1️⃣ 校验云测试基础设施配置..."
echo "   ℹ️ 测试数据库: ${CLOUD_TEST_POSTGRES_DB_VALUE:-bot_db_test}"

echo "2️⃣ 启动云测试 Postgres/Redis..."
compose up -d --no-recreate postgres-test redis-test
wait_for_container_ready \
    "云测试 Postgres" \
    "docker exec cloud-postgres-test pg_isready -U '${CLOUD_TEST_POSTGRES_USER_VALUE:-postgres}' -d '${CLOUD_TEST_POSTGRES_DB_VALUE:-bot_db_test}'" \
    40 \
    3
wait_for_container_ready \
    "云测试 Redis" \
    "docker exec cloud-redis-test sh -lc 'redis-cli -a \"\$CLOUD_TEST_REDIS_PASSWORD\" ping | grep -q PONG'" \
    40 \
    3

echo "3️⃣ 构建云测试控制面镜像..."
compose build central-api-test web-api-test dashboard-backend-test dashboard-frontend-test

echo "4️⃣ 检查 Alembic head..."
HEAD_COUNT="$(compose run --rm --no-deps web-api-test sh -lc 'alembic heads | wc -l' | tr -d '[:space:]')"
if [ "$HEAD_COUNT" != "1" ]; then
    echo "❌ Alembic head 数量异常: $HEAD_COUNT"
    compose run --rm --no-deps web-api-test alembic heads || true
    exit 1
fi

echo "5️⃣ 初始化/迁移云测试库..."
if [ "$(cloud_db_has_users_table)" != "1" ]; then
    echo "   ℹ️ 检测到云测试库为空，使用当前 ORM schema 初始化并 stamp Alembic head。"
    bootstrap_empty_cloud_db
else
    echo "   ℹ️ 检测到已有云测试 schema，执行 Alembic upgrade head。"
    compose run --rm --no-deps web-api-test alembic upgrade head
    sync_cloud_seed_data
fi

echo "6️⃣ 启动云测试控制面服务..."
remove_test_control_containers
compose up -d --no-deps central-api-test imgproxy-test
compose up -d --no-deps web-api-test dashboard-backend-test dashboard-frontend-test

echo "7️⃣ 等待健康检查..."
wait_for_http_ready "云测试 Central API" "http://${CLOUD_TEST_HEALTH_HOST}:8004/health" 40 5
wait_for_http_ready "云测试 Web API" "http://${CLOUD_TEST_HEALTH_HOST}:8001/api/health" 40 5
wait_for_http_ready "云测试 Dashboard API" "http://${CLOUD_TEST_HEALTH_HOST}:8044/api/health" 40 5
wait_for_http_ready "云测试 Dashboard Frontend" "http://${CLOUD_TEST_HEALTH_HOST}:${DASHBOARD_FRONTEND_TEST_PORT_VALUE}/api/health" 40 5

echo "✅ 云端测试控制面部署完成。"
echo "👉 查看服务: ${COMPOSE_CMD[*]} --env-file .env.cloud.test -f deploy/docker-compose-cloud-test.yml ps"
echo "👉 Dashboard 测试前端: http://${CLOUD_TEST_HEALTH_HOST}:${DASHBOARD_FRONTEND_TEST_PORT_VALUE}/ （仅限 Tailscale/受控来源访问）。"
echo "👉 公网测试 Web 已迁移到 web-test.aivison.it.com 的边缘 VPS；Web 前端 dev 容器默认不启动。"
echo "👉 不要启动 bot-test，除非你已经停止本地 tg-bot-test。"
