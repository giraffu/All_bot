FROM python:3.10-slim

ARG ALLBOT_GIT_SHA
ARG ALLBOT_SOURCE=https://github.com/giraffu/All_bot
LABEL org.opencontainers.image.revision=$ALLBOT_GIT_SHA \
      org.opencontainers.image.source=$ALLBOT_SOURCE

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev postgresql-client ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app
COPY deploy/docker/python-release-entrypoint.sh /usr/local/bin/allbot-release-entrypoint
RUN chmod 755 /usr/local/bin/allbot-release-entrypoint
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/local/bin/allbot-release-entrypoint"]
CMD ["python", "src/bot_main.py"]
