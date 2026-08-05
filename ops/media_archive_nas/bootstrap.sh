#!/bin/sh
set -eu

mc alias set archive https://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" --api S3v4 --path auto
for bucket in allbot-media-archive-v1 allbot-media-derived-v1 allbot-media-quarantine-v1; do
  mc mb --ignore-existing "archive/$bucket"
done
mc version enable archive/allbot-media-archive-v1
mc admin policy create archive archive-worker /policies/archive-worker.json
mc admin policy create archive analytics-readonly /policies/analytics-readonly.json
mc admin user add archive "$ARCHIVE_WORKER_ACCESS_KEY" "$ARCHIVE_WORKER_SECRET_KEY"
mc admin user add archive "$ANALYTICS_ACCESS_KEY" "$ANALYTICS_SECRET_KEY"
mc admin policy attach archive archive-worker --user "$ARCHIVE_WORKER_ACCESS_KEY"
mc admin policy attach archive analytics-readonly --user "$ANALYTICS_ACCESS_KEY"
echo "MinIO archive buckets, versioning, users and policies are ready"
