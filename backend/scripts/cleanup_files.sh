#!/bin/bash

# 配置需要清理的目录列表
DIRECTORIES=(
    "/home/ubantu/comfyui/input"
    "/home/ubantu/comfyui/output"
    "/home/ubantu/comfyui/temp"
)

# 设置保留天数（+3 表示清理3天前修改的文件）
DAYS=3

# 日志文件路径
LOG_FILE="/home/ubantu/backend/cleanup.log"

echo "---------------------------------------------------" >> "$LOG_FILE"
echo "Starting cleanup at $(date)" >> "$LOG_FILE"

for DIR in "${DIRECTORIES[@]}"; do
    if [ -d "$DIR" ]; then
        echo "Processing directory: $DIR" >> "$LOG_FILE"
        
        # 查找并删除超过指定天数的文件
        # -type f: 仅查找文件
        # -mtime +$DAYS: 修改时间在 N 天前
        # -exec rm -f {}: 执行删除命令
        # -print: 打印被删除的文件名到日志
        find "$DIR" -type f -mtime +$DAYS -print -exec rm -f {} \; >> "$LOG_FILE" 2>&1
        
        # 可选：清理空文件夹（如果有子目录结构）
        # find "$DIR" -type d -empty -delete
    else
        echo "Directory not found: $DIR" >> "$LOG_FILE"
    fi
done

echo "Cleanup completed at $(date)" >> "$LOG_FILE"
echo "---------------------------------------------------" >> "$LOG_FILE"
