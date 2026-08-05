#!/bin/sh
set -eu

env_file=${1:-./.env}
test -f "$env_file" || { echo "missing $env_file" >&2; exit 2; }
set -a
. "$env_file"
set +a

printf '%s\n' "${MINIO_IMAGE:-}" | grep -Eq '(@sha256:|^sha256:)[0-9a-f]{64}$' || { echo "MINIO_IMAGE must be content-addressed" >&2; exit 2; }
printf '%s\n' "${MINIO_MC_IMAGE:-}" | grep -Eq '(@sha256:|^sha256:)[0-9a-f]{64}$' || { echo "MINIO_MC_IMAGE must be content-addressed" >&2; exit 2; }
test "${#MINIO_ROOT_PASSWORD}" -ge 32 || { echo "root password is too short" >&2; exit 2; }
test "${#ARCHIVE_WORKER_SECRET_KEY}" -ge 32 || { echo "worker secret is too short" >&2; exit 2; }
test "${#ANALYTICS_SECRET_KEY}" -ge 32 || { echo "analytics secret is too short" >&2; exit 2; }
test -d "${MINIO_DATA_PATH}" || { echo "missing data directory: ${MINIO_DATA_PATH}" >&2; exit 2; }
test -f "${MINIO_CERT_PATH}/public.crt" || { echo "missing public.crt" >&2; exit 2; }
test -f "${MINIO_CERT_PATH}/private.key" || { echo "missing private.key" >&2; exit 2; }
test -f "${MINIO_CERT_PATH}/CAs/allbot-archive-ca.crt" || { echo "missing MinIO CA bundle" >&2; exit 2; }
test -n "${MINIO_DIRECT_BIND_IP:-}" || { echo "MINIO_DIRECT_BIND_IP is required" >&2; exit 2; }
ip -4 address show | grep -Fq " ${MINIO_DIRECT_BIND_IP}/" || {
  echo "direct-link IP is not configured: ${MINIO_DIRECT_BIND_IP}" >&2
  exit 2
}
echo "MinIO NAS preflight passed"
