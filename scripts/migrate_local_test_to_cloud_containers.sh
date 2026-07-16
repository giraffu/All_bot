#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-allbot-do-sgp1-control}"
REMOTE_DIR="${REMOTE_DIR:-/home/deploy/APP/All_bot}"
TS="$(date +%Y%m%d_%H%M%S)"
LOCAL_BACKUP_DIR="${ROOT_DIR}/backups/cloud-test-container-migration/${TS}"
REMOTE_BACKUP_DIR="${REMOTE_DIR}/backups/cloud-test-container-migration/${TS}"

LOCAL_ENV="${ROOT_DIR}/.env.test"
CLOUD_ENV="${ROOT_DIR}/.env.cloud.test"
CLOUD_COMPOSE="deploy/docker-compose-cloud-test.yml"
WORKER_COMPOSE="workers/docker-compose-cloud-worker-test.yml"

log() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

read_env() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
for line in path.read_text(errors="ignore").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    if k == key:
        print(v.strip().strip('"').strip("'"))
        break
PY
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Required file not found: $1" >&2
    exit 1
  fi
}

require_file "$LOCAL_ENV"
require_file "$CLOUD_ENV"

LOCAL_DB_NAME="${LOCAL_DB_NAME:-bot_db_test}"
CLOUD_DB_NAME="${CLOUD_DB_NAME:-$(read_env "$CLOUD_ENV" CLOUD_TEST_POSTGRES_DB)}"
CLOUD_DB_NAME="${CLOUD_DB_NAME:-bot_db_test}"
CLOUD_DB_USER="${CLOUD_DB_USER:-$(read_env "$CLOUD_ENV" CLOUD_TEST_POSTGRES_USER)}"
CLOUD_DB_USER="${CLOUD_DB_USER:-postgres}"

CLOUD_TS_IP="$(read_env "$CLOUD_ENV" CLOUD_TEST_TAILSCALE_IP)"
if [[ -z "$CLOUD_TS_IP" ]]; then
  CLOUD_TS_IP="$(read_env "$CLOUD_ENV" CLOUD_TEST_BIND_IP)"
fi
if [[ -z "$CLOUD_TS_IP" ]]; then
  echo "CLOUD_TEST_TAILSCALE_IP or CLOUD_TEST_BIND_IP is required in .env.cloud.test" >&2
  exit 1
fi

MINIO_BUCKETS=(
  "$(read_env "$LOCAL_ENV" MINIO_BUCKET)"
  "$(read_env "$LOCAL_ENV" MINIO_RESULT_BUCKET)"
  "$(read_env "$LOCAL_ENV" MINIO_TEMPLATE_BUCKET)"
)

LOCAL_MINIO_ACCESS_KEY="$(read_env "$LOCAL_ENV" MINIO_ACCESS_KEY)"
LOCAL_MINIO_SECRET_KEY="$(read_env "$LOCAL_ENV" MINIO_SECRET_KEY)"
LOCAL_MINIO_ENDPOINT="$(read_env "$LOCAL_ENV" MINIO_ENDPOINT)"
LOCAL_MINIO_SECURE="$(read_env "$LOCAL_ENV" MINIO_SECURE)"
R2_ENDPOINT="$(read_env "$CLOUD_ENV" R2_ENDPOINT)"
R2_BUCKET="$(read_env "$CLOUD_ENV" R2_BUCKET)"
R2_ACCESS_KEY="$(read_env "$CLOUD_ENV" R2_ACCESS_KEY)"
R2_SECRET_KEY="$(read_env "$CLOUD_ENV" R2_SECRET_KEY)"

LOCAL_MINIO_SCHEME="http"
if [[ "${LOCAL_MINIO_SECURE,,}" == "true" ]]; then
  LOCAL_MINIO_SCHEME="https"
fi

mkdir -p "$LOCAL_BACKUP_DIR"

log "Preflight: checking local and cloud services"
docker exec postgres-server pg_isready -U postgres >/dev/null
docker exec redis-server redis-cli --version >/dev/null
ssh -o BatchMode=yes "$REMOTE_HOST" "docker exec cloud-postgres-test pg_isready -U '${CLOUD_DB_USER}' >/dev/null && docker exec cloud-redis-test redis-cli --version >/dev/null"
python3 - "$CLOUD_ENV" <<'PY' >/dev/null
from pathlib import Path
import sys

import boto3
from botocore.config import Config

cfg = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    cfg[k] = v.strip().strip('"').strip("'")

endpoint = cfg["R2_ENDPOINT"]
client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=cfg["R2_ACCESS_KEY"],
    aws_secret_access_key=cfg["R2_SECRET_KEY"],
    config=Config(
        signature_version="s3v4",
        retries={"max_attempts": 1},
        connect_timeout=5,
        read_timeout=10,
    ),
)
client.list_objects_v2(Bucket=cfg["R2_BUCKET"], MaxKeys=1)
PY

