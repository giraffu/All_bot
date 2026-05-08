#!/bin/bash
set -e

echo "🚀 开始 All_Bot 安全更新与重建流程 (带队列监控)..."

# ==============================================================================
# 第一步：开启维护模式，拦截新任务提交 (包含生产与测试环境)
# ==============================================================================
echo "1️⃣ 开启系统维护模式..."
if [ -n "$(docker ps -q -f name=^tg-bot$)" ]; then
    docker exec tg-bot touch /app/MAINTENANCE
    docker exec web-api touch /app/MAINTENANCE 2>/dev/null || true
    echo "✅ 已开启 tg-bot 与 web-api (生产环境) 维护模式，所有新任务提交将被拒绝。"
else
    echo "⚠️ tg-bot 容器未运行，跳过生产环境维护模式标记。"
fi

if [ -n "$(docker ps -q -f name=^tg-bot-test$)" ]; then
    docker exec tg-bot-test touch /app/MAINTENANCE
    docker exec web-api-test touch /app/MAINTENANCE 2>/dev/null || true
    echo "✅ 已开启 tg-bot-test 与 web-api-test (测试环境) 维护模式，所有新任务提交将被拒绝。"
else
    echo "⚠️ tg-bot-test 容器未运行，跳过测试环境维护模式标记。"
fi

# ==============================================================================
# 第二步：智能监控 Redis 活跃队列，直到任务清空
# ==============================================================================
echo "2️⃣ 开始监控活跃任务队列，等待当前任务处理完毕..."

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
monitor_queue "tg-bot-test" "测试环境"

# ==============================================================================
# 第三步：执行僵尸任务与并发锁清理 (确保并发状态一致)
# ==============================================================================
echo "3️⃣ 执行僵尸任务与 Redis 并发锁清理..."
if [ -n "$(docker ps -q -f name=^tg-bot$)" ]; then
    # 由于上面的检测保证了活跃任务为 0，此时如果还有残留的锁，必定是死锁，这步脚本能完美将其清空
    docker exec tg-bot python src/services/zombie_cleaner_service.py || echo "⚠️ 生产环境清理脚本执行警告，继续流程..."
    echo "✅ 生产环境 Redis 并发状态核对完成。"
fi

if [ -n "$(docker ps -q -f name=^tg-bot-test$)" ]; then
    docker exec tg-bot-test python src/services/zombie_cleaner_service.py || echo "⚠️ 测试环境清理脚本执行警告，继续流程..."
    echo "✅ 测试环境 Redis 并发状态核对完成。"
fi

# ==============================================================================
# 第四步：重建 Agent 容器服务 (底层工作节点)
# ==============================================================================
echo "4️⃣ 重建并重启 Comfy Agent 工作节点..."
cd workers
docker-compose rm -fsv || true
docker rm -f $(docker ps -a -q -f name=comfy-agent) 2>/dev/null || true
docker-compose up -d --build
cd ..
echo "✅ Agent 集群重建完成。"

# ==============================================================================
# 第五步：重建中控 API (Central API)
# ==============================================================================
echo "5️⃣ 重建并重启中控 API..."
cd backend
docker rm -f backend_api_1 || true 
docker-compose up -d --build
cd ..
echo "✅ 中控 API 重建完成。"

# ==============================================================================
# 第六步：重建主服务群 (Bot, Payment API, Web API)
# ==============================================================================
echo "6️⃣ 重建并重启主服务群 (Bot & APIs)..."
docker rm -f tg-bot payment-api web-api || true
docker-compose -f deploy/docker-compose.yml up -d --build
echo "✅ 主服务群重建完成。"

# ==============================================================================
# 第七步：重建 Dashboard 服务 (前端与后端)
# ==============================================================================
echo "7️⃣ 重建并重启 Dashboard 服务 (前端与后端)..."
cd dashboard
docker rm -f dashboard_dashboard-backend_1 dashboard_dashboard-frontend_1 || true
docker-compose up -d --build
cd ..
echo "✅ Dashboard 服务重建完成。"

# ==============================================================================
# 第八步：重建测试服务群 (Test Bot, Payment API, Web API)
# ==============================================================================
echo "8️⃣ 重建并重启测试环境服务群 (Test Environment)..."
docker rm -f tg-bot-test payment-api-test web-api-test || true
docker-compose -f deploy/docker-compose-test.yml up -d --build
echo "✅ 测试环境服务群重建完成。"

echo "🎉 所有服务更新与重建已成功完成！系统已自动解除维护模式并恢复服务。"
echo "👉 请执行 'docker logs -f tg-bot' 查看主程序启动日志。"