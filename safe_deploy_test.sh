#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEPLOY_SUCCEEDED=0
TEST_ENV_FILE="$ROOT_DIR/.env.test"
TEST_ENTRY_CONTAINERS=(
    "tg-bot-test"
    "payment-api-test"
    "web-api-test"
    "web-frontend-test"
    "dashboard-backend-test"
    "dashboard-frontend-test"
)
TEST_ENTRY_SERVICES=(
    "bot-test"
    "payment-api-test"
    "web-api-test"
    "web-frontend-test"
    "dashboard-backend-test"
    "dashboard-frontend-test"
)

remove_container_if_exists() {
    local container_name=$1

    if [ -n "$(docker ps -aq -f name=^${container_name}$)" ]; then
        docker rm -f "${container_name}" >/dev/null 2>&1 || true
    fi
}

remove_compose_service_containers() {
    local service_name=$1
    local container_ids

    container_ids=$(docker ps -aq -f "label=com.docker.compose.service=${service_name}")
    if [ -n "$container_ids" ]; then
        docker rm -f $container_ids >/dev/null 2>&1 || true
    fi
}

cleanup_test_entry_service_containers() {
    local container_name
    local service_name

    for container_name in "${TEST_ENTRY_CONTAINERS[@]}"; do
        remove_container_if_exists "$container_name"
    done

    for service_name in "${TEST_ENTRY_SERVICES[@]}"; do
        remove_compose_service_containers "$service_name"
    done
}

remove_maintenance_markers() {
    local containers=(
        "tg-bot-test"
        "web-api-test"
    )

    for container_name in "${containers[@]}"; do
        if [ -n "$(docker ps -q -f name=^${container_name}$)" ]; then
            docker exec "${container_name}" rm -f /app/MAINTENANCE >/dev/null 2>&1 || true
        fi
    done
}

cleanup_on_exit() {
    local exit_code=$?

    remove_maintenance_markers

    if [ "$exit_code" -eq 0 ] && [ "$DEPLOY_SUCCEEDED" -eq 1 ]; then
        echo "✅ 已自动清理测试环境维护模式标记。"
    else
        echo "⚠️ 测试环境部署未完成，已尽力清理维护模式标记，请检查容器状态与日志。"
    fi

    exit "$exit_code"
}

trap cleanup_on_exit EXIT

wait_for_http_ready() {
    local service_name=$1
    local url=$2
    local max_retries=${3:-30}
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

    echo "   ❌ ${service_name} 在等待窗口内未就绪，停止部署。"
    return 1
}

if [ ! -f "$TEST_ENV_FILE" ]; then
    echo "❌ 未找到 $TEST_ENV_FILE，请先补齐测试环境配置。"
    exit 1
fi

set -a
source "$TEST_ENV_FILE"
set +a

echo "🚀 开始 All_Bot 测试环境安全更新与重建流程..."
echo "ℹ️ 本脚本只处理测试环境与测试调度栈，正式 Dashboard 保持不动；测试 Dashboard 会一并重建。"

# ==============================================================================
# 第一步：开启测试环境维护模式
# ==============================================================================
echo "1️⃣ 开启测试环境维护模式..."
if [ -n "$(docker ps -q -f name=^tg-bot-test$)" ]; then
    docker exec tg-bot-test touch /app/MAINTENANCE
    docker exec web-api-test touch /app/MAINTENANCE 2>/dev/null || true
    echo "✅ 已开启 tg-bot-test 与 web-api-test 维护模式。"
else
    echo "⚠️ tg-bot-test 容器未运行，跳过维护模式标记。"
fi

# ==============================================================================
# 第二步：等待测试环境活跃任务清空
# ==============================================================================
echo "2️⃣ 开始监控测试环境活跃任务队列..."

monitor_queue() {
    local container_name=$1

    if [ -n "$(docker ps -q -f name=^${container_name}$)" ]; then
        echo "   👉 开始监控 [测试环境] 活跃任务队列..."

        CHECK_SCRIPT=$(cat << 'EOF'
import sys
try:
    import asyncio
    from src.services.redis_client import redis_client
    from config import REDIS_PREFIX

    async def check_active_tasks():
        try:
            count = await redis_client.redis.hlen(f"{REDIS_PREFIX}active_tasks")
            print(count)
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            await redis_client.close()

    if __name__ == "__main__":
        asyncio.run(check_active_tasks())
except Exception as e:
    print(f"IMPORT_ERROR: {e}")
EOF
        )

        local retry_count=0
        local max_retries=30

        while true; do
            ACTIVE_COUNT=$(docker exec "${container_name}" python -c "$CHECK_SCRIPT" 2>/dev/null | tail -n 1 | tr -d '\r')

            if [[ ! "$ACTIVE_COUNT" =~ ^[0-9]+$ ]]; then
                retry_count=$((retry_count + 1))
                echo "   ⚠️ 获取任务数量失败 ($ACTIVE_COUNT)，10秒后重试 ($retry_count/$max_retries)..."
                if [ "$retry_count" -ge "$max_retries" ]; then
                    echo "   ❌ 达到最大重试次数，强制跳过监控，继续后续流程..."
                    break
                fi
                sleep 10
                continue
            fi

            retry_count=0

            if [ "$ACTIVE_COUNT" -eq 0 ]; then
                echo "   🎉 [测试环境] 活跃任务队列已完全清空 (Count: 0)！"
                break
            else
                echo "   ⏳ [测试环境] 当前仍有 $ACTIVE_COUNT 个任务正在生成中，10秒后再次检测..."
                sleep 10
            fi
        done
    else
        echo "   ⚠️ ${container_name} 容器未运行，跳过队列监控。"
    fi
}