log "Stopping cloud test writers"
docker-compose --env-file "$CLOUD_ENV" -f "${ROOT_DIR}/${WORKER_COMPOSE}" stop || true
ssh -o BatchMode=yes "$REMOTE_HOST" "cd '${REMOTE_DIR}' && docker compose --env-file .env.cloud.test -f '${CLOUD_COMPOSE}' --profile bot stop bot-test web-api-test central-api-test imgproxy-test || true"

log "Creating cloud backup directory: ${REMOTE_BACKUP_DIR}"
ssh -o BatchMode=yes "$REMOTE_HOST" "mkdir -p '${REMOTE_BACKUP_DIR}'"

log "Backing up current cloud Postgres test database"
ssh -o BatchMode=yes "$REMOTE_HOST" "docker exec cloud-postgres-test pg_dump -U '${CLOUD_DB_USER}' -Fc -d '${CLOUD_DB_NAME}' > '${REMOTE_BACKUP_DIR}/cloud_before_${CLOUD_DB_NAME}.dump'"

log "Dumping local Postgres test database"
docker exec postgres-server pg_dump -U postgres -Fc -d "${LOCAL_DB_NAME}" > "${LOCAL_BACKUP_DIR}/local_${LOCAL_DB_NAME}.dump"
rsync -az "${LOCAL_BACKUP_DIR}/local_${LOCAL_DB_NAME}.dump" "${REMOTE_HOST}:${REMOTE_BACKUP_DIR}/"

log "Restoring local Postgres test database into cloud container"
ssh -o BatchMode=yes "$REMOTE_HOST" "set -euo pipefail
docker exec cloud-postgres-test dropdb --force -U '${CLOUD_DB_USER}' '${CLOUD_DB_NAME}' 2>/dev/null || true
docker exec cloud-postgres-test createdb -U '${CLOUD_DB_USER}' '${CLOUD_DB_NAME}'
docker exec -i cloud-postgres-test pg_restore -U '${CLOUD_DB_USER}' --no-owner --dbname '${CLOUD_DB_NAME}' < '${REMOTE_BACKUP_DIR}/local_${LOCAL_DB_NAME}.dump'
"

log "Backing up current cloud Redis and migrating Redis DB 3/4 with redis-cli --pipe"
ssh -o BatchMode=yes "$REMOTE_HOST" "set -euo pipefail
docker exec cloud-redis-test sh -lc 'REDISCLI_AUTH=\"\$CLOUD_TEST_REDIS_PASSWORD\" redis-cli --rdb /tmp/cloud_redis_before.rdb >/dev/null'
docker cp cloud-redis-test:/tmp/cloud_redis_before.rdb '${REMOTE_BACKUP_DIR}/cloud_redis_before.rdb'
docker exec cloud-redis-test rm -f /tmp/cloud_redis_before.rdb
"

redis_pipe_db() {
  local env_name="$1"
  local db="$2"

  ssh -o BatchMode=yes "$REMOTE_HOST" "docker exec cloud-redis-test sh -lc 'REDISCLI_AUTH=\"\$CLOUD_TEST_REDIS_PASSWORD\" redis-cli -n ${db} FLUSHDB >/dev/null'"
  python3 - "$ROOT_DIR" "$env_name" "$db" <<'PY' | ssh -o BatchMode=yes "$REMOTE_HOST" "docker exec -i cloud-redis-test sh -lc 'REDISCLI_AUTH=\"\$CLOUD_TEST_REDIS_PASSWORD\" redis-cli -n ${db} --pipe'"
import sys
from pathlib import Path
from urllib.parse import urlparse

import redis

root = Path(sys.argv[1])
env_name = sys.argv[2]
fallback_db = int(sys.argv[3])

env = {}
for line in (root / ".env.test").read_text(errors="ignore").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    env[k] = v.strip().strip('"').strip("'")

value = env.get(env_name) or env.get("REDIS_URL") or ""
parsed = urlparse(value)
host = parsed.hostname or "127.0.0.1"
if host in {"host.docker.internal", "redis-server"}:
    host = "127.0.0.1"
port = parsed.port or 6379
password = parsed.password
try:
    db = int((parsed.path or "").strip("/") or fallback_db)
except ValueError:
    db = fallback_db

src = redis.Redis(host=host, port=port, password=password, db=db)
out = sys.stdout.buffer

def as_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode()

def emit(*parts):
    out.write(f"*{len(parts)}\r\n".encode())
    for part in parts:
        data = as_bytes(part)
        out.write(f"${len(data)}\r\n".encode())
        out.write(data)
        out.write(b"\r\n")

for key in src.scan_iter(count=500):
    key_type = src.type(key).decode()
    pttl = src.pttl(key)

    if key_type == "string":
        value = src.get(key)
        if value is None:
            continue
        emit("SET", key, value)
    elif key_type == "hash":
        values = src.hgetall(key)
        if values:
            args = ["HSET", key]
            for field, item in values.items():
                args.extend([field, item])
            emit(*args)
    elif key_type == "list":
        values = src.lrange(key, 0, -1)
        if values:
            emit("RPUSH", key, *values)
    elif key_type == "set":
        values = list(src.smembers(key))
        if values:
            emit("SADD", key, *values)
    elif key_type == "zset":
        values = src.zrange(key, 0, -1, withscores=True)
        if values:
            args = ["ZADD", key]
            for member, score in values:
                args.extend([repr(score), member])
            emit(*args)
    elif key_type == "stream":
        for entry_id, fields in src.xrange(key, "-", "+"):
            args = ["XADD", key, entry_id]
            for field, item in fields.items():
                args.extend([field, item])
            emit(*args)
    else:
        raise RuntimeError(f"Unsupported Redis key type {key_type!r} for key {key!r}")

    if pttl and pttl > 0:
        emit("PEXPIRE", key, str(pttl))
PY
}

