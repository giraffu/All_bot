#!/bin/bash
set -e

echo "Starting File Migration to MinIO..."
python3 scripts/migrate_file_to_minio.py
echo "File Migration Completed."
