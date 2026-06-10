#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
COMPOSE_FILE="/home/hfy/APP/All_bot/deploy/docker-compose-local-registry.yml"
DATA_ROOT="/srv/allbot/docker-registry"

for arg in "$@"; do
  case "$arg" in
    --execute)
      MODE="execute"
      ;;
    --dry-run)
      MODE="dry-run"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

echo "Local registry compose: ${COMPOSE_FILE}"
echo "Local registry data root: ${DATA_ROOT}"
echo "Bind addresses: 127.0.0.1:5000, 192.168.1.115:5000"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 1
fi

if [[ "$MODE" != "execute" ]]; then
  echo "[dry-run] Would create ${DATA_ROOT}"
  echo "[dry-run] Would run: ${COMPOSE_CMD[*]} -f ${COMPOSE_FILE} up -d"
  echo "[dry-run] Would verify: curl http://127.0.0.1:5000/v2/"
  echo "[dry-run] Would verify: curl http://192.168.1.115:5000/v2/"
  exit 0
fi

mkdir -p "${DATA_ROOT}"
docker ps -aq --filter "name=allbot-local-registry" | xargs -r docker rm -f >/dev/null
"${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" up -d
curl -fsS "http://127.0.0.1:5000/v2/" >/dev/null
curl -fsS "http://192.168.1.115:5000/v2/" >/dev/null
echo "allbot-local-registry is reachable at http://127.0.0.1:5000/v2/ and http://192.168.1.115:5000/v2/"
