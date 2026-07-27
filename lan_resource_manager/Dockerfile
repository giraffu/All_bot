FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/oras-project/oras:v1.3.2@sha256:46c55ba0eac848ade573594ef23fa5b1784227f151dab6eac38de2afd0b9c382 AS oras

FROM node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS node-runtime

FROM ghcr.io/giraffu/allbot-dashboard-backend@sha256:92f533feae2b8aa22aa14cf19d6ded1dce857ffd80e52809cd57f92f995f6e4b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/workspace \
    HOME=/home/app \
    NPM_CONFIG_CACHE=/home/app/.cache/allbot/npm \
    XDG_CONFIG_HOME=/home/app/.cache/allbot/config
WORKDIR /app
RUN sed -i \
      -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
      -e 's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 update \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 install -y --no-install-recommends ca-certificates git gh \
    && rm -rf /var/lib/apt/lists/*
COPY --from=oras /bin/oras /usr/local/bin/oras
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home app
COPY __init__.py /app/lan_resource_manager/__init__.py
COPY backend/ /app/lan_resource_manager/backend/
COPY --from=frontend /build/dist /app/lan_resource_manager/frontend/dist
COPY ssh_config /home/app/.ssh/config
RUN install -d -o app -g app -m 700 /data \
    && install -d -o app -g app -m 770 /runner \
    && install -d -o app -g app -m 700 /home/app/.config/allbot \
    && install -d -o app -g app -m 700 /home/app/.cache/allbot/releases \
    && chown -R app:app /app/lan_resource_manager /home/app \
    && chmod 700 /home/app/.ssh \
    && chmod 600 /home/app/.ssh/config
USER 1000:1000
EXPOSE 8096
CMD ["python", "-m", "uvicorn", "lan_resource_manager.backend.main:app", "--host", "127.0.0.1", "--port", "8096", "--workers", "1", "--no-access-log"]