redis_pipe_db REDIS_URL_TEST 3
redis_pipe_db WORKER_REDIS_URL 4
for db in 3 4; do
  count="$(ssh -o BatchMode=yes "$REMOTE_HOST" "docker exec cloud-redis-test sh -lc 'REDISCLI_AUTH=\"\$CLOUD_TEST_REDIS_PASSWORD\" redis-cli -n ${db} DBSIZE'")"
  log "Cloud Redis DB${db} keys after migration: ${count}"
done

log "Mirroring local test MinIO buckets into the R2 test bucket root"
docker run --rm --network host --entrypoint sh \
  -e LOCAL_MINIO_ACCESS_KEY="$LOCAL_MINIO_ACCESS_KEY" \
  -e LOCAL_MINIO_SECRET_KEY="$LOCAL_MINIO_SECRET_KEY" \
  -e R2_ACCESS_KEY="$R2_ACCESS_KEY" \
  -e R2_SECRET_KEY="$R2_SECRET_KEY" \
  minio/mc:latest -lc '
set -eu
mc alias set src "'"${LOCAL_MINIO_SCHEME}://${LOCAL_MINIO_ENDPOINT}"'" "$LOCAL_MINIO_ACCESS_KEY" "$LOCAL_MINIO_SECRET_KEY" >/dev/null
mc alias set r2 "'"${R2_ENDPOINT}"'" "$R2_ACCESS_KEY" "$R2_SECRET_KEY" >/dev/null
for bucket in '"${MINIO_BUCKETS[*]}"'; do
  [ -n "$bucket" ] || continue
  if mc stat "src/$bucket" >/dev/null 2>&1; then
    mc mirror --overwrite --quiet "src/$bucket" "r2/'"${R2_BUCKET}"'" >/dev/null
  fi
done
'

log "Verifying R2 test bucket access from cloud test configuration"
python3 - "$CLOUD_ENV" <<'PY'
from pathlib import Path
import sys
import boto3
from botocore.config import Config

cfg = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    cfg[k] = v.strip().strip('"').strip("'")

client = boto3.client(
    "s3",
    endpoint_url=cfg["R2_ENDPOINT"],
    aws_access_key_id=cfg["R2_ACCESS_KEY"],
    aws_secret_access_key=cfg["R2_SECRET_KEY"],
    config=Config(
        signature_version="s3v4",
        retries={"max_attempts": 1},
        connect_timeout=5,
        read_timeout=10,
    ),
)
resp = client.list_objects_v2(Bucket=cfg["R2_BUCKET"], MaxKeys=1)
print(f"r2-list-ok=true keycount-sample={resp.get('KeyCount', 0)}")
PY

log "Restarting cloud test control plane"
ssh -o BatchMode=yes "$REMOTE_HOST" "cd '${REMOTE_DIR}' && ./scripts/safe_deploy_cloud_test.sh"
ssh -o BatchMode=yes "$REMOTE_HOST" "cd '${REMOTE_DIR}' && docker compose --env-file .env.cloud.test -f '${CLOUD_COMPOSE}' --profile bot up -d bot-test"

log "Restarting local cloud GPU workers"
"${ROOT_DIR}/scripts/start_cloud_worker_test.sh"

log "Running post-migration health checks"
curl --noproxy '*' -fsS "http://${CLOUD_TS_IP}:8004/health" >/dev/null
curl --noproxy '*' -fsS "http://${CLOUD_TS_IP}:8001/api/health" >/dev/null
curl --noproxy '*' -fsS "http://${CLOUD_TS_IP}:8044/api/health" >/dev/null
curl --noproxy '*' -fsS "http://${CLOUD_TS_IP}:8087/api/health" >/dev/null
curl --noproxy '*' -fsS "http://${CLOUD_TS_IP}:8004/system/workers" | python3 -m json.tool | sed -n '1,180p'

log "Migration complete"
printf 'Local backup directory: %s\n' "$LOCAL_BACKUP_DIR"
printf 'Remote backup directory: %s\n' "$REMOTE_BACKUP_DIR"
