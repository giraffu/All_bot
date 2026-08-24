#!/usr/bin/env bash
set -euo pipefail

confirm_value="MIGRATE_LAN_ARTIFACTS_TO_NAS"
confirm=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --confirm) confirm="${2:-}"; shift 2 ;;
    *) echo "usage: $0 --confirm ${confirm_value}" >&2; exit 2 ;;
  esac
done
if [ "$confirm" != "$confirm_value" ]; then
  echo "bootstrap requires exact confirmation: ${confirm_value}" >&2
  exit 2
fi
test "$(id -u)" -eq 0 || { echo "bootstrap requires root" >&2; exit 2; }
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${script_dir}/preflight.sh" --execute --confirm "$confirm_value"
docker compose --env-file "${script_dir}/.env" -f "${script_dir}/compose.yml" up -d
set -a
# shellcheck disable=SC1091
source "${script_dir}/.env"
set +a
for _ in $(seq 1 60); do
  if curl -fsS "http://${NAS_DIRECT_BIND_IP}:9010/minio/health/ready" >/dev/null \
    && curl -fsS "http://${NAS_DIRECT_BIND_IP}:5000/v2/" >/dev/null; then
    echo "NAS registry and model cache are healthy"
    exit 0
  fi
  sleep 2
done
echo "NAS artifact services did not become healthy" >&2
exit 1

