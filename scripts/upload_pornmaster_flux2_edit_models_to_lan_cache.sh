#!/usr/bin/env bash
set -euo pipefail

MODE="dry-run"
ENV_FILE=".env.lan.model-cache"
BUNDLE="pornmaster_flux2_edit_baseline"
VERSION="2026-06-27"
BUCKET="allbot-model-cache"
PREFIX="pornmaster_flux2_edit/2026-06-27"
ENDPOINT="http://192.168.1.115:9010"

usage() {
  cat <<'USAGE'
Usage:
  scripts/upload_pornmaster_flux2_edit_models_to_lan_cache.sh [--dry-run|--execute] [--env-file <path>]

Uploads the pornmaster_flux2_edit_baseline model bundle from
/srv/allbot/model-registry to allbot-model-cache/pornmaster_flux2_edit/2026-06-27.

Run scripts/import_pornmaster_flux2_edit_models.py --execute first. That import
requires the PornMaster Flux2 9B UNET via --unet-path or an authorized Civitai token.
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

echo "LAN model cache endpoint: ${ENDPOINT}"
echo "LAN model cache bucket: ${BUCKET}"
echo "LAN model cache prefix: ${PREFIX}"
echo "Model bundle: ${BUNDLE}@${VERSION}"

if [ "$MODE" != "execute" ]; then
  echo "[dry-run] Would upload bundle with redacted credentials:"
  echo "[dry-run] python scripts/upload_model_bundle_to_r2.py --bundle ${BUNDLE} --version ${VERSION} --bucket ${BUCKET} --prefix ${PREFIX} --create-bucket"
  exit 0
fi

: "${LAN_MODEL_CACHE_ACCESS_KEY:?LAN_MODEL_CACHE_ACCESS_KEY is required}"
: "${LAN_MODEL_CACHE_SECRET_KEY:?LAN_MODEL_CACHE_SECRET_KEY is required}"

export RUNPOD_MODEL_ENDPOINT="${ENDPOINT}"
export RUNPOD_MODEL_ACCESS_KEY="${LAN_MODEL_CACHE_ACCESS_KEY}"
export RUNPOD_MODEL_SECRET_KEY="${LAN_MODEL_CACHE_SECRET_KEY}"
export RUNPOD_MODEL_SECURE="false"
export RUNPOD_MODEL_BUCKET="${BUCKET}"
export RUNPOD_MODEL_PREFIX="${PREFIX}"

python scripts/upload_model_bundle_to_r2.py \
  --env-file /dev/null \
  --bundle "${BUNDLE}" \
  --version "${VERSION}" \
  --bucket "${BUCKET}" \
  --prefix "${PREFIX}" \
  --create-bucket \
  --execute
