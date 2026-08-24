#!/usr/bin/env bash
set -euo pipefail

mode="dry-run"
confirm=""
confirm_value="COPY_MODEL_CACHE_TO_NAS"
source_endpoint="${MODEL_CACHE_SOURCE_ENDPOINT:-http://10.250.150.1:19010}"
target_endpoint="${MODEL_CACHE_TARGET_ENDPOINT:-http://10.250.150.2:9010}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --execute) mode="execute"; shift ;;
    --confirm) confirm="${2:-}"; shift 2 ;;
    --source-endpoint) source_endpoint="${2:?missing source endpoint}"; shift 2 ;;
    --target-endpoint) target_endpoint="${2:?missing target endpoint}"; shift 2 ;;
    *)
      echo "usage: $0 [--execute --confirm ${confirm_value}]" >&2
      exit 2
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
test -f "${script_dir}/.env" || { echo "missing private .env" >&2; exit 2; }
set -a
# shellcheck disable=SC1091
source "${script_dir}/.env"
set +a
: "${MODEL_CACHE_MC_IMAGE:?required}"
: "${LAN_MODEL_CACHE_ACCESS_KEY:?required}"
: "${LAN_MODEL_CACHE_SECRET_KEY:?required}"

if [ "$mode" = "execute" ] && [ "$confirm" != "$confirm_value" ]; then
  echo "execute requires exact confirmation: ${confirm_value}" >&2
  exit 2
fi

mirror_mode="--dry-run"
if [ "$mode" = "execute" ]; then
  mirror_mode=""
fi
docker run --rm --network host \
  --env-file "${script_dir}/.env" \
  -e "MC_SOURCE_ENDPOINT=${source_endpoint}" \
  -e "MC_TARGET_ENDPOINT=${target_endpoint}" \
  -e "MC_MIRROR_MODE=${mirror_mode}" \
  -e "MC_MAX_WORKERS=${MODEL_CACHE_MIRROR_WORKERS:-8}" \
  --entrypoint /bin/sh \
  "$MODEL_CACHE_MC_IMAGE" -ec '
    mc alias set source "$MC_SOURCE_ENDPOINT" "$LAN_MODEL_CACHE_ACCESS_KEY" "$LAN_MODEL_CACHE_SECRET_KEY" --api S3v4 --path auto >/dev/null
    mc alias set target "$MC_TARGET_ENDPOINT" "$LAN_MODEL_CACHE_ACCESS_KEY" "$LAN_MODEL_CACHE_SECRET_KEY" --api S3v4 --path auto >/dev/null
    mc mirror $MC_MIRROR_MODE --overwrite --preserve --retry \
      --max-workers "$MC_MAX_WORKERS" \
      source/allbot-model-cache target/allbot-model-cache
    if [ -z "$MC_MIRROR_MODE" ]; then
      differences="$(mc diff --json source/allbot-model-cache target/allbot-model-cache)"
      if [ -n "$differences" ]; then
        echo "model cache mirror verification found differences" >&2
        exit 1
      fi
      mc stat target/allbot-model-cache >/dev/null
    fi
  '
if [ "$mode" = "execute" ]; then
  echo "model cache mirror and mc diff verification passed"
else
  echo "model cache mirror dry-run passed"
fi