monitor_queue "tg-bot-test"

# ==============================================================================
# 第三步：清理测试环境僵尸任务与并发锁
# ==============================================================================
echo "3️⃣ 执行测试环境僵尸任务与 Redis 并发锁清理..."
if [ -n "$(docker ps -q -f name=^tg-bot-test$)" ]; then
    docker exec tg-bot-test python src/services/zombie_cleaner_service.py || echo "⚠️ 测试环境清理脚本执行警告，继续流程..."
    echo "✅ 测试环境 Redis 并发状态核对完成。"
else
    echo "⚠️ tg-bot-test 容器未运行，跳过僵尸任务清理。"
fi

# ==============================================================================
# 第四步：执行测试数据库迁移
# ==============================================================================
echo "4️⃣ 执行测试数据库 Alembic 迁移..."

ALEMBIC_CMD=()
if [ -x "$ROOT_DIR/venv/bin/alembic" ]; then
    ALEMBIC_CMD=("$ROOT_DIR/venv/bin/alembic")
elif [ -x "$ROOT_DIR/.venv/bin/alembic" ]; then
    ALEMBIC_CMD=("$ROOT_DIR/.venv/bin/alembic")
elif command -v alembic >/dev/null 2>&1; then
    ALEMBIC_CMD=("$(command -v alembic)")
else
    echo "❌ 未找到 alembic 可执行文件，请先激活正确的 Python 环境或安装 Alembic。"
    exit 1
fi

HEAD_COUNT=$("${ALEMBIC_CMD[@]}" heads | awk '/\(head\)/ {count++} END {print count+0}')
if [ "$HEAD_COUNT" -gt 1 ]; then
    echo "❌ 检测到 Alembic 存在多个 head，safe_deploy_test 已停止以避免半途失败。"
    "${ALEMBIC_CMD[@]}" heads
    echo "👉 请先创建并提交 merge migration，再重新执行 safe_deploy_test.sh。"
    exit 1
fi

(
    set -a
    source "$TEST_ENV_FILE"
    export BOT_TYPE=TEST
    set +a
    "${ALEMBIC_CMD[@]}" upgrade head
)
echo "✅ 测试数据库迁移完成。"

# ==============================================================================
# 第五步：重建测试 Agent 集群
# ==============================================================================
echo "5️⃣ 重建并重启测试 Comfy Agent 工作节点..."
cd "$ROOT_DIR/workers"
docker-compose -f docker-compose-test.yml rm -fsv || true
docker rm -f $(docker ps -a -q -f name=comfy-agent-test) 2>/dev/null || true
docker-compose -f docker-compose-test.yml up -d --build
cd "$ROOT_DIR"
echo "✅ 测试 Agent 集群重建完成。"

# ==============================================================================
# 第六步：重建测试中控 API
# ==============================================================================
echo "6️⃣ 重建并重启测试中控 API..."
cd "$ROOT_DIR/backend"
docker rm -f central-api-test 2>/dev/null || true
docker-compose -f docker-compose-test.yml up -d --build
cd "$ROOT_DIR"
wait_for_http_ready "测试中控 API" "http://127.0.0.1:8004/health"
echo "✅ 测试中控 API 重建完成。"

# ==============================================================================
# 第七步：重建测试入口服务群
# ==============================================================================
echo "7️⃣ 重建并重启测试环境服务群（含 Web 与 Dashboard 测试前后端）..."
cleanup_test_entry_service_containers
docker-compose -f deploy/docker-compose-test.yml up -d --build
wait_for_http_ready "测试 Web API" "http://127.0.0.1:8001/api/health"
wait_for_http_ready "测试 Web 前端" "http://127.0.0.1:5173" 60 5
wait_for_http_ready "测试 Dashboard 后端" "http://127.0.0.1:8044/api/health"
wait_for_http_ready "测试 Dashboard 前端" "http://127.0.0.1:5174" 60 5
echo "✅ 测试环境服务群重建完成。"

DEPLOY_SUCCEEDED=1

echo "🎉 测试环境更新与重建已成功完成！"
echo "ℹ️ 正式 Dashboard 未参与本次部署，继续使用现有生产实例。"
echo "👉 可执行 'docker logs -f tg-bot-test' 查看测试 Bot 启动日志。"
echo "👉 可执行 'docker logs -f web-frontend-test' 查看测试前端启动日志。"
echo "👉 可执行 'docker logs -f dashboard-backend-test' 查看测试 Dashboard 后端日志。"
echo "👉 可执行 'docker logs -f dashboard-frontend-test' 查看测试 Dashboard 前端日志。"
echo "👉 测试前端默认监听 5173 端口，可通过 http://<宿主机IP>:5173 访问。"
echo "👉 测试 Dashboard 后端监听 8044 端口，可通过 http://<宿主机IP>:8044/api/health 自检。"
echo "👉 测试 Dashboard 前端默认监听 5174 端口，可通过 http://<宿主机IP>:5174 访问。"
