#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET_BUCKET="${TARGET_BUCKET:-user-data-complete-shadow}"
LOCAL_WORKERS="${LOCAL_WORKERS:-24}"
COLD_WORKERS="${COLD_WORKERS:-16}"
PROGRESS_INTERVAL="${PROGRESS_INTERVAL:-60}"

echo "started_at=$(date -Is)"
echo "target_bucket=${TARGET_BUCKET}"
echo "local_workers=${LOCAL_WORKERS}"
echo "cold_workers=${COLD_WORKERS}"

python3 scripts/import_minio_bucket_normalized.py \
  --source local \
  --source-bucket bot-data \
  --target-bucket "${TARGET_BUCKET}" \
  --workers "${LOCAL_WORKERS}" \
  --progress-interval "${PROGRESS_INTERVAL}" \
  --label local-bot-data \
  --execute

python3 scripts/import_minio_bucket_normalized.py \
  --source local \
  --source-bucket comfyui-temp \
  --target-bucket "${TARGET_BUCKET}" \
  --workers "${LOCAL_WORKERS}" \
  --progress-interval "${PROGRESS_INTERVAL}" \
  --label local-comfyui-temp \
  --execute

python3 scripts/import_minio_bucket_normalized.py \
  --source cold \
  --source-bucket bot-data \
  --target-bucket "${TARGET_BUCKET}" \
  --workers "${COLD_WORKERS}" \
  --progress-interval "${PROGRESS_INTERVAL}" \
  --label cold-bot-data \
  --execute

echo "finished_at=$(date -Is)"
