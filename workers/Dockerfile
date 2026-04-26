FROM python:3.10-slim

WORKDIR /app

# 仅拷贝轻量级依赖文件，极大提升构建速度
COPY worker_requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r worker_requirements.txt

COPY comfy_agent /app/worker

# 设置 Python 寻址路径
ENV PYTHONPATH=/app

CMD ["python", "/app/worker/agent_main.py"]
