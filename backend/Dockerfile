FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app/
COPY workflows/ /app/workflows/

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
