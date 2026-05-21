#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEPLOY_SUCCEEDED=0
PROD_ENV_FILE="$ROOT_DIR/.env"

remove_maintenance_markers() {
    local containers=(
        "tg-bot"
        "web-api"
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
        echo "✅ 已自动清理生产环境维护模式标记。"
    else
        echo "⚠️ 部署未完成，已尽力清理维护模式标记，请检查容器状态与日志。"
    fi

    exit "$exit_code"
}

trap cleanup_on_exit EXIT

if [ ! -f "$PROD_ENV_FILE" ]; then
    echo "❌ 未找到 $PROD_ENV_FILE，请先补齐生产环境配置。"
    exit 1
fi

set -a
source "$PROD_ENV_FILE"
set +a

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

echo "🚀 开始 All_Bot 生产环境安全更新与重建流程 (带队列监控)..."

# ==============================================================================
# 第一步：开启生产环境维护模式，拦截新任务提交
# ==============================================================================
echo "1️⃣ 开启生产环境维护模式..."
if [ -n "$(docker ps -q -f name=^tg-bot$)" ]; then
    docker exec tg-bot touch /app/MAINTENANCE
    docker exec web-api touch /app/MAINTENANCE 2>/dev/null || true
    echo "✅ 已开启 tg-bot 与 web-api (生产环境) 维护模式，所有新任务提交将被拒绝。"
else
    echo "⚠️ tg-bot 容器未运行，跳过生产环境维护模式标记。"
fi

# ==============================================================================
# 第二步：智能监控生产 Redis 活跃队列，直到任务清空
# ==============================================================================
echo "2️⃣ 开始监控生产环境活跃任务队列，等待当前任务处理完毕..."

monitor_queue() {
    local container_name=$1
    local env_name=$2

    if [ -n "$(docker ps -q -f name=^${container_name}$)" ]; then
        echo "   👉 开始监控 [${env_name}] 活跃任务队列..."
        
        # 注入一段 Python 脚本来查询 Redis 中的活跃任务数量
        CHECK_SCRIPT=$(cat << 'EOF'
import sys
try:
    import asyncio
    import json
    from src.services.redis_client import redis_client
    from config import REDIS_PREFIX

    async def check_active_tasks():
        try:
            # 直接使用底层方法获取哈希表长度，避免反序列化全部数据
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
            # 在容器内执行检测脚本
            ACTIVE_COUNT=$(docker exec ${container_name} python -c "$CHECK_SCRIPT" 2>/dev/null | tail -n 1 | tr -d '\r')
            
            # 错误容忍：如果获取失败（可能是 Redis 短暂网络波动或代码异常），当作还有任务，继续等待
            if [[ ! "$ACTIVE_COUNT" =~ ^[0-9]+$ ]]; then
                retry_count=$((retry_count+1))
                echo "   ⚠️ 获取任务数量失败 ($ACTIVE_COUNT)，10秒后重试 ($retry_count/$max_retries)..."
                if [ $retry_count -ge $max_retries ]; then
                    echo "   ❌ 达到最大重试次数 ($max_retries)，强制跳过监控，直接继续..."
                    break
                fi
                sleep 10
                continue
            fi

            # 获取成功则重置连续失败计数
            retry_count=0

            if [ "$ACTIVE_COUNT" -eq 0 ]; then
                echo "   🎉 [${env_name}] 活跃任务队列已完全清空 (Count: 0)！"
                break
            else
                echo "   ⏳ [${env_name}] 当前仍有 $ACTIVE_COUNT 个任务正在生成中，请耐心等待 (10秒后再次检测)..."
                sleep 10
            fi
        done
    else
        echo "   ⚠️ ${container_name} 容器未运行，跳过队列监控。"
    fi
}

monitor_queue "tg-bot" "生产环境"

# ==============================================================================
# 第三步：执行生产僵尸任务与并发锁清理 (确保并发状态一致)
# ==============================================================================
echo "3️⃣ 执行生产环境僵尸任务与 Redis 并发锁清理..."
if [ -n "$(docker ps -q -f name=^tg-bot$)" ]; then
    # 由于上面的检测保证了活跃任务为 0，此时如果还有残留的锁，必定是死锁，这步脚本能完美将其清空
    docker exec tg-bot python src/services/zombie_cleaner_service.py || echo "⚠️ 生产环境清理脚本执行警告，继续流程..."
    echo "✅ 生产环境 Redis 并发状态核对完成。"
fi

# ==============================================================================
# 第四步：执行数据库迁移 (无待迁移时会安全跳过)
# ==============================================================================
echo "4️⃣ 执行 Alembic 数据库迁移..."

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
    echo "❌ 检测到 Alembic 存在多个 head，safe_deploy 已停止以避免半途失败。"
    "${ALEMBIC_CMD[@]}" heads
    echo "👉 请先创建并提交 merge migration，再重新执行 safe_deploy.sh。"
    exit 1
fi

"${ALEMBIC_CMD[@]}" upgrade head
echo "✅ 数据库迁移完成（若无待执行迁移，此步会直接安全通过）。"

# ==============================================================================
# 第五步：重建 Agent 容器服务 (底层工作节点)
# ==============================================================================
echo "5️⃣ 重建并重启 Comfy Agent 工作节点..."
cd "$ROOT_DIR/workers"
docker-compose rm -fsv || true
docker rm -f $(docker ps -a -q -f name=comfy-agent) 2>/dev/null || true
docker-compose up -d --build
cd "$ROOT_DIR"
echo "✅ Agent 集群重建完成。"

# ==============================================================================
# 第六步：重建中控 API (Central API)
# ==============================================================================
echo "6️⃣ 重建并重启中控 API..."
cd "$ROOT_DIR/backend"
docker rm -f backend_api_1 || true 
docker-compose up -d --build
cd "$ROOT_DIR"
wait_for_http_ready "生产中控 API" "http://127.0.0.1:8003/health"
echo "✅ 中控 API 重建完成。"

# ==============================================================================
# 第七步：重建主服务群 (Bot, Payment API, Web API)
# ==============================================================================
echo "7️⃣ 重建并重启主服务群 (Bot & APIs)..."
docker rm -f tg-bot payment-api web-api || true
docker-compose -f deploy/docker-compose.yml up -d --build
wait_for_http_ready "生产 Web API" "http://127.0.0.1:8000/api/health"
wait_for_http_ready "Imgproxy" "http://127.0.0.1:8084/health"
echo "✅ 主服务群重建完成。"

# ==============================================================================
# 第八步：重建 Dashboard 服务 (前端与后端)
# ==============================================================================
echo "8️⃣ 重建并重启 Dashboard 服务 (前端与后端)..."
cd "$ROOT_DIR/dashboard"
docker rm -f dashboard_dashboard-backend_1 dashboard_dashboard-frontend_1 || true
docker-compose up -d --build
cd "$ROOT_DIR"
wait_for_http_ready "Dashboard Backend" "http://127.0.0.1:8043/api/health"
wait_for_http_ready "Dashboard Frontend" "http://127.0.0.1:8085"
echo "✅ Dashboard 服务重建完成。"

# ==============================================================================
DEPLOY_SUCCEEDED=1

echo "🎉 生产环境服务更新与重建已成功完成！系统已自动解除维护模式并恢复服务。"
echo "👉 请执行 'docker logs -f tg-bot' 查看主程序启动日志。"
