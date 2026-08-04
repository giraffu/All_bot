FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

EXPOSE 8098

CMD ["sh", "-c", "uvicorn app.main:app --host ${LOCAL_ANALYTICS_HOST:-0.0.0.0} --port ${LOCAL_ANALYTICS_PORT:-8098}"]
