FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "agent_main.py"]
