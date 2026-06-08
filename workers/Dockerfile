FROM python:3.10-slim

WORKDIR /app

RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g; s|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 仅拷贝轻量级依赖文件，极大提升构建速度
COPY worker_requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r worker_requirements.txt

COPY comfy_agent /app/worker
COPY local_relay /app/local_relay

# 设置 Python 寻址路径
ENV PYTHONPATH=/app

CMD ["python", "/app/worker/agent_main.py"]
