FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/giraffu/allbot-dashboard-backend@sha256:92f533feae2b8aa22aa14cf19d6ded1dce857ffd80e52809cd57f92f995f6e4b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/workspace \
    HOME=/home/app
WORKDIR /app
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home app
COPY __init__.py /app/lan_resource_manager/__init__.py
COPY backend/ /app/lan_resource_manager/backend/
COPY --from=frontend /build/dist /app/lan_resource_manager/frontend/dist
COPY ssh_config /home/app/.ssh/config
RUN install -d -o app -g app -m 700 /data \
    && chown -R app:app /app/lan_resource_manager /home/app \
    && chmod 700 /home/app/.ssh \
    && chmod 600 /home/app/.ssh/config
USER 1000:1000
EXPOSE 8096
CMD ["python", "-m", "uvicorn", "lan_resource_manager.backend.main:app", "--host", "127.0.0.1", "--port", "8096", "--workers", "1", "--no-access-log"]
