#!/bin/bash
set -e

echo "Starting Database Migration to PostgreSQL..."
python3 scripts/migrate_db_to_pgsql.py
echo "Database Migration Completed."
