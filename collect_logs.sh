#!/bin/bash
# -----------------------------------------------------------------------------
# collect_logs.sh
# 自动化日志采集与过滤脚本（由 ops-log-monitor 技能调用）
# 用法: bash collect_logs.sh [分钟数] (默认15分钟)
# -----------------------------------------------------------------------------

MINUTES=${1:-15}
TEMP_DIR="logs_temp"

echo "[*] 开始采集过去 ${MINUTES} 分钟的容器日志..."
mkdir -p "$TEMP_DIR"

# 定义需要监控的容器列表
CONTAINERS=("tg-bot" "tg-bot-test" "web-api" "web-api-test" "backend_api_1")

for CONTAINER in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        echo "  -> 正在提取 $CONTAINER 的日志..."
        docker logs --since "${MINUTES}m" "$CONTAINER" > "$TEMP_DIR/${CONTAINER}.log" 2>&1
    else
        echo "  -> 未发现正在运行的容器 $CONTAINER，跳过。"
    fi
done

echo "[*] 正在过滤 ERROR、WARN、Exception、Timeout 等异常日志..."
# 将过滤出的报错聚合至 errors.log（若无报错也不会中断脚本）
grep -iE "error|exception|traceback|warn|timeout|fail|status code [^2]" "$TEMP_DIR"/*.log > "$TEMP_DIR/errors.log" || true

echo "[*] 采集完成！"
echo "  - 原始日志存放于: $TEMP_DIR/"
echo "  - 已过滤的异常日志存放于: $TEMP_DIR/errors.log"
echo "-----------------------------------------------------------------------------"
echo "AI 分析指引: 请直接读取 $TEMP_DIR/errors.log 并在完成报告后删除 $TEMP_DIR 目录。"
