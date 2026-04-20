FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 python 缓冲输出，便于查看日志
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装依赖
# 先复制 requirements.txt 以利用 Docker 缓存
COPY requirements.txt requirements_langgraph.txt ./

# 合并两个 requirements 文件并安装
# 添加阿里云镜像源以解决网络连接超时导致的找不到包的问题
RUN cat requirements.txt requirements_langgraph.txt > merged_requirements.txt \
    && pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r merged_requirements.txt

# 复制项目所有文件
COPY . .

# 启动命令
CMD ["python", "bot.py"]