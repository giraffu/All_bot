#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
ENV_FILE=".env.lan.model-cache"
COMPOSE_FILE="/home/hfy/APP/All_bot/deploy/docker-compose-model-cache-lan.yml"
DATA_ROOT="/srv/allbot/model-cache-lan"
BUCKET="allbot-model-cache"

usage() {
  cat <<'USAGE'
Usage:
  scripts/manage_lan_model_cache.sh [--dry-run|--execute] [--env-file <path>]

Starts the LAN-only model cache at 192.168.1.115:9010 and ensures the
allbot-model-cache bucket exists. Secrets must come from an ignored env file
or the shell environment.
USAGE
}

load_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in
      ""|\#*) continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      LAN_MODEL_CACHE_ACCESS_KEY|LAN_MODEL_CACHE_SECRET_KEY)
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        export "${key}=${value}"
        ;;
    esac
  done < "$file"
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    printf '%s\n' "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    printf '%s\n' "docker-compose"
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute)
      MODE="execute"
      shift
      ;;
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --env-file)
      ENV_FILE="${2:?missing value for --env-file}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

load_env_file "$ENV_FILE"

COMPOSE_CMD="$(compose_cmd)"

echo "LAN model cache compose: ${COMPOSE_FILE}"
echo "LAN model cache data root: ${DATA_ROOT}"
echo "LAN model cache bucket: ${BUCKET}"
echo "Bind addresses: 127.0.0.1:9010, 192.168.1.115:9010"

if [ "$MODE" != "execute" ]; then
  echo "[dry-run] Would create ${DATA_ROOT}"
  echo "[dry-run] Would run: ${COMPOSE_CMD} --env-file ${ENV_FILE} -f ${COMPOSE_FILE} up -d"
  echo "[dry-run] Would create bucket ${BUCKET} via minio/mc with redacted credentials"
  echo "[dry-run] Would verify http://127.0.0.1:9010/minio/health/ready"
  echo "[dry-run] Would verify http://192.168.1.115:9010/minio/health/ready"
  exit 0
fi

: "${LAN_MODEL_CACHE_ACCESS_KEY:?LAN_MODEL_CACHE_ACCESS_KEY is required}"
: "${LAN_MODEL_CACHE_SECRET_KEY:?LAN_MODEL_CACHE_SECRET_KEY is required}"

mkdir -p "${DATA_ROOT}"
docker ps -aq --filter "name=allbot-model-cache-lan" | xargs -r docker rm -f >/dev/null
${COMPOSE_CMD} --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:9010/minio/health/ready" >/dev/null; then
    break
  fi
  sleep 2
done
curl -fsS "http://127.0.0.1:9010/minio/health/ready" >/dev/null

docker run --rm --network host \
  -e "MC_ACCESS_KEY=${LAN_MODEL_CACHE_ACCESS_KEY}" \
  -e "MC_SECRET_KEY=${LAN_MODEL_CACHE_SECRET_KEY}" \
  --entrypoint sh \
  minio/mc:RELEASE.2025-04-16T18-13-26Z \
  -lc 'mc alias set lan http://127.0.0.1:9010 "$MC_ACCESS_KEY" "$MC_SECRET_KEY" >/dev/null && mc mb --ignore-existing lan/allbot-model-cache >/dev/null'

curl -fsS "http://192.168.1.115:9010/minio/health/ready" >/dev/null
echo "allbot-model-cache-lan is reachable and bucket ${BUCKET} exists."
